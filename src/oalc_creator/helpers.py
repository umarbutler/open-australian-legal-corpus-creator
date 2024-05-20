import asyncio

from typing import Any, Callable
from textwrap import dedent

import orjson
import msgspec

from rich.console import Console
from alive_progress import alive_bar

console = Console()

def log(func: Callable) -> Callable:
    """Log any arguments passed to a function when an exception arises."""
    
    ERROR_MESSAGE = """
    Function: {func.__name__}
    Error message: {e}
    Arguments: {args}
    Keyword arguments: {kwargs}
    """
    ERROR_MESSAGE = dedent(ERROR_MESSAGE)
    
    def sync_wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        
        except Exception as e:
            warning(ERROR_MESSAGE.format(
                func=func,
                e=e,
                args=args,
                kwargs=kwargs,
            ))
            
            raise e
    
    async def async_wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        
        except Exception as e:
            warning(ERROR_MESSAGE.format(
                func=func,
                e=e,
                args=args,
                kwargs=kwargs,
            ))
            
            raise e
    
    return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

def save_json(path: str, content: Any, encoder: Callable[[Any], bytes] = msgspec.json.encode) -> None:
    """Save content as a json file."""
    
    with open(path, 'wb') as writer:
        writer.write(encoder(content))

def load_json(path: str, decoder: Callable[[bytes], Any] = orjson.loads) -> Any:
    """Load a json file."""
    
    with open(path, 'rb') as reader:
        return decoder(reader.read())

def load_jsonl(path: str, decoder: Callable[[bytes], Any] = orjson.loads) -> list:
    """Load a jsonl file."""
    
    with open(path, 'rb') as file:
        return [decoder(json) for json in file]

def save_jsonl(path: str, content: list, encoder: Callable[[Any], bytes] = msgspec.json.encode) -> None:
    """Save a list of objects as a jsonl file."""
    
    with open(path, 'wb') as file:
        for entry in content:
            file.write(encoder(entry))
            file.write(b'\n')

async def alive_gather(*funcs):
    """`asyncio.gather` with a progress bar from `alive_progress`."""
    
    # Initalise the progress bar.
    with alive_bar(len(funcs)) as bar:
        # Create a wrapper function to update the progress bar and preserve the order of the results.
        async def wrapper(i, func):
            # Wait for the result.
            res = await func
            
            # Update the progress bar.
            bar()
            
            # Return the index and result.
            return i, res
        
        # Wrap the functions and wait for the results.
        res = [await func for func in asyncio.as_completed([wrapper(i, func) for i, func in enumerate(funcs)])]
        
        # Return the results sorted by index.
        return [r for _, r in sorted(res)]

def alive_as_completed(funcs):
    """`asyncio.as_completed` with a progress bar from `alive_progress`."""
    
    # Initalise the progress bar.
    with alive_bar(len(funcs)) as bar:
        # Create a wrapper function to update the progress bar.
        async def wrapper(func):
            # Wait for the result.
            res = await func
            
            # Update the progress bar.
            bar()
            
            # Return the result.
            return res
        
        # Wrap the functions and yield the results.
        for func in asyncio.as_completed([wrapper(func) for func in funcs]):
            yield func

def warning(message: str) -> None:
    """Log a warning message."""
    
    console.print(f'\n:warning-emoji:  {message}', style='orange1 bold', emoji=True, soft_wrap=True)