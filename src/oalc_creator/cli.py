import asyncio
import os

import click
import rich
from platformdirs import user_data_dir
from rich.traceback import install

from .creator import SOURCES, Creator

# Use `uvloop` instead of `asyncio` if it's available.
try:
    from uvloop import run as async_run
except ImportError:
    from asyncio import run as async_run

# Setup traceback pretty printing with `rich` (suppressing full traceback for exceptions raised by `rich`, `click` and `asyncio`).
install(suppress=[rich, click, asyncio])

@click.command('mkoalc', context_settings={'help_option_names': ['-h', '--help']})
@click.version_option()
@click.option(
    '-s', '--sources',
    default=','.join(SOURCES.keys()),
    show_default=True,
    help='The names of the sources to be scraped, delimited by commas.',
)
@click.option(
    '-o', '--output',
    default=os.path.join(os.getcwd(), 'corpus.jsonl'),
    show_default=True,
    help='The path to the Corpus.',
)
@click.option(
    '-d', '--data_dir',
    default=os.path.join(os.getcwd(), user_data_dir('Open Australian Legal Corpus', 'Umar Butler')),
    show_default=True,
    help='The directory in which Corpus data should be stored.',
)
def create(sources, output, data_dir):
    """The creator of the Open Australian Legal Corpus."""
    
    # Convert `sources` to a list of source names.
    sources = sources.split(',')
    
    # Create the Corpus.
    async_run(Creator(sources=sources, corpus_path=output, data_dir=data_dir).create())

if __name__ == '__main__':
    create()