import os
import orjsonl
import glob
import striprtf.striprtf
from contextlib import nullcontext

_SEARCHES = (
    'imports/south_australian_legislation/A',
    'imports/south_australian_legislation/P',
    'imports/south_australian_legislation/POL',
    'imports/south_australian_legislation/R',
)

def get_searches():
    searches = orjsonl.load('indices/south_australian_legislation/searches.jsonl') if os.path.exists('indices/south_australian_legislation/searches.jsonl') else []

    return [['south_australian_legislation', search] for search in _SEARCHES if search not in searches]

def get_search(search_path, lock=nullcontext()):
    documents = [['south_australian_legislation', file.replace('\\', '/')] for file in glob.glob(f'{search_path}\**\*.rtf', recursive=True)]

    with lock:
        orjsonl.append('indices/south_australian_legislation/documents.jsonl', documents)
        orjsonl.append('indices/south_australian_legislation/searches.jsonl', [search_path])

def get_document(path, lock=nullcontext()):
    try:
        document = {
            'text' : striprtf.striprtf.rtf_to_text(open(path, 'r', encoding='cp1252').read(), encoding='cp1252', errors='ignore'),
            'type' : 'primary_legislation' if '/A/' in path else 'secondary_legislation',
            'source' : 'south_australian_legislation',
            'citation' : ' '.join(f"{path.split('south_australian_legislation')[1].split('/')[2]} (SA)".split()),
            'url' : f'https://www.legislation.sa.gov.au/__legislation/lz/c{path.split("south_australian_legislation")[1].lower()}'.replace(' ', '%20')
        }
        
        with lock:
            orjsonl.append('corpus.jsonl', [document])
            orjsonl.append('indices/downloaded.jsonl', [['south_australian_legislation', path]])

    except Exception as e:
        raise Exception(f'Error getting document from {path}.') from e