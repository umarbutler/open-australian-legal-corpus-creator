import asyncio
import math
import re
from datetime import timedelta

import aiohttp
import aiohttp.client_exceptions
import lxml.html
import mammoth
import pdfplumber
import regex
from inscriptis.css_profiles import CSS_PROFILES
from inscriptis.html_properties import Display
from inscriptis.model.html_element import HtmlElement

from ..custom_inscriptis import CustomInscriptis, CustomParserConfig
from ..data import Document, Entry, Request
from ..helpers import log, warning
from ..scraper import Scraper


class FederalCourtOfAustralia(Scraper):
    """A scraper for the Federal Court of Australia database."""
    
    def __init__(self,
                 indices_refresh_interval: bool | timedelta = None,
                 index_refresh_interval: bool | timedelta = None,
                 semaphore: asyncio.Semaphore = None,
                 session: aiohttp.ClientSession = None,
                 ) -> None:
        super().__init__(
            source='federal_court_of_australia',
            indices_refresh_interval=indices_refresh_interval,
            index_refresh_interval=index_refresh_interval,
            semaphore=semaphore,
            session=session
        )
        
        # Remove `aiohttp.client_exceptions.ClientPayloadError` from the list of exceptions to retry on as we need to handle it in `self.get_index` and retrying on it would just waste time since it is not a transient error.
        self.retry_exceptions = tuple(exception for exception in self.retry_exceptions if exception is not aiohttp.client_exceptions.ClientPayloadError)

        self._type = 'decision'
        
        self._base_url = 'https://search2.fedcourt.gov.au/s/search.html?collection=judgments&sort=adate&meta_v_phrase_orsand=judgments/Judgments&'
        self._decisions_per_page = 20
        
        # Create a custom Inscriptis CSS profile.
        inscriptis_profile = CSS_PROFILES['strict'].copy()
        
        # Omit newlines before and after `p` elements.
        inscriptis_profile['p'] = HtmlElement(display=Display.block)
        
        # Omit newlines after headings, but retain them before.
        inscriptis_profile |= dict.fromkeys(('h1', 'h2', 'h3', 'h4', 'h5'), HtmlElement(display=Display.block, margin_before=1))
        
        # Create an Inscriptis parser config using the custom CSS profile.
        self._inscriptis_config = CustomParserConfig(inscriptis_profile)

        # Initialise a map of class names to the number of ems they should be indented by.
        # NOTE This map was created by inspecting the CSS of the Federal Court of Australia database.
        self._class_indentations = {
            'Quote1': 6,
            'Quote1Bullet': 6,
            'Quote2': 9,
            'Quote2Bullet': 9,
            'Quote3': 12,
            'Quote3Bullet': 12,
            'ListNo': 7,
            'FTOC2': 2,
            'FTOC3': 4,
            'FTOC4': 6,
            'ListNo1': 3,
            'ListNo2': 6,
            'ListNo3': 8,
            'Order2': 1,
            'Order3': 3,
            'FCBullets': 3,
            'Order4': 4,
            'Quote4': 15,
            'Quote4Bullet': 15,
            'ListNo1alt': 3,
            'ListNo2alt': 6,
            'ListNo3alt': 8,
            'FCBullets2': 4,
        }

    @log
    async def get_index_reqs(self) -> set[Request]:
        # NOTE There is a bug in the Federal Court of Australia's database that causes the total number of decisions reported by the first 11,000 or so search engine results pages ('SERPs') to be lower than what they really are (cf https://search2.fedcourt.gov.au/s/search.html?collection=judgments&sort=adate&meta_v_phrase_orsand=judgments/Judgments&num_ranks=20&start_rank=1001 and https://search2.fedcourt.gov.au/s/search.html?collection=judgments&sort=adate&meta_v_phrase_orsand=judgments/Judgments&num_ranks=20&start_rank=66001). To determine the actual total number of decisions, we must extract it from what is supposed to be the final SERP.

        # Extract the total number of decisions alleged to exist from the first SERP (NOTE in the url used, we set the number of results per page to 1, as we only need the total number of results, not the results themselves).
        first_serp = (await self.get(f'{self._base_url}num_ranks=1')).text
        alleged_total_decisions = int(re.search(r'Display results 1</span> - 1 of ([\d,]+)', first_serp).group(1).replace(',', ''))

        # Extract the actual total number of decisions from what should be, but is actually not, the final SERP.
        alleged_final_serp = (await self.get(f'{self._base_url}num_ranks=1&start_rank={alleged_total_decisions}')).text
        total_decisions = int(re.search(r'Display results [\d,]+</span> - [\d,]+ of ([\d,]+)', alleged_final_serp).group(1).replace(',', ''))
        
        # Generate SERPs required to retrieve all decisions.
        return {
            Request(f'{self._base_url}num_ranks={self._decisions_per_page}&start_rank={i*self._decisions_per_page+1}')
            
            for i in range(0, math.ceil(total_decisions/self._decisions_per_page))
        }

    @log
    async def get_index(self, req: Request) -> set[Entry]:
        # NOTE There is a bug in the Federal Court of Australia's database that causes certain SERPs to return the exact same results, thereby leading to the inclusion of duplicates in the document index.
        # NOTE There is another bug in the Federal Court of Australia's database that causes any SERPs containing references to a specific set of documents to not work. To mitigate against this, we return an empty set wherever `aiohttp.client_exceptions.ClientPayloadError` is encountered.
        try:
            resp = (await self.get(req)).text
        
        except aiohttp.client_exceptions.ClientPayloadError:
            warning(f"""Unable to retrieve index from {req.path}. Error encountered: aiohttp.client_exceptions.ClientPayloadError. This is likely due to a bug in the Federal Court of Australia's database that causes any search engine results pages containing references to a specific set of documents to not work. Returning an empty set instead.""")
            
            return set()
        
        # Extract entries from the index.
        return {
            Entry(
                request=Request(url, encoding='windows-1250'), # NOTE For whatever reason, judgements are encoded in windows-1250 rather than utf-8 like the rest of the website.
                version_id=url.split('/Judgments/')[1].split('.')[0], # The version id is everything between '/Judgments/' and the first '.' (intended to remove file extensions).
                source=self.source,
                type='decision',
                jurisdiction='norfolk_island' if '/Judgments/nfsc/' in url else 'commonwealth', # NOTE Decisions of the Supreme Court of Norfolk Island are included in the Federal Court of Australia database although they do not belong to the `commonwealth` jurisdiction. Norfolk Island is the only exception.
                title=title,
            )
            
            for url, title in re.findall(r'<a href="(https://www\.judgments\.fedcourt\.gov\.au/judgments/Judgments/[^"]+)"\s+title="([^"]*)">', resp)
        }

    @log
    async def get_doc(self, entry: Entry) -> Document | None:
        # Retrieve the document.
        resp = await self.get(entry.request)
        
        # If error 404 is encountered, return None.
        if resp.status == 404:
            warning(f'Unable to retrieve document from {entry.request.path}. Error 404 (Not Found) encountered. Returning `None`.')
            
            return

        # Store the url of the document (this is to allow for the url to be overriden in the event that we must retrieve the DOCX version of the document, which will occur if it is not possible to decode the document).
        url = entry.request.path
        
        match resp.type:
            case 'text/html':
                # Try to decode the response.
                try:
                    # Try to decode the response as `windows-1250` (most judgements use this encoding).
                    try:
                        resp = resp.decode('windows-1250')
                    
                    # If a `UnicodeDecodeError` is encountered, try decoding the response as `cp1252` instead (this is also possible (see, eg, https://www.judgments.fedcourt.gov.au/judgments/Judgments/fca/single/2007/2007fca0517)).
                    except UnicodeDecodeError:
                        resp = resp.decode('cp1252')
                
                # If we are unable to decode the response, retrieve the DOCX version of the document instead.
                except UnicodeDecodeError:
                    # Extract the url of the DOCX version of the document.
                    url = re.search(rb'<a\s+href="([^"]+)"\s*>Original Word Document', resp).group(1).decode('cp1252')
                    
                    # Retrieve the DOCX version of the document.
                    resp = await self.get(url)

                    # Convert the document to HTML.
                    # NOTE Converting DOCX files to HTML with `mammoth` outperforms using `pypandoc`, `python-docx`, `docx2txt` and `docx2python` to convert DOCX files directly to text.
                    html = mammoth.convert_to_html(resp.stream, convert_image=lambda _: {})

                    # Extract text from the generated HTML.
                    etree = lxml.html.fromstring(html.value)
                    text = CustomInscriptis(etree, self._inscriptis_config).get_text()
                
                # If we were able to decode the response, extract text from it.
                else:      
                    # Remove break elements that are neither preceded nor followed by another break element (the intention is to remove extra newlines). NOTE We use the `regex` module as `re` requires fixed-width lookbehinds.
                    resp = regex.sub(r'(?<!<br />\s*)<br />(?!\s*<br />)', '', resp)
                    
                    # Create an etree from the response.
                    etree = lxml.html.fromstring(resp)

                    # Extract the text of the document from `div.judgment_content`.
                    text_elm = etree.xpath('//div[@class="judgment_content"]')[0]
                    
                    # Ensure that any elements with classes in `self.class_indentations` are indented by the number of ems specified in `self.class_indentations`.
                    # Iterate over all elements with a `class` attribute.
                    for elm in text_elm.xpath('//*[@class]'):
                        # Retrieve the element's classes as a set.
                        classes = set(elm.get('class', '').split(' '))
                        
                        # Determine whether any of the element's classes are in `self.class_indentations`.
                        # NOTE It is possible for more than one class to match, in such a case, whatever class is returned by `matching_classes.pop()` is the one that will be used.
                        if matching_classes := classes.intersection(self._class_indentations):
                            # Retrieve the element's `style` attribute if it exists, otherwise use an empty string.
                            style = elm.get('style', '')
                            
                            # Add the indentation to the element's `style` attribute.
                            elm.set('style', f'margin-left: {self._class_indentations[matching_classes.pop()]}em; {style}')
                    
                    # Use Inscriptis to extract the text of the document.
                    text = CustomInscriptis(text_elm, self._inscriptis_config).get_text()

                    # Remove trailing whitespace (this also helps remove newlines comprised entirely of whitespace).
                    text = regex.sub(r' +\n', '\n', text)
            
            case 'application/pdf':
                with pdfplumber.open(resp.stream) as pdf:
                    # NOTE Although `pdfplumber` appears incapable of distinguishing between visual line breaks (ie, from paragraphs wrapping around a page) and semantic/real line breaks, a workaround is to instruct `pdfplumber` to retain blank chars, thereby preserving trailing whitespaces before newlines, and then replace those trailing whitespaces with a single space thereby removing visual line breaks.
                    text = '\n'.join(re.sub(r'\s\n', ' ', page.extract_text(keep_blank_chars=True)) for page in pdf.pages)
            
            case _:
                raise ValueError(f'Unable to retrieve document from {url}. Invalid content type: {resp.type}.')
        
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