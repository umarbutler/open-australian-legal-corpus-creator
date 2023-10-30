import html
import re
from functools import cached_property
from io import BytesIO

import orjson
from attrs import define, field
from frozndict import frozendict

from .helpers import dict2inst


@define(frozen=True)
class Request:
    """A request."""
    
    path: str
    method: str = 'get'
    data: frozendict = field(default=frozendict(), converter=frozendict) # NOTE `frozendict` is used instead of `dict` to ensure that the request is hashable.
    headers: frozendict = field(default=frozendict(), converter=frozendict)
    encoding: str = 'utf-8'
    
    @property
    def args(self) -> dict:
        """Convert the request to arguments for `aiohttp.ClientSession.request`."""
        
        return {
            'method' : self.method.upper(),
            'url' : self.path,
            'data' : self.data,
            'headers' : self.headers,
        }

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

@define(frozen=True)
class Entry:
    """An entry in a document index."""
    
    # Allow for the passing of `dict`s as requests by converting them to `Request`s.
    request: Request = field(converter=dict2inst(Request))
    version_id: str
    source: str
    type: str = None
    jurisdiction: str = None
    title: str = None
    
    def __attrs_post_init__(self):
        # Format the version id.
        object.__setattr__(self, "version_id", self.format_id(self.version_id, self.source))
    
    @classmethod
    def format_id(cls, version_id: str, source: str) -> str:
        """Format a version id if it is not already formatted."""
        
        # Check whether the version id has already been formatted.
        if version_id[:len(source) + 1] == f'{source}:':
            return version_id
        
        return f'{source}:{version_id}'

@define(frozen=True)
class Document:
    """A document."""
    
    version_id: str
    type: str
    jurisdiction: str
    source: str
    citation: str
    url: str
    text: str
    
    def __attrs_post_init__(self):
        # Format the citation.
        object.__setattr__(self, "citation", self.format_citation(self.citation, self.type, self.jurisdiction))
    
    def format_citation(self, title: str, type: str, jurisdiction: str) -> str:
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