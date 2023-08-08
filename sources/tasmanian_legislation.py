import os
import inscriptis
import lxml
import orjsonl
import itertools
import pytz
import datetime
import orjson
import itertools
import re
from contextlib import nullcontext
from requests import get

_INSCRIPTIS_CONFIG = inscriptis.model.config.ParserConfig(inscriptis.css_profiles.CSS_PROFILES['strict'])

def get_searches():
    searches = orjsonl.load('indices/tasmanian_legislation/searches.jsonl') if os.path.exists('indices/tasmanian_legislation/searches.jsonl') else []

    return [['tasmanian_legislation', search_base] for type_, year in itertools.product({'act.reprint', 'reprint'}, range(1839, datetime.datetime.now(tz=pytz.timezone("Australia/Tasmania")).year+1)) if (search_base:=f'https://www.legislation.tas.gov.au/projectdata?ds=EnAct-BrowseDataSource&start=1&count=5000&sortField=sort.title&sortDirection=asc&expression=PrintType={type_}+AND+Year={year}') not in searches]

def get_search(search_base, lock=nullcontext()):
    if 'data' in (results:=orjson.loads(get(search_base + f'?+AND+PitValid=@pointInTime({datetime.datetime.now(tz=pytz.timezone("Australia/Tasmania")).strftime(r"%Y%m%d%H%M%S")})&collection=').text)):
        documents = results['data'] if isinstance(results['data'], list) else [results['data']]

        documents = [document['id']['__value__'] for document in documents if document['repealed']['__value__'] == 'N']

        documents = [['tasmanian_legislation', f'https://www.legislation.tas.gov.au/view/whole/html/inforce/current/{document_id}'] for document_id in documents]
        
        with lock: orjsonl.append('indices/tasmanian_legislation/documents.jsonl', documents)

    with lock: orjsonl.append('indices/tasmanian_legislation/searches.jsonl', [search_base])

def get_document(url, lock=nullcontext()):
    try:
        if '<span id="view-whole">' in (data:=get(url).text.replace('&#150;', '&#8211;')):
            etree = lxml.html.document_fromstring(data)

            citation = re.sub(r' No \d+$', '', etree.xpath('//h1[@class="title"]')[0].text)
            citation = ' '.join(f'{citation} (Tas)'.split())

            document = {
                'text' : inscriptis.Inscriptis(etree.xpath('//div[@id="fragview"]')[0], _INSCRIPTIS_CONFIG).get_text(),
                'type' : 'primary_legislation' if url.split('/')[-1].split('-')[0] == 'act' else 'secondary_legislation',
                'jurisdiction' : 'tasmania',
                'source' : 'tasmanian_legislation',
                'citation' : citation,
                'url' : url
            }

            with lock: orjsonl.append('corpus.jsonl', [document])

        with lock: orjsonl.append('indices/downloaded.jsonl', [['tasmanian_legislation', url]])

    except Exception as e:
        raise Exception(f'Error getting document from {url}.') from e