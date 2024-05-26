import io

import mammoth


def dummy_image_converter(_) -> dict:
    """A dummy image converter function that returns an empty dict."""
    
    return {}

def docx2html(doc: io.BytesIO) -> str:
    """Convert a Microsoft Word document into HTML."""
    
    return mammoth.convert_to_html(doc, convert_image = dummy_image_converter)