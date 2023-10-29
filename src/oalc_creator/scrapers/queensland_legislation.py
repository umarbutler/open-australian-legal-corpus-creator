import asyncio
import re
from datetime import datetime, timedelta

import aiohttp
import lxml.html
import pdfplumber
import pytz
from inscriptis import Inscriptis
from inscriptis.css_profiles import CSS_PROFILES
from inscriptis.html_properties import Display
from inscriptis.model.config import ParserConfig
from inscriptis.model.html_element import HtmlElement

from ..css import CustomAttribute
from ..data import Document, Entry, Request
from ..helpers import log, warning
from ..scraper import Scraper


class QueenslandLegislation(Scraper):
    """A scraper for the Queensland Legislation database."""
    
    def __init__(self,
                 indices_refresh_interval: bool | timedelta = None,
                 index_refresh_interval: bool | timedelta = None,
                 semaphore: asyncio.Semaphore = None,
                 session: aiohttp.ClientSession = None,
                 ) -> None:
        super().__init__(
            source='queensland_legislation',
            indices_refresh_interval=indices_refresh_interval,
            index_refresh_interval=index_refresh_interval,
            semaphore=semaphore,
            session=session
        )

        self._jurisdiction = 'queensland'

        # Create a custom Inscriptis CSS profile.
        inscriptis_profile = CSS_PROFILES['strict'].copy()

        # Omit newlines before and after `p` elements.
        inscriptis_profile['p'] = HtmlElement(display=Display.block)
        
        # Ensure that whitespace is inserted before and after `span` elements to prevent words from sticking together (this was taken from the `relaxed` profile, however, we do not use that profile as it also pads `div`s).
        inscriptis_profile['span'] = HtmlElement(display=Display.inline, prefix=' ', suffix=' ', limit_whitespace_affixes=True)
        
        # Ensure that blockquotes are indented.
        inscriptis_profile['blockquote'] = HtmlElement(display=Display.block, padding_inline=4)
        
        # Create an Inscriptis parser config using the custom CSS profile.
        self._inscriptis_config = ParserConfig(inscriptis_profile)

        # Override Inscriptis' default attribute handler and, by extension, CSS parser.
        self._inscriptis_config.attribute_handler = CustomAttribute()

    @log
    async def get_index_reqs(self) -> set[Request]:
        return {
            Request(f'https://www.legislation.qld.gov.au/tables/{suffix}{datetime.now(tz=pytz.timezone("Australia/Queensland")).strftime(r"%d/%m/%Y")}&sort=chron&renderas=html&generate=')
            
            for suffix in ('pubactsif?pit=', 'siif?pit=', 'bills?dstart=03/11/1992&dend=')
        }

    @log
    async def get_index(self, req: Request) -> set[Entry]:
        # Determine the document type of the index.
        table = re.search(r'https://www.legislation.qld.gov.au/tables/([^?]+?)(?:if)?\?', req.path).group(1)
        
        match table:
            case 'pubacts':
                type = 'primary_legislation'
            
            case 'si':
                type = 'secondary_legislation'
            
            case 'bills':
                type = 'bill'
            
            case _:
                raise ValueError(f'Unable to retrieve index from {req.path}. Invalid table: {table}.')
                
        # Retrieve the index.
        resp = (await self.get(req)).text
        
        # Extract document paths and titles from the index.
        paths_and_titles = re.findall(r'<a(?: class="indent")? href="/view/([^"]+)">((?:.|\n)*?)</a>', resp)
        
        # Create entries from the paths and titles.
        return set(await asyncio.gather(*[self._get_entry(path, title, type) for path, title in paths_and_titles]))
    
    @log
    async def _get_entry(self, path: str, title: str, type: str) -> Entry:
        # If the document is a bill then we already have its version id.
        if type == 'bill':
            version_id = path
            
            # Remove 'html/' and 'pdf/' from the version id.
            version_id = version_id.replace('html/', '').replace('pdf/', '')
        
        # Otherwise, we must retrieve the document's status page to determine the id of its latest version.
        else:
            # Extract the document id from the path.
            doc_id = path.split('/')[-1]

            # Retrieve the document's status page.
            resp = (await self.get(f"https://legislation.qld.gov.au/view/html/inforce/current/{doc_id}")).text 

            # Extract the point in time of the latest version of the document.
            pit = re.search(r'PublicationDate%3D(\d+)', resp).group(1)
            pit = f'{pit[:4]}-{pit[4:6]}-{pit[6:8]}'

            # Create the version id by appending the document id to the point in time.
            version_id = f'{pit}/{doc_id}'
        
        # Create the entry.
        return Entry(
            request=Request(f'https://legislation.qld.gov.au/view/whole/html/inforce/{version_id}'),
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
        if resp.status == 404:
            warning(f'Unable to retrieve document from {entry.request.path}. Error 404 (Not Found) encountered. Returning `None`.')
            
            return

        # If the document does not contain '<span id="view-whole">' then we know that it was extracted from a PDF and so we download the PDF and extract the text from it directly.
        if '<span id="view-whole">' not in resp.text:
            # Update the url.
            url = entry.request.path.replace('html', 'pdf')
            
            # Retrieve the PDF.
            resp = (await self.get(Request(url))).stream
            
            # Extract the text of the document.
            with pdfplumber.open(resp) as pdf:
                # NOTE Although `pdfplumber` appears incapable of distinguishing between visual line breaks (ie, from paragraphs wrapping around a page) and semantic/real line breaks, a workaround is to instruct `pdfplumber` to retain blank chars, thereby preserving trailing whitespaces before newlines, and then replace those trailing whitespaces with a single space thereby removing visual line breaks.
                text = '\n'.join(page.extract_text() for page in pdf.pages)
            
        else:
            # Store the document's url.
            url = entry.request.path
        
            # Create an etree from the response.
            etree = lxml.html.fromstring(resp.text)
            
            # Select the element containing the text of the document.
            text_elm = etree.xpath('//div[@id="fragview"]')[0]

            # Iterate over all elements with a `class` attribute.
            for elm in text_elm.xpath('//*[@class]'):
                # Retrieve the element's classes as a set.
                classes = set(elm.get('class', '').split(' '))
                
                # Remove footnotes, repealed text (they are both supposed to be hidden by Javascript) and links to the source of particular sections in the document (see, eg, https://www.legislation.qld.gov.au/view/whole/html/inforce/current/act-2023-019 'section 2(2)' which appears on the right side underneath the heading 'Schedule 1 Appropriations for 2023-2024').
                if classes & {
                    'view-history-note', # Footnotes.
                    'view-repealed', # Repealed text.
                    'source', # Links to the source of particular sections in the document.
                }:
                    elm.drop_tree()

            # Extract the text of the document.
            text = Inscriptis(text_elm, self._inscriptis_config).get_text()
        
        # Return the document.
        return Document(
            version_id=entry.version_id,
            type=entry.type,
            jurisdiction=entry.jurisdiction,
            source=entry.source,
            citation=entry.title,
            url=url,
            text=text
        )