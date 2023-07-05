from contextlib import nullcontext
from bs4 import BeautifulSoup
import certifi
import urllib3
import inscriptis
import lxml
import orjsonl
import os
import re

_SEARCHES = {
    'https://www.legislation.gov.au/Browse/ByTitle/Constitution/InForce' : 'primary_legislation',
    'https://www.legislation.gov.au/Browse/Results/ByRegDate/Acts/InForce/2/0/0/all' : 'primary_legislation',
    'https://www.legislation.gov.au/Browse/Results/ByRegDate/NorfolkIslandLegislation/InForce/2/0' : 'regex',
    'https://www.legislation.gov.au/Browse/Results/ByRegDate/LegislativeInstruments/InForce/1/0/0/all' : 'secondary_legislation',
    'https://www.legislation.gov.au/Browse/Results/ByRegDate/LegislativeInstruments/InForce/2/0/0/all' : 'secondary_legislation',
    'https://www.legislation.gov.au/Browse/Results/ByRegDate/NotifiableInstruments/InForce/2/0/0/all' : 'secondary_legislation',
    'https://www.legislation.gov.au/Browse/ByRegDate/AdministrativeArrangementsOrders/InForce/0/0/' : 'secondary_legislation',
    'https://www.legislation.gov.au/Browse/Results/ByRegDate/PrerogativeInstruments/InForce/2/0' : 'secondary_legislation',
    'https://www.legislation.gov.au/Browse/Results/ByYearNumber/Bills/AsMade/1/0/0' : 'bill',
    'https://www.legislation.gov.au/Browse/Results/ByYearNumber/Bills/AsMade/2/0/0' : 'bill',
}

_INSCRIPTIS_CONFIG = inscriptis.model.config.ParserConfig(inscriptis.css_profiles.CSS_PROFILES['strict'])

urllib3.util.ssl_.DEFAULT_CIPHERS = 'ALL:@SECLEVEL=1'
_session = urllib3.PoolManager(cert_reqs='CERT_REQUIRED', ca_certs=certifi.where())

def get_searches():
    searches_completed = [search[0] for search in (orjsonl.load('indices/federal_register_of_legislation/searches.jsonl') if os.path.exists('indices/federal_register_of_legislation/searches.jsonl') else [])]
    searches = []

    for search in _SEARCHES.keys():
        soup = BeautifulSoup(_session.request('GET', search).data.decode('utf-8'), features='lxml')

        data = {
            '__EVENTTARGET': 'ctl00$MainContent$gridBrowse',
            '__EVENTARGUMENT': 'FireCommand:ctl00$MainContent$gridBrowse$ctl00;PageSize;100',
            '__VIEWSTATE': soup.find(id='__VIEWSTATE')['value'],
            '__VIEWSTATEGENERATOR': soup.find(id='__VIEWSTATEGENERATOR')['value'],
            '__VIEWSTATEENCRYPTED': '',
            '__PREVIOUSPAGE': soup.find(id='__PREVIOUSPAGE')['value'],
            '__EVENTVALIDATION': soup.find(id='__EVENTVALIDATION')['value'],
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

        soup = BeautifulSoup(_session.request('POST', search, fields=data).data.decode('utf-8'), features='lxml')

        data['__EVENTARGUMENT'] = ''
        data['__VIEWSTATE'] = soup.find(id='__VIEWSTATE')['value']
        data['__EVENTVALIDATION'] = soup.find(id='__EVENTVALIDATION')['value']
        data['ctl00_MainContent_gridBrowse_ctl00_ctl02_ctl00_PageSizeComboBox_ClientState'] = ''
        data['ctl00$MainContent$gridBrowse$ctl00$ctl03$ctl01$PageSizeComboBox'] = '100'

        pages = int(soup.find(class_='rgWrap rgInfoPart').find_all('strong')[1].text)
        page_code_number = 3

        for page in range(1, pages + 1):
            page_code_number += 2
            page_code = f'0{page_code_number}' if len(str(page_code_number)) == 1 else page_code_number

            data['__EVENTTARGET'] = f'ctl00$MainContent$gridBrowse$ctl00$ctl02$ctl00$ctl{page_code}'

            searches.append(['federal_register_of_legislation', [f'{search}#{page}', dict(data)]])

            if page % 10 == 1 and page not in {1, pages}:
                soup = BeautifulSoup(_session.request('POST', search, fields=data).data.decode('utf-8'), features='lxml')
                data['__VIEWSTATE'] = soup.find(id='__VIEWSTATE')['value']
                data['__EVENTVALIDATION'] = soup.find(id='__EVENTVALIDATION')['value']

                if (pages-page < 9):
                    page_code_number = 23 - (2 * (pages - page - 1))
                    continue

                page_code_number = 7
    
    return [search for search in searches if search[1][0] not in searches_completed]

def get_search(search, lock=nullcontext()):
    documents = [['federal_register_of_legislation', [_SEARCHES[search[0].split('#')[0]], f'https://www.legislation.gov.au/Details/{id_}']] for id_ in re.findall('<span id="ctl00_MainContent_gridBrowse_ctl00_ctl\d+_lblComlawId">(.+)<\/span>', _session.request('POST', search[0], fields=search[1]).data.decode('utf-8'))]

    with lock:
        orjsonl.append('indices/federal_register_of_legislation/documents.jsonl', documents)
        orjsonl.append('indices/federal_register_of_legislation/searches.jsonl', [search])

def get_document(type_and_url, lock=nullcontext()):
    try:
        response = _session.request('GET', type_and_url[1]).data.decode('utf-8')

        # Ignore index errors raised by attempting to parse pages that do not contain text but instead link to PDFs.
        try:
            etree = lxml.html.document_fromstring(response)
            text = inscriptis.Inscriptis(etree.xpath('//div[@id="MainContent_pnlHtmlControls"]')[0], _INSCRIPTIS_CONFIG).get_text()

        except IndexError:
            with lock: orjsonl.append('indices/downloaded.jsonl', [['federal_register_of_legislation', type_and_url]])
            return

        citation = ' '.join(etree.xpath("//meta[@name='DC.Title']/@content")[0].split())

        if type_and_url[0] == 'regex':
            if re.search('<meta name="DC.Title" content="[\w\d\s]* Act \d{4} \(NI\)\s*"\s?\/>', response):
                type_ = 'primary_legislation' # Create a new `type_` variable rather than overwriting `type_and_url[0]` to ensure that entires added to `indices/downloaded.jsonl` match with their originals in `indices/federal_register_of_legislation/documents.jsonl`.
            else:
                type_ = 'secondary_legislation'
        else:
            type_ = type_and_url[0]
            citation += ' (Cth)'

        document = {
            'text' : text,
            'type' : type_,
            'source' : 'federal_register_of_legislation',
            'citation' : citation,
            'url' : type_and_url[1],
        }

        with lock:
            orjsonl.append('corpus.jsonl', [document])
            orjsonl.append('indices/downloaded.jsonl', [['federal_register_of_legislation', type_and_url]])

    except Exception as e:
        raise Exception(f'Error getting document from {type_and_url[1]}.') from e