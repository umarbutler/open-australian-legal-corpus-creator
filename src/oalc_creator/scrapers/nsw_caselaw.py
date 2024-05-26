import re
import asyncio

from math import ceil
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

import aiohttp
import lxml.html

from inscriptis.css_profiles import CSS_PROFILES
from inscriptis.html_properties import Display
from inscriptis.model.html_element import HtmlElement

from ..ocr import pdf2txt
from ..data import Entry, Request, Document, make_doc
from ..helpers import log
from ..scraper import Scraper, ParseError
from ..custom_inscriptis import CustomInscriptis, CustomParserConfig


class NswCaselaw(Scraper):
    """A scraper for the NSW Caselaw database."""
    
    def __init__(self,
                 indices_refresh_interval: bool | timedelta = None,
                 index_refresh_interval: bool | timedelta = None,
                 semaphore: asyncio.Semaphore = None,
                 session: aiohttp.ClientSession = None,
                 thread_pool_executor: ThreadPoolExecutor = None
                 ) -> None:        
        super().__init__(
            source='nsw_caselaw',
            indices_refresh_interval=indices_refresh_interval,
            index_refresh_interval=index_refresh_interval,
            semaphore=semaphore or asyncio.Semaphore(10), # Employ a lower semaphore limit to avoid overloading the NSW Caselaw database.
            session=session,
            thread_pool_executor=thread_pool_executor
        )

        self._jurisdiction = 'new_south_wales'
        self._type = 'decision'

        # Create a custom Inscriptis CSS profile.
        inscriptis_profile = CSS_PROFILES['strict'].copy()

        # Omit newlines before and after `p` elements.
        inscriptis_profile['p'] = HtmlElement(display=Display.block)
        
        # Omit newlines after headings, but retain them before.
        inscriptis_profile |= dict.fromkeys(('h1', 'h2', 'h3', 'h4', 'h5'), HtmlElement(display=Display.block, margin_before=1))
        
        # Create an Inscriptis parser config using the custom CSS profile.
        self._inscriptis_config = CustomParserConfig(inscriptis_profile)

        # Initialise a map of class names to the number of ems they should be indented by.
        # NOTE This map was created by inspecting the CSS of the NSW Caselaw database.
        self._class_indentations = {
            'quote': 8,
            'indent1' : 8,
            'indent2' : 12,
            'indent3' : 16,
            'indent4' : 20,
        }

    @log
    async def get_index_reqs(self) -> set[Request]:
        # Retrieve the total number of decisions in the database from the first search engine results page ('SERP').
        resp = (await self.get('https://www.caselaw.nsw.gov.au/browse?display=all')).text
        total_decisions = int(re.search(r'<span class="total">(\d+)</span>', resp).group(1))
        pages = ceil(total_decisions / 200)
        
        # Generate requests for every page of the queries.
        # NOTE Pages start at 0, which is why we don't add 1 to the range.
        return {Request(f'https://www.caselaw.nsw.gov.au/browse/list?page={page}') for page in range(0, pages)}

    @log
    async def get_index(self, req: Request) -> set[Entry]:
        # Retrieve the index.
        resp = (await self.get(req)).json
        
        # Extract entries from the index.
        return {
            Entry(
                request=Request(f'https://www.caselaw.nsw.gov.au/decision/{entry["id"]}'),
                version_id=entry['id'],
                source=self.source,
                jurisdiction=self._jurisdiction,
                date=datetime.strptime(entry['decisionDateText'], '%d %B %Y').strftime('%Y-%m-%d') if 'decisionDateText' in entry and entry['decisionDateText'] else None, # NOTE We use `decisionDateText` instead of `decisionDate` (which is an integer) because I have seen cases where `decisionDate` is negative, despite `decisionDateText` being valid and indeed truthful upon inspection (see, eg, https://www.caselaw.nsw.gov.au/decision/56b12bc8e4b0e71e17f4eb55).
                title=f'{(entry["title"] if "title" in entry else "")} {entry["mnc"]}',
            )
            
            for entry in resp['searchableDecisions']
            
            # Filter out empty and restricted decisions.
            if not entry['restricted'] and ('title' not in entry or ('decision number not in use' not in (cleaned_title := ' '.join(entry['title'].lower().split())) and 'decision restricted' not in cleaned_title))
        }

    @log
    async def _get_doc(self, entry: Entry) -> Document | None:
        # Retrieve the document.
        resp = (await self.get(entry.request)).text
        
        # Preserve the document's url.
        # NOTE This allows us to overwrite the url if we need to retrieve its PDF version.
        url = entry.request.path
        
        # If the document is PDF-only, extract the text of the document from its PDF version.
        match: re.Match | None # Type hint the match.
        if match := re.search(r'<a href="/asset/([^"]+)">See Attachment \(PDF\)</a>', resp):
            url = f'https://www.caselaw.nsw.gov.au/asset/{match.group(1)}'
            resp = await self.get(url)
            
            # Raise a `ParseError` if the PDF can't be loaded.
            try:
                # Extract the text of the document from the PDF with OCR.
                text = await pdf2txt(resp.stream, self.ocr_batch_size, self.thread_pool_executor)
                
            except Exception as e:
                raise ParseError(f'Unable to extract text from PDF at {url}.') from e

            # Remove the header.
            text = re.sub(r'[^\n]*JOBNAME: [^\n]+\n/reports/[^\n]+\n?', '', text)
            
            # Store the mime of the document.
            mime = 'application/pdf'
            
        else:
            # Construct an etree from the response.
            etree = lxml.html.fromstring(resp)

            # Retrieve the element containing the text of the decision if it exists, otherwise raise a `ParseError`.
            text_elm = etree.xpath('//div[@class="judgment"]')
            
            if text_elm:
                text_elm = text_elm[0]
            
            else:
                raise ParseError()

            # Convert description lists (used for headnotes) into tables as Inscriptis renders description lists incorrectly.
            text_elm = self.dls_to_tables(text_elm)

            # Iterate over all elements with a `class` attribute.
            elm: lxml.html.HtmlElement # Type hint the element.
            for elm in text_elm.xpath('//*[@class]'):
                # Retrieve the element's classes as a set.
                classes = set(elm.get('class', '').split(' '))
                
                # Ensure that any elements with classes in `self.class_indentations` are indented by the number of ems specified in `self.class_indentations`.
                if matching_classes := classes.intersection(self._class_indentations):
                    # Retrieve the element's `style` attribute if it exists, otherwise use an empty string.
                    style = elm.get('style', '')

                    # Calculate how many ems the element should be indented by.
                    indentation = sum([self._class_indentations[matching_class] for matching_class in matching_classes])
                    
                    # Add the indentation to the element's `style` attribute.
                    elm.set('style', f'margin-left: {indentation}em; {style}')
                
                # Remove the decision actions buttons.
                if 'decision-actions' in classes:
                    elm.drop_tree()
        
            # Extract the text of the decision.
            text = CustomInscriptis(text_elm, self._inscriptis_config).get_text()
            
            # Remove the single space indentation added before paragraph numbers.
            text = re.sub(r'(\n) (\d+\.)', r'\1\2', text)
            
            # Insert a newline after the title.
            text = re.sub(r'^([^\n]+ Court\nNew South Wales\n)', r'\1\n', text)

            # Insert a newline before the endnotes divider (note I have seen 10 asterisks used as a divider as well as 9, so for good measure, this will match 7 or more asterisks).
            text = re.sub(r'(\n\*{7,}\n)', r'\n\1', text)
            
            # Store the mime of the document.
            mime = 'text/html'
                
        # Create the document.
        return make_doc(
            version_id=entry.version_id,
            type=self._type,
            jurisdiction=self._jurisdiction,
            source=self.source,
            mime=mime,
            date=entry.date,
            citation=entry.title,
            url=url,
            text=text,
        )
    
    @log
    def dls_to_tables(self, etree: lxml.html.HtmlElement) -> lxml.html.HtmlElement:
        """Convert any description lists in an etree into tables."""
        
        # If there are no `dt` elements in the etree, return the etree.
        if not etree.xpath('//dt'):
            return etree

        # Separate the etree from any parents by re-serialising it.
        etree = lxml.html.fromstring(lxml.html.tostring(etree))
        
        # Iterate through all parent description lists (defined as elements that have a `dt` child that are not the children of elements that have `dt` children, excluding `body` elements. NOTE this will match description lists that are not `dl` tags, such as `div`s, which is intended behaviour).
        dl: lxml.html.HtmlElement # Type hint description lists.
        for dl in etree.xpath('//*[dt and not(ancestor::*[dt])]'):
            # Exclude `body` elements as they should not constitute description lists.
            # NOTE This is necessary because if the etree consists of `dt`s with no parent, the above XPath will match a `body` element that was added by lxml when we cloned the element as a separate etree.
            if dl.tag == 'body':
                continue
            
            rows: list[list[str, list[str]]] = []
            
            # Iterate through the list's children.
            for di in dl:
                # If the child is a `dt` element, convert any child description lists of the element to tables and then place its html in the first column of a new row.
                if di.tag == 'dt':
                    di = self.dls_to_tables(di)
                    rows.append([lxml.html.tostring(di).decode('utf-8'), []])
                
                # If we are inside a row, convert any child description lists of the element to tables and then append its html to the second column of the latest row.
                elif rows:
                    di = self.dls_to_tables(di)
                    
                    rows[-1][1].append(lxml.html.tostring(di).decode('utf-8'))
            
            # Overwrite the description list with a table.
            # NOTE We use `vertical-align:top;` to ensure that row cells are aligned to each other.
            rows = ''.join([f'<tr><td style="vertical-align:top;">{dt}</td><td style="vertical-align:top;">{"".join(dds)}</td></tr>' for dt, dds in rows])
            table = lxml.html.fragment_fromstring(rows, create_parent='table')
            dl.getparent().replace(dl, table)
        
        return etree