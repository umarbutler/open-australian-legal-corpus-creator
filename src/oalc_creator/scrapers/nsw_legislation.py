import asyncio
import re
from datetime import datetime, timedelta

import aiohttp
import lxml.html
import pdfplumber
import pytz
from inscriptis.css_profiles import CSS_PROFILES
from inscriptis.html_properties import Display
from inscriptis.model.html_element import HtmlElement

from ..data import Document, Entry, Request
from ..helpers import log, warning
from ..scraper import Scraper
from ..custom_inscriptis import CustomParserConfig, CustomInscriptis


class NswLegislation(Scraper):
    """A scraper for the NSW Legislation database."""
    
    def __init__(self,
                 indices_refresh_interval: bool | timedelta = None,
                 index_refresh_interval: bool | timedelta = None,
                 semaphore: asyncio.Semaphore = None,
                 session: aiohttp.ClientSession = None,
                 ) -> None:
        super().__init__(
            source='nsw_legislation',
            indices_refresh_interval=indices_refresh_interval,
            index_refresh_interval=index_refresh_interval,
            semaphore=semaphore,
            session=session
        )

        self._jurisdiction = 'new_south_wales'
        
        # Create a custom Inscriptis CSS profile.
        inscriptis_profile = CSS_PROFILES['strict'].copy()
        
        # Ensure that blockquotes are indented.
        inscriptis_profile['blockquote'] = HtmlElement(display=Display.block, padding_inline=4)
        
        # Create an Inscriptis parser config using the custom CSS profile.
        self._inscriptis_config = CustomParserConfig(inscriptis_profile)

    @log
    async def get_index_reqs(self) -> set[Request]:
        return {
            Request(f'https://legislation.nsw.gov.au/tables/{table}if?pit={datetime.now(tz=pytz.timezone("Australia/NSW")).strftime(r"%d/%m/%Y")}&sort=chron&renderas=html&generate=')
            for table in ('pubacts', 'pvtacts', 'si', 'epi')
        }

    @log
    async def get_index(self, req: Request) -> set[Entry]:        
        # Determine the document type of the index.
        type = 'primary_legislation' if 'actsif?' in req.path else 'secondary_legislation'
        
        # Retrieve the index.
        resp = (await self.get(req)).text
        
        # Extract document paths and titles from the index.
        paths_and_titles = re.findall(r'<a(?: class="indent")? href="/view/(?:html|pdf)/([^"]+)">((?:.|\n)*?)</a>', resp)
        
        # Create entries from the paths and titles.
        entries = await asyncio.gather(*[self._get_entry(path, title, type) for path, title in paths_and_titles])
        
        # Filter out entries that are None.
        # NOTE It is possible for some documents to simply be missing which is why we filter out None rather than raising an exception.
        entries = {entry for entry in entries if entry}
        
        return entries
    
    @log
    async def _get_entry(self, path: str, title: str, type: str) -> Entry | None:
        # If the document's path begins with 'asmade/' then we already have its version id.
        if path.startswith('asmade/'):
            version_id = path
        
        # Otherwise, we must retrieve the document's status page to determine its latest version id.
        else:
            # Extract the document id from the path.
            doc_id = path.split('/')[-1]

            # Retrieve the document's status page.
            resp = await self.get(f"https://legislation.nsw.gov.au/view/html/inforce/current/{doc_id}")

            # If error 404 is encountered, return None.
            # NOTE It is possible for some documents to simply be missing which is why we return None rather than raising an exception.
            if resp.status == 404:
                warning(f'Unable to retrieve document from https://legislation.nsw.gov.au/view/html/inforce/current/{doc_id}. Error 404 (Not Found) encountered. Returning `None`.')
                
                return
        
            match resp.type:
                case 'text/html':
                    # Extract the point in time of the latest version of the document.
                    pit = re.search(r'<a\s+href="/search\?pointInTime=(\d{4}-\d{2}-\d{2})&', resp.text).group(1)
                
                # If a PDF version of the document is returned, then we must use the current point in time.
                case 'application/pdf':
                    pit = datetime.now(tz=pytz.timezone("Australia/NSW")).strftime(r"%Y-%m-%d")
                
                case _:
                    raise ValueError(f"Unable to retrieve entry from https://legislation.nsw.gov.au/view/html/inforce/current/{doc_id}. Invalid content type: {resp.type}.")

            # Create the version id by appending the document id to the point in time.
            version_id = f'{pit}/{doc_id}'
        
        # Create the entry.
        return Entry(
            request=Request(f'https://legislation.nsw.gov.au/view/whole/html/inforce/{version_id}'),
            version_id=version_id,
            source=self.source,
            type=type,
            jurisdiction=self._jurisdiction,
            title=title,
        )

    @log
    async def get_doc(self, entry: Entry) -> Document | None:
        # Retrieve the document.
        resp = await self.get(entry.request)
        
        # If error 404 is encountered, return None.
        # NOTE It is possible for some documents to simply be missing which is why we return None rather than raising an exception.
        if resp.status == 404:
            warning(f'Unable to retrieve document from {entry.request.path}. Error 404 (Not Found) encountered. Returning `None`.')
            
            return
        
        match resp.type:
            case 'text/html':
                # Create an etree from the response.
                etree = lxml.html.fromstring(resp.text)
                
                # Select the element containing the text of the document.
                text_elm = etree.xpath('//div[@id="frag-col"]')[0]
                
                # Remove the toolbar.
                text_elm.xpath('//div[@id="fragToolbar"]')[0].drop_tree()
                
                # Remove the search results (they are supposed to be hidden by Javascript).
                text_elm.xpath('//div[@class="nav-result display-none"]')[0].drop_tree()

                # Remove footnotes (they are supposed to be hidden by Javascript).
                for elm in text_elm.xpath("//*[contains(concat(' ', normalize-space(@class), ' '), ' view-history-note ')]"): elm.drop_tree()

                # Extract the text of the document.
                text = CustomInscriptis(text_elm, self._inscriptis_config).get_text()
            
            case 'application/pdf':
                with pdfplumber.open(resp.stream) as pdf:
                    # NOTE Although `pdfplumber` appears incapable of distinguishing between visual line breaks (ie, from paragraphs wrapping around a page) and semantic/real line breaks, a workaround is to instruct `pdfplumber` to retain blank chars, thereby preserving trailing whitespaces before newlines, and then replace those trailing whitespaces with a single space thereby removing visual line breaks.
                    text = '\n'.join(re.sub(r'\s\n', ' ', page.extract_text(keep_blank_chars=True)) for page in pdf.pages)
            
            case _:
                raise ValueError(f'Unable to retrieve document from {entry.request.path}. Invalid content type: {resp.type}.')
        
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