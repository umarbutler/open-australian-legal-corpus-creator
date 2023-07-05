import urllib3
import certifi
import os
import inscriptis
import lxml
import orjsonl
import pytz
import datetime
import re
from contextlib import nullcontext

_SEARCH_BASES = (
    'https://www.legislation.qld.gov.au/tables/pubactsif?pit=',
    'https://www.legislation.qld.gov.au/tables/siif?pit=',
    'https://www.legislation.qld.gov.au/tables/bills?dstart=03/11/1992&dend='
)

_INSCRIPTIS_CONFIG = inscriptis.css_profiles.CSS_PROFILES['strict'].copy()
_INSCRIPTIS_CONFIG['span'] = inscriptis.model.html_element.HtmlElement(display=inscriptis.html_properties.Display.inline, prefix=' ', suffix=' ', limit_whitespace_affixes=True)
_INSCRIPTIS_CONFIG = inscriptis.model.config.ParserConfig(_INSCRIPTIS_CONFIG)

_session = urllib3.PoolManager(cert_reqs='CERT_REQUIRED', ca_certs=certifi.where())

def get_searches():
    searches = orjsonl.load('indices/queensland_legislation/searches.jsonl') if os.path.exists('indices/queensland_legislation/searches.jsonl') else []

    return [['queensland_legislation', search_base] for search_base in _SEARCH_BASES if search_base not in searches]

def get_search(search_base, lock=nullcontext()):
    documents = [['queensland_legislation', f'https://www.legislation.qld.gov.au/view/whole{document_path}'] for document_path in re.findall(r'<a(?: class="indent")? href="\/view([^"]+)">', _session.request('GET', f'{search_base}{datetime.datetime.now(tz=pytz.timezone("Australia/Queensland")).strftime(r"%d/%m/%Y")}&sort=chron&renderas=html&generate=').data.decode('utf-8'))]

    with lock:
        orjsonl.append('indices/queensland_legislation/documents.jsonl', documents)
        orjsonl.append('indices/queensland_legislation/searches.jsonl', [search_base])

def get_document(url, lock=nullcontext()):
    try:
        if '<span id="view-whole">' in (data:=_session.request('GET', url).data.decode('utf-8')):
            match url.split('/')[-1].split('-')[0]:
                case 'act':
                    type_ = 'primary_legislation'
                case 'sl':
                    type_ = 'secondary_legislation'
                case 'bill':
                    type_ = 'bill'
            
            etree = lxml.html.document_fromstring(data)

            citation = re.sub(r' No \d+$', '', etree.xpath('//h1[@class="title"]')[0].text)
            citation = ' '.join(f'{citation} (Qld)'.split())
            
            document = {
                'text' : inscriptis.Inscriptis(etree.xpath('//div[@id="fragview"]')[0], _INSCRIPTIS_CONFIG).get_text(),
                'type' : type_,
                'jurisdiction' : 'queensland',
                'source' : 'queensland_legislation',
                'citation' : citation,
                'url' : url
            }
            
            with lock: orjsonl.append('corpus.jsonl', [document])

        with lock: orjsonl.append('indices/downloaded.jsonl', [['queensland_legislation', url]])
    
    except Exception as e:
        raise Exception(f'Error getting document from {url}.') from e