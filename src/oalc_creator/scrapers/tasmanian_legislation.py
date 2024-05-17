import re
import asyncio
import itertools

from datetime import datetime, timedelta

import pytz
import aiohttp
import lxml.html

from inscriptis.css_profiles import CSS_PROFILES
from inscriptis.html_properties import Display
from inscriptis.model.html_element import HtmlElement

from ..data import Entry, Request, Document, make_doc
from ..helpers import log, warning
from ..scraper import Scraper
from ..custom_inscriptis import CustomInscriptis, CustomParserConfig


class TasmanianLegislation(Scraper):
    """A scraper for the Tasmanian Legislation database."""
    
    def __init__(self,
                 indices_refresh_interval: bool | timedelta = None,
                 index_refresh_interval: bool | timedelta = None,
                 semaphore: asyncio.Semaphore = None,
                 session: aiohttp.ClientSession = None,
                 ) -> None:
        super().__init__(
            source='tasmanian_legislation',
            indices_refresh_interval=indices_refresh_interval,
            index_refresh_interval=index_refresh_interval,
            semaphore=semaphore,
            session=session
        )

        self._jurisdiction = 'tasmania'
        
        # Create a custom Inscriptis CSS profile.
        inscriptis_profile = CSS_PROFILES['strict'].copy()
        
        # Ensure that blockquotes are indented.
        inscriptis_profile['blockquote'] = HtmlElement(display=Display.block, padding_inline=4)
        
        # Create an Inscriptis parser config using the custom CSS profile.
        self._inscriptis_config = CustomParserConfig(inscriptis_profile)

    @log
    async def get_index_reqs(self) -> set[Request]:
        # Get the current date in Tasmania.
        pit = datetime.now(tz=pytz.timezone("Australia/Tasmania")).strftime(r"%Y%m%d%H%M%S")
        
        # NOTE Here we generate a set of search queries intended to result in the retrieval of all documents in the database that are in force at this current point in time. The queries are to an internal API. Queries are generated for all possible combinations of valid types ('act.reprint' for primary legislation and 'reprint' for secondary legislation) and years. The range of years used is from 1839 (when the earliest document in the database is dated) to the current year. The queries are sorted by title, in ascending order (ie, from A to Z). The first 5,000 results are retrieved (technically, this means that it is possible that some documents will be missed, however, this is almost certainly impossible as the number of laws in force in Tasmania at any given point in time is no where near that number).
        return {
            Request(f'https://www.legislation.tas.gov.au/projectdata?ds=EnAct-BrowseDataSource&start=1&count=5000&sortField=sort.title&sortDirection=asc&expression=PrintType={type}+AND+Year={year}?+AND+PitValid=@pointInTime({pit})&collection=')
            
            for type, year in itertools.product({'act.reprint', 'reprint'}, range(1839, datetime.now(tz=pytz.timezone("Australia/Tasmania")).year+1))
        }

    @log
    async def get_index(self, req: Request) -> set[Entry]:
        # Retrieve the index.
        resp = (await self.get(req)).json
        
        # If there are no results, return an empty set.
        if 'data' not in resp:
            return set()
        
        # If there is a single result, place it in a list.
        results = resp['data'] if isinstance(resp['data'], list) else [resp['data']]
        
        # Determine the document type of the index.
        type = 'primary_legislation' if 'PrintType=act.reprint' in req.path else 'secondary_legislation'
        
        # Create entries, filtering out repealed documents in the process.
        return {
            Entry(
                request=Request(f"""https://www.legislation.tas.gov.au/view/whole/html/inforce/current/{result["id"]["__value__"]}"""),
                version_id=f'{result["publication.date"][:10]}/{result["id"]["__value__"]}',
                source=self.source,
                type=type,
                jurisdiction=self._jurisdiction,
                title=result['title']['__value__'],
            )
            
            for result in results if result['repealed']['__value__'] == 'N'
        }

    @log
    async def get_doc(self, entry: Entry) -> Document | None:
        # Retrieve the document.  
        resp = (await self.get(entry.request))
        
        # If the document is missing, then this may be because it is not possible to find a version of the document at the given point in time (this seems to be a bug in the Tasmanian Legislation database. For an example, see https://www.legislation.tas.gov.au/view/whole/html/inforce/2018-06-21/sr-2018-030). In such a case, we search for the latest version of the document and update the url.
        if resp.status == 404:
            # Update the url to the latest version of the document.
            url = re.sub(r'/\d{4}-\d{2}-\d{2}/', '/current/', entry.request.path)
            
            # Retrieve the latest version of the document.
            resp = await self.get(url)
        
        else:
            url = entry.request.path
        
        # Extract text from the response.
        resp = resp.text
    
        # If the response contains the substring 'Content Not Found.', then return `None` as there is a bug in the Tasmanian Legislation database preventing the retrieval of certain documents (see, eg, https://www.legislation.tas.gov.au/view/whole/html/inforce/current/act-2022-033).
        if 'Content Not Found.' in resp.text:
            warning(f"Unable to retrieve document from {entry.request.path}. 'Content Not Found.' encountered in the response, indicating that the document is missing from the Tasmanian Legislation database. Returning `None`.")
            return
        
        # Replace the non-standard HTML character entity &#150; with the standard HTML character entity &#8211; (en dash).
        resp = resp.replace('&#150;', '&#8211;')
        
        # Create an etree from the response.
        etree = lxml.html.fromstring(resp)

        # Select the element containing the text of the document.
        text_elm = etree.xpath('//div[@id="fragview"]')[0]
        
        # Convert the tags of titles and headings from `blockquote` to `h1` to prevent them from being indented.
        for elm in text_elm.xpath("//blockquote[contains(@class, 'HeadingParagraph')]"): elm.tag = 'h1'
        
        # Remove footnotes (they are supposed to be hidden by Javascript).
        for elm in text_elm.xpath("//*[contains(concat(' ', normalize-space(@class), ' '), ' view-history-note ')]"): elm.drop_tree()
        
        # Extract the text of the document.
        text = CustomInscriptis(text_elm, self._inscriptis_config).get_text()
        
        # Return the document.
        return make_doc(
            version_id=entry.version_id,
            type=entry.type,
            jurisdiction=entry.jurisdiction,
            source=entry.source,
            citation=entry.title,
            url=url,
            text=text
        )