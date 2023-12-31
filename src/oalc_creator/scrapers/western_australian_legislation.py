import asyncio
import itertools
import re
import string
from datetime import timedelta

import aiohttp
import lxml.html
import mammoth
from inscriptis.css_profiles import CSS_PROFILES
from inscriptis.html_properties import Display
from inscriptis.model.html_element import HtmlElement

from ..custom_inscriptis import CustomInscriptis, CustomParserConfig
from ..data import Document, Entry, Request
from ..helpers import log
from ..scraper import Scraper


class WesternAustralianLegislation(Scraper):
    """A scraper for the Western Australian Legislation database."""
    
    def __init__(self,
                 indices_refresh_interval: bool | timedelta = None,
                 index_refresh_interval: bool | timedelta = None,
                 semaphore: asyncio.Semaphore = None,
                 session: aiohttp.ClientSession = None,
                 ) -> None:
        super().__init__(
            source='western_australian_legislation',
            indices_refresh_interval=indices_refresh_interval or False,
            index_refresh_interval=index_refresh_interval,
            semaphore=semaphore,
            session=session
        )

        self._jurisdiction = 'western_australia'
        
        # Create a custom Inscriptis CSS profile.
        inscriptis_profile = CSS_PROFILES['strict'].copy()
        
        # Omit newlines before and after `p` elements.
        inscriptis_profile['p'] = HtmlElement(display=Display.block)
        
        # Omit newlines after headings, but retain them before.
        inscriptis_profile |= dict.fromkeys(('h1', 'h2', 'h3', 'h4', 'h5'), HtmlElement(display=Display.block, margin_before=1))
        
        # Create an Inscriptis parser config using the custom CSS profile.
        self._inscriptis_config = CustomParserConfig(inscriptis_profile)
        
    @log
    async def get_index_reqs(self) -> set[Request]:
        # NOTE Because the Western Australian Legislation database indexes documents by type and then by the first letter of their title, we generate requests for every possible combination of available document types and letters of the alphabet.
        return {
            Request(f'https://www.legislation.wa.gov.au/legislation/statutes.nsf/{type}if_{letter}.html')
            for type, letter in itertools.product(
                {'acts', 'subs'},
                string.ascii_lowercase
            )
        }

    @log
    async def get_index(self, req: Request) -> set[Entry]:        
        # Determine the document type of the index.
        type = 'primary_legislation' if 'acts' in req.path else 'secondary_legislation'
        
        # Retrieve the index.
        resp = (await self.get(req)).text

        # Extract all table rows barring the first, which will be the header.
        rows = re.findall(r"<tr>((?:.|\n)*?)</tr>", resp)[1:]
        
        # Extract entries from the rows.
        return {self._get_entry(row, type) for row in rows}

    @log
    def _get_entry(self, row: str, type: str) -> Entry:       
        # Extract the title of the document from the link to its entry.
        title = re.search(r"<a href='[\w\d_]+\.html' class='[\w]+ alive'>((?:.|\n)*?)</a>", row).group(1)
        
        # Extract the version id from the link to the DOCX version of the document.
        version_id = re.search(r"<a href='RedirectURL\?OpenAgent&amp;query=([^']*)\.docx' class='tooltip' target='_blank'>", row).group(1)
        
        # Build the request from the version id.
        req = Request(f'https://www.legislation.wa.gov.au/legislation/statutes.nsf/RedirectURL?OpenAgent&query={version_id}.docx')
        
        return Entry(
            request=req,
            version_id=version_id,
            type=type,
            jurisdiction=self._jurisdiction,
            source=self.source,
            title=title
        )

    @log
    async def get_doc(self, entry: Entry) -> Document:
        # Retrieve the document.
        resp = (await self.get(entry.request)).stream

        # Convert the document to HTML. 
        # NOTE This appears to be the most reliable method of extracting text from documents on the Western Australian Legislation database. It outperforms using the database's HTML versions of documents (which are often formatted incorrectly), extracting text from or OCR-ing the database's PDF versions, and using the `pypandoc`, `python-docx`, `docx2txt` and `docx2python` libraries to convert the DOCX versions directly to text.
        # NOTE We disable image conversion by creating an image converter function that returns an empty dict.
        html = mammoth.convert_to_html(resp, convert_image=lambda _: {})

        # Extract text from the generated HTML.
        etree = lxml.html.fromstring(html.value)

        text = CustomInscriptis(etree, self._inscriptis_config).get_text()

        # Return the document.
        return Document(
            version_id=entry.version_id,
            type=entry.type,
            jurisdiction=entry.jurisdiction,
            source=entry.source,
            citation=entry.title,
            url=entry.request.path,
            text=text
        )