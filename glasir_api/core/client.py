# glasir_api/core/client.py
import asyncio
import logging
from typing import Any, Dict, Optional

import httpx
from httpx import Limits

# Assuming ConcurrencyManager will be in the same directory or handled elsewhere
# from .concurrency_manager import ConcurrencyManager
# Placeholder type hint for now if ConcurrencyManager is not yet defined
ConcurrencyManager = Any

# Default headers similar to the old CLI client
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    # Content-Type is handled specifically for POST later
}

# Basic logging setup
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(name)s - %(message)s')
log = logging.getLogger(__name__)


class AsyncApiClient:
    """
    An asynchronous HTTP client for interacting with the Glasir API,
    handling retries and session parameters.
    """

    def __init__(
        self,
        base_url: str,
        cookies: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        external_client: Optional[httpx.AsyncClient] = None, # Added parameter
    ):
        """
        Initializes the AsyncApiClient.

        Args:
            base_url: The base URL for the API.
            cookies: Optional dictionary of cookies to include in requests.
            timeout: Request timeout in seconds.
            max_retries: Maximum number of retries for failed requests.
            backoff_factor: Factor to determine sleep time between retries (exponential backoff).
            external_client: Optional pre-configured httpx.AsyncClient to use.
                             If provided, this client will NOT be closed by AsyncApiClient.
        """
        self.base_url = base_url.rstrip("/")
        self.cookies = cookies or {} # Note: Cookies might need merging if external_client already has some
        self.timeout = timeout # Timeout might be redundant if external_client is used
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self._is_external_client = external_client is not None

        if self._is_external_client:
            self.client = external_client
            # Merge provided cookies into the external client's cookie jar
            if self.cookies:
                for name, value in self.cookies.items():
                    self.client.cookies.set(name, value) # Use httpx's way to set cookies
                log.info(f"Merged {len(self.cookies)} cookies into external client's jar.")
            # Set default headers on the external client instance
            self.client.headers.update(DEFAULT_HEADERS)
            log.info(f"Updated external client headers with defaults.")
            log.info(f"AsyncApiClient initialized using external httpx client for base URL: {self.base_url}")
        else:
            # Create internal client with cookies and default headers
            limits = Limits(max_keepalive_connections=20, max_connections=100)
            self.client = httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                verify=True,  # Consider making this configurable
                cookies=self.cookies, # Use cookies passed to this init
                headers=DEFAULT_HEADERS.copy(), # Use default headers
                limits=limits,
                http2=True,
            )
            log.info(f"AsyncApiClient initialized with internal httpx client for base URL: {self.base_url}")

    async def __aenter__(self):
        """Allows using the client with 'async with'."""
        return self

    async def __aexit__(self, *args):
        """Closes the client session on exiting 'async with' block."""
        await self.close()

    async def close(self):
        """
        Closes the underlying httpx client session, ONLY if it was created internally.
        """
        if not self._is_external_client and not self.client.is_closed:
            await self.client.aclose()
            log.info("AsyncApiClient closed its internally managed session.")
        elif self._is_external_client:
            log.debug("AsyncApiClient close() called, but using external client (not closing).")
        # else: client was internal but already closed

    async def _request_with_retries(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        concurrency_manager: Optional[ConcurrencyManager] = None,
        force_max_concurrency: bool = False,
        **kwargs,
    ) -> httpx.Response:
        """
        Makes an HTTP request with retry logic and optional session parameter injection.

        Args:
            method: HTTP method (e.g., "GET", "POST").
            url: URL path (relative to base_url) or absolute URL.
            params: Dictionary of URL query parameters.
            data: Dictionary of data for the request body (for POST/PUT).
            headers: Dictionary of request headers.
            concurrency_manager: Optional ConcurrencyManager instance for dynamic rate limiting.
            force_max_concurrency: If True, forces max concurrency (ignores manager adjustments).
            **kwargs: Additional arguments passed to httpx.request.

        Returns:
            The httpx.Response object on success.

        Raises:
            httpx.RequestError or httpx.HTTPStatusError after exhausting retries.
        """
        attempt = 0
        last_exc = None
        full_url = (
            url if url.startswith("http") else f"{self.base_url}/{url.lstrip('/')}"
        )

        while attempt < self.max_retries:
            try:
                log.debug(f"Attempt {attempt + 1}/{self.max_retries} for {method} {full_url}")
                # Prepare headers: start with client defaults, update with specific request headers
                request_headers = self.client.headers.copy()
                if headers:
                    request_headers.update(headers)

                response = await self.client.request(
                    method,
                    full_url,
                    params=params,
                    data=data, # Pass data directly
                    headers=request_headers, # Pass potentially merged headers
                    **kwargs,
                )
                response.raise_for_status()  # Raise exception for 4xx/5xx responses

                # Report success to concurrency manager if used
                if concurrency_manager and not force_max_concurrency:
                    # Check if the manager object is valid and has the method
                    if hasattr(concurrency_manager, 'report_success') and callable(concurrency_manager.report_success):
                         concurrency_manager.report_success()
                    # else:
                         # log.warning("Concurrency manager provided but lacks 'report_success' method.")


                # log.debug(f"Request successful: {method} {full_url} (Status: {response.status_code})") # Removed: Too verbose
                return response

            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                last_exc = e
                report_failure = False
                status_code = e.response.status_code if isinstance(e, httpx.HTTPStatusError) else None

                # Determine if failure should affect concurrency
                if isinstance(e, (httpx.TimeoutException, httpx.ConnectError)):
                    report_failure = True
                elif status_code in [429, 500, 503]: # Rate limiting or server errors
                    report_failure = True

                # Report failure to concurrency manager if applicable
                if report_failure and concurrency_manager and not force_max_concurrency:
                    if hasattr(concurrency_manager, 'report_failure') and callable(concurrency_manager.report_failure):
                        concurrency_manager.report_failure()
                    # else:
                        # log.warning("Concurrency manager provided but lacks 'report_failure' method.")


                endpoint = full_url.split("?")[0] # Log cleaner endpoint
                log.warning(
                    f"API {method} {endpoint} attempt {attempt + 1} failed: {type(e).__name__}"
                    f"{f' (Status: {status_code})' if status_code else ''}"
                )

                attempt += 1
                if attempt >= self.max_retries:
                    log.error(
                        f"API {method} {endpoint} failed after {self.max_retries} attempts."
                    )
                    break # Exit loop after max retries

                # Calculate sleep time and wait
                sleep_time = self.backoff_factor * (2 ** (attempt - 1))
                log.info(f"Retrying in {sleep_time:.2f} seconds...")
                await asyncio.sleep(sleep_time)

        # If loop finishes without returning, raise the last exception
        if last_exc is None:
             # This case should ideally not happen if max_retries > 0
             # but handle defensively
             log.error(f"API {method} {full_url.split('?')[0]} failed without a specific exception after {self.max_retries} attempts.")
             raise httpx.RequestError(f"Request failed after {self.max_retries} retries without specific error.")
        raise last_exc


    async def get(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        concurrency_manager: Optional[ConcurrencyManager] = None,
        force_max_concurrency: bool = False,
        **kwargs,
    ) -> httpx.Response:
        """
        Performs an asynchronous GET request with retry logic.

        Args:
            url: URL path or absolute URL.
            params: Dictionary of URL query parameters.
            headers: Dictionary of request headers.
            concurrency_manager: Optional ConcurrencyManager instance.
            force_max_concurrency: If True, forces max concurrency.
            **kwargs: Additional arguments passed to httpx.request.

        Returns:
            The httpx.Response object on success.
        """
        return await self._request_with_retries(
            "GET",
            url,
            params=params,
            headers=headers,
            concurrency_manager=concurrency_manager,
            force_max_concurrency=force_max_concurrency,
            **kwargs,
        )

    async def post(
        self,
        url: str,
        *,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        concurrency_manager: Optional[ConcurrencyManager] = None,
        force_max_concurrency: bool = False,
        **kwargs,
    ) -> httpx.Response:
        """
        Performs an asynchronous POST request with retry logic.

        Args:
            url: URL path or absolute URL.
            data: Dictionary of data for the request body.
            headers: Dictionary of request headers.
            concurrency_manager: Optional ConcurrencyManager instance.
            force_max_concurrency: If True, forces max concurrency.
            **kwargs: Additional arguments passed to httpx.request.

        Returns:
            The httpx.Response object on success.
        """
        # Content-Type is typically handled by httpx based on 'data' presence,
        # but we ensure application/x-www-form-urlencoded if data is provided
        # and Content-Type isn't explicitly set in the call.
        # The merging logic in _request_with_retries handles combining with client defaults.
        post_headers = headers or {}
        if data and 'Content-Type' not in post_headers:
             post_headers['Content-Type'] = 'application/x-www-form-urlencoded'
             log.debug(f"Ensuring Content-Type header for POST {url}")

        return await self._request_with_retries(
            "POST",
            url,
            data=data,
            headers=post_headers, # Pass specific headers for this POST
            concurrency_manager=concurrency_manager,
            force_max_concurrency=force_max_concurrency,
            **kwargs,
        )