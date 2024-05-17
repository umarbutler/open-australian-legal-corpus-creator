import re
import asyncio

from math import ceil
from datetime import timedelta

import aiohttp
import mammoth
import lxml.html
import pdfplumber

from inscriptis.css_profiles import CSS_PROFILES
from inscriptis.html_properties import Display, WhiteSpace
from inscriptis.model.html_element import HtmlElement

from ..data import Entry, Request, Document, make_doc
from ..helpers import log, warning
from ..scraper import Scraper
from ..custom_inscriptis import CustomInscriptis, CustomParserConfig


class FederalRegisterOfLegislation(Scraper):
    """A scraper for the Federal Register of Legislation database."""
    
    def __init__(self,
                 indices_refresh_interval: bool | timedelta = None,
                 index_refresh_interval: bool | timedelta = None,
                 semaphore: asyncio.Semaphore = None,
                 session: aiohttp.ClientSession = None,
                 ) -> None:
        super().__init__(
            source='federal_register_of_legislation',
            indices_refresh_interval=indices_refresh_interval,
            index_refresh_interval=index_refresh_interval,
            semaphore=semaphore,
            session=session,
        )
        
        # Add status codes to the list of status codes to retry on that are transient errors that occur when the Federal Register of Legislation's servers are overloaded.
        self.retry_statuses += (502, 400,)

        # Create a custom Inscriptis CSS profile.
        inscriptis_profile = CSS_PROFILES['strict'].copy()
        
        # Omit additional newlines before and after `p` elements.
        inscriptis_profile['p'] = HtmlElement(display=Display.block)
        
        # Preserve the indentation of `span` elements with whitespace.
        inscriptis_profile['span'] = HtmlElement(whitespace=WhiteSpace.pre)
        
        # Omit newlines after headings, but retain them before.
        inscriptis_profile |= dict.fromkeys(('h1', 'h2', 'h3', 'h4', 'h5'), HtmlElement(display=Display.block, margin_before=1))
        
        # Create an Inscriptis parser config using the custom CSS profile.
        self._inscriptis_config = CustomParserConfig(inscriptis_profile)
        
        # Define the maximum number of documents that can be returned by a search engine results page ('SERP').
        self._docs_per_serp = 500
        
        # Map database collection names to document types and jurisdictions.
        self._collections = {
            'Constitution': ('primary_legislation', 'commonwealth'),
            'Act': ('primary_legislation', 'commonwealth'),
            'LegislativeInstrument': ('secondary_legislation', 'commonwealth'),
            'NotifiableInstrument': ('secondary_legislation', 'commonwealth'),
            'AdministrativeArrangementsOrder': ('secondary_legislation', 'commonwealth'),
            'PrerogativeInstrument': ('secondary_legislation', 'commonwealth'),
            'ContinuedLaw': (None, 'norfolk_island'),
        }

    @log
    async def get_index_reqs(self) -> set[Request]:
        # Retrieve the first search engine results page ('SERP') to determine the total number of pages.
        first_page = await self.get(
            f"""https://api.prod.legislation.gov.au/v1/titles/search(
                criteria = 'and(
                        collection(
                            {','.join(self._collections)}
                            ),
                        status(InForce)
                    )'
            )?
            $top=0""".replace('\n', '').replace(' ', '') # Remove newlines and spaces that were inserted into the url template for readability.
        )
        total_docs = first_page.json['@odata.count']
        total_pages = ceil(total_docs/self._docs_per_serp)
        
        # Generate requests for every page of results.
        return {
            Request(
                f"""https://api.prod.legislation.gov.au/v1/titles/search(
                    criteria = 'and(
                            collection(
                                Constitution,
                                Act,
                                LegislativeInstrument,
                                NotifiableInstrument,
                                AdministrativeArrangementsOrder,
                                PrerogativeInstrument,
                                ContinuedLaw),
                            status(InForce)
                        )'
                )?
                &$ select = collection, id, name, searchContexts
                &$ expand = searchContexts($expand=fullTextVersion)
                &$ top = {self._docs_per_serp}
                &$ skip = {self._docs_per_serp*page}""".replace('\n', '').replace(' ', '') # Remove newlines and spaces that were inserted into the url template for readability.
            )
            
            for page in range(total_pages)
        }
    
    @log
    async def get_index(self, req: Request) -> set[Entry]:
        # Retrieve the index.
        resp = (await self.get(req))
        
        # Raise an exception if no results were returned.
        if len(resp.json['value']) == 0:
            raise Exception(f'No entries were found for the request:\n{req}')
        
        # Extract entries from the index.
        return {
            Entry(
                request = Request(f"https://www.legislation.gov.au/{entry['id']}"),
                version_id=entry['searchContexts']['fullTextVersion']['registerId'],
                source=self.source,
                type=self._collections[entry['collection']][0], # NOTE it is possible for the document type to be None (eg, for Norfolk Island legislation); in such cases, the document type is determined when retrieving the document.
                jurisdiction=self._collections[entry['collection']][1],
                title=entry['name'],
            )
            
            for entry in resp.json['value']
        }

    @log
    async def get_doc(self, entry: Entry) -> Document | None:
        # If no document type was set, determine the document type from the title.
        if entry.type is None:
            # NOTE This regex only matches primary legislation for Norfolk Island as Norfolk Island is currently the only jurisdiction for which the document type will not already be set.
            if re.search(r'^.*\sAct\s+\d{4}\s+\(NI\)\s*$', entry.title):
                type = 'primary_legislation'
            
            else:
                type = 'secondary_legislation'
        
        else:
            type = entry.type
        
        # Retrieve the document's status page.
        status_page = await self.get(entry.request)
        
        # Extract the link to the document's HTML full text if it exists otherwise search for other versions of the document.
        url = re.search(r'<iframe[^>]+name="epubFrame"[^>]+src="([^"]+)">', status_page.text)
        
        # Retrieve and parse the document's HTML full text if it is available.
        if url:
            url = url.group(1)

            # Retrieve the document's full text.
            resp = await self.get(url)
            
            # Create an etree from the response.
            etree = lxml.html.document_fromstring(resp)
                
            # Extract the text of the document.
            text = CustomInscriptis(etree, self._inscriptis_config).get_text()
        
        # If there is no link to the document's HTML full text, search for other versions of the document.
        else:
            url = f'{entry.request.path}/asmade/downloads'
            downloads_page = await self.get(url)
            downloads_page_etree = lxml.html.document_fromstring(downloads_page)
            
            # If there are no available versions of the document, log a warning and return `None`.
            downloads = downloads_page_etree.xpath("//*[contains(concat(' ', normalize-space(@class), ' '), ' download-list-primary ')]")
            
            if not downloads:
                warning(f'Unable to retrieve document from {entry.request.path}. No valid version found. The status code of the response was {downloads_page.status}. Returning `None`.')
                return None
            
            # Search for Word and then PDF versions of the document.
            for format in ('word', 'pdf'):
                format_downloads = downloads[0].xpath(f".//*[contains(concat(' ', normalize-space(@class), ' '), ' document-format-{format} ')]")
                
                # Skip to the next format if the document is not available in this format.
                if not format_downloads:
                    continue
                
                # Extract links to the version's constituent parts.
                part_links = format_downloads[0].xpath(".//a/@href")
                
                # Skip to the next format if there are no links to the document in this format.
                if not part_links:
                    continue
                
                break
            
            # If there are neither any Word nor any PDF versions of the document, log a warning and return `None`.
            else:
                warning(f'Unable to retrieve document from {entry.request.path}. No valid version found. This may be because the document simply does not have any versions available, or it could be that any versions it does have available are unsupported. The status code of the response was {downloads_page.status}. Returning `None`.')
                return None
            
            # If there is just one part, use that as the url otherwise append the format's name to the url to the document's download page to indicate how the document was downloaded.
            if len(part_links) == 1:
                url = part_links[0]
            
            else:
                url = f'{url}#{format}'
            
            # Retrieve the version's constituent parts.
            part_resps = await asyncio.gather(*[self.get(part_link) for part_link in part_links])
            
            # Extract the text of the version's parts.
            match format:
                case 'word':
                    # Convert the parts to HTML.
                    # NOTE Converting DOCX files to HTML with `mammoth` outperforms using `pypandoc`, `python-docx`, `docx2txt` and `docx2python` to convert DOCX files directly to text.
                    htmls = [mammoth.convert_to_html(resp.stream, convert_image=lambda _: {}) for resp in part_resps]
                    
                    # Extract text from the generated HTML.
                    etrees = [lxml.html.fromstring(html.value) for html in htmls]
                    texts = [CustomInscriptis(etree, self._inscriptis_config).get_text() for etree in etrees]
                
                case 'pdf':
                    # Extract the text of the PDFs.
                    texts = []
                    
                    for resp in part_resps:
                        with pdfplumber.open(resp.stream) as pdf:
                            # NOTE Although `pdfplumber` appears incapable of distinguishing between visual line breaks (ie, from sentences wrapping around a page) and semantic/real line breaks, a workaround is to instruct `pdfplumber` to retain blank chars, thereby preserving trailing whitespaces before newlines, and then replace those trailing whitespaces with a single space thereby removing visual line breaks.
                            texts.append('\n'.join(re.sub(r'\s\n', ' ', page.extract_text(keep_blank_chars=True)) for page in pdf.pages))
            
            # Stitch together the version's parts to form the full text of the version.
            text = '\n'.join(texts)
            
        # Return the document.
        return make_doc(
            version_id=entry.version_id,
            type=type,
            jurisdiction=entry.jurisdiction,
            source=entry.source,
            citation=entry.title,
            url=url,
            text=text
        )