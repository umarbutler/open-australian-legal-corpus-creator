import io
import asyncio
import multiprocessing

from concurrent.futures import ThreadPoolExecutor

import pypdfium2
import tesserocr

from .helpers import batch_generator


async def pdf2txt(
    pdf: io.BytesIO,
    batch_size: int = None,
    thread_pool_executor: ThreadPoolExecutor = None,
) -> str:
    """OCR a PDF."""
    
    # Initialise the thread pool executor if necessary.
    if thread_pool_executor is None:
        thread_pool_executor = ThreadPoolExecutor(multiprocessing.cpu_count() - 1 or 1)
    
    # Set the batch size if necessary.
    if batch_size is None:
        batch_size = thread_pool_executor._max_workers * 5
    
    # Load the PDF.
    pdf = pypdfium2.PdfDocument(pdf)
   
    # OCR every page of the PDF in batches.
    # NOTE We using batching to avoid going OOM when we convert the pages into images.
    txt = []
    
    for pages in batch_generator(pdf, batch_size):
        # Convert the pages into images.
        imgs = [pg.render(scale = 3).to_pil() for pg in pages]
        
        # OCR the pages.
        loop = asyncio.get_event_loop()
        txt.extend(await asyncio.gather(*[loop.run_in_executor(thread_pool_executor, tesserocr.image_to_text, img) for img in imgs]))
    
    return '\n'.join(txt)