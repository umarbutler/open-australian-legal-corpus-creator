import random
import asyncio

from abc import ABC, abstractmethod
from typing import override
from datetime import timedelta
from contextlib import nullcontext

import aiohttp
import aiohttp.client_exceptions
from torch import Value

from .data import Entry, Request, Document, Response
from .helpers import log


class Scraper(ABC):
    """A scraper."""
    
    def __init__(self,
                 source: str,
                 indices_refresh_interval: timedelta | bool = None,
                 index_refresh_interval: timedelta | bool = None,
                 semaphore: asyncio.Semaphore = None,
                 session: aiohttp.ClientSession = None,
                 retry_exceptions: tuple[type[BaseException]] = (
                        asyncio.TimeoutError,
                        aiohttp.ClientConnectorError,
                        aiohttp.client_exceptions.ServerDisconnectedError,
                        aiohttp.client_exceptions.ClientOSError,
                        aiohttp.client_exceptions.ClientPayloadError,
                        aiohttp.client_exceptions.ClientResponseError,
                 ),
                 retry_statuses: tuple[int] = (429,),
                 ) -> None:
        """Initialise a scraper.
        
        Args:
            source (str): The name of the source.
            indices_refresh_interval (timedelta | bool, optional): The interval at which to refresh document indices or `True` if document indices must be refreshed. Defaults to 1 day.
            index_refresh_interval (timedelta | bool, optional): The interval at which to refresh the document index or `True` if the document index must be refreshed. Defaults to 1 day.
            semaphore (asyncio.Semaphore, optional): A semaphore for limiting the number of concurrent requests. Defaults to a semaphore with a limit of 30.
            session (aiohttp.ClientSession, optional): An `aiohttp` session to use for making requests. Defaults to `None`, thereby creating a new session for every request.
            retry_exceptions (tuple[type[BaseException]], optional): A tuple of exceptions to retry on. Defaults to a tuple of `asyncio.TimeoutError`, `aiohttp.ClientConnectorError`, `aiohttp.client_exceptions.ServerDisconnectedError`, `aiohttp.client_exceptions.ClientOSError`, `aiohttp.client_exceptions.ClientPayloadError`, and `aiohttp.client_exceptions.ClientResponseError`.
            retry_statuses (tuple[int], optional): A tuple of statuses to retry on. Defaults to an empty tuple."""
        
        self.source: str = source
        """The name of the source."""
        
        self.indices_refresh_interval: timedelta | bool = indices_refresh_interval or timedelta(days=1)
        """The interval at which to refresh document indices or `True` if document indices must be refreshed."""
        
        self.index_refresh_interval: timedelta | bool = index_refresh_interval or timedelta(days=1)
        """The interval at which to refresh the document index or `True` if the document index must be refreshed."""
        
        self.semaphore: asyncio.Semaphore = semaphore or asyncio.Semaphore(30)
        """A semaphore for limiting the number of concurrent requests."""
        
        self.session: aiohttp.ClientSession = session
        """An `aiohttp` session to use for making requests."""
        
        self.retry_exceptions: tuple[type[BaseException]] = retry_exceptions
        """A tuple of exceptions to retry on."""
        
        self.retry_statuses: tuple[int] = retry_statuses
        """A tuple of statuses to retry on."""
        
        self.stop_after_waiting: int = 15 * 60
        """The maximum number of seconds that can be waited between retries before raising an exception."""
        
        self.max_wait: int = 2.5 * 60
        """The maximum number of seconds to wait between retries."""
        
        self.wait_base: int = 1.25
        """The exponential backoff base."""
    
    @abstractmethod
    async def get_index_reqs(self) -> set[Request]:
        """Retrieve a set of requests for document indices."""
        pass
    
    @abstractmethod
    async def get_index(self, req: Request) -> set[Entry]:
        """Retrieve a set of entries from a document index."""
        pass
    
    @override
    def _get_entry(self, *args, **kwargs) -> Entry | None:
        """Retrieve an entry from an element of a document index."""
        pass
    
    @abstractmethod
    async def _get_doc(self, entry: Entry) -> Document | None:
        """Retrieve a document."""
        pass
    
    @log
    async def get_doc(self, entry: Entry) -> Document | None:
        """Retrieve a document, retrying if necessary for up to `self.stop_after_waiting` seconds."""
        
        attempt = 0
        elapsed = 0
        
        while True:
            try:
                return await self._get_doc(entry)
            
            except ParseError as e:
                if elapsed > self.stop_after_waiting:
                    raise e
                
                attempt += 1
                
                # Implement exponential backoff with jitter.
                wait = self.wait_base ** attempt / 2 # We divide by 2 so that `wait + jitter` is always <= `self.wait_base ** attempt`.
                
                # Set our jitter to a random number between 0 and `wait`.
                jitter = random.uniform(0, wait)
                
                wait = wait + jitter
                
                # If `wait` is greater than `self.max_wait`, set `wait` to `self.max_wait`.
                wait = min(wait, self.max_wait)
                
                # Wait for `wait` seconds.
                await asyncio.sleep(wait)
                
                elapsed += wait
    
    @log
    async def get(self, req: Request | str) -> Response:
        """Retrieve content."""

        # If the request is a string, convert it to a request object.
        if isinstance(req, str):
            req = Request(req)

        # If the request method is `open`, open the file and load the binary content.
        if req.method == 'open':
            with open(req.path, 'rb') as reader:
                return Response(
                    await reader.read(),
                    encoding=req.encoding,
                )

        # Otherwise, attempt to fetch the url and load the binary response, retrying if necessary for up to `self.stop_after_waiting` seconds.
        attempt = 0
        elapsed = 0
    
        while True:
            try:
                # If `self.session` exists and has not been closed, use it. Otherwise, create a new session.
                # NOTE We do not use `self.session` in a with statement but instead use a nullcontext (which acts as a flag for us to overwrite our session with `self.session`) in order to avoid closing `self.session` when it is not ours to close. The responsibility of closing `self.session` is on whoever passed it to the scraper.
                async with self.semaphore, (nullcontext() if self.session and not self.session.closed else aiohttp.ClientSession()) as session:
                    session = session or self.session # NOTE `session` will be `None` if our context manager is a nullcontext.
                    async with session.request(**req.args) as response:
                        # Raise a custom `aiohttp.client_exceptions.ClientResponseError` exception if the response status code is in `self.retry_statuses`.
                        if response.status in self.retry_statuses:
                            raise aiohttp.client_exceptions.ClientResponseError(
                                request_info=response.request_info,
                                history=response.history,
                                status=response.status,
                                message=response.reason,
                                headers=response.headers,
                            )
                        
                        return Response(
                            await response.read(),
                            encoding=req.encoding,
                            type=response.content_type,
                            status=response.status,
                        )
            
            except self.retry_exceptions as e:
                if elapsed > self.stop_after_waiting:
                    raise e
                
                attempt += 1
                
                # Implement exponential backoff with jitter.
                wait = self.wait_base ** attempt / 2 # We divide by 2 so that `wait + jitter` is always <= `self.wait_base ** attempt`.
                
                # Set our jitter to a random number between 0 and `wait`.
                jitter = random.uniform(0, wait)
                
                wait = wait + jitter
                
                # If `wait` is greater than `self.max_wait`, set `wait` to `self.max_wait`.
                wait = min(wait, self.max_wait)
                
                # Wait for `wait` seconds.
                await asyncio.sleep(wait)
                
                elapsed += wait

class ParseError(ValueError):
    """Downloaded content is unparseable."""
    
    def __init__(
        self,
        message: str = 'Unable to parse downloaded content. This could mean that the server is overloaded and retrying is in order or it could be that the content is actually unparseable. You are advised to inspect the source yourself.',
    ) -> None:
        self.message = message
        
        super().__init__(self.message)