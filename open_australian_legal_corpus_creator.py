import sources.federal_court_of_australia as federal_court_of_australia
import sources.federal_register_of_legislation as federal_register_of_legislation
import sources.nsw_legislation as nsw_legislation
import sources.queensland_legislation as queensland_legislation
import sources.south_australian_legislation as south_australian_legislation
import sources.tasmanian_legislation as tasmanian_legislation
import sources.western_australian_legislation as western_australian_legislation
import random
import orjsonl
import os
from tqdm.contrib.concurrent import thread_map
from threading import Lock

SOURCES = {
    'federal_register_of_legislation' : federal_register_of_legislation,
    'federal_court_of_australia' : federal_court_of_australia,
    'nsw_legislation' : nsw_legislation,
    'queensland_legislation' : queensland_legislation,
    'south_australian_legislation' : south_australian_legislation,
    'tasmanian_legislation' : tasmanian_legislation,
    'western_australian_legislation' : western_australian_legislation,
}

LOCK = Lock()

if not os.path.exists('indices'):
    os.mkdir('indices')

for source in SOURCES:
    if not os.path.exists(f'indices/{source}'):
        os.mkdir(f'indices/{source}')

print('Determining what pages and folders from each source must be searched in order to create an index of documents to be included in the Corpus.')
searches = [search for searches_ in thread_map(lambda module: module.get_searches(), SOURCES.values()) for search in searches_]
random.shuffle(searches)

print('\nSearching pages and folders from each source for documents to be included in the Corpus.')
if searches: thread_map(lambda search: SOURCES[search[0]].get_search(search[1], LOCK), searches)
documents_already_included = orjsonl.load('indices/downloaded.jsonl') if os.path.exists('indices/downloaded.jsonl') else []
documents = [document for documents_ in [orjsonl.load(f'indices/{source}/documents.jsonl') for source in SOURCES] for document in documents_ if document not in documents_already_included]

unique_documents = []

for document in documents:
    if document not in unique_documents:
        unique_documents.append(document)

documents = unique_documents
random.shuffle(documents)

print('\nAdding indexed documents to the Corpus.')
thread_map(lambda document: SOURCES[document[0]].get_document(document[1], LOCK), documents)