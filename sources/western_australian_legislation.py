import urllib3
import certifi
import os
import re
import inscriptis
import lxml
import orjsonl
import string
import itertools
from contextlib import nullcontext

_INSCRIPTIS_CONFIG = inscriptis.model.config.ParserConfig(inscriptis.css_profiles.CSS_PROFILES['strict'])

_session = urllib3.PoolManager(cert_reqs='CERT_REQUIRED', ca_certs=certifi.where())

def get_searches():
    searches = orjsonl.load('indices/western_australian_legislation/searches.jsonl') if os.path.exists('indices/western_australian_legislation/searches.jsonl') else []

    return [['western_australian_legislation', list_url] for type_, letter in itertools.product({'acts', 'subs'}, string.ascii_lowercase) if (list_url:=f'https://www.legislation.wa.gov.au/legislation/statutes.nsf/{type_}if_{letter}.html') not in searches]

def get_search(index_url, lock=nullcontext()):
    documents = [['western_australian_legislation', ['primary_legislation' if 'acts' in index_url else 'secondary_legislation', f'https://www.legislation.wa.gov.au/legislation/statutes.nsf/RedirectURL?OpenAgent&query={document_id}.htm']] for document_id in re.findall(r"""<a href='RedirectURL\?OpenAgent&amp;query=([^']*)\.htm' class""", _session.request('GET', index_url).data.decode('utf-8'))]

    with lock:
        if documents: orjsonl.append('indices/western_australian_legislation/documents.jsonl', documents)
        orjsonl.append('indices/western_australian_legislation/searches.jsonl', [index_url])

def get_document(type_and_url, lock=nullcontext()):
    try:
        etree = lxml.html.document_fromstring(_session.request('GET', type_and_url[1]).data.decode('utf-8'))
        
        citation = etree.xpath('//span[@class="NameofActReg-H"]')[0].text_content().replace('\xa0', ' ')
        citation = ' '.join(f'{citation} (WA)')

        document = {
            'text' : inscriptis.Inscriptis(etree, _INSCRIPTIS_CONFIG).get_text(),
            'type' : type_and_url[0],
            'source' : 'western_australian_legislation',
            'citation' : citation,
            'url' : type_and_url[1]
        }

        with lock:
            orjsonl.append('corpus.jsonl', [document])
            orjsonl.append('indices/downloaded.jsonl', [['western_australian_legislation', type_and_url]])

    except Exception as e:
        raise Exception(f'Error getting document from {type_and_url[1]}.') from e