import urllib3
import certifi
import os
import inscriptis
import lxml
import orjsonl
import itertools
import pytz
import datetime
import orjson
import itertools
from contextlib import nullcontext

_INSCRIPTIS_CONFIG = inscriptis.model.config.ParserConfig(inscriptis.css_profiles.CSS_PROFILES['strict'])

_session = urllib3.PoolManager(cert_reqs='CERT_REQUIRED', ca_certs=certifi.where())

def get_searches():
    searches = orjsonl.load('indices/tasmanian_legislation/searches.jsonl') if os.path.exists('indices/tasmanian_legislation/searches.jsonl') else []

    return [['tasmanian_legislation', search_base] for type_, year in itertools.product({'act.reprint', 'reprint'}, range(1839, datetime.datetime.now(tz=pytz.timezone("Australia/Tasmania")).year+1)) if (search_base:=f'https://www.legislation.tas.gov.au/projectdata?ds=EnAct-BrowseDataSource&start=1&count=5000&sortField=sort.title&sortDirection=asc&expression=PrintType={type_}+AND+Year={year}') not in searches]

def get_search(search_base, lock=nullcontext()):
    if 'data' in (results:=orjson.loads(_session.request('GET', search_base + f'?+AND+PitValid=@pointInTime({datetime.datetime.now(tz=pytz.timezone("Australia/Tasmania")).strftime(r"%Y%m%d%H%M%S")})&collection=').data.decode('utf-8'))):
        documents = results['data'] if isinstance(results['data'], list) else [results['data']]

        documents = [document['id']['__value__'] for document in documents if document['repealed']['__value__'] == 'N']

        documents = [['tasmanian_legislation', f'https://www.legislation.tas.gov.au/view/whole/html/inforce/current/{document_id}'] for document_id in documents]
        
        with lock: orjsonl.append('indices/tasmanian_legislation/documents.jsonl', documents)

    with lock: orjsonl.append('indices/tasmanian_legislation/searches.jsonl', [search_base])

def get_document(url, lock=nullcontext()):
    try:
        if '<span id="view-whole">' in (data:=_session.request('GET', url).data.decode('utf-8').replace('&#150;', '&#8211;')):
            document = {
                'text' : inscriptis.Inscriptis(lxml.html.document_fromstring(data).xpath('//div[@id="fragview"]')[0], _INSCRIPTIS_CONFIG).get_text(),
                'type' : 'primary_legislation' if url.split('/')[-1].split('-')[0] == 'act' else 'secondary_legislation',
                'source' : 'tasmanian_legislation',
                'url' : url
            }

            with lock: orjsonl.append('corpus.jsonl', [document])

        with lock: orjsonl.append('indices/downloaded.jsonl', [['tasmanian_legislation', url]])

    except Exception as e:
        raise Exception(f'Error getting document from {url}.') from e