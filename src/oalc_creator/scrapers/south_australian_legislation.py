import datetime
import re
import string
import asyncio
import itertools

from datetime import timedelta, datetime

import aiohttp

from striprtf.striprtf import rtf_to_text

from ..data import Entry, Request, Document, make_doc, Response
from ..helpers import log
from ..scraper import Scraper
from xxhash import xxh3_64_hexdigest


class SouthAustralianLegislation(Scraper):
    """A scraper for the South Australian Legislation database."""
    
    def __init__(self,
                 indices_refresh_interval: bool | timedelta = None,
                 index_refresh_interval: bool | timedelta = None,
                 semaphore: asyncio.Semaphore = None,
                 session: aiohttp.ClientSession = None,
                 ) -> None:
        super().__init__(
            source='south_australian_legislation',
            indices_refresh_interval=indices_refresh_interval,
            index_refresh_interval=index_refresh_interval,
            semaphore=semaphore,
            session=session
        )
        
        self._jurisdiction = 'south_australia'

    @log
    async def get_index_reqs(self) -> set[Request]:
        # NOTE Because the South Australian Legislation database indexes documents by type and then by the first letter of their title, we generate requests for every possible combination of available document types and letters of the alphabet.
        return {
            Request(f'https://www.legislation.sa.gov.au/legislation/{type}?key={letter}')
            for type, letter in itertools.product(
                {'acts/consolidated', 'bills/current', 'bills/archived', 'regulations-and-rules/consolidated', 'policies/consolidated', 'proclamations-and-notices/consolidated'},
                string.ascii_lowercase
            )
        }

    @log
    async def get_index(self, req: Request) -> set[Entry]:
        # Determine the document type of the index.
        if '/acts/' in req.path:
            type = 'primary_legislation'
        
        elif '/bills/' in req.path:
            type = 'bill'
        
        else:
            type = 'secondary_legislation'
        
        # Retrieve the index.
        resp = (await self.get(req)).text
        
        # Extract all table rows.
        rows = re.findall(r"<tr\s*>((?:.|\n)*?)</tr>", resp)
        
        # Create entries from the rows.
        entries = await asyncio.gather(*[self._get_entry(row, type) for row in rows])
        
        # Filter out any entries that are `None`.
        # NOTE It is possible for documents not to be available in the database (see, eg, https://www.legislation.sa.gov.au/lz?path=/c/a/appraisers%20act%20and%20auctioneers%20act%20repeal%20act%201980 and https://www.legislation.sa.gov.au/lz?path=/c/a/adelaide%20show%20grounds%20(by-laws)%20act%201929). This is why it is acceptable for `self._get_entry` to return `None`.
        entries = {entry for entry in entries if entry}
        
        return entries
    
    @log
    async def _get_entry(self, row: str, type: str) -> Entry:
        # Extract the entry's title and the path to its status page.
        status_page_path, title = re.search(r'<a\s+href="[^"]+"\s+title="([^"]+)"\s*>((?:.|\n)*?)</a>', row).groups()
        
        # Retrieve the document's status page.
        resp: Response = (await self.get(status_page_path)).text
        
        # Extract the link to the latest version of the document as well as the document's id if it is available otherwise return `None`.
        # NOTE It is possible for documents not to be available on the database (see, eg, https://www.legislation.sa.gov.au/lz?path=/c/a/appraisers%20act%20and%20auctioneers%20act%20repeal%20act%201980 and https://www.legislation.sa.gov.au/lz?path=/c/a/adelaide%20show%20grounds%20(by-laws)%20act%201929). This is why it is acceptable to return `None`.
        if (url_doc_id := re.search(r'<a\s+href="(https://www\.legislation\.sa\.gov\.au/__legislation/.+/current/(.+)\.rtf)"', resp)):
            url, doc_id = url_doc_id.groups()
        
        else:
            return None
        
        # Attempt to extract the end date of the previous version of the document and use the date immediately following it as the document's date and version id if possible.
        date = None
        
        if (prev_end_date := re.search(r'\(\d{2} [A-Z][a-z]+ \d{4} - (\d{2} [A-Z][a-z]+ \d{4}), Authorised\)', resp)):
            date = prev_end_date.group(1)
            date = datetime.strptime(date, '%d %B %Y') + timedelta(days=1)
            date = date.strftime('%Y-%m-%d')
            
            version_id = f'{date}/{doc_id}'
            
        # Otherwise, extract the date the document's status page was last modified and then append the document's id to produce the document's version id.
        # NOTE Unfortunately, the South Australian Legislation database does not provide version ids nor does it provide a way to determine the date of a document's version from its status page apart from looking at the end date of the previous version, so we have to use the XXH3 64-bit hexidecimal hash of the status page's `main` element as the document's version id.
        else:
            version_hash = xxh3_64_hexdigest(re.search(r'<main[^>]*>(.*?)</main>', resp, re.DOTALL).group(1))
            version_id = f'{version_hash}/{doc_id}'
        
        return Entry(
            request=Request(url, encoding='cp1252'),
            version_id=version_id,
            source=self.source,
            type=type,
            jurisdiction=self._jurisdiction,
            date=date,
            title=title,
        )

    @log
    async def _get_doc(self, entry: Entry) -> Document | None:
        # Retrieve the document.
        resp: Response = await self.get(entry.request)
        
        # If the document's date is not known, attempt to extract it.
        date = entry.date
        
        if not date:
            date_str = re.search(rb'Version: (\d{1,2}\.\d{1,2}\.\d{4})', resp)
            
            if date_str:
                date = date_str.group(1).decode('cp1252')
                date = datetime.strptime(date, '%d.%m.%Y').strftime('%Y-%m-%d')
                
        # Extract text from the document.
        text = rtf_to_text(resp.text, encoding='cp1252', errors='ignore')

        # Return the document.
        return make_doc(
            version_id=entry.version_id,
            type=entry.type,
            jurisdiction=entry.jurisdiction,
            source=entry.source,
            mime='application/rtf',
            date=date,
            citation=entry.title,
            url=entry.request.path,
            text=text,
        )