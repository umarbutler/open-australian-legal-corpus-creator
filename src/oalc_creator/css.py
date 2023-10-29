from contextlib import suppress

from inscriptis.html_properties import Display
from inscriptis.model.attribute import Attribute
from inscriptis.model.css import CssParse
from inscriptis.model.html_element import HtmlElement


class CustomCssParse(CssParse):
    """A custom Inscriptis CSS parser for the Open Australian Legal Corpus."""
    
    # Override the default CSS parser for the `style` attribute.
    @staticmethod
    def attr_style(style_attribute: str, html_element: HtmlElement) -> None:
        for style_directive in style_attribute.lower().split(';'):
            if ':' not in style_directive:
                continue
            key, value = (s.strip() for s in style_directive.split(':', 1))

            try:
                # Reference the custom CSS parser instead of the default CSS parser.
                apply_style = getattr(CustomCssParse, 'attr_'
                                      + key.replace('-webkit-', '')
                                      .replace('-', '_'))
                apply_style(value, html_element)
            except AttributeError:
                pass
    
    # Create a method for padding elements with left margins.
    @staticmethod
    def attr_margin_left(value: str, html_element: HtmlElement) -> None:
        """Apply the given left margin."""
        
        with suppress(ValueError):
            html_element.padding_inline += CssParse._get_em(value)

    # Override the default method for applying the `padding-left` property.
    @staticmethod
    def attr_padding_left(value: str, html_element: HtmlElement):
        with suppress(ValueError):
            # Ensure that the padding is added to whatever padding is already present rather than replacing it as the default method does.
            html_element.padding_inline += CssParse._get_em(value)
    
    # Create a method for parsing the `class` attribute.
    @staticmethod
    def attr_class(classes: str, html_element: HtmlElement) -> None:
        # If the element is not a `p`, `div` or `li` tag or if it has no classes, return.
        if html_element.tag not in {'p', 'div', 'li'} or not classes:
            return
        
        classes = classes.split(' ')
        
        # If the element possesses a class that contains the substrings 'Head', 'Title' or 'heading', then treat it as a heading.
        for class_ in classes:
            if any(substring in class_ for substring in {'Head', 'Title', 'heading'}):
                    
                # Set the element's display to block.
                html_element.display = Display.block
                
                # Add a newline before the heading.
                html_element.margin_before = 1
                
                # Ensure that a newline is not added after the heading.
                html_element.margin_after = 0
                
                break

class CustomAttribute(Attribute):
    """A custom Inscriptis attribute for the Open Australian Legal Corpus."""
    
    def __init__(self) -> None:
        super().__init__()
        
        # Override the default attribute mapping to use the custom CSS parser instead.
        self.attribute_mapping = {
            'style': CustomCssParse.attr_style,
            'align': CustomCssParse.attr_horizontal_align,
            'valign': CustomCssParse.attr_vertical_align,
            'class' : CustomCssParse.attr_class,
        }