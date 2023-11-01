import asyncio
import re
from datetime import timedelta

import aiohttp
import lxml.html
import mammoth
import pdfplumber
from inscriptis.css_profiles import CSS_PROFILES
from inscriptis.html_properties import Display, WhiteSpace
from inscriptis.model.html_element import HtmlElement
from striprtf.striprtf import rtf_to_text

from ..data import Document, Entry, Request
from ..helpers import log, warning
from ..scraper import Scraper
from ..custom_inscriptis import CustomParserConfig, CustomInscriptis


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
        
        # Create a map of base search engine results pages ('SERPs') to document types.
        self._base_serps = {
            'https://www.legislation.gov.au/Browse/ByTitle/Constitution/InForce' : ('primary_legislation', 'commonwealth'),
            'https://www.legislation.gov.au/Browse/Results/ByRegDate/Acts/InForce/2/0/0/all' : ('primary_legislation', 'commonwealth'),
            'https://www.legislation.gov.au/Browse/Results/ByRegDate/NorfolkIslandLegislation/InForce/2/0' : (None, 'norfolk_island'),
            'https://www.legislation.gov.au/Browse/Results/ByRegDate/LegislativeInstruments/InForce/1/0/0/all' : ('secondary_legislation', 'commonwealth'),
            'https://www.legislation.gov.au/Browse/Results/ByRegDate/LegislativeInstruments/InForce/2/0/0/all' : ('secondary_legislation', 'commonwealth'),
            'https://www.legislation.gov.au/Browse/Results/ByRegDate/NotifiableInstruments/InForce/2/0/0/all' : ('secondary_legislation', 'commonwealth'),
            'https://www.legislation.gov.au/Browse/ByRegDate/AdministrativeArrangementsOrders/InForce/0/0/' : ('secondary_legislation', 'commonwealth'),
            'https://www.legislation.gov.au/Browse/Results/ByRegDate/PrerogativeInstruments/InForce/2/0' : ('secondary_legislation', 'commonwealth'),
            'https://www.legislation.gov.au/Browse/Results/ByYearNumber/Bills/AsMade/1/0/0' : ('bill', 'commonwealth'),
            'https://www.legislation.gov.au/Browse/Results/ByYearNumber/Bills/AsMade/2/0/0' : ('bill', 'commonwealth'),
        }

    @log
    async def get_index_reqs(self) -> set[Request]:
        # Retrieve requests for every page of every base SERP.
        index_reqs = await asyncio.gather(*[self._get_index_reqs_from_base_serp(base_serp) for base_serp in self._base_serps])
        
        # Flatten and return the requests.
        return set().union(*index_reqs)
    
    @log
    async def _get_index_reqs_from_base_serp(self, base_serp: str) -> set[Request]:
        """Retrieve a set of requests for every page of a base search engine results page ('SERP')."""
        
        index_reqs = []
        
        # Retrieve the base SERP.
        resp = (await self.get(base_serp)).text
        
        # Switch to viewing 100 results per page.
        etree = lxml.html.fromstring(resp)
        data = {
            '__EVENTTARGET': 'ctl00$MainContent$gridBrowse',
            '__EVENTARGUMENT': 'FireCommand:ctl00$MainContent$gridBrowse$ctl00;PageSize;100',
            '__VIEWSTATE': etree.xpath('//input[@id="__VIEWSTATE"]/@value')[0],
            '__VIEWSTATEGENERATOR': etree.xpath('//input[@id="__VIEWSTATEGENERATOR"]/@value')[0],
            '__VIEWSTATEENCRYPTED': '',
            '__PREVIOUSPAGE': etree.xpath('//input[@id="__PREVIOUSPAGE"]/@value')[0],
            '__EVENTVALIDATION': etree.xpath('//input[@id="__EVENTVALIDATION"]/@value')[0],
            'ctl00$txtRegularSearch': '',
            'ctl00_txtRegularSearch_ClientState': '{"enabled":true,"emptyMessage":"","validationText":"","valueAsString":"","lastSetTextBoxValue":""}',
            'ctl00$MainContent$rcbBy': 'Registration date',
            'ctl00_MainContent_rcbBy_ClientState': '',
            'ctl00$MainContent$txtFilter': 'Enter text contained in the title',
            'ctl00_MainContent_txtFilter_ClientState': '{"enabled":true,"emptyMessage":"","validationText":"Enter text contained in the title","valueAsString":"Enter text contained in the title","lastSetTextBoxValue":"Enter text contained in the title"}',
            'ctl00_MainContent_RadTabStrip1_ClientState': '{"selectedIndexes":["0"],"logEntries":[],"scrollState":{}}',
            'ctl00$MainContent$gridBrowse$ctl00$ctl02$ctl00$PageSizeComboBox': '100',
            'ctl00_MainContent_gridBrowse_ctl00_ctl02_ctl00_PageSizeComboBox_ClientState': '{"logEntries":[],"value":"100","text":"100","enabled":true,"checkedIndices":[],"checkedItemsTextOverflows":false}',
            'ctl00$MainContent$gridBrowse$ctl00$ctl03$ctl01$PageSizeComboBox': '50',
            'ctl00_MainContent_gridBrowse_ctl00_ctl03_ctl01_PageSizeComboBox_ClientState': '',
            'ctl00_MainContent_gridBrowse_ClientState': '',
        }
        resp = (await self.get(Request(base_serp, method='POST', data=data))).text
        
        # Retrieve the total number of pages.
        etree = lxml.html.fromstring(resp)
        data |= {
            '__EVENTARGUMENT': '',
            '__VIEWSTATE': etree.xpath('//input[@id="__VIEWSTATE"]/@value')[0],
            '__VIEWSTATEGENERATOR': etree.xpath('//input[@id="__VIEWSTATEGENERATOR"]/@value')[0],
            'ctl00_MainContent_gridBrowse_ctl00_ctl02_ctl00_PageSizeComboBox_ClientState': '',
            'ctl00$MainContent$gridBrowse$ctl00$ctl03$ctl01$PageSizeComboBox': '100',
        }
        total_pages = int(etree.xpath('//div[@class="rgWrap rgInfoPart"]/strong[2]/text()')[0])
        
        # Generate requests for every page.
        # NOTE We are able to navigate between pages by setting the `__EVENTTARGET` field to 'ctl00$MainContent$gridBrowse$ctl00$ctl02$ctl00$ctl{page_code}' where `page_code` is a zero-padded two-digit number that:
        # - Begins at 05 for the first page;
        # - Increases by 2 for each subsequent page;
        # - Resets to 09 once it reaches 25 (on the 11th page);
        # - Continues to increase by 2 for each subsequent page;
        # - Resets to 09 once it reaches 27 (on the 21st, 31st, 41st, etc. pages);
        # - Continues to follow the same pattern of incrementing 2 and resetting to 09 at 27 until it reaches 27 for the final time at which point it resets to `25 - (2 * (total_number_of_pages - current_page_number - 1))` and then continues to increase by 2 for each subsequent page.
        
        # Begin the page code number at 5.
        page_code_num = 5
        
        for page_num in range(1, total_pages + 1):
            # Update the `__EVENTTARGET` field with the current page code and then create a request for the page using the resulting new payload.
            page_code = f'0{page_code_num}' if len(str(page_code_num)) == 1 else page_code_num
            data['__EVENTTARGET'] = f'ctl00$MainContent$gridBrowse$ctl00$ctl02$ctl00$ctl{page_code}'
            index_reqs.append(Request(base_serp, method='POST', data=data))

            # If the current page number ends in the number one (i.e. it is the first page in a group of up to 10 pages (the maximum amount of pages the database allows us to navigate between at once)), and it is neither the first page nor the last page, then we must retrieve new `__VIEWSTATE` and `__VIEWSTATEGENERATOR` values.
            if page_num % 10 == 1 and page_num not in {1, total_pages}:
                # Update the `__VIEWSTATE` and `__VIEWSTATEGENERATOR`.
                resp = (await self.get(Request(base_serp, method='POST', data=data))).text
                etree = lxml.html.fromstring(resp)
                data |= {
                    '__VIEWSTATE': etree.xpath('//input[@id="__VIEWSTATE"]/@value')[0],
                    '__VIEWSTATEGENERATOR': etree.xpath('//input[@id="__VIEWSTATEGENERATOR"]/@value')[0],
                }

                # If the current page number is the first page in the last group of 10 or less pages, then the `page_code` for the next page will be 25 - (2 * (total_number_of_pages - current_page_number - 1)).
                if total_pages-page_num < 10:
                    page_code_num = 25 - (2 * (total_pages - page_num - 1))
                
                # Otherwise, the `page_code` for the next page will be 9.
                else:
                    page_code_num = 9
            
            # Otherwise, we increment the `page_code` by 2.
            else:
                page_code_num += 2
        
        return set(index_reqs)
        
    @log
    async def get_index(self, req: Request) -> set[Entry]:
        # Determine the type and jurisdiction of the index.
        # NOTE it is possible for the document type to be None (eg, for Norfolk Island legislation); in such cases, the document type is determined when retrieving the document.
        type, jurisdiction = self._base_serps[req.path]
        
        # Retrieve the index.
        resp = (await self.get(req))
        
        # Extract entries from the index.
        entries = {
            Entry(
                request = Request(f'https://www.legislation.gov.au/Details/{version_id}'),
                version_id = version_id,
                source = self.source,
                type = type,
                jurisdiction = jurisdiction,
                title = title,
            )
            
            for version_id, title in re.findall(r'<a id="ctl00_MainContent_gridBrowse_ctl00_ctl\d+_hl" class="LegBookmark" href="[\./]+Details/([^"]+)">((?:.|\n)*?)</a>', resp.text)
        }
        
        # Raise an exception if no entries were found.
        if len(entries) == 0:
            raise Exception(f'No entries were found for the request:\n{req}')
        
        return entries

    @log
    async def get_doc(self, entry: Entry) -> Document | None:
        # Retrieve the document.
        resp = await self.get(entry.request)
        
        # If no document type was set, determine the document type from the title.
        if entry.type is None:
            # NOTE This regex only matches primary legislation for Norfolk Island as Norfolk Island is currently the only jurisdiction for which the document type will not already be set.
            if re.search(r'^.*\sAct\s+\d{4}\s+\(NI\)\s*$', entry.title):
                type = 'primary_legislation'
            
            else:
                type = 'secondary_legislation'
        
        else:
            type = entry.type
        
        # Create an etree from the response.
        etree = lxml.html.document_fromstring(resp.text)
        
        # Select the element containing the text of the document.
        text_element = etree.xpath('//div[@id="MainContent_pnlHtmlControls"]')

        # If `text_element` is not in the document, then we know that we cannot extract text from the web page and instead need to download the document.
        if not text_element:
            # Search for RTF, DOCX and PDF versions of the document, in that order.
            for format in ('RTF', 'DOCX', 'PDF', 'PDFAuthoritative'):
                # Search for the url of the parent element of an element where the `src` is 'https://www.legislation.gov.au/Images/Attachments/icon{INSERT_FORMAT}.gif', if such an element exists.
                url = etree.xpath(f'//img[@src="https://www.legislation.gov.au/Images/Attachments/icon{format}.gif"]/parent::a/@href')
                
                # If the url was found, then break from the loop.
                if url:
                    break
            
            # If the format is set to 'PDFAuthoritative', then convert it to 'PDF'.
            if format == 'PDFAuthoritative': format = 'PDF'
            
            # If the url was not found, then log a warning and return None.
            # NOTE Some documents do not have any versions available (see, eg, https://www.legislation.gov.au/Details/C2004B00787). This is why it is acceptable to return None.
            if not url:
                warning(f'Unable to retrieve document from {entry.request.path}. No valid version found. This may be because the document simply does not have any versions available, or it could be that any versions it does have available are unsupported. The status code of the response was {resp.status}. Returning `None`.')
                
                return
            
            # Now that the url has been found, extract it.
            url = url[0]
            
            # Download the document.
            resp = await self.get(url)
            
            match format:
                case 'RTF':
                    text = rtf_to_text(resp.text, encoding='cp1252', errors='ignore')

                case 'DOCX':
                    # Convert the document to HTML.
                    # NOTE Converting DOCX files to HTML with `mammoth` outperforms using `pypandoc`, `python-docx`, `docx2txt` and `docx2python` to convert DOCX files directly to text.
                    html = mammoth.convert_to_html(resp.stream, convert_image=lambda _: {})

                    # Extract text from the generated HTML.
                    etree = lxml.html.fromstring(html.value)
                    text = CustomInscriptis(etree, self._inscriptis_config).get_text()
                
                case 'PDF':
                    # Extract the text of the document from the PDF.
                    with pdfplumber.open(resp.stream) as pdf:
                        # NOTE Although `pdfplumber` appears incapable of distinguishing between visual line breaks (ie, from sentences wrapping around a page) and semantic/real line breaks, a workaround is to instruct `pdfplumber` to retain blank chars, thereby preserving trailing whitespaces before newlines, and then replace those trailing whitespaces with a single space thereby removing visual line breaks.
                        text = '\n'.join(re.sub(r'\s\n', ' ', page.extract_text(keep_blank_chars=True)) for page in pdf.pages)
        
        # Otherwise, extract the text of the document.
        else:
            # Store the document's url.
            url = entry.request.path
            
            # Extract the text of the document.
            text = CustomInscriptis(text_element[0], self._inscriptis_config).get_text()
        
        # Return the document.
        return Document(
            version_id=entry.version_id,
            type=type,
            jurisdiction=entry.jurisdiction,
            source=entry.source,
            citation=entry.title,
            url=url,
            text=text
        )