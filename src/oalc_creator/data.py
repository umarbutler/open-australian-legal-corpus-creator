import re
import html
import datetime

from io import BytesIO
from typing import Callable
from functools import cached_property

import orjson
import msgspec

from frozndict import frozendict

encoder = msgspec.json.Encoder().encode

class Request(msgspec.Struct, frozen = True):
    """A request."""

    path: str
    method: str = 'get'
    data: dict = frozendict()    # NOTE `frozendict` is used instead of `dict` to ensure that the request is hashable,
    headers: dict = frozendict() # which is necessary to be able to place it in a set.
    encoding: str = 'utf-8'
    
    def __post_init__(self) -> None:
        # Convert the data and headers to `frozendict` objects if they are not already.
        if not isinstance(self.data, frozendict):
            msgspec.structs.force_setattr(self, 'data', frozendict(self.data))
        
        if not isinstance(self.headers, frozendict):
            msgspec.structs.force_setattr(self, 'headers', frozendict(self.headers))

    @property
    def args(self) -> dict:
        """Convert the request into arguments for `aiohttp.ClientSession.request`."""
        
        return {
            'method' : self.method.upper(),
            'url' : self.path,
            'data' : self.data,
            'headers' : self.headers,
        }

requests_decoder: Callable[[dict], set[Request]] = msgspec.json.Decoder(set[Request]).decode

class Response(bytes):    
    def __new__(cls, *args,
                encoding: str,
                type: str,
                status: int,
                **kwargs):
        return super().__new__(cls, *args, **kwargs)

    def __init__(self, *args,
                encoding: str,
                type: str,
                status: int,
                **kwargs):
        """A response."""
    
        self.encoding = encoding
        self.type = type
        self.status = status
        super().__init__()

    @cached_property
    def text(self) -> str:
        return self.decode(self.encoding)

    @property
    def stream(self) -> BytesIO:
        return BytesIO(self)
    
    @cached_property
    def json(self) -> dict:
        # NOTE It is necessary to convert the response to a `bytes` object before passing it to `orjson.loads()` as that function refuses to accept objects of the `Response` type despite the fact that `Response` is a subclass of `bytes`.
        return orjson.loads(bytes(self))

class Entry(msgspec.Struct, frozen = True):
    """An entry in a document index."""

    request: Request
    version_id: str
    source: str
    type: str | None = None
    jurisdiction: str | None = None
    title: str | None = None

    def __post_init__(self) -> None:
        # Format the version id.
        msgspec.structs.force_setattr(self, "version_id", self.format_id(self.version_id, self.source))
    
    @classmethod
    def format_id(cls, version_id: str, source: str) -> str:
        """Format a version id if it is not already formatted."""
        
        # Check whether the version id has already been formatted.
        if version_id[:len(source) + 1] == f'{source}:':
            return version_id
        
        return f'{source}:{version_id}'

class Entries(msgspec.Struct, frozen = True):
    request: Request
    entries: set[Entry]
    when_indexed: float

entries_decoder: Callable[[dict], Entries] = msgspec.json.Decoder(Entries).decode

class Document(msgspec.Struct, frozen = True):
    """A document."""
    
    version_id: str
    type: str
    jurisdiction: str
    source: str
    citation: str
    url: str
    when_scraped: str
    text: str
    
def format_citation(title: str, type: str, jurisdiction: str) -> str:
    """Format a citation."""
    
    JURISDICTIONS = {
        'commonwealth' : 'Cth',
        'new_south_wales' : 'NSW',
        'victoria' : 'Vic',
        'queensland' : 'Qld',
        'south_australia' : 'SA',
        'western_australia' : 'WA',
        'tasmania' : 'Tas',
        'northern_territory' : 'NT',
        'australian_capital_territory' : 'ACT',
        'norfolk_island' : 'NI',
    }
    
    # Unescape HTML character entities.
    title = html.unescape(title)
    
    # Format the citations of legislation.
    if type != 'decision':
        # If the title ends with 'No <number>', remove it.
        title = re.sub(r' No\s+\d+$', '', title)
        
        # Determine which abbreviated jurisdiction to append to the title.
        if jurisdiction not in JURISDICTIONS:
            raise ValueError(f'Unable to find an abbreviated form of the following jurisdiction: {jurisdiction}.')
        
        abbreviated_jurisdiction = JURISDICTIONS[jurisdiction]
        
        # If the abbreviated jurisdiction is already inside the title, remove it and any text following it.
        title = title.split(f'({abbreviated_jurisdiction})')[0]
        
        # Append the abbreviated jurisdiction to the title.
        title = f'{title} ({abbreviated_jurisdiction})'

    # Remove extra whitespace characters.
    title = re.sub(r'\s+', ' ', title)
    
    # Remove leading and trailing whitespace characters.
    title = ' '.join(title.split())
    
    return title

def make_doc(
    version_id: str,
    type: str,
    jurisdiction: str,
    source: str,
    citation: str,
    url: str,
    text: str,
) -> Document:
    """Create a document."""
    
    citation = format_citation(citation, type, jurisdiction)
    
    return Document(
        version_id = version_id,
        type = type,
        jurisdiction = jurisdiction,
        source = source,
        citation = citation,
        url = url,
        when_scraped = datetime.datetime.now().astimezone().isoformat(),
        text = text,
    )

document_decoder: Callable[[dict], Document] = msgspec.json.Decoder(Document).decode