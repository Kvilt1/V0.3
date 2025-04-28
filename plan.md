This file is a merged representation of a subset of the codebase, containing files not matching ignore patterns, combined into a single document by Repomix.
The content has been processed where comments have been removed, empty lines have been removed, content has been formatted for parsing in markdown style, security check has been disabled.

# File Summary

## Purpose
This file contains a packed representation of the entire repository's contents.
It is designed to be easily consumable by AI systems for analysis, code review,
or other automated processes.

## File Format
The content is organized as follows:
1. This summary section
2. Repository information
3. Directory structure
4. Multiple file entries, each consisting of:
  a. A header with the file path (## File: path/to/file)
  b. The full contents of the file in a code block

## Usage Guidelines
- This file should be treated as read-only. Any changes should be made to the
  original repository files, not this packed version.
- When processing this file, use the file path to distinguish
  between different files in the repository.
- Be aware that this file may contain sensitive information. Handle it with
  the same level of security as you would the original repository.

## Notes
- Some files may have been excluded based on .gitignore rules and Repomix's configuration
- Binary files are not included in this packed representation. Please refer to the Repository Structure section for a complete list of file paths, including binary files
- Files matching these patterns are excluded: .roomodes
- Files matching patterns in .gitignore are excluded
- Files matching default ignore patterns are excluded
- Code comments have been removed from supported file types
- Empty lines have been removed from all files
- Content has been formatted for parsing in markdown style
- Security check has been disabled - content may contain sensitive information
- Files are sorted by Git change count (files with more changes are at the bottom)

## Additional Info

# Directory Structure
```
glasir_api/
  core/
    client.py
    constants.py
    date_utils.py
    extractor.py
    formatting.py
    parsers.py
    service.py
    session.py
  models/
    models.py
  main.py
  README.md
  requirements.txt
glasir_auth_tool/
  get_auth.py
.gitignore
README.md
```

# Files

## File: glasir_api/core/client.py
````python
import asyncio
import logging
from typing import Any, Dict, Optional
import httpx
from httpx import Limits
ConcurrencyManager = Any
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(name)s - %(message)s')
log = logging.getLogger(__name__)
class AsyncApiClient:
    def __init__(
        self,
        base_url: str,
        cookies: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        external_client: Optional[httpx.AsyncClient] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.cookies = cookies or {}
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self._is_external_client = external_client is not None
        if self._is_external_client:
            self.client = external_client
            if self.cookies:
                for name, value in self.cookies.items():
                    self.client.cookies.set(name, value) # Use httpx's way to set cookies
                log.info(f"Merged {len(self.cookies)} cookies into external client's jar.")
            self.client.headers.update(DEFAULT_HEADERS)
            log.info(f"Updated external client headers with defaults.")
            log.info(f"AsyncApiClient initialized using external httpx client for base URL: {self.base_url}")
        else:
            limits = Limits(max_keepalive_connections=20, max_connections=100)
            self.client = httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                verify=True,
                cookies=self.cookies,
                headers=DEFAULT_HEADERS.copy(),
                limits=limits,
                http2=True,
            )
            log.info(f"AsyncApiClient initialized with internal httpx client for base URL: {self.base_url}")
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        await self.close()
    async def close(self):
        if not self._is_external_client and not self.client.is_closed:
            await self.client.aclose()
            log.info("AsyncApiClient closed its internally managed session.")
        elif self._is_external_client:
            log.debug("AsyncApiClient close() called, but using external client (not closing).")
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
        attempt = 0
        last_exc = None
        full_url = (
            url if url.startswith("http") else f"{self.base_url}/{url.lstrip('/')}"
        )
        while attempt < self.max_retries:
            try:
                log.debug(f"Attempt {attempt + 1}/{self.max_retries} for {method} {full_url}")
                request_headers = self.client.headers.copy()
                if headers:
                    request_headers.update(headers)
                response = await self.client.request(
                    method,
                    full_url,
                    params=params,
                    data=data,
                    headers=request_headers,
                    **kwargs,
                )
                response.raise_for_status()
                if concurrency_manager and not force_max_concurrency:
                    if hasattr(concurrency_manager, 'report_success') and callable(concurrency_manager.report_success):
                         concurrency_manager.report_success()
                return response
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                last_exc = e
                report_failure = False
                status_code = e.response.status_code if isinstance(e, httpx.HTTPStatusError) else None
                if isinstance(e, (httpx.TimeoutException, httpx.ConnectError)):
                    report_failure = True
                elif status_code in [429, 500, 503]:
                    report_failure = True
                if report_failure and concurrency_manager and not force_max_concurrency:
                    if hasattr(concurrency_manager, 'report_failure') and callable(concurrency_manager.report_failure):
                        concurrency_manager.report_failure()
                endpoint = full_url.split("?")[0]
                log.warning(
                    f"API {method} {endpoint} attempt {attempt + 1} failed: {type(e).__name__}"
                    f"{f' (Status: {status_code})' if status_code else ''}"
                )
                attempt += 1
                if attempt >= self.max_retries:
                    log.error(
                        f"API {method} {endpoint} failed after {self.max_retries} attempts."
                    )
                    break
                sleep_time = self.backoff_factor * (2 ** (attempt - 1))
                log.info(f"Retrying in {sleep_time:.2f} seconds...")
                await asyncio.sleep(sleep_time)
        if last_exc is None:
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
        # The merging logic in _request_with_retries handles combining with client defaults.
        post_headers = headers or {}
        if data and 'Content-Type' not in post_headers:
             post_headers['Content-Type'] = 'application/x-www-form-urlencoded'
             log.debug(f"Ensuring Content-Type header for POST {url}")
        return await self._request_with_retries(
            "POST",
            url,
            data=data,
            headers=post_headers,
            concurrency_manager=concurrency_manager,
            force_max_concurrency=force_max_concurrency,
            **kwargs,
        )
````

## File: glasir_api/core/constants.py
````python
GLASIR_BASE_URL = "https://tg.glasir.fo"
GLASIR_TIMETABLE_URL = f"{GLASIR_BASE_URL}/132n/"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}
DAY_NAME_MAPPING = {
    "Mánadagur": "Monday",
    "Týsdagur": "Tuesday",
    "Mikudagur": "Wednesday",
    "Hósdagur": "Thursday",
    "Fríggjadagur": "Friday",
    "Leygardagur": "Saturday",
    "Sunnudagur": "Sunday",
}
CANCELLED_CLASS_INDICATORS = [
    "lektionslinje_lesson1",
    "lektionslinje_lesson2",
    "lektionslinje_lesson3",
    "lektionslinje_lesson4",
    "lektionslinje_lesson5",
    "lektionslinje_lesson7",
    "lektionslinje_lesson10",
    "lektionslinje_lessoncancelled",
]
TEACHER_MAP_CACHE_TTL = 86400
# Add other relevant constants below as needed, e.g., specific selectors if used frequently.
````

## File: glasir_api/core/date_utils.py
````python
import logging
import re
from datetime import datetime
from functools import lru_cache
from typing import Dict, Optional, Tuple
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(name)s - %(message)s')
log = logging.getLogger(__name__)
PERIOD_DATE_FULL = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")
PERIOD_DATE_SHORT = re.compile(r"(\d{1,2})\.(\d{1,2})")
HYPHEN_DATE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
SLASH_DATE_SHORT = re.compile(r"(\d{1,2})/(\d{1,2})")
SLASH_DATE_WITH_YEAR = re.compile(r"(\d{1,2})/(\d{1,2})-(\d{4})")
@lru_cache(maxsize=256)
def parse_date(date_str: str, year: Optional[int] = None) -> Optional[Dict[str, str]]:
    if not date_str or not isinstance(date_str, str):
        log.debug(f"Invalid input for parse_date: {date_str}")
        return None
    default_year = year if year is not None else datetime.now().year
    log.debug(f"Parsing date string: '{date_str}' with default year: {default_year}")
    match = PERIOD_DATE_FULL.match(date_str)
    if match:
        day, month, yr = match.groups()
        log.debug(f"Matched PERIOD_DATE_FULL: d={day}, m={month}, y={yr}")
        return {"day": day.zfill(2), "month": month.zfill(2), "year": yr}
    match = PERIOD_DATE_SHORT.match(date_str)
    if match:
        day, month = match.groups()
        log.debug(f"Matched PERIOD_DATE_SHORT: d={day}, m={month}, using year={default_year}")
        return {"day": day.zfill(2), "month": month.zfill(2), "year": str(default_year)}
    match = HYPHEN_DATE.match(date_str)
    if match:
        yr, month, day = match.groups()
        log.debug(f"Matched HYPHEN_DATE: y={yr}, m={month}, d={day}")
        return {"day": day.zfill(2), "month": month.zfill(2), "year": yr}
    match = SLASH_DATE_SHORT.match(date_str)
    if match:
        day, month = match.groups()
        log.debug(f"Matched SLASH_DATE_SHORT: d={day}, m={month}, using year={default_year}")
        return {"day": day.zfill(2), "month": month.zfill(2), "year": str(default_year)}
    match = SLASH_DATE_WITH_YEAR.match(date_str)
    if match:
        day, month, yr = match.groups()
        log.debug(f"Matched SLASH_DATE_WITH_YEAR: d={day}, m={month}, y={yr}")
        return {"day": day.zfill(2), "month": month.zfill(2), "year": yr}
    log.warning(f"Could not parse date string: '{date_str}' with any known format.")
    return None
def format_date(
    date_dict: Optional[Dict[str, str]], output_format: str = "iso"
) -> Optional[str]:
    if not date_dict:
        return None
    required_keys = ["year", "month", "day"]
    if not all(key in date_dict for key in required_keys):
        log.warning(f"Invalid date_dict for formatting: {date_dict}")
        return None
    year = str(date_dict["year"])
    month = str(date_dict["month"]).zfill(2)
    day = str(date_dict["day"]).zfill(2)
    if output_format in ["iso", "hyphen"]:
        return f"{year}-{month}-{day}"
    elif output_format == "period":
        return f"{day}.{month}.{year}"
    elif output_format == "slash":
        return f"{day}/{month}/{year}"
    else:
        log.error(f"Unsupported output format requested: {output_format}")
        return None
@lru_cache(maxsize=128)
def convert_date_format(
    date_str: str, output_format: str = "iso", year: Optional[int] = None
) -> Optional[str]:
    parsed = parse_date(date_str, year)
    if parsed:
        return format_date(parsed, output_format)
    return None
@lru_cache(maxsize=128)
def to_iso_date(date_str: str, year: Optional[int] = None) -> Optional[str]:
    if not date_str:
        return None
    return convert_date_format(date_str, "iso", year)
def parse_time_range(time_range: str) -> Tuple[Optional[str], Optional[str]]:
    if not time_range or not isinstance(time_range, str) or "-" not in time_range:
        log.debug(f"Invalid time range format for parsing: '{time_range}'")
        return None, None
    parts = time_range.split("-")
    if len(parts) == 2:
        start_time = parts[0].strip()
        end_time = parts[1].strip()
        return start_time, end_time
    else:
        log.warning(f"Could not split time range '{time_range}' into two parts.")
        return None, None
````

## File: glasir_api/core/extractor.py
````python
import asyncio
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
import aiofiles
from pathlib import Path
import time
from cachetools import TTLCache, cached
from .client import AsyncApiClient
from .parsers import parse_homework_html, parse_teacher_html
from .constants import TEACHER_MAP_CACHE_TTL
ConcurrencyManager = Any
# Basic logging setup
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(name)s - %(message)s')
log = logging.getLogger(__name__)
# Directory for saving debug HTML
DEBUG_HTML_DIR = Path("debug_html")
DEBUG_HTML_DIR.mkdir(exist_ok=True) # Create dir if it doesn't exist
teacher_cache: TTLCache = TTLCache(maxsize=1, ttl=TEACHER_MAP_CACHE_TTL)
class TimetableExtractor:
    def __init__(self, api_client: AsyncApiClient, lname: Optional[str] = None):
        self.api = api_client
        self.lname = lname
        log.info(f"TimetableExtractor initialized with lname: {self.lname}")
    @cached(teacher_cache)
    async def fetch_teacher_map(self) -> Dict[str, str]:
        log.info("Fetching fresh teacher map from API (or using cache)...")
        try:
            timer = str(int(datetime.now().timestamp() * 1000))
            data = {
                "fname": "Henry",
                "lname": self.lname,
                "timer": timer,
            }
            log.debug(f"Fetching teacher map with data: {data}")
            resp = await self.api.post(
                "/i/teachers.asp",
                data=data
            )
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = DEBUG_HTML_DIR / f"teachers_{timestamp}_{resp.status_code}.html"
            try:
                async with aiofiles.open(filename, "w", encoding='utf-8') as f:
                    await f.write(f"<!-- URL: {resp.url} -->\n<!-- Status: {resp.status_code} -->\n{resp.text}")
                log.info(f"Saved debug HTML for teacher map to {filename}")
            except Exception as save_err:
                log.error(f"Failed to save debug HTML for teacher map: {save_err}")
            resp.raise_for_status()
            teacher_data = parse_teacher_html(resp.text)
            log.info(f"Successfully fetched and parsed teacher map ({len(teacher_data)} entries).")
            return teacher_data
        except Exception as e:
            log.error(f"Failed to fetch or parse teacher map: {e}", exc_info=True)
            return {}
    async def fetch_week_html(
        self,
        offset: int,
        student_id: Optional[str] = None,
        week_concurrency_manager: Optional[ConcurrencyManager] = None,
        force_max_concurrency: bool = False,
    ) -> str:
        log.debug(f"Fetching HTML for week offset: {offset}")
        try:
            timer = str(int(datetime.now().timestamp() * 1000))
            data = {
                "fname": "Henry",
                "q": "stude",
                "v": str(offset),
                "lname": self.lname,
                "timex": timer,
            }
            if student_id:
                data["id"] = student_id
            log.debug(f"Fetching week HTML with data: {data}")
            resp = await self.api.post(
                "/i/udvalg.asp",
                data=data,
                concurrency_manager=week_concurrency_manager,
                force_max_concurrency=force_max_concurrency,
            )
            log.debug(f"Response headers for week {offset}: {resp.headers}")
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = DEBUG_HTML_DIR / f"week_{offset}_{timestamp}_{resp.status_code}.html"
            try:
                async with aiofiles.open(filename, "w", encoding='utf-8') as f:
                    await f.write(f"<!-- URL: {resp.url} -->\n<!-- Status: {resp.status_code} -->\n{resp.text}")
                log.info(f"Saved debug HTML for week {offset} to {filename}")
            except Exception as save_err:
                log.error(f"Failed to save debug HTML for week {offset}: {save_err}")
            if resp.status_code >= 300 and resp.status_code < 400:
                 log.warning(f"Received redirect status {resp.status_code} for week {offset}. Content might be login page.")
            elif resp.status_code >= 400:
                 resp.raise_for_status() # Raise for client/server errors
            # log.debug(f"Fetched HTML for week offset: {offset} (Status: {resp.status_code})") # Removed: Too verbose
            return resp.text
        except Exception as e:
            log.error(f"Failed to fetch week {offset}: {e}", exc_info=True)
            return "" # Return empty string to indicate failure
    async def fetch_homework_for_lessons(
        self,
        lesson_ids: List[str],
        student_id: Optional[str] = None, # Add student_id if needed by payload (seems not?)
        concurrency_manager: Optional[ConcurrencyManager] = None,
        force_max_concurrency: bool = False,
    ) -> Dict[str, str]:
        results: Dict[str, str] = {}
        if not lesson_ids:
            log.debug("No lesson IDs provided for homework fetching.")
            return results
        log.debug(f"Fetching homework for {len(lesson_ids)} lessons.")
        async def fetch_one(lesson_id: str, force_flag: bool):
            try:
                # Generate fresh timer and construct payload
                timer = str(int(datetime.now().timestamp() * 1000))
                data = {
                    "fname": "Henry", # Seems constant, verify if needed
                    "q": lesson_id,
                    "MyFunktion": "ReadNotesToLessonWithLessonRID", # Specific function key
                    "lname": self.lname, # Use stored lname
                    "timer": timer,      # Use fresh timer
                    # student_id doesn't seem to be part of this payload based on old code
                }
                log.debug(f"Fetching homework for lesson {lesson_id} with data: {data}")
                resp = await self.api.post(
                    "/i/note.asp",
                    data=data,
                    concurrency_manager=concurrency_manager,
                    force_max_concurrency=force_flag,
                )
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = DEBUG_HTML_DIR / f"homework_{lesson_id}_{timestamp}_{resp.status_code}.html"
                try:
                    async with aiofiles.open(filename, "w", encoding='utf-8') as f:
                        await f.write(f"<!-- URL: {resp.url} -->\n<!-- Status: {resp.status_code} -->\n{resp.text}")
                    log.info(f"Saved debug HTML for homework {lesson_id} to {filename}")
                except Exception as save_err:
                    log.error(f"Failed to save debug HTML for homework {lesson_id}: {save_err}")
                if resp.status_code >= 300 and resp.status_code < 400:
                    log.warning(f"Received redirect status {resp.status_code} for homework {lesson_id}. Content might be login page.")
                    return
                elif resp.status_code >= 400:
                    resp.raise_for_status()
                parsed_homework = parse_homework_html(resp.text)
                if lesson_id in parsed_homework:
                    results[lesson_id] = parsed_homework[lesson_id]
            except Exception as e:
                log.warning(f"Failed to fetch homework for lesson {lesson_id}: {e}")
        tasks = [fetch_one(lid, force_max_concurrency) for lid in lesson_ids]
        await asyncio.gather(*tasks)
        log.info(f"Finished fetching homework. Found details for {len(results)}/{len(lesson_ids)} lessons.")
        return results
````

## File: glasir_api/core/formatting.py
````python
import logging
from functools import lru_cache
from typing import Optional
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(name)s - %(message)s')
log = logging.getLogger(__name__)
@lru_cache(maxsize=128)
def format_academic_year(year_code: Optional[str]) -> Optional[str]:
    if not year_code:
        return None
    if len(year_code) == 4 and year_code.isdigit():
        try:
            start_year = int(f"20{year_code[:2]}")
            end_year = int(f"20{year_code[2:]}")
            if end_year == start_year + 1:
                return f"{start_year}-{end_year}"
            else:
                log.warning(f"Year code '{year_code}' does not represent consecutive years. Returning original.")
                return year_code
        except ValueError:
            log.warning(f"Could not parse year code '{year_code}' as integer parts. Returning original.")
            return year_code
    else:
        log.debug(f"Year code '{year_code}' is not 4 digits or not numeric. Returning original.")
        return year_code
````

## File: glasir_api/core/parsers.py
````python
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from bs4 import BeautifulSoup, Tag
from .constants import CANCELLED_CLASS_INDICATORS, DAY_NAME_MAPPING
from .date_utils import to_iso_date, parse_time_range
from .formatting import format_academic_year
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(name)s - %(message)s')
log = logging.getLogger(__name__)
_RE_SPACE_BEFORE_NEWLINE = re.compile(r" +\n")
_RE_SPACE_AFTER_NEWLINE = re.compile(r"\n +")
def parse_homework_html(html: str) -> Dict[str, str]:
    result = {}
    lesson_id = None
    try:
        soup = BeautifulSoup(html, "lxml")
        lesson_id_input = soup.select_one(
            'input[type="hidden"][id^="LektionsID"]'
        )
        if not lesson_id_input:
            log.warning("Could not find LektionsID input field in homework HTML.")
            return result
        lesson_id = lesson_id_input.get("value")
        if not lesson_id:
            log.warning("LektionsID input field found, but has no value.")
            return result
        homework_header = soup.find("b", string="Heimaarbeiði")
        if not homework_header:
            log.debug(
                f"No 'Heimaarbeiði' header found for lesson {lesson_id}. Assuming no homework."
            )
            return result # No homework section found
        # Find the parent <p> tag containing the homework text
        homework_p = homework_header.find_parent("p")
        if not homework_p:
            log.warning(
                f"Found 'Heimaarbeiði' header but could not find its parent <p> tag for lesson {lesson_id}."
            )
            return result
        # --- Internal function to process nodes recursively into Markdown ---
        def process_node(
            node, is_first_level=False, header_skipped=False, first_br_skipped=False
        ):
            parts = []
            current_header_skipped = header_skipped
            current_first_br_skipped = first_br_skipped
            if isinstance(node, str):
                # Append text nodes directly
                parts.append(node)
            elif isinstance(node, Tag):
                # Skip the "Heimaarbeiði" header itself at the top level
                if (
                    is_first_level
                    and not current_header_skipped
                    and node.name == "b"
                    and node.get_text(strip=True) == "Heimaarbeiði"
                ):
                    return [], True, current_first_br_skipped # Mark header as skipped
                # Skip the first <br> immediately after the header at the top level
                if (
                    is_first_level
                    and current_header_skipped
                    and not current_first_br_skipped
                    and node.name == "br"
                ):
                    return [], current_header_skipped, True # Mark first <br> as skipped
                # Convert tags to Markdown or process children
                if node.name == "br":
                    parts.append("\n")
                elif node.name == "b": # Bold
                    inner_parts = []
                    temp_header_skipped = current_header_skipped
                    temp_br_skipped = current_first_br_skipped
                    for child in node.children:
                        child_res = process_node(
                            child, False, temp_header_skipped, temp_br_skipped
                        )
                        inner_parts.extend(child_res[0])
                        # Propagate skipped status from children
                        temp_header_skipped = child_res[1]
                        temp_br_skipped = child_res[2]
                    inner = "".join(inner_parts).strip()
                    if inner: parts.append(f"**{inner}**")
                    # Update main skipped status based on processing children
                    current_header_skipped = temp_header_skipped
                    current_first_br_skipped = temp_br_skipped
                elif node.name == "i": # Italic
                    inner_parts = []
                    temp_header_skipped = current_header_skipped
                    temp_br_skipped = current_first_br_skipped
                    for child in node.children:
                        child_res = process_node(
                            child, False, temp_header_skipped, temp_br_skipped
                        )
                        inner_parts.extend(child_res[0])
                        temp_header_skipped = child_res[1]
                        temp_br_skipped = child_res[2]
                    inner = "".join(inner_parts).strip()
                    if inner: parts.append(f"*{inner}*")
                    current_header_skipped = temp_header_skipped
                    current_first_br_skipped = temp_br_skipped
                else: # Process children of other tags
                    temp_header_skipped = current_header_skipped
                    temp_br_skipped = current_first_br_skipped
                    for child in node.children:
                        child_res = process_node(
                            child, False, temp_header_skipped, temp_br_skipped
                        )
                        parts.extend(child_res[0])
                        temp_header_skipped = child_res[1]
                        temp_br_skipped = child_res[2]
                    current_header_skipped = temp_header_skipped
                    current_first_br_skipped = temp_br_skipped
            return parts, current_header_skipped, current_first_br_skipped
        # --- End internal function ---
        markdown_parts = []
        final_header_skipped = False
        final_first_br_skipped = False
        # Process all direct children of the homework <p> tag
        for element in homework_p.contents:
            processed_parts, final_header_skipped, final_first_br_skipped = (
                process_node(
                    element, True, final_header_skipped, final_first_br_skipped
                )
            )
            markdown_parts.extend(processed_parts)
        # Join parts and clean up whitespace
        homework_text = "".join(markdown_parts)
        homework_text = _RE_SPACE_BEFORE_NEWLINE.sub("\n", homework_text)
        homework_text = _RE_SPACE_AFTER_NEWLINE.sub("\n", homework_text)
        homework_text = homework_text.strip()
        if homework_text:
            result[lesson_id] = homework_text
            log.debug(f"Extracted homework for lesson {lesson_id}")
        else:
            # Log if structure was found but no text followed
            log.debug(
                f"Found 'Heimaarbeiði' structure but no subsequent text for lesson {lesson_id}."
            )
    except Exception as e:
        log.error(f"Error parsing homework HTML for lesson ID '{lesson_id if lesson_id else 'unknown'}': {e}", exc_info=True)
    return result
# --- Teacher Parser ---
_RE_TEACHER_WITH_LINK = re.compile(r"([^<>]+?)\s*\(\s*<a[^>]*?>([A-Z]{2,4})</a>\s*\)")
_RE_TEACHER_NO_LINK = re.compile(r"([^<>]+?)\s*\(\s*([A-Z]{2,4})\s*\)")
def parse_teacher_html(html: str) -> Dict[str, str]:
    teacher_map = {}
    try:
        soup = BeautifulSoup(html, "lxml")
        # First, try parsing a <select> element (common for teacher lists)
        select_tag = soup.select_one("select")
        if select_tag:
            for option in select_tag.select("option"):
                initials = option.get("value")
                full_name = option.get_text(strip=True)
                # Ignore placeholder options (like value="-1")
                if initials and initials != "-1" and full_name:
                    teacher_map[initials] = full_name
            log.debug(f"Parsed {len(teacher_map)} teachers from <select> tag.")
        # If no teachers found in <select>, try regex patterns as a fallback
        if not teacher_map:
            log.debug("No <select> tag found or no teachers parsed, trying regex fallback.")
            compiled_patterns = [_RE_TEACHER_WITH_LINK, _RE_TEACHER_NO_LINK]
            for compiled_pattern in compiled_patterns:
                matches = compiled_pattern.findall(html)
                for match in matches:
                    # Ensure both name and initials were captured
                    if len(match) == 2:
                        full_name = match[0].strip()
                        initials = match[1].strip()
                        # Add only if not already found (prefer <select> results if any)
                        if initials and full_name and initials not in teacher_map:
                            teacher_map[initials] = full_name
            log.debug(f"Parsed {len(teacher_map)} teachers using regex fallback.")
    except Exception as e:
        log.error(f"Error parsing teacher HTML: {e}", exc_info=True)
    if not teacher_map:
        log.warning("Could not parse any teacher information from the provided HTML.")
    return teacher_map
# --- Timetable Parser ---
# Regex for student info (Name, Class) - made slightly more robust
# Regex updated to capture name potentially containing commas, stopping before the last comma,
# and capturing the class after the last comma.
# Regex refined: Capture name (non-greedy) and class after the colon and comma. Applied to the text content *after* finding the correct TD.
# Regex refined: Capture name (non-greedy) and class (alphanumeric) directly after the prefix. Applied to the full text content of the TD.
_RE_STUDENT_INFO = re.compile(
    r"N[æ&aelig;]mingatímatalva\s*:\s*([^<]+?)\s*,\s*(\w+)"
) # Example: "Næmingatímatalva: Rókur Kvilt Meitilberg, 22y <..." -> ('Rókur Kvilt Meitilberg', '22y')
_RE_DATE_RANGE = re.compile(
    r"(\d{1,2}\.\d{1,2}\.\d{4})\s*-\s*(\d{1,2}\.\d{1,2}\.\d{4})"
)
_RE_DAY_DATE = re.compile(r"(\w+)\s+(\d{1,2}/\d{1,2})") # Faroese day name + DD/MM
def get_timeslot_info(start_col_index: int) -> Dict[str, str]:
    # These ranges seem based on the original implementation's logic.
    if 2 <= start_col_index <= 25:
        return {"slot": "1", "time": "08:10-09:40"}
    elif 26 <= start_col_index <= 50:
        return {"slot": "2", "time": "10:05-11:35"}
    elif 51 <= start_col_index <= 71:
        return {"slot": "3", "time": "12:10-13:40"}
    elif 72 <= start_col_index <= 90:
        return {"slot": "4", "time": "13:55-15:25"}
    elif 91 <= start_col_index <= 111:
        return {"slot": "5", "time": "15:30-17:00"}
    elif 112 <= start_col_index <= 131:
        return {"slot": "6", "time": "17:15-18:45"}
    else:
        log.warning(f"Unknown timeslot for start column index: {start_col_index}")
        return {"slot": "N/A", "time": "N/A"}
def parse_timetable_html(
    html: str, teacher_map: Optional[Dict[str, str]] = None
) -> Tuple[Dict[str, Any], List[str]]:
    timetable_data: Dict[str, Any] = {"studentInfo": {}, "weekInfo": {}, "events": []}
    homework_ids: List[str] = []
    teacher_map = teacher_map or {}
    try:
        log.debug(f"Parser received FULL HTML:\n{html}\n--- END OF FULL HTML ---")
        log.debug("Attempting to parse HTML using 'lxml'")
        soup = BeautifulSoup(html, "lxml")
        student_info_td = soup.find(lambda tag: tag.name == 'td' and 'Næmingatímatalva' in tag.get_text())
        student_name = None
        student_class = None
        if student_info_td:
            initial_text = ""
            for content in student_info_td.contents:
                if isinstance(content, str):
                    initial_text += content
                elif isinstance(content, Tag) and content.name == 'table':
                    break
            initial_text = initial_text.strip()
            log.debug(f"Extracted initial text from student info TD: '{initial_text}'")
            student_info_match = _RE_STUDENT_INFO.search(initial_text)
            if student_info_match:
                student_name = student_info_match.group(1).strip()
                student_class = student_info_match.group(2).strip()
                log.debug(f"Parsed student info from initial text (regex): Name='{student_name}', Class='{student_class}'")
            else:
                log.warning(f"Regex failed on student info initial text: '{initial_text}'. Trying split fallback.")
                parts = initial_text.split(':')
                if len(parts) > 1:
                    name_class_part = parts[1].strip()
                    name_class_split = name_class_part.split(',')
                    if len(name_class_split) > 1:
                        student_name = name_class_split[0].strip()
                        student_class = name_class_split[1].strip()
                        log.debug(f"Parsed student info from initial text (split fallback): Name='{student_name}', Class='{student_class}'")
                    else:
                         log.warning(f"Could not split name/class part after colon using comma: '{name_class_part}'")
                else:
                    log.warning(f"Could not find colon ':' in student info initial text.")
        else:
            log.warning("Could not find TD containing 'Næmingatímatalva'.")
        if student_name and student_class:
             timetable_data["studentInfo"] = {
                 "studentName": student_name,
                 "class": student_class,
             }
        else:
             log.error("Failed to parse student name and class after attempting multiple methods.")
        week_info = timetable_data["weekInfo"]
        week_link = soup.select_one("a.UgeKnapValgt")
        if week_link:
            week_text = week_link.get_text(strip=True)
            if week_text.startswith("Vika "):
                try:
                    week_info["weekNumber"] = int(week_text.replace("Vika ", ""))
                except ValueError:
                    log.warning(f"Could not parse week number from text: '{week_text}'")
            else:
                log.warning(f"Selected week link text format unexpected: '{week_text}'")
        else:
            log.warning("Could not find selected week link (a.UgeKnapValgt) in HTML.")
        date_range_match = _RE_DATE_RANGE.search(html)
        current_year = None
        if date_range_match:
            start_date_str = date_range_match.group(1)
            end_date_str = date_range_match.group(2)
            week_info["startDate"] = to_iso_date(start_date_str)
            week_info["endDate"] = to_iso_date(end_date_str)
            if week_info.get("startDate"):
                try:
                    current_year = int(week_info["startDate"].split("-")[0])
                    week_info["year"] = current_year
                except (ValueError, IndexError, TypeError):
                    log.warning(f"Could not parse year from ISO startDate: {week_info.get('startDate')}")
            else:
                 log.warning(f"Could not parse start date '{start_date_str}' to ISO format.")
        else:
            log.warning("Could not parse date range (DD.MM.YYYY - DD.MM.YYYY) from HTML.")
        if not current_year:
             current_year = datetime.now().year
             week_info["year"] = current_year
             log.warning(f"Falling back to current system year: {current_year}")
        log.debug(f"Parsed week info: {week_info}")
        table = soup.select_one("table.time_8_16")
        if not table:
             log.error("Timetable table (table.time_8_16) not found in HTML.")
             return timetable_data, homework_ids
        log.debug(f"Successfully located timetable table using 'table.time_8_16'.")
        rows = table.select("tr")
        current_day_name_fo: Optional[str] = None
        current_date_part: Optional[str] = None
        for row_index, row in enumerate(rows):
            cells = row.select("td")
            if not cells:
                continue
            first_cell = cells[0]
            first_cell_text = first_cell.get_text(separator=" ", strip=True)
            day_match = _RE_DAY_DATE.match(first_cell_text)
            is_day_header = "lektionslinje_1" in first_cell.get(
                "class", []
            ) or "lektionslinje_1_aktuel" in first_cell.get("class", [])
            if is_day_header:
                log.debug(f"Row {row_index}: Identified as day header. Text: '{first_cell_text}'")
                if day_match:
                    current_day_name_fo = day_match.group(1)
                    current_date_part = day_match.group(2)
                    log.debug(f"Row {row_index}: Successfully parsed day header: Day='{current_day_name_fo}', Date='{current_date_part}'")
                else:
                    log.warning(f"Row {row_index}: Identified as day header (class check), but regex failed to parse date: '{first_cell_text}'. Resetting day context.")
                    current_day_name_fo = None
                    current_date_part = None
                # because lesson data might be in subsequent cells of the same row.
            elif not day_match: # Explicitly check if it wasn't a day header based on regex match
                log.debug(f"Row {row_index}: Not identified as day header based on text/regex. First cell text: '{first_cell_text}', Classes: {first_cell.get('class', [])}. Skipping row processing.")
                continue
            # --- Process Lesson Cells (Only if not a header row) ---
            # Ensure we have valid day context before processing lesson cells
            if not current_day_name_fo or not current_date_part:
                 # Skip processing cells if we haven't encountered a valid day header yet
                 log.debug(f"Skipping row {row_index} cell processing as current day/date context is not validly set.")
                 continue
            log.debug(f"Processing row index {row_index} for day: {current_day_name_fo}")
            current_col_index = 1
            lessons_found_in_row = 0
            day_en = DAY_NAME_MAPPING.get(current_day_name_fo, current_day_name_fo)
            for cell_index, cell in enumerate(cells):
                 # Skip the first cell (index 0) in *any* row being processed by this inner loop.
                 # This cell contains either the day/date info (in header rows) or is an empty spacer.
                 if cell_index == 0:
                      log.debug(f"  Skipping cell 0 (contains day info or is a spacer)")
                      # Need to account for its colspan if skipping, to keep current_col_index accurate
                      try:
                            # Use the actual first cell (cells[0]) to get colspan, not the loop variable 'cell'
                            colspan = int(cells[0].get("colspan", 1))
                      except ValueError:
                            colspan = 1
                      current_col_index += colspan
                      continue
                 log.debug(f"  Processing cell {cell_index} (Col ~{current_col_index}) - Classes: {cell.get('class', 'N/A')}") # ADDED DETAILED LOG
                 colspan = 1
                 # --- Start of indented block ---
                 try:
                     colspan_str = cell.get("colspan")
                     if colspan_str:
                         colspan = int(colspan_str)
                 except (ValueError, TypeError):
                     log.warning(f"Could not parse colspan for cell: {cell.get('colspan', 'None')}")
                     colspan = 1 # Default to 1 if parsing fails
                 # Revert to standard class check but add detailed logging
                 classes = cell.get("class", []) # Get class list
                 class_str = ' '.join(classes) if isinstance(classes, list) else str(classes) # For logging
                 # --- Lesson Identification (Reverted & Refined) ---
                 # Check for class names starting with 'lektionslinje_lesson' followed by a digit,
                 # as observed in the actual HTML (e.g., 'lektionslinje_lesson0').
                 # Also check for cells with 'mellem' class that contain lesson information.
                 is_lesson = False
                 lesson_class_pattern = re.compile(r"lektionslinje_lesson\d+")
                 if isinstance(classes, list):
                     for cls in classes:
                          if lesson_class_pattern.match(cls):
                              is_lesson = True
                              break # Found a match
                 elif isinstance(classes, str): # Fallback if class is a single string
                     if lesson_class_pattern.match(classes):
                         is_lesson = True
                 # Removed the check for 'mellem' class as potential lessons,
                 # as the HTML analysis shows 'mellem' cells are just spacers.
                 # Lesson identification now relies solely on the 'lektionslinje_lesson\d+' class pattern.
                 is_cancelled = any(cls in CANCELLED_CLASS_INDICATORS for cls in classes if isinstance(cls, str))
                 log.debug(f"    Cell {cell_index} check result: is_lesson={is_lesson} (based on class pattern), is_cancelled={is_cancelled}, Classes='{class_str}'")
                 if is_lesson:
                     lessons_found_in_row += 1 # Increment counter
                     a_tags = cell.select("a") # Select links directly from the lesson cell
                     # Expecting at least 3 <a> tags for subject, teacher, room in a valid lesson cell
                     if len(a_tags) >= 3:
                         log.debug(f"      Cell {cell_index}: Identified as lesson AND found {len(a_tags)} links. Proceeding to parse.")
                         class_code_raw = a_tags[0].get_text(strip=True)
                         teacher_short = a_tags[1].get_text(strip=True)
                         room_raw = a_tags[2].get_text(strip=True)
                         # --- Code below is now correctly indented within the if len(a_tags) >= 3 block ---
                         # --- Parse Subject Code ---
                         code_parts = class_code_raw.split("-")
                         subject_code = ""
                         level = ""
                         year_code = "" # Academic year part like '2425'
                         if code_parts:
                             # Handle specific "Várroynd" format
                             if code_parts[0] == "Várroynd" and len(code_parts) > 4:
                                 subject_code = f"{code_parts[0]}-{code_parts[1]}"
                                 level = code_parts[2]
                                 # Assuming team/group is part 3, year is part 4
                                 year_code = code_parts[4]
                             # Handle standard format like SUBJ-LVL-TEAM-YEAR
                             elif len(code_parts) > 3:
                                 subject_code = code_parts[0]
                                 level = code_parts[1]
                                 # Assuming team is part 2, year is part 3
                                 year_code = code_parts[3]
                             else: # Fallback if format is unexpected
                                 subject_code = class_code_raw # Use the raw string
                                 log.warning(f"Unexpected subject code format: {class_code_raw}")
                         # --- Teacher and Location ---
                         teacher_full = teacher_map.get(teacher_short, teacher_short) # Use map or default to short
                         location = room_raw.replace("st.", "").strip() # Clean room string
                         # --- Time and Date ---
                         # Determine time slot based on column index
                         if colspan >= 90: # Heuristics for all-day events based on colspan
                             time_info = {"slot": "All day", "time": "08:10-15:25"} # Approximate
                         else:
                             time_info = get_timeslot_info(current_col_index)
                         # log.debug(f"      Calculated time_info: {time_info}") # Compacted log
                         iso_date = None
                         if current_date_part and current_year:
                             # Combine DD/MM with the year determined earlier
                             iso_date = to_iso_date(current_date_part, current_year)
                         elif current_date_part:
                             log.warning(
                                 f"Cannot determine ISO date for '{current_date_part}' - year is missing or failed parsing."
                             )
                         start_time, end_time = parse_time_range(time_info["time"])
                         # --- Lesson ID ---
                         lesson_id = None
                         # Look for the span containing the lesson ID
                         lesson_span = cell.select_one('span[id^="MyWindow"][id$="Main"]')
                         if lesson_span and lesson_span.get("id"):
                             span_id = lesson_span["id"]
                             # Extract ID: remove prefix "MyWindow" and suffix "Main"
                             if len(span_id) > 12: # "MyWindow" (8) + "Main" (4) = 12
                                 lesson_id = span_id[8:-4]
                             else:
                                 log.warning(
                                     f"Found lesson span with unexpected ID format: {span_id}"
                                 )
                         else:
                             # Log if the span is missing, might indicate HTML structure change
                             log.warning(
                                 f"Could not find lesson ID span in cell for {subject_code} on {iso_date}"
                             )
                         # log.debug(f"      Extracted lesson_id: {lesson_id}") # Compacted log
                         # --- Homework Note Check ---
                         has_homework_note = False
                         # Check for the note image icon using attribute selector
                         note_img = cell.select_one(
                             'input[type="image"][src*="note.gif"]'
                         )
                         if note_img:
                             has_homework_note = True
                             if lesson_id:
                                 # Only add ID if homework note is present AND ID was found
                                 homework_ids.append(lesson_id)
                                 log.debug(f"Homework note found for lesson ID: {lesson_id}")
                             else:
                                 log.warning(f"Homework note found, but no lessonId extracted for cell: {subject_code} on {iso_date}")
                         # --- Assemble Event Dictionary ---
                         try:
                             event = {
                                 "title": subject_code,
                                 "level": level,
                                 "year": format_academic_year(year_code), # Format '2425' -> '2024-2025'
                                 "date": iso_date,
                                 "dayOfWeek": day_en, # Use translated day name
                                 "teacher": (
                                     teacher_full.split(" (")[0] # Clean up name if initials are appended
                                     if " (" in teacher_full
                                     else teacher_full
                                 ),
                                 "teacherShort": teacher_short,
                                 "location": location,
                                 "timeSlot": time_info["slot"],
                                 "startTime": start_time,
                                 "endTime": end_time,
                                 "timeRange": time_info["time"],
                                 "cancelled": is_cancelled,
                                 "lessonId": lesson_id,
                                 "hasHomeworkNote": has_homework_note,
                                 "description": None, # Placeholder for homework text (added later)
                             }
                             log.debug(f"        Assembled event dictionary: {event}") # Log the event before appending
                             timetable_data["events"].append(event)
                             log.debug(f"        Successfully appended event for {subject_code}")
                         except Exception as event_err:
                             log.error(f"      ERROR assembling or appending event for cell {cell_index} ({subject_code} on {iso_date}): {event_err}", exc_info=True)
                     else:
                         # Log if it was identified as a lesson but didn't have enough links
                         log.warning(f"      Cell {cell_index}: Identified as lesson based on class, but found only {len(a_tags)} links. Skipping event creation.")
                         current_col_index += colspan
                         continue
                 else:
                     log.debug(f"      Cell {cell_index}: Not identified as a lesson based on class pattern. Skipping.")
                     current_col_index += colspan
                     continue
                 current_col_index += colspan
            try:
                log.debug(f"Finished processing row index {row_index}. Found {lessons_found_in_row} lesson(s). Row HTML: {row.prettify()}")
            except Exception as prettify_err:
                log.warning(f"Finished processing row index {row_index}. Found {lessons_found_in_row} lesson(s). Error logging row HTML: {prettify_err}")
    except Exception as e:
        log.error(f"Critical error during timetable HTML parsing: {e}", exc_info=True)
    log.info(f"Finished parsing timetable. Found {len(timetable_data['events'])} potential events.")
    unique_homework_ids = set(homework_ids)
    log.info(f"Identified {len(unique_homework_ids)} unique lessons with homework notes.")
    if len(timetable_data["events"]) == 0 and timetable_data.get("studentInfo", {}).get("class"):
        log.warning("No events found through normal parsing. Attempting to extract from class info.")
        class_info = timetable_data["studentInfo"]["class"]
        day_matches = re.finditer(r'([A-ZÁÐÍÓÚÝÆØÅa-záðíóúýæøå]+dagur)\s+(\d{1,2}/\d{1,2})', class_info)
        for day_match in day_matches:
            day_name_fo = day_match.group(1)
            date_part = day_match.group(2)
            day_en = DAY_NAME_MAPPING.get(day_name_fo, day_name_fo)
            day_pos = day_match.start()
            next_day_match = re.search(r'[A-ZÁÐÍÓÚÝÆØÅa-záðíóúýæøå]+dagur', class_info[day_pos + 1:])
            day_end_pos = next_day_match.start() + day_pos + 1 if next_day_match else len(class_info)
            day_content = class_info[day_pos:day_end_pos]
            course_matches = re.finditer(r'([a-zæøåA-ZÆØÅ]+-[A-Z]-\d+-\d{4}-\w+)\s+([A-Z]{2,4})\s+st\.\s+(\d+)', day_content)
            for i, course_match in enumerate(course_matches):
                course_code = course_match.group(1)
                teacher_short = course_match.group(2)
                location = course_match.group(3)
                code_parts = course_code.split("-")
                subject_code = code_parts[0] if len(code_parts) > 0 else course_code
                level = code_parts[1] if len(code_parts) > 1 else ""
                year_code = code_parts[3] if len(code_parts) > 3 else ""
                iso_date = None
                current_year = timetable_data.get("weekInfo", {}).get("year")
                if current_year:
                    iso_date = to_iso_date(date_part, current_year)
                time_info = get_timeslot_info((i + 1) * 10)
                start_time, end_time = parse_time_range(time_info["time"])
                teacher_full = teacher_map.get(teacher_short, teacher_short)
                event = {
                    "title": subject_code,
                    "level": level,
                    "year": format_academic_year(year_code),
                    "date": iso_date,
                    "dayOfWeek": day_en,
                    "teacher": teacher_full.split(" (")[0] if " (" in teacher_full else teacher_full,
                    "teacherShort": teacher_short,
                    "location": location,
                    "timeSlot": time_info["slot"],
                    "startTime": start_time,
                    "endTime": end_time,
                    "timeRange": time_info["time"],
                    "cancelled": False,
                    "lessonId": None,
                    "hasHomeworkNote": False,
                    "description": None,
                }
                timetable_data["events"].append(event)
                log.debug(f"Extracted event from class info: {subject_code} with {teacher_short} in room {location}")
        log.info(f"Extracted {len(timetable_data['events'])} events from class info as fallback.")
    log.debug(f"FINAL Events list contains {len(timetable_data['events'])} events.")
    return timetable_data, homework_ids
def merge_homework_into_events(events: List[Dict[str, Any]], homework_map: Dict[str, str]):
    if not homework_map:
        log.debug("No homework map provided, skipping merge.")
        return
    merged_count = 0
    for event in events:
        lesson_id = event.get("lessonId")
        if lesson_id and lesson_id in homework_map:
            homework_text = homework_map[lesson_id]
            event["description"] = homework_text
            log.debug(f"Merged homework for lesson ID {lesson_id} into event '{event.get('title', 'N/A')}'")
            merged_count += 1
        elif lesson_id:
            pass
    log.info(f"Merged homework descriptions into {merged_count} events.")
_RE_WEEK_OFFSET = re.compile(r"v=(-?\d+)")
def parse_available_offsets(html: str) -> List[int]:
    offsets = set()
    try:
        soup = BeautifulSoup(html, "lxml")
        nav_links = soup.select('a[onclick*="v="]')
        if not nav_links:
            log.warning("No week navigation links ('a[onclick*=v=]') found in HTML.")
            return []
        for link in nav_links:
            onclick_attr = link.get("onclick")
            if onclick_attr:
                match = _RE_WEEK_OFFSET.search(onclick_attr)
                if match:
                    try:
                        offset = int(match.group(1))
                        offsets.add(offset)
                    except (ValueError, IndexError):
                        log.warning(f"Could not parse integer offset from onclick: {onclick_attr}")
                else:
                    log.debug(f"Regex did not match expected offset pattern in onclick: {onclick_attr}")
    except Exception as e:
        log.error(f"Error parsing available week offsets from HTML: {e}", exc_info=True)
        return []
    if not offsets:
        log.warning("Parsed HTML but found no valid week offsets in navigation links.")
    sorted_offsets = sorted(list(offsets))
    log.info(f"Found {len(sorted_offsets)} unique week offsets: {sorted_offsets}")
    return sorted_offsets
````

## File: glasir_api/core/service.py
````python
import httpx
import asyncio
import logging
from typing import Dict, Tuple, Optional, List
from datetime import datetime
from fastapi import HTTPException
from pydantic import ValidationError
from .client import AsyncApiClient
from .constants import GLASIR_TIMETABLE_URL, GLASIR_BASE_URL
from .extractor import TimetableExtractor
from .parsers import parse_timetable_html, merge_homework_into_events
from .session import extract_session_params_from_html
from ..models.models import TimetableData
log = logging.getLogger(__name__)
async def _fetch_and_process_week(offset: int, extractor: TimetableExtractor, student_id: str, teacher_map: dict) -> Optional[Dict]:
    try:
        week_html = await extractor.fetch_week_html(offset, student_id)
        if not week_html:
            log.warning(f"No HTML content received for week offset {offset}, student {student_id}.")
            return None
        timetable_data, homework_ids = parse_timetable_html(week_html, teacher_map)
        if not timetable_data:
            log.warning(f"Failed to parse timetable data for week offset {offset}, student {student_id}.")
            return None
        if homework_ids:
            homework_map = await extractor.fetch_homework_for_lessons(homework_ids, student_id)
            if homework_map:
                merge_homework_into_events(timetable_data['events'], homework_map)
            else:
                log.warning(f"Failed to fetch homework details for week offset {offset}, student {student_id}. Proceeding without homework.")
        return timetable_data
    except httpx.RequestError as e:
        log.error(f"Network error fetching week {offset} for student {student_id}: {e.request.url}", exc_info=True)
        return None
    except httpx.HTTPStatusError as e:
        log.error(f"HTTP error {e.response.status_code} fetching week {offset} for student {student_id}: {e.request.url}", exc_info=True)
        return None
    except Exception as e:
        log.error(f"Unexpected error processing week {offset} for student {student_id}", exc_info=True)
        return None
async def _setup_extractor(cookies_str: str, shared_client: httpx.AsyncClient) -> Tuple[TimetableExtractor, dict, str]:
    try:
        parsed_cookies = {}
        if cookies_str:
            for item in cookies_str.split(';'):
                item = item.strip()
                if '=' in item:
                    key, value = item.split('=', 1)
                    parsed_cookies[key.strip()] = value.strip()
        if not parsed_cookies:
            log.error("Invalid or empty cookie string provided during setup.")
            raise HTTPException(status_code=400, detail="Invalid or missing authentication cookie provided.")
        response = await shared_client.get(GLASIR_TIMETABLE_URL, cookies=parsed_cookies, follow_redirects=False)
        if response.status_code != 200:
            log.error(f"Initial GET to {GLASIR_TIMETABLE_URL} failed authentication. Status: {response.status_code}. Check cookies/session.")
            raise HTTPException(status_code=401, detail="Authentication failed with Glasir. Check credentials/cookie.")
        initial_html = response.text
        lname = extract_session_params_from_html(initial_html)
        if not lname:
            log.error("Could not extract 'lname' session parameter from Glasir page during setup.")
            raise HTTPException(status_code=502, detail="Failed to extract session parameters from Glasir response.")
        api_client = AsyncApiClient(
            base_url=GLASIR_BASE_URL,
            cookies=parsed_cookies,
            external_client=shared_client
        )
        extractor = TimetableExtractor(api_client, lname=lname)
        teacher_map = await extractor.fetch_teacher_map()
        if teacher_map is None:
             log.error("Failed to fetch teacher map during setup.")
             raise HTTPException(status_code=502, detail="Failed to fetch teacher map from Glasir.")
        return extractor, teacher_map, lname
    except httpx.RequestError as e:
        log.error(f"Network error during initial setup: {e.request.url}", exc_info=True)
        raise HTTPException(status_code=504, detail=f"Network error during Glasir setup: {e.request.url}")
    except httpx.HTTPStatusError as e:
        log.error(f"HTTP error during initial setup: {e.response.status_code} for URL {e.request.url}", exc_info=True)
        raise HTTPException(status_code=502, detail=f"Glasir backend error ({e.response.status_code}) during setup: {e.request.url}")
    except Exception as e:
        log.error(f"Unexpected error during setup", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Unexpected internal error during setup: {type(e).__name__}")
async def get_multiple_weeks(
    username: str,
    student_id: str,
    cookies_str: str,
    requested_offsets: List[int],
    shared_client: httpx.AsyncClient
) -> List[TimetableData]:
    extractor: Optional[TimetableExtractor] = None
    teacher_map: Optional[Dict] = None
    lname: Optional[str] = None
    processed_weeks: List[TimetableData] = []
    try:
        extractor, teacher_map, lname = await _setup_extractor(cookies_str, shared_client)
        log.info(f"Extractor setup successful for user {username}, lname: {lname}")
        tasks = []
        if not requested_offsets:
            log.warning(f"No offsets requested for user {username}, student {student_id}.")
            return []
        log.info(f"Creating {len(requested_offsets)} tasks for offsets: {requested_offsets}")
        for offset in requested_offsets:
            task = asyncio.create_task(
                _fetch_and_process_week(offset, extractor, student_id, teacher_map)
            )
            tasks.append(task)
        results = await asyncio.gather(*tasks, return_exceptions=True)
        log.info(f"Finished gathering results for {len(results)} tasks.")
        for i, result in enumerate(results):
            offset = requested_offsets[i]
            if isinstance(result, Exception):
                log.error(f"Task for offset {offset} failed with exception: {result}", exc_info=result)
            elif result is None:
                log.warning(f"Task for offset {offset} returned None (fetch/parse error).")
            else:
                try:
                    validated_data = TimetableData.model_validate(result)
                    processed_weeks.append(validated_data)
                    log.debug(f"Successfully validated and added data for offset {offset}.")
                except ValidationError as e:
                    log.error(f"Validation failed for offset {offset}: {e}")
                    log.debug(f"Invalid data structure for offset {offset}: {result}")
                except Exception as e_val:
                    log.error(f"Unexpected error processing result for offset {offset}: {e_val}", exc_info=True)
        processed_weeks.sort(key=lambda x: x.week_info.week_number if x.week_info and x.week_info.week_number is not None else float('inf'))
        log.info(f"Successfully processed and validated {len(processed_weeks)} weeks out of {len(requested_offsets)} requested.")
        return processed_weeks
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Unexpected error in get_multiple_weeks for user {username}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected server error occurred while fetching multiple weeks: {e}")
    # as the shared_client's lifecycle is managed by the FastAPI application lifespan.
````

## File: glasir_api/core/session.py
````python
import logging
import re
from typing import Dict, Optional
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(name)s - %(message)s')
log = logging.getLogger(__name__)
LNAME_PATTERNS = [
    re.compile(r"lname=([^&\"'\s]+)"), # Common case in URLs or simple assignments
    re.compile(r"xmlhttp\.send\(\"[^\"]*lname=([^&\"'\s]+)\""), # Inside an xmlhttp.send call
    re.compile(r"MyUpdate\('[^']*','[^']*','[^']*',\d+,(\d+)\)"), # Specific JS function call pattern (assuming the last number is lname)
    re.compile(r"name=['\"]lname['\"]\s*value=['\"]([^'\"]+)['\"]"), # Inside an input tag
]
def extract_session_params_from_html(html: str) -> Optional[str]:
    lname: Optional[str] = None
    log.debug("Attempting to extract 'lname' session parameter from HTML.")
    # Iterate through predefined regex patterns to find 'lname'
    for pattern in LNAME_PATTERNS:
        match = pattern.search(html)
        if match:
            raw_lname = match.group(1) # Extract the captured group
            # Check if the extracted value contains a comma and strip if necessary
            if ',' in raw_lname:
                lname = raw_lname.split(',')[0]
                log.info(f"Successfully extracted raw 'lname': {raw_lname}, using modified 'lname': {lname} (pattern: {pattern.pattern})")
            else:
                lname = raw_lname
                log.info(f"Successfully extracted 'lname': {lname} using pattern: {pattern.pattern}")
            break # Stop searching once found
    if not lname:
        log.warning("Could not extract 'lname' session parameter from the provided HTML.")
    return lname
````

## File: glasir_api/models/models.py
````python
from datetime import datetime
from typing import List, Optional, Union
from pydantic import BaseModel, Field, model_validator, validator
class StudentInfo(BaseModel):
    student_name: str = Field(..., alias="studentName")
    class_: str = Field(..., alias="class")
    class Config:
        populate_by_name = True
        frozen = True
        json_schema_extra = {"example": {"studentName": "John Doe", "class": "22y"}}
class WeekInfo(BaseModel):
    week_number: int = Field(..., alias="weekNumber")
    start_date: str = Field(..., alias="startDate")
    end_date: str = Field(..., alias="endDate")
    year: int
    week_key: Optional[str] = Field(None, alias="weekKey")
    @validator("start_date", "end_date")
    def validate_date_format(cls, v):
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except ValueError:
            raise ValueError("Date must be in ISO format (YYYY-MM-DD)")
    @validator("week_number")
    def validate_week_number(cls, v):
        if not 1 <= v <= 53:
            raise ValueError("Week number must be between 1 and 53")
        return v
    @model_validator(mode="after")
    def generate_week_key(self):
        if not self.week_key:
            self.week_key = f"{self.year}-W{self.week_number:02d}"
        return self
    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "weekNumber": 13,
                "startDate": "2025-03-24",
                "endDate": "2025-03-30",
                "year": 2025,
                "weekKey": "2025-W13",
            }
        }
class Event(BaseModel):
    title: str
    level: str
    year: Optional[str]
    date: Optional[str]
    day_of_week: str = Field(..., alias="dayOfWeek")
    teacher: str
    teacher_short: str = Field(..., alias="teacherShort")
    location: str
    time_slot: Union[int, str] = Field(..., alias="timeSlot")
    start_time: Optional[str] = Field(..., alias="startTime")
    end_time: Optional[str] = Field(..., alias="endTime")
    time_range: str = Field(..., alias="timeRange")
    cancelled: bool = False
    lesson_id: Optional[str] = Field(None, alias="lessonId")
    description: Optional[str] = None
    has_homework_note: bool = Field(False, alias="hasHomeworkNote")
    @validator("date")
    def validate_date_format(cls, v):
        if v is None:
            return v
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except ValueError:
            raise ValueError("Date must be in ISO format (YYYY-MM-DD)")
    @validator("start_time", "end_time")
    def validate_time_format(cls, v):
        if not v or not isinstance(v, str):
            return v
        try:
            datetime.strptime(v, "%H:%M")
            return v
        except ValueError:
            raise ValueError("Time must be in HH:MM format")
    class Config:
        populate_by_name = True
        frozen = False
        json_schema_extra = {
            "example": {
                "title": "evf",
                "level": "A",
                "year": "2024-2025",
                "date": "2025-03-24",
                "dayOfWeek": "Monday",
                "teacher": "Brynjálvur I. Johansen",
                "teacherShort": "BIJ",
                "location": "608",
                "timeSlot": 2,
                "startTime": "10:05",
                "endTime": "11:35",
                "timeRange": "10:05-11:35",
                "cancelled": False,
                "lessonId": "12345678-1234-1234-1234-123456789012",
                "description": "Homework text goes here.",
                "hasHomeworkNote": True,
            }
        }
class TimetableData(BaseModel):
    student_info: StudentInfo = Field(..., alias="studentInfo")
    events: List[Event]
    week_info: WeekInfo = Field(..., alias="weekInfo")
    format_version: int = Field(2, alias="formatVersion")
    @validator("format_version")
    def validate_format_version(cls, v):
        if v != 2:
            raise ValueError("Format version must be 2")
        return v
    class Config:
        populate_by_name = True
        frozen = False # Set to False to allow modification
````

## File: glasir_api/main.py
````python
import sys
import httpx
from typing import Annotated, Optional, List, Tuple
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header, Query, Path, Request
from fastapi.responses import ORJSONResponse
from .models.models import TimetableData
from .core.service import _setup_extractor, _fetch_and_process_week, get_multiple_weeks
from .core.parsers import parse_available_offsets
from .core.extractor import TimetableExtractor
from .core.constants import GLASIR_TIMETABLE_URL
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
@asynccontextmanager
async def lifespan(app: FastAPI):
    client = httpx.AsyncClient(
        base_url=GLASIR_TIMETABLE_URL,
        timeout=30.0,
        follow_redirects=True,
        limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
        http2=True
    )
    logging.info("Lifespan startup: HTTPX client created.")
    app.state.http_client = client
    parser_logger = logging.getLogger("glasir_api.core.parsers")
    if not any(isinstance(h, logging.StreamHandler) for h in parser_logger.handlers):
         root_logger = logging.getLogger()
         stream_handler = None
         for h in root_logger.handlers:
              if isinstance(h, logging.StreamHandler):
                   stream_handler = h
                   break
         if stream_handler:
              parser_logger.addHandler(stream_handler)
              parser_logger.setLevel(logging.DEBUG) # Set parser logger to DEBUG
              parser_logger.propagate = False # Prevent messages from being logged twice by root logger
              logging.info(f"Lifespan startup: Configured 'glasir_api.core.parsers' logger to DEBUG level.") # Use logging
         else:
              logging.warning("Lifespan startup: Could not find root stream handler to configure parser logger.") # Use logging
    else:
         # Ensure level is still DEBUG even if handler exists
         parser_logger.setLevel(logging.DEBUG)
         logging.info(f"Lifespan startup: 'glasir_api.core.parsers' logger handler already exists, ensured level is DEBUG.") # Use logging
    # --- End logger configuration ---
    yield # Application runs here
    # Close the client when the app shuts down
    if not client.is_closed:
        await client.aclose()
        logging.info("Lifespan shutdown: HTTPX client closed.") # Use logging
    else:
        logging.info("Lifespan shutdown: HTTPX client was already closed.") # Use logging
# Create the FastAPI app instance with lifespan
app = FastAPI(default_response_class=ORJSONResponse, lifespan=lifespan)
@app.get("/")
async def read_root():
    # Updated message as per Plan.md Phase 1
    return {"message": "Glasir API"}
# --- Phase 3 Endpoints ---
# Define specific routes BEFORE the general route with path parameters
@app.get(
    "/profiles/{username}/weeks/all",
    response_model=List[TimetableData], # Response is a list of timetables
    response_model_exclude_none=True,
    summary="Get timetable for all available weeks",
    tags=["Timetable"]
)
async def get_all_weeks(
    request: Request, # Inject Request to access app state
    username: Annotated[str, Path(description="Identifier for the user profile")],
    student_id: Annotated[str, Query(description="The student's unique ID from Glasir")],
    cookie: Annotated[str | None, Header(description="Glasir authentication cookies")] = None
):
    if not cookie:
        raise HTTPException(status_code=400, detail="Cookie header is required.")
    if not student_id:
        raise HTTPException(status_code=400, detail="student_id query parameter is required.")
    http_client: httpx.AsyncClient = request.app.state.http_client
    extractor: Optional[TimetableExtractor] = None
    try:
        # 1. Initial Setup (Get extractor, teacher_map, lname)
        setup_result = await _setup_extractor(cookie, http_client)
        if setup_result is None:
            # Logged within _setup_extractor or service layer
            raise HTTPException(status_code=502, detail="Failed initial setup with Glasir. Check auth or Glasir status.")
        extractor, teacher_map, lname = setup_result # Unpack necessary parts
        # 2. Fetch Base Week HTML (Offset 0) to find available offsets
        # Use the already setup extractor
        base_week_html = await extractor.fetch_week_html(offset=0, student_id=student_id)
        if not base_week_html:
            # This could happen if offset 0 is somehow invalid, or network issue
            raise HTTPException(status_code=404, detail="Could not fetch base week (offset 0) to determine available weeks.")
        # 3. Parse Available Offsets
        available_offsets = parse_available_offsets(base_week_html)
        if not available_offsets:
            # Logged within parser
            # Return empty list if no offsets found, maybe week 0 had no nav?
            logging.warning(f"No available week offsets found for user {username}, student {student_id}. Returning empty list.")
            return []
        # 4. Call the Multi-Week Service Function
        # Pass the shared client explicitly as required by the service function signature
        all_weeks_data = await get_multiple_weeks(
            username=username,
            student_id=student_id,
            cookies_str=cookie,
            requested_offsets=available_offsets,
            shared_client=http_client # Pass the shared client
        )
        # 5. Return the result from the service
        return all_weeks_data
    except HTTPException as e:
        # Re-raise HTTPExceptions raised by setup or service layer
        raise e
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        url = e.request.url
        detail = f"Glasir backend error ({status}) accessing {url} during multi-week fetch."
        raise HTTPException(status_code=502, detail=detail)
    except httpx.RequestError as e:
        url = e.request.url
        detail = f"Network error communicating with Glasir ({url}) during multi-week fetch."
        raise HTTPException(status_code=504, detail=detail)
    except Exception as e:
        logging.error(f"Unexpected internal error in /weeks/all for user {username}", exc_info=True) # Log full traceback
        raise HTTPException(status_code=500, detail=f"An unexpected internal server error occurred ({type(e).__name__}).") # Refined detail
    # No finally block needed for client closure due to lifespan management
@app.get(
    "/profiles/{username}/weeks/current_forward",
    response_model=List[TimetableData],
    response_model_exclude_none=True,
    summary="Get timetable for current and future weeks",
    tags=["Timetable"]
)
async def get_current_and_forward_weeks(
    request: Request,
    username: Annotated[str, Path(description="Identifier for the user profile")],
    student_id: Annotated[str, Query(description="The student's unique ID from Glasir")],
    cookie: Annotated[str | None, Header(description="Glasir authentication cookies")] = None
):
    if not cookie:
        raise HTTPException(status_code=400, detail="Cookie header is required.")
    if not student_id:
        raise HTTPException(status_code=400, detail="student_id query parameter is required.")
    http_client: httpx.AsyncClient = request.app.state.http_client
    extractor: Optional[TimetableExtractor] = None
    try:
        # 1. Initial Setup
        setup_result = await _setup_extractor(cookie, http_client)
        if setup_result is None:
            raise HTTPException(status_code=502, detail="Failed initial setup with Glasir.")
        extractor, teacher_map, lname = setup_result
        # 2. Fetch Base Week HTML
        base_week_html = await extractor.fetch_week_html(offset=0, student_id=student_id)
        if not base_week_html:
            raise HTTPException(status_code=404, detail="Could not fetch base week (offset 0).")
        # 3. Parse Available Offsets
        available_offsets = parse_available_offsets(base_week_html)
        if not available_offsets:
            logging.warning(f"No available week offsets found for user {username}, student {student_id}. Returning empty list.")
            return []
        # 4. Filter Offsets (Keep 0 and positive values)
        forward_offsets = [offset for offset in available_offsets if offset >= 0]
        if not forward_offsets:
             logging.info(f"No current or future week offsets found (>=0) for user {username}, student {student_id}. Returning empty list.")
             return []
        logging.info(f"Filtered offsets for current/forward: {forward_offsets}")
        # 5. Call the Multi-Week Service Function with filtered offsets
        forward_weeks_data = await get_multiple_weeks(
            username=username,
            student_id=student_id,
            cookies_str=cookie,
            requested_offsets=forward_offsets, # Use filtered list
            shared_client=http_client
        )
        # 6. Return the result
        return forward_weeks_data
    except HTTPException as e:
        raise e
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        url = e.request.url
        detail = f"Glasir backend error ({status}) accessing {url} during current/forward fetch."
        raise HTTPException(status_code=502, detail=detail)
    except httpx.RequestError as e:
        url = e.request.url
        detail = f"Network error communicating with Glasir ({url}) during current/forward fetch."
        raise HTTPException(status_code=504, detail=detail)
    except Exception as e:
        logging.error(f"Unexpected internal error in /weeks/current_forward for user {username}", exc_info=True) # Log full traceback
        raise HTTPException(status_code=500, detail=f"An unexpected internal server error occurred ({type(e).__name__}).") # Refined detail
# --- Phase 4 Endpoint: N Future Weeks ---
@app.get(
    "/profiles/{username}/weeks/forward/{count}",
    response_model=List[TimetableData],
    response_model_exclude_none=True,
    summary="Get timetable for current week and N future weeks",
    tags=["Timetable"]
)
async def get_n_forward_weeks(
    request: Request,
    username: Annotated[str, Path(description="Identifier for the user profile")],
    count: Annotated[int, Path(description="Number of future weeks to fetch (0 = current week only)")],
    student_id: Annotated[str, Query(description="The student's unique ID from Glasir")],
    cookie: Annotated[str | None, Header(description="Glasir authentication cookies")] = None
):
    if not cookie:
        raise HTTPException(status_code=400, detail="Cookie header is required.")
    if not student_id:
        raise HTTPException(status_code=400, detail="student_id query parameter is required.")
    if count < 0: # Corrected line
        raise HTTPException(status_code=400, detail="Count parameter cannot be negative.")
    http_client: httpx.AsyncClient = request.app.state.http_client
    try:
        # 1. Generate the list of requested offsets
        requested_offsets = list(range(count + 1)) # [0, 1, ..., count]
        logging.info(f"Requesting offsets for N forward weeks ({count}): {requested_offsets}")
        # 2. Call the Multi-Week Service Function
        # No need to fetch base week first, as we explicitly define the offsets
        n_forward_weeks_data = await get_multiple_weeks(
            username=username,
            student_id=student_id,
            cookies_str=cookie,
            requested_offsets=requested_offsets,
            shared_client=http_client
        )
        # 3. Return the result
        return n_forward_weeks_data
    except HTTPException as e:
        # Re-raise HTTPExceptions (e.g., from validation or service layer)
        raise e
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        url = e.request.url
        detail = f"Glasir backend error ({status}) accessing {url} during N forward weeks fetch."
        raise HTTPException(status_code=502, detail=detail)
    except httpx.RequestError as e:
        url = e.request.url
        detail = f"Network error communicating with Glasir ({url}) during N forward weeks fetch."
        raise HTTPException(status_code=504, detail=detail)
    except Exception as e:
        logging.error(f"Unexpected internal error in /weeks/forward/{count} for user {username}", exc_info=True) # Log full traceback
        raise HTTPException(status_code=500, detail=f"An unexpected internal server error occurred ({type(e).__name__}).") # Refined detail
# --- Phase 1 Endpoint (Now defined AFTER specific Phase 3 endpoints) ---
@app.get(
    "/profiles/{username}/weeks/{offset}",
    response_model=TimetableData, # Automatically validates/serializes output
    response_model_exclude_none=True, # Don't include None values in JSON response
    summary="Get timetable for a specific week offset",
    tags=["Timetable"] # Add a tag for better OpenAPI docs organization
)
async def get_week_by_offset(
    request: Request, # Inject Request to access app state
    username: Annotated[str, Path(description="Identifier for the user profile (e.g., username used for login)")],
    offset: Annotated[int, Path(description="Week offset relative to the current week (0=current, 1=next, -1=previous)")],
    student_id: Annotated[str, Query(description="The student's unique ID obtained from Glasir (often found in cookies or profile page)")],
    cookie: Annotated[str | None, Header(description="Glasir authentication cookies as a single string (e.g., 'ASP.NET_SessionId=...; studentid=...')")] = None
):
    if not cookie:
        raise HTTPException(status_code=400, detail="Cookie header is required for authentication.")
    if not student_id:
         raise HTTPException(status_code=400, detail="student_id query parameter is required.")
    # Access the shared client from app state
    http_client: httpx.AsyncClient = request.app.state.http_client
    extractor: Optional[TimetableExtractor] = None # Only need extractor now
    try:
        # Setup extractor using the shared client and get teacher map
        # _setup_extractor now accepts the shared client
        setup_result = await _setup_extractor(cookie, http_client)
        if setup_result is None:
            raise HTTPException(status_code=502, detail="Failed initial setup with Glasir: Could not parse cookies, get session parameters, or fetch teacher map.")
        # Unpack the result, ignoring the third value (lname) which is handled by the extractor now
        extractor, teacher_map, _ = setup_result
        # Fetch and process the specific week's timetable data
        processed_data = await _fetch_and_process_week(offset, extractor, student_id, teacher_map)
        if processed_data is None:
            raise HTTPException(status_code=404, detail=f"Timetable data not found or failed to process for offset {offset}. The offset might be invalid or data unavailable.")
        processed_data['student_info'] = {'student_id': student_id, 'username': username}
        return TimetableData(**processed_data)
    except httpx.HTTPStatusError as e:
         status = e.response.status_code
         url = e.request.url
         detail = f"Glasir backend returned an error ({status}) when accessing URL: {url}. Check if Glasir is down or if the request parameters (offset, student_id) are valid."
         raise HTTPException(status_code=502, detail=detail)
    except httpx.RequestError as e:
         url = e.request.url
         detail = f"Network error occurred while trying to communicate with Glasir URL: {url}. Check network connectivity and Glasir server status."
         raise HTTPException(status_code=504, detail=detail)
    except Exception as e:
         logging.error(f"Unexpected internal error in /weeks/{offset} for user {username}", exc_info=True)
         raise HTTPException(status_code=500, detail=f"An unexpected internal server error occurred ({type(e).__name__}).")
        #     pass
````

## File: glasir_api/README.md
````markdown
# Glasir Timetable API

## Purpose

This API provides endpoints to extract and retrieve timetable data from the Glasir online system.

## Setup

It is recommended to use a virtual environment.

1.  **Create a virtual environment (optional):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```
2.  **Install dependencies:**
    ```bash
    pip install -r glasir_api/requirements.txt
    ```

## Running the API

To start the API server, run the following command from the project's root directory (`V0.3`):

```bash
uvicorn glasir_api.main:app --host 0.0.0.0 --port 8000
```

For development, you can use the `--reload` flag to automatically restart the server when code changes are detected:

```bash
uvicorn glasir_api.main:app --host 0.0.0.0 --port 8000 --reload
```

## Authentication Helper

The `get_glasir_auth.py` script, located in the parent directory (`V0.3`), helps obtain the necessary authentication details (`Cookie` header and `student_id`) required by the API endpoints.

Run the script using:

```bash
python ../get_glasir_auth.py --force-login
```

This will prompt you for your Glasir username and password and save the required `Cookie` string and `student_id` to files (`glasir_auth_tool/cookies.json` and `glasir_auth_tool/student_id.txt` respectively) in the `glasir_auth_tool` directory. You will need these values for the API requests.

## API Endpoints

The following endpoints are available:

### Get Timetable for a Specific Week Offset

*   **Method:** `GET`
*   **Path:** `/profiles/{username}/weeks/{offset}`
*   **Path Parameters:**
    *   `username`: Your Glasir username (e.g., `rm3112z9`).
    *   `offset`: The week offset relative to the current week (e.g., `0` for the current week, `-1` for the previous week, `1` for the next week).
*   **Query Parameters:**
    *   `student_id`: Your Glasir student ID.
*   **Required Headers:**
    *   `Cookie`: The authentication cookie string obtained from `get_glasir_auth.py`.
*   **Example `curl`:**
    ```bash
    curl -X GET -H "Cookie: YOUR_COOKIE_STRING" "http://localhost:8000/profiles/YOUR_USERNAME/weeks/0?student_id=YOUR_STUDENT_ID"
    ```
*   **Response:** A JSON object representing the `TimetableData` for the specified week.

### Get Timetable for All Available Weeks

*   **Method:** `GET`
*   **Path:** `/profiles/{username}/weeks/all`
*   **Path Parameters:**
    *   `username`: Your Glasir username.
*   **Query Parameters:**
    *   `student_id`: Your Glasir student ID.
*   **Required Headers:**
    *   `Cookie`: The authentication cookie string.
*   **Example `curl`:**
    ```bash
    curl -X GET -H "Cookie: YOUR_COOKIE_STRING" "http://localhost:8000/profiles/YOUR_USERNAME/weeks/all?student_id=YOUR_STUDENT_ID"
    ```
*   **Response:** A JSON array containing `TimetableData` objects for all weeks found.

### Get Timetable from Current Week Forward

*   **Method:** `GET`
*   **Path:** `/profiles/{username}/weeks/current_forward`
*   **Path Parameters:**
    *   `username`: Your Glasir username.
*   **Query Parameters:**
    *   `student_id`: Your Glasir student ID.
*   **Required Headers:**
    *   `Cookie`: The authentication cookie string.
*   **Example `curl`:**
    ```bash
    curl -X GET -H "Cookie: YOUR_COOKIE_STRING" "http://localhost:8000/profiles/YOUR_USERNAME/weeks/current_forward?student_id=YOUR_STUDENT_ID"
    ```
*   **Response:** A JSON array containing `TimetableData` objects starting from the current week.

### Get Timetable for a Specific Number of Weeks Forward

*   **Method:** `GET`
*   **Path:** `/profiles/{username}/weeks/forward/{count}`
*   **Path Parameters:**
    *   `username`: Your Glasir username.
    *   `count`: The number of weeks forward from the current week to retrieve (inclusive of the current week).
*   **Query Parameters:**
    *   `student_id`: Your Glasir student ID.
*   **Required Headers:**
    *   `Cookie`: The authentication cookie string.
*   **Example `curl`:**
    ```bash
    curl -X GET -H "Cookie: YOUR_COOKIE_STRING" "http://localhost:8000/profiles/YOUR_USERNAME/weeks/forward/5?student_id=YOUR_STUDENT_ID"
    ```
*   **Response:** A JSON array containing `TimetableData` objects for the specified number of weeks forward.
````

## File: glasir_api/requirements.txt
````
absl-py==2.2.0
accelerate==0.32.1
aiofiles==24.1.0
aiohappyeyeballs==2.4.6
aiohttp==3.8.5
aiosignal==1.3.2
aiosqlite==0.21.0
albucore==0.0.23
albumentations==1.4.24
annotated-types==0.7.0
antlr4-python3-runtime==4.7.2
anyio==4.8.0
appdirs==1.4.4
appnope==0.1.4
argon2-cffi==23.1.0
argon2-cffi-bindings==21.2.0
arrow==1.3.0
asttokens==3.0.0
async-lru==2.0.5
async-timeout==4.0.3
asyncio==3.4.3
attrs==25.1.0
autoflake==2.3.1
babel==2.17.0
backoff==2.2.1
base64io==1.0.3
beautifulsoup4==4.12.2
bitsandbytes==0.42.0
black==25.1.0
bleach==6.2.0
blinker==1.9.0
Brotli==1.1.0
browserbase==1.2.0
cachetools==5.5.2
cairocffi==1.7.1
CairoSVG==2.7.1
certifi==2025.1.31
cffi==1.17.1
chardet==3.0.4
charset-normalizer==3.4.1
# Editable install with no version control (chemvlm-optimization==0.1.0)
-e /Users/rokur/Documents/Downloader
chess==1.11.2
click==8.1.8
click-spinner==0.1.10
cloudscraper==1.2.71
cmake==3.31.6
comm==0.2.2
contourpy==1.3.1
coverage==7.8.0
cryptography==41.0.7
cssselect2==0.8.0
cycler==0.12.1
Cython==3.0.12
dataclasses-json==0.6.7
datasets==3.3.2
debugpy==1.8.14
decorator==5.2.1
defusedxml==0.7.1
dep-logic==0.4.11
depender==0.1.2
Deprecated==1.2.18
diffusers==0.32.2
dill==0.3.8
distlib==0.3.9
distro==1.9.0
docstring_parser==0.16
easyocr==1.7.2
ecdsa==0.19.1
einops==0.8.1
emoji==2.14.1
entmax==1.3
eval_type_backport==0.2.2
exceptiongroup==1.2.2
executing==2.2.0
faiss-cpu==1.10.0
fastapi==0.109.0
fastjsonschema==2.21.1
ffmpeg==1.4
ffmpy==0.5.0
filelock==3.17.0
filetype==1.2.0
findpython==0.6.3
Flask==3.1.0
Flask-WTF==1.2.2
flatbuffers==25.2.10
fonttools==4.56.0
fqdn==1.5.1
frozenlist==1.5.0
fsspec==2024.12.0
git-lfs==1.6
google-ai-generativelanguage==0.4.0
google-api-core==2.24.1
google-auth==2.38.0
google-cloud-aiplatform==1.88.0
google-cloud-bigquery==3.31.0
google-cloud-core==2.4.2
google-cloud-resource-manager==1.14.2
google-cloud-storage==2.19.0
google-cloud-translate==3.20.1
google-crc32c==1.7.1
google-generativeai==0.3.2
google-resumable-media==2.7.2
googleapis-common-protos==1.59.1
googletrans==4.0.0rc1
gradio==5.23.0
gradio_client==1.8.0
graphviz==0.20.3
greenlet==3.1.1
groovy==0.1.2
grpc-google-iam-v1==0.14.0
grpcio==1.70.0
grpcio-status==1.63.0rc1
h11==0.14.0
h2==3.2.0
hf_transfer==0.1.9
hishel==0.1.2
hpack==3.0.0
hstspreload==2025.1.1
html5lib==1.1
httpcore==1.0.7
httpx==0.26.0
httpx-sse==0.4.0
huggingface-hub==0.29.1
hyperframe==5.2.0
icalendar==5.0.11
idna==2.10
imageio==2.37.0
importlib_metadata==8.6.1
iniconfig==2.0.0
installer==0.7.0
ipykernel==6.29.5
ipython==8.35.0
ipywidgets==8.1.6
isoduration==20.11.0
isort==6.0.1
itsdangerous==2.2.0
jax==0.5.3
jaxlib==0.5.3
jedi==0.19.2
Jinja2==3.1.5
jiter==0.8.2
joblib==1.4.2
json5==0.12.0
jsonpatch==1.33
jsonpointer==3.0.0
jsonschema==4.23.0
jsonschema-specifications==2024.10.1
jupyter==1.1.1
jupyter-console==6.6.3
jupyter-events==0.12.0
jupyter-lsp==2.2.5
jupyter_client==8.6.3
jupyter_core==5.7.2
jupyter_server==2.15.0
jupyter_server_terminals==0.5.3
jupyterlab==4.4.0
jupyterlab_pygments==0.3.0
jupyterlab_server==2.27.3
jupyterlab_widgets==3.0.14
keyboard==0.13.5
kiwisolver==1.4.8
langchain==0.3.23
langchain-community==0.3.21
langchain-core==0.3.51
langchain-google-vertexai==2.0.20
langchain-text-splitters==0.3.8
langdetect==1.0.9
langsmith==0.3.11
latex2sympy2==1.9.1
lazy_loader==0.4
Levenshtein==0.27.1
lightning==2.5.0.post0
lightning-utilities==0.12.0
line_profiler==4.2.0
lxml==5.3.1
Markdown==3.7
markdown-it-py==3.0.0
MarkupSafe==3.0.2
marshmallow==3.26.1
matplotlib==3.10.1
matplotlib-inline==0.1.7
mdit-py-plugins==0.4.2
mdurl==0.1.2
mediapipe==0.10.21
mistune==3.1.3
ml_dtypes==0.5.1
mlx==0.23.1
mlx-lm==0.21.4
MouseInfo==0.1.3
mpmath==1.3.0
msgpack==1.1.0
mss==10.0.0
multidict==6.1.0
multiprocess==0.70.16
munch==4.0.0
mypy-extensions==1.0.0
nbclient==0.10.2
nbconvert==7.16.6
nbformat==5.10.4
nest-asyncio==1.6.0
networkx==3.4.2
ninja==1.11.1.3
nltk==3.9.1
notebook==7.4.0
notebook_shim==0.2.4
nougat-ocr==0.1.17
npm==0.1.1
numpy==1.26.4
olefile==0.47
openai==1.65.2
opencv-contrib-python==4.11.0.86
opencv-python==4.8.1.78
opencv-python-headless==4.11.0.86
opentelemetry-api==1.31.1
opentelemetry-exporter-jaeger==1.21.0
opentelemetry-exporter-jaeger-proto-grpc==1.21.0
opentelemetry-exporter-jaeger-thrift==1.21.0
opentelemetry-instrumentation==0.52b1
opentelemetry-instrumentation-httpx==0.52b1
opentelemetry-sdk==1.31.1
opentelemetry-semantic-conventions==0.52b1
opentelemetry-util-http==0.52b1
opt_einsum==3.4.0
optimum==1.24.0
optional-django==0.1.0
orjson==3.9.10
outcome==1.3.0.post0
overrides==7.7.0
packaging==24.2
pandas==2.2.3
pandocfilters==1.5.1
parso==0.8.4
pathlib==1.0.1
pathspec==0.12.1
pbs-installer==2025.3.17
pdf2image==1.17.0
# Editable install with no version control (pdf_splitter_modular==0.1.0)
-e /Users/rokur/Documents/Alisfrøði solve/pdf_splitter_modular
pdfminer.six==20240706
pdm==2.23.0
peft==0.14.0
pexpect==4.9.0
Pillow==10.1.0
pix2tex==0.1.4
pixi==1.0.1
pixiv-api==0.3.7
platformdirs==4.3.6
playwright==1.51.0
pluggy==1.5.0
praw==7.8.1
prawcore==2.4.0
prometheus_client==0.21.1
prompt_toolkit==3.0.50
propcache==0.3.0
proto-plus==1.26.0
protobuf==4.25.6
psutil==7.0.0
ptyprocess==0.7.0
pure_eval==0.2.3
py==1.11.0
pyarrow==19.0.1
pyasn1==0.6.1
pyasn1_modules==0.4.1
PyAutoGUI==0.9.54
pyclipper==1.3.0.post6
pycparser==2.22
pydantic==2.5.3
pydantic-settings==2.8.1
pydantic_core==2.14.6
pydeps==3.0.1
pydub==0.25.1
pydyf==0.11.0
pyee==12.1.1
pyflakes==3.3.2
pyftrace==0.3.1
PyGetWindow==0.0.9
Pygments==2.19.1
PyJWT==2.10.1
PyMsgBox==1.0.9
PyMuPDF==1.25.3
pynput==1.8.0
pyobjc==11.0
pyobjc-core==11.0
pyobjc-framework-Accessibility==11.0
pyobjc-framework-Accounts==11.0
pyobjc-framework-AddressBook==11.0
pyobjc-framework-AdServices==11.0
pyobjc-framework-AdSupport==11.0
pyobjc-framework-AppleScriptKit==11.0
pyobjc-framework-AppleScriptObjC==11.0
pyobjc-framework-ApplicationServices==11.0
pyobjc-framework-AppTrackingTransparency==11.0
pyobjc-framework-AudioVideoBridging==11.0
pyobjc-framework-AuthenticationServices==11.0
pyobjc-framework-AutomaticAssessmentConfiguration==11.0
pyobjc-framework-Automator==11.0
pyobjc-framework-AVFoundation==11.0
pyobjc-framework-AVKit==11.0
pyobjc-framework-AVRouting==11.0
pyobjc-framework-BackgroundAssets==11.0
pyobjc-framework-BrowserEngineKit==11.0
pyobjc-framework-BusinessChat==11.0
pyobjc-framework-CalendarStore==11.0
pyobjc-framework-CallKit==11.0
pyobjc-framework-Carbon==11.0
pyobjc-framework-CFNetwork==11.0
pyobjc-framework-Cinematic==11.0
pyobjc-framework-ClassKit==11.0
pyobjc-framework-CloudKit==11.0
pyobjc-framework-Cocoa==11.0
pyobjc-framework-Collaboration==11.0
pyobjc-framework-ColorSync==11.0
pyobjc-framework-Contacts==11.0
pyobjc-framework-ContactsUI==11.0
pyobjc-framework-CoreAudio==11.0
pyobjc-framework-CoreAudioKit==11.0
pyobjc-framework-CoreBluetooth==11.0
pyobjc-framework-CoreData==11.0
pyobjc-framework-CoreHaptics==11.0
pyobjc-framework-CoreLocation==11.0
pyobjc-framework-CoreMedia==11.0
pyobjc-framework-CoreMediaIO==11.0
pyobjc-framework-CoreMIDI==11.0
pyobjc-framework-CoreML==11.0
pyobjc-framework-CoreMotion==11.0
pyobjc-framework-CoreServices==11.0
pyobjc-framework-CoreSpotlight==11.0
pyobjc-framework-CoreText==11.0
pyobjc-framework-CoreWLAN==11.0
pyobjc-framework-CryptoTokenKit==11.0
pyobjc-framework-DataDetection==11.0
pyobjc-framework-DeviceCheck==11.0
pyobjc-framework-DeviceDiscoveryExtension==11.0
pyobjc-framework-DictionaryServices==11.0
pyobjc-framework-DiscRecording==11.0
pyobjc-framework-DiscRecordingUI==11.0
pyobjc-framework-DiskArbitration==11.0
pyobjc-framework-DVDPlayback==11.0
pyobjc-framework-EventKit==11.0
pyobjc-framework-ExceptionHandling==11.0
pyobjc-framework-ExecutionPolicy==11.0
pyobjc-framework-ExtensionKit==11.0
pyobjc-framework-ExternalAccessory==11.0
pyobjc-framework-FileProvider==11.0
pyobjc-framework-FileProviderUI==11.0
pyobjc-framework-FinderSync==11.0
pyobjc-framework-FSEvents==11.0
pyobjc-framework-GameCenter==11.0
pyobjc-framework-GameController==11.0
pyobjc-framework-GameKit==11.0
pyobjc-framework-GameplayKit==11.0
pyobjc-framework-HealthKit==11.0
pyobjc-framework-ImageCaptureCore==11.0
pyobjc-framework-InputMethodKit==11.0
pyobjc-framework-InstallerPlugins==11.0
pyobjc-framework-InstantMessage==11.0
pyobjc-framework-Intents==11.0
pyobjc-framework-IntentsUI==11.0
pyobjc-framework-IOBluetooth==11.0
pyobjc-framework-IOBluetoothUI==11.0
pyobjc-framework-IOSurface==11.0
pyobjc-framework-iTunesLibrary==11.0
pyobjc-framework-KernelManagement==11.0
pyobjc-framework-LatentSemanticMapping==11.0
pyobjc-framework-LaunchServices==11.0
pyobjc-framework-libdispatch==11.0
pyobjc-framework-libxpc==11.0
pyobjc-framework-LinkPresentation==11.0
pyobjc-framework-LocalAuthentication==11.0
pyobjc-framework-LocalAuthenticationEmbeddedUI==11.0
pyobjc-framework-MailKit==11.0
pyobjc-framework-MapKit==11.0
pyobjc-framework-MediaAccessibility==11.0
pyobjc-framework-MediaExtension==11.0
pyobjc-framework-MediaLibrary==11.0
pyobjc-framework-MediaPlayer==11.0
pyobjc-framework-MediaToolbox==11.0
pyobjc-framework-Metal==11.0
pyobjc-framework-MetalFX==11.0
pyobjc-framework-MetalKit==11.0
pyobjc-framework-MetalPerformanceShaders==11.0
pyobjc-framework-MetalPerformanceShadersGraph==11.0
pyobjc-framework-MetricKit==11.0
pyobjc-framework-MLCompute==11.0
pyobjc-framework-ModelIO==11.0
pyobjc-framework-MultipeerConnectivity==11.0
pyobjc-framework-NaturalLanguage==11.0
pyobjc-framework-NetFS==11.0
pyobjc-framework-Network==11.0
pyobjc-framework-NetworkExtension==11.0
pyobjc-framework-NotificationCenter==11.0
pyobjc-framework-OpenDirectory==11.0
pyobjc-framework-OSAKit==11.0
pyobjc-framework-OSLog==11.0
pyobjc-framework-PassKit==11.0
pyobjc-framework-PencilKit==11.0
pyobjc-framework-PHASE==11.0
pyobjc-framework-Photos==11.0
pyobjc-framework-PhotosUI==11.0
pyobjc-framework-PreferencePanes==11.0
pyobjc-framework-PushKit==11.0
pyobjc-framework-Quartz==11.0
pyobjc-framework-QuickLookThumbnailing==11.0
pyobjc-framework-ReplayKit==11.0
pyobjc-framework-SafariServices==11.0
pyobjc-framework-SafetyKit==11.0
pyobjc-framework-SceneKit==11.0
pyobjc-framework-ScreenCaptureKit==11.0
pyobjc-framework-ScreenSaver==11.0
pyobjc-framework-ScreenTime==11.0
pyobjc-framework-ScriptingBridge==11.0
pyobjc-framework-SearchKit==11.0
pyobjc-framework-Security==11.0
pyobjc-framework-SecurityFoundation==11.0
pyobjc-framework-SecurityInterface==11.0
pyobjc-framework-SensitiveContentAnalysis==11.0
pyobjc-framework-ServiceManagement==11.0
pyobjc-framework-SharedWithYou==11.0
pyobjc-framework-SharedWithYouCore==11.0
pyobjc-framework-ShazamKit==11.0
pyobjc-framework-Social==11.0
pyobjc-framework-SoundAnalysis==11.0
pyobjc-framework-Speech==11.0
pyobjc-framework-SpriteKit==11.0
pyobjc-framework-StoreKit==11.0
pyobjc-framework-Symbols==11.0
pyobjc-framework-SyncServices==11.0
pyobjc-framework-SystemConfiguration==11.0
pyobjc-framework-SystemExtensions==11.0
pyobjc-framework-ThreadNetwork==11.0
pyobjc-framework-UniformTypeIdentifiers==11.0
pyobjc-framework-UserNotifications==11.0
pyobjc-framework-UserNotificationsUI==11.0
pyobjc-framework-VideoSubscriberAccount==11.0
pyobjc-framework-VideoToolbox==11.0
pyobjc-framework-Virtualization==11.0
pyobjc-framework-Vision==11.0
pyobjc-framework-WebKit==11.0
pypandoc==1.15
pyparsing==3.2.1
pypdf==5.4.0
PyPDF2==3.0.1
pypdfium2==4.30.0
pyperclip==1.9.0
pyphen==0.17.2
pyproject_hooks==1.2.0
PyQt5==5.15.11
PyQt5-Qt5==5.15.16
PyQt5_sip==12.17.0
PyQt6==6.8.1
PyQt6-Qt6==6.8.2
PyQt6-WebEngine==6.8.0
PyQt6-WebEngine-Qt6==6.8.2
PyQt6_sip==13.10.0
PyRect==0.2.0
PyScreeze==1.0.1
PySide6==6.8.2.1
PySide6_Addons==6.8.2.1
PySide6_Essentials==6.8.2.1
PySimpleGUI==5.0.8.3
PySocks==1.7.1
pytesseract==0.3.10
pytest==8.3.5
pytest-asyncio==0.26.0
pytest-asyncio-cooperative==0.37.0
pytest-cov==6.1.1
python-bidi==0.6.6
python-chess==1.999
python-dateutil==2.9.0.post0
python-docx==1.1.2
python-dotenv==1.0.0
python-iso639==2025.2.18
python-jose==3.3.0
python-json-logger==3.3.0
python-Levenshtein==0.27.1
python-magic==0.4.27
python-markdown-math==0.8
python-multipart==0.0.20
python-oxmsg==0.0.2
python-slugify==8.0.4
pytorch-lightning==2.5.0.post0
pyttsx3==2.98
pytube==12.1.2
pytweening==1.2.0
pytz==2025.1
PyYAML==6.0.2
pyzmq==26.4.0
RapidFuzz==3.12.2
rdkit==2024.9.5
# Editable install with no version control (reddit-fetcher==0.1.0)
-e /Users/rokur/Desktop/AI Shorts/Reddit fetcher
referencing==0.36.2
regex==2024.11.6
requests==2.31.0
requests-toolbelt==1.0.0
resolvelib==1.1.0
retry==0.9.2
rfc3339-validator==0.1.4
rfc3986==1.5.0
rfc3986-validator==0.1.1
rich==13.9.4
rpds-py==0.24.0
rsa==4.9
ruamel.yaml==0.18.10
ruamel.yaml.clib==0.2.12
rubicon-objc==0.5.0
ruff==0.11.2
rumps==0.4.0
safehttpx==0.1.6
safetensors==0.5.3
scikit-image==0.25.2
scipy==1.15.2
sconf==0.2.5
screeninfo==0.8.1
selenium==4.30.0
semantic-version==2.10.0
Send2Trash==1.8.3
sentencepiece==0.2.0
shapely==2.0.7
shellingham==1.5.4
shiboken6==6.8.2.1
simsimd==6.2.1
six==1.17.0
snakeviz==2.2.2
sniffio==1.3.1
socksio==1.0.0
sortedcontainers==2.4.0
sounddevice==0.5.1
soupsieve==2.6
SQLAlchemy==2.0.25
stack-data==0.6.3
starlette==0.35.1
stdlib-list==0.11.1
stringzilla==3.12.2
surya-ocr==0.13.0
sympy==1.13.1
tenacity==9.0.0
terminado==0.18.1
text-unidecode==1.3
thrift==0.21.0
tifffile==2025.3.13
tiktoken==0.9.0
timm==0.9.12
tinycss2==1.4.0
tinyhtml5==2.0.0
tk==0.1.0
tokenizers==0.21.0
tomli==2.2.1
tomlkit==0.13.2
torch==2.6.0
torchaudio==2.6.0
torchmetrics==1.6.2
torchvision==0.21.0
tornado==6.4.2
tqdm==4.67.1
traitlets==5.14.3
transformers==4.49.0
trio==0.29.0
trio-websocket==0.12.2
truststore==0.10.1
ttkthemes==3.2.2
typer==0.15.2
types-python-dateutil==2.9.0.20241206
typing-inspect==0.9.0
typing-inspection==0.4.0
typing_extensions==4.12.2
tzdata==2025.1
unearth==0.17.3
unstructured==0.17.2
unstructured-client==0.32.3
update-checker==0.18.0
uri-template==1.3.0
urllib3==2.3.0
uv==0.6.10
uvicorn==0.27.0
uvloop==0.21.0
validators==0.34.0
virtualenv==20.30.0
vulture==2.14
wcwidth==0.2.13
weasyprint==65.0
webcolors==24.11.1
webencodings==0.5.1
websocket-client==1.8.0
websockets==15.0.1
Werkzeug==3.1.3
widgetsnbextension==4.0.14
wrapt==1.17.2
wsproto==1.2.0
WTForms==3.2.1
x-transformers==0.15.0
xxhash==3.5.0
yappi==1.6.10
yarl==1.18.3
yt-dlp==2025.2.19
zipp==3.21.0
zopfli==0.2.3.post1
zstandard==0.23.0
````

## File: glasir_auth_tool/get_auth.py
````python
import asyncio
import re
import json
import os
import argparse
from pathlib import Path
from playwright.async_api import async_playwright, Error as PlaywrightError
import httpx
import aiofiles
SCRIPT_DIR = Path(__file__).parent.resolve()
USERNAME_FILE = SCRIPT_DIR / "username.txt"
COOKIES_FILE = SCRIPT_DIR / "cookies.json"
STUDENT_ID_FILE = SCRIPT_DIR / "student_id.txt"
_RE_GUID = re.compile(
    r"[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}"
)
async def load_data():
    username = None
    cookies = None
    student_id = None
    if USERNAME_FILE.exists():
        try:
            async with aiofiles.open(USERNAME_FILE, "r") as f:
                username = (await f.read()).strip()
        except Exception as e:
            print(f"Warning: Could not read username file: {e}")
    if COOKIES_FILE.exists():
        try:
            async with aiofiles.open(COOKIES_FILE, "r") as f:
                cookies = json.loads(await f.read())
        except Exception as e:
            print(f"Warning: Could not read or parse cookies file: {e}")
    if STUDENT_ID_FILE.exists():
        try:
            async with aiofiles.open(STUDENT_ID_FILE, "r") as f:
                student_id = (await f.read()).strip()
        except Exception as e:
            print(f"Warning: Could not read student ID file: {e}")
    return username, cookies, student_id
async def save_data(username: str, cookies: list, student_id: str):
    try:
        async with aiofiles.open(USERNAME_FILE, "w") as f:
            await f.write(username)
    except Exception as e:
        print(f"Error saving username: {e}")
    try:
        async with aiofiles.open(COOKIES_FILE, "w") as f:
            await f.write(json.dumps(cookies, indent=2))
    except Exception as e:
        print(f"Error saving cookies: {e}")
    try:
        async with aiofiles.open(STUDENT_ID_FILE, "w") as f:
            await f.write(student_id)
    except Exception as e:
        print(f"Error saving student ID: {e}")
async def perform_playwright_login():
    username = None
    cookies = None
    student_id = None
    async with async_playwright() as p:
        browser = None
        try:
            username_input = input("Please enter your Glasir username: ").strip()
            if not username_input:
                print("Username cannot be empty. Exiting.")
                return None, None, None
            print("Launching browser...")
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()
            print("Navigating to Glasir login page (https://tg.glasir.fo)...")
            await page.goto("https://tg.glasir.fo", timeout=60000)
            print("\n" + "="*50)
            print("ACTION REQUIRED:")
            print("Please log in to Glasir in the browser window.")
            print("After logging in, navigate to your timetable page.")
            print("Waiting for login and navigation...")
            print("="*50 + "\n")
            await page.wait_for_url("https://tg.glasir.fo/132n/**", timeout=0)
            print("Timetable URL detected.")
            await page.wait_for_selector("table.time_8_16", state="visible", timeout=0)
            print("Timetable table detected. Extracting data...")
            cookies = await context.cookies()
            content = await page.content()
            guid_match = _RE_GUID.search(content)
            student_id = guid_match.group(0).strip() if guid_match else None
            if cookies and student_id:
                print("Playwright login and data extraction successful.")
                username = username_input
                await save_data(username, cookies, student_id)
            else:
                print("Error: Could not extract cookies or student ID after login.")
                return None, None, None
        except PlaywrightError as e:
            print(f"\nAn error occurred during Playwright operation: {e}")
            return None, None, None
        except Exception as e:
            print(f"\nAn unexpected error occurred during Playwright login: {e}")
            return None, None, None
        finally:
            if browser:
                await browser.close()
            print("Browser closed.")
    return username, cookies, student_id
async def make_api_call(username: str, cookies: list, student_id: str, endpoint: str):
    if not all([username, cookies, student_id]):
        print("Missing data for API call. Skipping.")
        return
    print("\n" + "="*50)
    print("Attempting API Call...")
    print("="*50)
    cookie_string = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
    base_api_url = f"http://127.0.0.1:8000/profiles/{username}"
    if endpoint == "week/0":
        api_url = f"{base_api_url}/weeks/0?student_id={student_id}"
        output_filename = SCRIPT_DIR / "api_response_week_0.json"
    elif endpoint == "weeks/all":
        api_url = f"{base_api_url}/weeks/all?student_id={student_id}"
        output_filename = SCRIPT_DIR / "api_response_all.json"
    elif endpoint == "weeks/current_forward":
        api_url = f"{base_api_url}/weeks/current_forward?student_id={student_id}"
        output_filename = SCRIPT_DIR / "api_response_current_forward.json"
    elif endpoint.startswith("weeks/forward/"):
        try:
            count_str = endpoint.split('/')[-1]
            count = int(count_str)
            if count < 0:
                print("Error: Count for forward weeks cannot be negative.")
                return
            api_url = f"{base_api_url}/weeks/forward/{count}?student_id={student_id}"
            output_filename = SCRIPT_DIR / f"api_response_forward_{count}.json"
        except (ValueError, IndexError):
            print(f"Error: Invalid format for forward weeks endpoint: {endpoint}")
            return
    else:
        print(f"Error: Unknown endpoint '{endpoint}'.")
        return
    headers = {"Cookie": cookie_string}
    print(f"Target Endpoint: {endpoint}")
    print(f"Output File: {output_filename}")
    try:
        async with httpx.AsyncClient() as client:
            print(f"Sending GET request to: {api_url}")
            response = await client.get(api_url, headers=headers, timeout=30.0)
            print(f"API Response Status Code: {response.status_code}")
            if response.status_code == 200:
                try:
                    response_data = response.json()
                    print("\nAPI Response (JSON):")
                    print(json.dumps(response_data, indent=2))
                    try:
                        async with aiofiles.open(output_filename, "w", encoding='utf-8') as f:
                            await f.write(json.dumps(response_data, indent=2, ensure_ascii=False))
                        print(f"\nAPI response saved to {output_filename}")
                    except Exception as e:
                        print(f"\nError saving API response to {output_filename}: {e}")
                except json.JSONDecodeError:
                    print("\nError: Could not decode JSON response from API.")
                    print("Response Text:", response.text)
            else:
                print("\nAPI request failed.")
                print("Response Text:", response.text)
    except httpx.RequestError as exc:
        print(f"\nAn error occurred while requesting {exc.request.url!r}: {exc}")
    except httpx.HTTPStatusError as exc:
        print(f"\nError response {exc.response.status_code} while requesting {exc.request.url!r}.")
        print("Response Text:", exc.response.text)
    except Exception as e:
         print(f"\nAn unexpected error occurred during API call: {e}")
async def main():
    parser = argparse.ArgumentParser(
        description="Get Glasir authentication data (cookies, student ID) and optionally test API."
    )
    parser.add_argument(
        "--force-login",
        action="store_true",
        help="Force a new login via Playwright, ignoring any saved data.",
    )
    parser.add_argument(
        "--test-all",
        action="store_true",
        help="Test all endpoints (week/0, weeks/all, weeks/current_forward) sequentially.",
    )
    args = parser.parse_args()
    try:
        import aiofiles
    except ImportError:
        print("Error: 'aiofiles' package is required. Please install it (`pip install aiofiles`)")
        return
    username = None
    cookies = None
    student_id = None
    if args.force_login:
        print("--force-login specified. Skipping saved data check and initiating Playwright login...")
        username, cookies, student_id = await perform_playwright_login()
    else:
        print("Checking for existing authentication data...")
        username, cookies, student_id = await load_data()
        if all([username, cookies, student_id]):
            print("Existing data found:")
            print(f"  Username: {username}")
            print(f"  Cookies: Loaded ({len(cookies) if isinstance(cookies, list) else 'Invalid Format'})")
            print(f"  Student ID: {student_id}")
            print("Using existing data.")
        else:
            print("Existing data incomplete or not found. Starting Playwright login...")
            username, cookies, student_id = await perform_playwright_login()
    if not all([username, cookies, student_id]):
            print("Failed to obtain authentication data via Playwright. Exiting.")
            return
    endpoints_to_call = []
    if args.test_all:
        print("\n--test-all specified. Testing all endpoints (will prompt for count)...")
        while True:
            try:
                count_input = input("Enter the 'count' for the forward weeks endpoint test (e.g., 3): ").strip()
                count = int(count_input)
                if count >= 0:
                    break
                else:
                    print("Count must be non-negative.")
            except ValueError:
                print("Invalid input. Please enter an integer.")
            except (EOFError, KeyboardInterrupt):
                 print("\nOperation cancelled by user.")
                 return
        endpoints_to_call = ["week/0", "weeks/all", "weeks/current_forward", f"weeks/forward/{count}"]
    else:
        print("\nSelect the API endpoint to call:")
        print("  1: week/0 (Default single week)")
        print("  2: weeks/all (All available weeks)")
        print("  3: weeks/current_forward (Current and future weeks)")
        print("  4: weeks/forward/{count} (N future weeks)")
        while True:
            try:
                choice = input("Enter choice (1-4): ").strip()
                if choice == '1':
                    endpoints_to_call.append("week/0")
                    break
                elif choice == '2':
                    endpoints_to_call.append("weeks/all")
                    break
                elif choice == '3':
                    endpoints_to_call.append("weeks/current_forward")
                    break
                elif choice == '4':
                    while True:
                        try:
                            count_input = input("Enter the number of forward weeks (count): ").strip()
                            count = int(count_input)
                            if count >= 0:
                                endpoints_to_call.append(f"weeks/forward/{count}")
                                break
                            else:
                                print("Count must be non-negative.")
                        except ValueError:
                            print("Invalid input. Please enter an integer.")
                        except (EOFError, KeyboardInterrupt):
                            print("\nOperation cancelled by user.")
                            return
                    break
                else:
                    print("Invalid choice. Please enter 1, 2, 3, or 4.")
            except EOFError:
                print("\nOperation cancelled by user.")
                return
            except KeyboardInterrupt:
                print("\nOperation cancelled by user.")
                return
    if not endpoints_to_call:
        print("No endpoint selected or specified. Exiting.")
    else:
        for endpoint in endpoints_to_call:
            print(f"\n--- Calling Endpoint: {endpoint} ---")
            await make_api_call(username, cookies, student_id, endpoint)
            if args.test_all and endpoint != endpoints_to_call[-1]:
                print("\nWaiting a moment before next test...")
                await asyncio.sleep(2)
    print("\nScript finished.")
if __name__ == "__main__":
    asyncio.run(main())
````

## File: .gitignore
````
# Python
__pycache__/
*.pyc
*.pyo
*.pyd
*.egg-info/
dist/
build/

# Virtual environment
venv/
.venv/
env/
ENV/

# OS specific
.DS_Store

# IDE directories
.vscode/
.idea/

# Project specific
# Ignore everything in glasir_auth_tool except get_auth.py
glasir_auth_tool/*
!glasir_auth_tool/get_auth.py

# Debugging output
debug_html/

# Logs
*.log

# Profiling output
profile_output.prof

# Environment variables
.env
# Planning and output files
Plan.md
repomix-output-tree-simplified.md
roo_task_apr-26-2025_4-07-46-pm.md

# Specstory directory
/.specstory
````

## File: README.md
````markdown
# Glasir Timetable API

## Purpose

This API provides endpoints to extract and retrieve timetable data from the Glasir online system.

## Setup

It is recommended to use a virtual environment.

1.  **Create a virtual environment (optional):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```
2.  **Install dependencies:**
    ```bash
    pip install -r glasir_api/requirements.txt
    ```

## Running the API

To start the API server, run the following command from the project's root directory (`V0.3`):

```bash
uvicorn glasir_api.main:app --host 0.0.0.0 --port 8000
```

For development, you can use the `--reload` flag to automatically restart the server when code changes are detected:

```bash
uvicorn glasir_api.main:app --host 0.0.0.0 --port 8000 --reload
```

## Authentication Helper

The `get_glasir_auth.py` script, located in the parent directory (`V0.3`), helps obtain the necessary authentication details (`Cookie` header and `student_id`) required by the API endpoints.

Run the script using:

```bash
python ../get_glasir_auth.py --force-login
```

This will prompt you for your Glasir username and password and save the required `Cookie` string and `student_id` to files (`glasir_auth_tool/cookies.json` and `glasir_auth_tool/student_id.txt` respectively) in the `glasir_auth_tool` directory. You will need these values for the API requests.

## API Endpoints

The following endpoints are available:

### Get Timetable for a Specific Week Offset

*   **Method:** `GET`
*   **Path:** `/profiles/{username}/weeks/{offset}`
*   **Path Parameters:**
    *   `username`: Your Glasir username (e.g., `rm3112z9`).
    *   `offset`: The week offset relative to the current week (e.g., `0` for the current week, `-1` for the previous week, `1` for the next week).
*   **Query Parameters:**
    *   `student_id`: Your Glasir student ID.
*   **Required Headers:**
    *   `Cookie`: The authentication cookie string obtained from `get_glasir_auth.py`.
*   **Example `curl`:**
    ```bash
    curl -X GET -H "Cookie: YOUR_COOKIE_STRING" "http://localhost:8000/profiles/YOUR_USERNAME/weeks/0?student_id=YOUR_STUDENT_ID"
    ```
*   **Response:** A JSON object representing the `TimetableData` for the specified week.

### Get Timetable for All Available Weeks

*   **Method:** `GET`
*   **Path:** `/profiles/{username}/weeks/all`
*   **Path Parameters:**
    *   `username`: Your Glasir username.
*   **Query Parameters:**
    *   `student_id`: Your Glasir student ID.
*   **Required Headers:**
    *   `Cookie`: The authentication cookie string.
*   **Example `curl`:**
    ```bash
    curl -X GET -H "Cookie: YOUR_COOKIE_STRING" "http://localhost:8000/profiles/YOUR_USERNAME/weeks/all?student_id=YOUR_STUDENT_ID"
    ```
*   **Response:** A JSON array containing `TimetableData` objects for all weeks found.

### Get Timetable from Current Week Forward

*   **Method:** `GET`
*   **Path:** `/profiles/{username}/weeks/current_forward`
*   **Path Parameters:**
    *   `username`: Your Glasir username.
*   **Query Parameters:**
    *   `student_id`: Your Glasir student ID.
*   **Required Headers:**
    *   `Cookie`: The authentication cookie string.
*   **Example `curl`:**
    ```bash
    curl -X GET -H "Cookie: YOUR_COOKIE_STRING" "http://localhost:8000/profiles/YOUR_USERNAME/weeks/current_forward?student_id=YOUR_STUDENT_ID"
    ```
*   **Response:** A JSON array containing `TimetableData` objects starting from the current week.

### Get Timetable for a Specific Number of Weeks Forward

*   **Method:** `GET`
*   **Path:** `/profiles/{username}/weeks/forward/{count}`
*   **Path Parameters:**
    *   `username`: Your Glasir username.
    *   `count`: The number of weeks forward from the current week to retrieve (inclusive of the current week).
*   **Query Parameters:**
    *   `student_id`: Your Glasir student ID.
*   **Required Headers:**
    *   `Cookie`: The authentication cookie string.
*   **Example `curl`:**
    ```bash
    curl -X GET -H "Cookie: YOUR_COOKIE_STRING" "http://localhost:8000/profiles/YOUR_USERNAME/weeks/forward/5?student_id=YOUR_STUDENT_ID"
    ```
*   **Response:** A JSON array containing `TimetableData` objects for the specified number of weeks forward.
````
