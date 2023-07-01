import urllib3
import certifi
import os
import inscriptis
import lxml
import orjsonl
import pytz
import datetime
import re
from contextlib import nullcontext, suppress

_SEARCH_BASES = (
    'https://legislation.nsw.gov.au/tables/pubactsif',
    'https://legislation.nsw.gov.au/tables/pvtactsif',
    'https://legislation.nsw.gov.au/tables/siif',
    'https://legislation.nsw.gov.au/tables/epiif',
)

_INSCRIPTIS_CONFIG = inscriptis.model.config.ParserConfig(inscriptis.css_profiles.CSS_PROFILES['strict'])

_session = urllib3.PoolManager(cert_reqs='CERT_REQUIRED', ca_certs=certifi.where())

def get_searches():
    searches = orjsonl.load('indices/nsw_legislation/searches.jsonl') if os.path.exists('indices/nsw_legislation/searches.jsonl') else []

    return [['nsw_legislation', search_base] for search_base in _SEARCH_BASES if search_base not in searches]

def get_search(search_base, lock=nullcontext()):
    documents = [['nsw_legislation', f'https://www.legislation.nsw.gov.au/view/whole{document_path}'] for document_path in re.findall(r'<a(?: class="indent")? href="\/view(\/html\/[^"]+)">', _session.request('GET', f'{search_base}?pit={datetime.datetime.now(tz=pytz.timezone("Australia/NSW")).strftime(r"%d/%m/%Y")}&sort=chron&renderas=html&generate=').data.decode('utf-8'))] 

    with lock:
        orjsonl.append('indices/nsw_legislation/documents.jsonl', documents)
        orjsonl.append('indices/nsw_legislation/searches.jsonl', [search_base])

def get_document(url, lock=nullcontext()):
    try:
    # Ignore unicode decode errors raised by attempts to parse PDF files as HTML (unfortunately, it is not possible to exclude PDFs from the index as NSW Legislation does not use file extensions: see, eg, https://legislation.nsw.gov.au/view/whole/html/inforce/current/epi-2018-0764). Also ignore index errors raised by attempts to scrape documents that, for whatever reason, do not exist (see, eg, https://legislation.nsw.gov.au/view/whole/html/inforce/current/sl-2020-0456).
        with suppress(UnicodeDecodeError, IndexError):
            etree = lxml.html.document_fromstring(_session.request('GET', url).data.decode('utf-8'))

            frag_toolbar = etree.xpath('//div[@id="fragToolbar"]')[0]
            frag_toolbar.getparent().remove(frag_toolbar)

            nav_result = etree.xpath('//div[@class="nav-result display-none"]')[0]
            nav_result.getparent().remove(nav_result)

            text_element = etree.xpath('//div[@id="frag-col"]')

            citation = re.sub(r' No \d+$', '', etree.xpath('//h1[@class="title"]')[0].text)
            citation = f'{citation} (NSW)'

            document = {
                    'text' : inscriptis.Inscriptis(text_element[0], _INSCRIPTIS_CONFIG).get_text(),
                    'type' : 'primary_legislation' if '/act-' in url else 'secondary_legislation',
                    'source' : 'nsw_legislation',
                    'citation' : citation,
                    'url' : url
                }

            with lock: orjsonl.append('corpus.jsonl', [document])

        with lock: orjsonl.append('indices/downloaded.jsonl', [['nsw_legislation', url]])
    except Exception as e:
        raise Exception(f'Error getting document from {url}.') from e