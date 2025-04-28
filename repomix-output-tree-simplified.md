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
- Files matching these patterns are excluded: pdm.lock, .roomodes
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
glasir_timetable/
  accounts/
    __init__.py
  api/
    client.py
  auth/
    cookies.py
    login.py
    session_params.py
  extractors/
    timetable_extractor.py
  interface/
    application.py
    cli.py
    config_manager.py
    orchestrator.py
  parsers/
    homework_parser.py
    teacher_parser.py
    timetable_parser.py
  shared/
    __init__.py
    concurrency_manager.py
    constants.py
    date_utils.py
    error_utils.py
    formatting.py
  storage/
    exporter.py
    profile_manager.py
  __init__.py
  models.py
__main__.py
.gitignore
INSTALLATION.md
main.py
pyproject.toml
README.md
requirements.txt
```

# Files

## File: glasir_timetable/accounts/__init__.py
````python

````

## File: glasir_timetable/api/client.py
````python
import asyncio
import os
import datetime
from typing import Any, Dict, Optional
from urllib.parse import urlparse, parse_qs
import httpx
from httpx import Limits
from glasir_timetable import raw_response_config, logger
from glasir_timetable.shared.concurrency_manager import ConcurrencyManager
class AsyncApiClient:
    def __init__(
        self,
        base_url: str,
        cookies: Optional[Dict[str, str]] = None,
        session_params: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
    ):
        self.base_url = base_url.rstrip("/")
        self.cookies = cookies or {}
        self.session_params = session_params or {}
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        limits = Limits(max_keepalive_connections=20, max_connections=100)
        self.client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            verify=True,
            cookies=self.cookies,
            limits=limits,
            http2=True,
        )
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        await self.close()
    async def close(self):
        await self.client.aclose()
    async def _request_with_retries(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        inject_params: bool = True,
        concurrency_manager: Optional[ConcurrencyManager] = None,
        force_max_concurrency: bool = False,
        **kwargs,
    ) -> httpx.Response:
        attempt = 0
        last_exc = None
        full_url = (
            url if url.startswith("http") else f"{self.base_url}/{url.lstrip('/')}"
        )
        merged_data = data.copy() if data else {}
        if inject_params and self.session_params:
            merged_data.update(self.session_params)
        while attempt < self.max_retries:
            try:
                response = await self.client.request(
                    method,
                    full_url,
                    params=params,
                    data=merged_data,
                    headers=headers,
                    **kwargs,
                )
                response.raise_for_status()
                await self._save_raw_response(response, method, full_url)
                if concurrency_manager and not force_max_concurrency:
                    concurrency_manager.report_success()
                return response
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                last_exc = e
                report_failure = False
                if isinstance(e, (httpx.TimeoutException, httpx.ConnectError)):
                    report_failure = True
                elif isinstance(
                    e, httpx.HTTPStatusError
                ) and e.response.status_code in [429, 500, 503]:
                    report_failure = True
                if report_failure and concurrency_manager and not force_max_concurrency:
                    concurrency_manager.report_failure()
                endpoint = full_url.split("?")[0]
                logger.warning(
                    f"API {method} {endpoint} attempt {attempt+1} failed: {type(e).__name__}"
                )
                attempt += 1
                if attempt >= self.max_retries:
                    break
                sleep_time = self.backoff_factor * (2 ** (attempt - 1))
                await asyncio.sleep(sleep_time)
        endpoint = full_url.split("?")[0]
        logger.error(
            f"API {method} {endpoint} failed after {self.max_retries} attempts"
        )
        raise last_exc
    async def _save_raw_response(
        self, response: httpx.Response, method: str, url: str
    ):
        if not raw_response_config["save_enabled"]:
            return
        try:
            save_dir = raw_response_config["directory"]
            os.makedirs(save_dir, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            parsed_url = urlparse(url)
            path_part = parsed_url.path.strip('/').replace('/', '_')
            if not path_part:
                path_part = "index"
            query_part = ""
            if parsed_url.query:
                params = parse_qs(parsed_url.query)
                if 'week' in params:
                    query_part = f"_week{params['week'][0]}"
                elif 'id' in params:
                    query_part = f"_id{params['id'][0]}"
            filename = f"{timestamp}_{method}_{path_part}{query_part}.raw"
            filepath = os.path.join(save_dir, filename)
            with open(filepath, "wb") as f:
                f.write(response.content)
            logger.debug(f"Saved raw response to: {filepath}")
            if raw_response_config["save_request_details"]:
                details_filepath = filepath.replace(".raw", ".request.txt")
                with open(details_filepath, "w") as f:
                    f.write(f"URL: {url}\n")
                    f.write(f"Method: {method}\n")
                    f.write(f"Status Code: {response.status_code}\n")
                    f.write("Headers:\n")
                    for k, v in response.request.headers.items():
                        f.write(f"  {k}: {v}\n")
        except Exception as e:
            logger.error(f"Failed to save raw response for {url}: {e}")
    async def get(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        inject_params: bool = True,
        concurrency_manager: Optional[ConcurrencyManager] = None,
        force_max_concurrency: bool = False,
        **kwargs,
    ) -> httpx.Response:
        return await self._request_with_retries(
            "GET",
            url,
            params=params,
            headers=headers,
            inject_params=inject_params,
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
        inject_params: bool = True,
        concurrency_manager: Optional[ConcurrencyManager] = None,
        force_max_concurrency: bool = False,
        **kwargs,
    ) -> httpx.Response:
        return await self._request_with_retries(
            "POST",
            url,
            data=data,
            headers=headers,
            inject_params=inject_params,
            concurrency_manager=concurrency_manager,
            force_max_concurrency=force_max_concurrency,
            **kwargs,
        )
````

## File: glasir_timetable/auth/cookies.py
````python
from datetime import datetime
from typing import Any, Dict, Optional
from glasir_timetable.shared import logger
from glasir_timetable.storage.profile_manager import ProfileData
DEFAULT_COOKIE_EXPIRY_HOURS = 24
async def load_cookies_for_profile(profile: ProfileData) -> Optional[Dict[str, Any]]:
    try:
        cookie_data = await profile.load_cookies()
        if cookie_data is None:
            logger.info(
                f"No cookie data loaded for user {profile.username} via ProfileData."
            )
            return None
        if not isinstance(cookie_data, dict) or not all(
            k in cookie_data for k in ("cookies", "created_at", "expires_at")
        ):
            logger.warning(
                f"Invalid cookie data format loaded for user {profile.username}"
            )
            return None
        return cookie_data
    except Exception as e:
        logger.error(
            f"Failed to load cookies for user {profile.username} via ProfileData: {e}"
        )
        return None
async def save_cookies_for_profile(
    profile: ProfileData, cookie_data: Dict[str, Any]
) -> None:
    try:
        await profile.save_cookies(cookie_data)
        logger.info(
            f"Initiated saving cookies for user {profile.username} via ProfileData."
        )
    except Exception as e:
        logger.error(
            f"Failed to save cookies for user {profile.username} via ProfileData: {e}"
        )
def is_cookies_valid(cookie_data: Optional[Dict[str, Any]]) -> bool:
    if not cookie_data:
        return False
    try:
        expires_at = datetime.fromisoformat(cookie_data["expires_at"])
        return datetime.now() < expires_at
    except Exception:
        logger.error("Error checking cookie expiry")
        return False
````

## File: glasir_timetable/auth/login.py
````python
import re
from typing import Any, Dict, Optional
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page
from glasir_timetable.shared import logger
from glasir_timetable.storage.profile_manager import ProfileManager
_RE_GUID = re.compile(
    r"[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}"
)
_RE_NAME_CLASS = re.compile(
    r"N[æ&aelig;]mingatímatalva:\s*([^,<]+?)\s*,\s*([^\s<]+)", re.IGNORECASE
)
async def _extract_student_info_from_page(page: Page) -> Optional[Dict[str, Any]]:
    logger.debug("Attempting to extract student info from page content...")
    try:
        content = await page.content()
    except Exception as e:
        logger.error(f"Cannot get page content for student info extraction: {e}")
        return None
    student_info = {"id": None, "name": None, "class": None}
    guid_match = _RE_GUID.search(content)
    if guid_match:
        student_info["id"] = guid_match.group(0).strip()
        logger.debug(f"Extracted student ID: {student_info['id']}")
    else:
        logger.warning("Could not extract student ID (GUID) from page content.")
    name_class_match = _RE_NAME_CLASS.search(content)
    if name_class_match:
        student_info["name"] = name_class_match.group(1).strip()
        student_info["class"] = name_class_match.group(2).strip()
        logger.debug(f"Extracted student name: {student_info['name']}")
        logger.debug(f"Extracted student class: {student_info['class']}")
    else:
        logger.warning("Could not extract student name and class from page content.")
        try:
            student_name_js = await page.evaluate(
                "() => document.querySelector('.main-content h1')?.textContent.trim()"
            )
            class_name_js = await page.evaluate(
                "() => document.querySelector('.main-content p')?.textContent.match(/Class: ([^,]+)/)?.[1].trim()"
            )
            if student_name_js and not student_info["name"]:
                student_info["name"] = student_name_js
                logger.debug(f"Extracted student name via JS: {student_info['name']}")
            if class_name_js and not student_info["class"]:
                student_info["class"] = class_name_js
                logger.debug(f"Extracted student class via JS: {student_info['class']}")
        except Exception as e:
            logger.warning(f"Error extracting student name/class via JS fallback: {e}")
    if student_info["id"]:
        logger.info(f"Successfully extracted student info: {student_info}")
        return student_info
    else:
        logger.error(
            "Failed to extract essential student ID. Cannot return student info."
        )
        return None
async def login(
    page: Page, username: str, password: str, domain: str = "glasir.fo"
) -> None:
    email = f"{username}@{domain}"
    try:
        logger.info(f"Navigating to https://tg.glasir.fo for user {email}")
        await page.goto("https://tg.glasir.fo", timeout=30000)
        logger.info("Filling username/email")
        await page.wait_for_selector("#i0116", state="visible", timeout=10000)
        await page.fill("#i0116", email)
        await page.click("#idSIButton9")
        logger.info("Filling password")
        await page.wait_for_selector("#passwordInput", state="visible", timeout=10000)
        await page.fill("#passwordInput", password)
        logger.info("Checking 'Keep me signed in'")
        await page.check("#kmsiInput")
        logger.info("Submitting login form")
        await page.click("#submitButton")
        logger.info("Waiting for redirect to timetable")
        await page.wait_for_url("https://tg.glasir.fo/132n/**", timeout=30000)
        logger.info("Waiting for timetable table to appear")
        await page.wait_for_selector("table.time_8_16", state="visible", timeout=15000)
        logger.info("Login successful")
        try:
            profile_manager = ProfileManager.get_instance()
            # (Requires modifying ProfileManager again, or calling extract here directly)
            # --- Load the specific profile for the current user and save student info ---
            try:
                # Load the profile corresponding to the username used for login
                user_profile = profile_manager.load_profile(username)
                current_info = await user_profile.load_student_info()
                # Check if info is missing or incomplete
                if not current_info or not all(
                    k in current_info and current_info[k]
                    for k in ("id", "name", "class")
                ):
                    logger.info(
                        f"Student info missing/incomplete for {username}. Extracting..."
                    )
                    extracted_info = await _extract_student_info_from_page(page)
                    if extracted_info and extracted_info.get("id"):
                        # Merge with existing data if any (prefer extracted non-empty values)
                        merged_info = current_info or {}
                        for key, value in extracted_info.items():
                            if (
                                value
                            ):  # Only update if extracted value is not None/empty
                                merged_info[key] = value
                        # Ensure all keys exist, default to "Unknown" if needed (though ID should exist)
                        merged_info.setdefault("id", extracted_info.get("id"))
                        merged_info.setdefault("name", "Unknown")
                        merged_info.setdefault("class", "Unknown")
                        # Save the updated info using the profile object's method
                        await user_profile.save_student_info(merged_info)
                        logger.info(
                            f"Saved extracted/updated student info for {username}"
                        )
                    else:
                        logger.warning(
                            f"Failed to extract student info for {username} after login."
                        )
                else:
                    logger.info(
                        f"Student info already present and complete for {username}."
                    )
            except FileNotFoundError:
                logger.error(
                    f"Profile '{username}' not found after login. Cannot save student info."
                )
            except Exception as e_info:
                logger.error(
                    f"Error loading/saving student info for profile '{username}': {e_info}"
                )
        except Exception as e:
            logger.error(f"Error ensuring student info after login: {e}")
    except PlaywrightError as e:
        logger.error(f"Playwright error during login: {e}")
        raise
    except Exception as e:
        logger.error(f"Login failed: {e}")
        raise
````

## File: glasir_timetable/auth/session_params.py
````python
import re
from typing import Dict
from glasir_timetable.shared import logger
LNAME_PATTERNS = [
    re.compile(r"lname=([^&\"'\s]+)"),
    re.compile(r"xmlhttp\.send\(\"[^\"]*lname=([^&\"'\s]+)\""),
    re.compile(r"MyUpdate\('[^']*','[^']*','[^']*',\d+,(\d+)\)"),
    re.compile(r"name=['\"]lname['\"]\s*value=['\"]([^'\"]+)['\"]"),
]
def extract_session_params_from_html(html: str) -> Dict[str, str]:
    lname = None
    # Extract lname
    for pattern in LNAME_PATTERNS:
        match = pattern.search(html)
        if match:
            lname = match.group(1)
            logger.debug(f"Extracted lname: {lname}")
            break
    if not lname:
        logger.warning("Could not extract 'lname' from HTML")
    return {"lname": lname}
````

## File: glasir_timetable/extractors/timetable_extractor.py
````python
import asyncio
from typing import Dict, List, Optional
from cachetools import TTLCache, cached
from glasir_timetable.api.client import AsyncApiClient
from glasir_timetable.parsers.homework_parser import parse_homework_html
from glasir_timetable.parsers.teacher_parser import parse_teacher_html
from glasir_timetable.shared import logger
from glasir_timetable.shared.concurrency_manager import ConcurrencyManager
from glasir_timetable.shared.constants import (
    TEACHER_MAP_CACHE_TTL,
)
teacher_cache = TTLCache(maxsize=1, ttl=TEACHER_MAP_CACHE_TTL)
class TimetableExtractor:
    def __init__(self, api_client: AsyncApiClient):
        self.api = api_client
    @cached(teacher_cache)
    async def fetch_teacher_map(self) -> Dict[str, str]:
        logger.info("Fetching fresh teacher map from API...")
        try:
            # relying on the session managed by the api_client.
            resp = await self.api.post(
                "/i/teachers.asp", data={"fname": "Henry"}, inject_params=True
            )
            resp.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
            return parse_teacher_html(resp.text)
        except Exception as e:
            logger.error(f"Failed to fetch or parse teacher map: {e}")
            # Return empty dict on failure, which will also be cached for the TTL duration
            return {}
    async def fetch_week_html(  # Add force_max_concurrency flag
        self,
        week_offset: int = 0,
        student_id: str = None,
        lname_value: str = None,
        timer_value: str = None,
        week_concurrency_manager: Optional[ConcurrencyManager] = None,
        force_max_concurrency: bool = False,  # New flag
    ) -> str:
        try:
            data = {
                "fname": "Henry",
                "timex": timer_value,
                "lname": lname_value,
                "id": student_id,
                "q": "stude",
                "v": str(week_offset),
            }
            resp = await self.api.post(
                "/i/udvalg.asp",
                data=data,
                inject_params=False,  # Don't inject potentially stale session params
                concurrency_manager=week_concurrency_manager,
                force_max_concurrency=force_max_concurrency,
            )
            return resp.text
        except Exception:
            logger.error(f"Failed to fetch week {week_offset}")
            return ""
    async def fetch_homework_for_lessons(
        self,
        lesson_ids: List[str],
        concurrency_manager: ConcurrencyManager,
        force_max_concurrency: bool = False,
    ) -> Dict[str, str]:
        results = {}
        async def fetch_one(lesson_id, force_flag):
            try:
                data = {
                    "fname": "Henry",
                    "q": lesson_id,
                    "MyFunktion": "ReadNotesToLessonWithLessonRID",
                }
                resp = await self.api.post(
                    "/i/note.asp",
                    data=data,
                    inject_params=True,
                    concurrency_manager=concurrency_manager,
                    force_max_concurrency=force_flag,
                )
                parsed = parse_homework_html(resp.text)
                if lesson_id in parsed:
                    results[lesson_id] = parsed[lesson_id]
            except Exception as e:
                logger.warning(f"Failed to fetch homework for lesson {lesson_id}: {e}")
        await asyncio.gather(
            *(fetch_one(lid, force_max_concurrency) for lid in lesson_ids)
        )
        return results
````

## File: glasir_timetable/interface/application.py
````python
class Application:
    def __init__(self, config: dict):
        self.config = config
        self.args = config.get("args")
        self.username = config.get("username")
        self.credentials = config.get("credentials")
        self.api_only_mode = config.get("api_only_mode", False)
        self.cached_student_info = config.get("cached_student_info")
        self.output_dir = config.get("output_dir")
        self.profile = config.get("profile")
        self.concurrency_config = config.get(
            "concurrency_config"
        )
        self.force_max_concurrency = (
            self.args.force_max_concurrency if self.args else False
        )
        self.logger = None
        self.api_cookies = {}
    def set_api_cookies(self, cookies_dict):
        self.api_cookies = cookies_dict
````

## File: glasir_timetable/interface/cli.py
````python
import argparse
import getpass
import sys
from typing import Optional, Tuple
from glasir_timetable.storage.profile_manager import ProfileManager
def parse_args():
    print("DEBUG: sys.argv before parsing:", sys.argv)
    parser = argparse.ArgumentParser(description="Extract timetable data from Glasir")
    parser.add_argument(
        "--weekforward", type=int, default=0, help="Number of weeks forward to extract"
    )
    parser.add_argument(
        "--weekbackward",
        type=int,
        default=0,
        help="Number of weeks backward to extract",
    )
    parser.add_argument(
        "--all-weeks",
        action="store_true",
        help="Extract all available weeks from all academic years",
    )
    parser.add_argument(
        "--forward",
        action="store_true",
        help="Extract only current and future weeks (positive offsets) dynamically",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="glasir_timetable/weeks",
        help="Directory to save output files",
    )
    parser.add_argument(
        "--headless",
        action="store_false",
        dest="headless",
        default=True,
        help="Run in non-headless mode (default: headless=True)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set the logging level",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default="output/logs/glasir_timetable.log",
        help="Log to a file instead of console (default: output/logs/glasir_timetable.log)",
    )
    parser.add_argument(
        "--account",
        type=str,
        default=None,
        help="Specify the account profile username directly, skipping interactive selection",
    )
    parser.add_argument(
        "--collect-error-details",
        action="store_true",
        help="Collect detailed error information",
    )
    parser.add_argument(
        "--collect-tracebacks",
        action="store_true",
        help="Collect tracebacks for errors",
    )
    parser.add_argument(
        "--enable-screenshots", action="store_true", help="Enable screenshots on errors"
    )
    parser.add_argument(
        "--error-limit",
        type=int,
        default=100,
        help="Maximum number of errors to store per category",
    )
    parser.add_argument(
        "--use-cookies",
        action="store_true",
        default=True,
        help="Use cookie-based authentication when possible",
    )
    parser.add_argument(
        "--cookie-path",
        type=str,
        default="cookies.json",
        help="Path to save/load cookies",
    )
    parser.add_argument(
        "--no-cookie-refresh",
        action="store_false",
        dest="refresh_cookies",
        default=True,
        help="Do not refresh cookies even if they are expired",
    )
    parser.add_argument(
        "--teacherupdate",
        action="store_true",
        help="Update the teacher mapping cache at the start of the script",
    )
    parser.add_argument(
        "--skip-timetable",
        action="store_true",
        help="Skip timetable extraction, useful when only updating teachers",
    )
    parser.add_argument(
        "--save-raw-responses",
        action="store_true",
        help="Save raw API responses before parsing",
    )
    parser.add_argument(
        "--raw-responses-dir",
        type=str,
        default="output/raw_responses/",
        help="Directory to save raw API responses (default: output/raw_responses/)",
    )
    parser.add_argument(
        "--force-max-concurrency",
        action="store_true",
        default=False,
        help="Force concurrency to predefined maximum limits for this run (does not save)",
    )
    args = parser.parse_args()
    return args
async def select_account() -> (
    Tuple[Optional[str], bool]
):
    profile_manager = ProfileManager.get_instance()
    profiles = profile_manager.list_profiles()
    if not profiles:
        print("No account profiles found.")
        create_new = (
            input("Would you like to create a new profile now? (y/n): ").strip().lower()
        )
        if create_new == "y":
            credentials = prompt_for_credentials()
            username = credentials.get("username")
            password = credentials.get("password")
            if username and password:
                try:
                    await profile_manager.create_profile(
                        username, credentials=credentials
                    )
                    print(f"Profile '{username}' created successfully.")
                    return username, True
                except Exception as e:
                    print(f"Error creating profile: {e}")
                    return None, False
            else:
                print("Username or password not provided. Cannot create profile.")
                return None, False
        else:
            print("Profile creation skipped.")
            return None, False
    print("\nAvailable account profiles:")
    for idx, username in enumerate(profiles, 1):
        print(f"  {idx}. {username}")
    while True:
        try:
            choice = input(
                f"Select a profile by number (1-{len(profiles)}) or press Enter to cancel: "
            ).strip()
            if not choice:
                print("Selection cancelled.")
                return None, False
            if not choice.isdigit():
                print("Invalid input. Please enter a number.")
                continue
            index = int(choice)
            if 1 <= index <= len(profiles):
                selected_username = profiles[index - 1]
                print(f"Selected profile: {selected_username}")
                return selected_username, False
            else:
                print(
                    f"Invalid number. Please enter a number between 1 and {len(profiles)}."
                )
        except KeyboardInterrupt:
            print("\nSelection cancelled.")
            return None, False
def prompt_for_credentials(username_hint=None):
    print("\nNo credentials found. Please enter your Glasir login details:")
    if username_hint:
        username = input(f"Username (without @glasir.fo) [{username_hint}]: ").strip()
        if not username:
            username = username_hint
    else:
        username = input("Username (without @glasir.fo): ").strip()
    password = getpass.getpass("Password: ")
    return {"username": username, "password": password}
````

## File: glasir_timetable/interface/config_manager.py
````python
from glasir_timetable import configure_raw_responses, logger
from glasir_timetable.auth.cookies import (
    is_cookies_valid,
)
from glasir_timetable.interface.cli import prompt_for_credentials
from glasir_timetable.storage.profile_manager import (
    ProfileData,
    ProfileManager,
)
async def load_config(
    args, selected_username, profile_created: bool = False
):
    profile_manager = ProfileManager.get_instance()
    try:
        profile: ProfileData = profile_manager.load_profile(selected_username)
        logger.info(f"Loaded profile for '{selected_username}' from {profile.base_dir}")
    except FileNotFoundError:
        logger.error(
            f"Profile '{selected_username}' not found. Please ensure the profile exists."
        )
        # TODO: Consider prompting for creation via ProfileManager.create_profile
        exit(f"Error: Profile '{selected_username}' does not exist.")
    except Exception as e:
        logger.error(f"Failed to load profile '{selected_username}': {e}")
        exit(f"Error loading profile: {e}")
    # --- 1.5 Load Concurrency Config ---
    concurrency_config = await profile.load_concurrency_config()
    logger.info(f"Loaded concurrency config: {concurrency_config}")
    # --- 2. Update Args/Defaults with Profile Paths ---
    # Args might still be used elsewhere, update them if necessary,
    # but prefer using profile paths directly from the config dict later.
    args.output_dir = str(profile.weeks_dir)  # Use profile's weeks_dir for output
    profile.weeks_dir.mkdir(parents=True, exist_ok=True)
    logger.debug(f"Ensured output directory exists: {profile.weeks_dir}")
    configure_raw_responses(
        args.save_raw_responses,
        args.raw_responses_dir,
        save_request_details=args.save_raw_responses,
    )
    credentials = await profile.load_credentials()
    if not profile_created and (
        not credentials
        or "username" not in credentials
        or "password" not in credentials
    ):
        logger.warning("Credentials file missing or incomplete. Prompting user.")
        credentials = prompt_for_credentials(selected_username)
        await profile.save_credentials(credentials)
    elif not credentials:
        logger.error(
            "Profile was just created, but credentials could not be loaded. This indicates an issue."
        )
        credentials = prompt_for_credentials(selected_username)
        await profile.save_credentials(credentials)
    api_only_mode = False
    cached_student_info = None
    auth_valid = False
    try:
        cookie_data = await profile.load_cookies()
        student_info = await profile.load_student_info()
        cookies_are_valid = is_cookies_valid(cookie_data)
        student_info_is_valid = student_info is not None and "id" in student_info
        if cookies_are_valid and student_info_is_valid:
            auth_valid = True
            cached_student_info = student_info
            api_only_mode = True
            logger.info(
                "Valid cookies and student info found. Automatically enabling API-only mode (skipping Playwright)."
            )
        elif not cookies_are_valid:
            logger.info("Cookies missing or expired.")
        elif not student_info_is_valid:
            logger.info("Student info missing or invalid.")
        if not auth_valid:
            logger.info(
                "Full auth data not available or valid. API-only mode disabled. Playwright login may be required."
            )
    except Exception as e:
        logger.error(f"Error checking auth data validity: {e}")
        logger.warning(
            "Proceeding with API-only mode disabled due to error checking auth data."
        )
    config = {
        "args": args,
        "username": selected_username,
        "profile": profile,
        "account_path": str(profile.base_dir),
        "cookie_path": str(profile.cookies_path),
        "output_dir": str(profile.weeks_dir),
        "student_id_path": str(profile.student_info_path),
        "credentials": credentials,
        "api_only_mode": api_only_mode,
        "cached_student_info": cached_student_info,
        "concurrency_config": concurrency_config,
        "force_max_concurrency": args.force_max_concurrency,
    }
    return config
````

## File: glasir_timetable/interface/orchestrator.py
````python
import asyncio
import re
import time
from asyncio import Queue
from datetime import datetime, timedelta
import httpx
import tqdm
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from tqdm.asyncio import tqdm as tqdm_asyncio
from glasir_timetable import logger
from glasir_timetable.api.client import AsyncApiClient
from glasir_timetable.auth.cookies import (
    load_cookies_for_profile,
    save_cookies_for_profile,
)
from glasir_timetable.auth.login import login as playwright_login
from glasir_timetable.auth.session_params import extract_session_params_from_html
from glasir_timetable.extractors.timetable_extractor import TimetableExtractor
from glasir_timetable.parsers.timetable_parser import parse_timetable_html
from glasir_timetable.shared.concurrency_manager import ConcurrencyManager
from glasir_timetable.shared.constants import (
    DEFAULT_HEADERS,
    DEFAULT_HOMEWORK_FETCH_CONCURRENCY,
    DEFAULT_WEEK_FETCH_CONCURRENCY,
    DEFAULT_WEEK_PROCESS_CONCURRENCY,
    FORCE_MAX_HOMEWORK_FETCH_CONCURRENCY,
    FORCE_MAX_WEEK_FETCH_CONCURRENCY,
    GLASIR_TIMETABLE_URL,
)
from glasir_timetable.shared.error_utils import (
    error_screenshot_context,
    register_console_listener,
)
from glasir_timetable.storage.exporter import save_timetable_export
from glasir_timetable.storage.profile_manager import ProfileData
_RE_WEEK_OFFSET = re.compile(r"v=(-?\d+)")
async def run_extraction(app):
    args = app.args
    credentials = app.credentials
    api_only_mode = app.api_only_mode
    cached_student_info = app.cached_student_info
    profile = app.profile
    concurrency_config = app.concurrency_config
    if not api_only_mode:
        async with async_playwright() as p:
            async with error_screenshot_context(
                None, "main", "general_errors", take_screenshot=args.enable_screenshots
            ):
                browser = await p.chromium.launch(headless=args.headless)
                context = await browser.new_context()
                page = await context.new_page()
                register_console_listener(page)
                try:
                    await playwright_login(
                        page, credentials["username"], credentials["password"]
                    )
                except Exception as e:
                    logger.error(f"Login failed: {e}")
                    return
                browser_cookies = await page.context.cookies()
                if profile:
                    cookie_data = {
                        "cookies": browser_cookies,
                        "created_at": datetime.now().isoformat(),
                        "expires_at": (
                            datetime.now() + timedelta(hours=24)
                        ).isoformat(),
                    }
                    await save_cookies_for_profile(profile, cookie_data)
                    logger.info(
                        f"Saved cookies for user {profile.username} after login"
                    )
                else:
                    logger.warning("No active profile found to save cookies")
                api_cookies = {
                    cookie["name"]: cookie["value"] for cookie in browser_cookies
                }
                app.set_api_cookies(api_cookies)
                student_info = (
                    await profile.load_student_info()
                )
                student_id = student_info.get("id") if student_info else None
                if not student_id:
                    logger.error(
                        "CRITICAL: Student ID not found in active profile after login/validation."
                    )
                # Extract session parameters regardless of student ID status for now
                content = await page.content()
                session_params = extract_session_params_from_html(content)
                lname_value = session_params.get("lname")
                # Initialize API client and extractor
                async with AsyncApiClient(
                    base_url="https://tg.glasir.fo",
                    cookies=api_cookies,
                    # Always use a dynamically generated timer for consistency
                    session_params={
                        "lname": lname_value,
                        "timer": str(int(time.time() * 1000)),
                    },
                ) as api_client:
                    extractor = TimetableExtractor(api_client)
                    # Fetch teacher map
                    try:
                        teacher_map = (
                            await extractor.fetch_teacher_map()
                        )  # fetch_teacher_map doesn't take cookies arg
                    except Exception as e:
                        logger.error(f"Failed to fetch teacher map: {e}")
                        teacher_map = {}
                    await _extract_weeks_with_extractor(
                        app,
                        extractor,
                        student_id,
                        teacher_map,
                        profile,
                        credentials["username"],
                        concurrency_config,
                    )
    else:
        profile = app.profile
        cookie_data = await load_cookies_for_profile(profile)
        api_cookies = (
            {cookie["name"]: cookie["value"] for cookie in cookie_data["cookies"]}
            if cookie_data
            else {}
        )
        app.set_api_cookies(api_cookies)
        student_id = cached_student_info.get("id") if cached_student_info else None
        if not student_id:
            logger.error(
                "Student ID missing in saved info, cannot proceed with API-only mode."
            )
            return
        extracted_lname = None
        try:
            async with httpx.AsyncClient(
                cookies=api_cookies, headers=DEFAULT_HEADERS, follow_redirects=True
            ) as client:
                response = await client.get(GLASIR_TIMETABLE_URL)
                response.raise_for_status()
                html_content = response.text
                logger.debug(
                    f"API-only mode: Fetched HTML snippet: {html_content[:1000]}..."
                )
                session_params = extract_session_params_from_html(html_content)
                extracted_lname = session_params.get("lname")
                generated_timer = str(int(time.time() * 1000))
                logger.info(
                    f"API-only mode: Extracted lname={extracted_lname}, Generated timer={generated_timer}"
                )
        except Exception as e:
            logger.warning(
                f"API-only mode: Failed to fetch/parse initial page for dynamic params: {e.__class__.__name__}: {e}"
            )
        async with AsyncApiClient(
            base_url="https://tg.glasir.fo",
            cookies=api_cookies,
            session_params={
                "lname": extracted_lname,
                "timer": generated_timer,
            },
        ) as api_client:
            extractor = TimetableExtractor(api_client)
            try:
                teacher_map = (
                    await extractor.fetch_teacher_map()
                )
            except Exception as e:
                logger.error(f"Failed to fetch teacher map: {e}")
                teacher_map = {}
            # Week extraction logic - Pass the app object
            await _extract_weeks_with_extractor(
                app,
                extractor,
                student_id,
                teacher_map,
                profile,
                credentials["username"],
                concurrency_config,
            )
# --- Producer-Consumer Implementation ---
async def _week_fetch_producer(  # Add force_max_concurrency flag
    fetch_queue: Queue,
    process_queue: Queue,
    extractor: TimetableExtractor,
    student_id: str,
    lname_value: str,
    timer_value: str,
    fetch_semaphore: asyncio.Semaphore,
    week_fetch_manager: ConcurrencyManager,
    force_max_concurrency: bool,
):
    while True:
        try:
            offset = await fetch_queue.get()
            if offset is None:  # Sentinel value indicates completion
                fetch_queue.task_done()
                break
            async with fetch_semaphore:  # Limit concurrent fetches
                tqdm.tqdm.write(f"[Producer] Fetching HTML for week offset {offset}")
                try:
                    html_content = await extractor.fetch_week_html(
                        week_offset=offset,
                        student_id=student_id,
                        lname_value=lname_value,
                        timer_value=timer_value,
                        week_concurrency_manager=week_fetch_manager,  # Pass manager
                        force_max_concurrency=force_max_concurrency,  # Pass flag
                    )
                    if html_content:
                        await process_queue.put((offset, html_content))
                        tqdm.tqdm.write(
                            f"[Producer] Queued week {offset} for processing."
                        )  # Changed from debug to info for visibility with tqdm
                    else:
                        tqdm.tqdm.write(
                            f"[Producer] WARNING: Received empty HTML for week {offset}, skipping."
                        )
                        # Success/failure reporting is now handled by the API client via the manager
                except Exception as e:
                    # Failure reporting is now handled by the API client
                    tqdm.tqdm.write(f"[Producer] ERROR fetching week {offset}: {e}")
                    # Optionally put an error marker or skip: await process_queue.put((offset, None, e))
                finally:
                    fetch_queue.task_done()  # Signal task completion for this offset
        except asyncio.CancelledError:
            tqdm.tqdm.write("Producer task cancelled.")
            break
        except Exception as e:
            tqdm.tqdm.write(f"Unexpected ERROR in producer: {e}")
            # Ensure task_done is called even on unexpected errors if an item was retrieved
            if "offset" in locals() and offset is not None:
                try:
                    fetch_queue.task_done()
                except ValueError:  # May happen if task_done called twice
                    pass
            break  # Exit loop on unexpected error
async def _week_process_consumer(
    process_queue: Queue,
    extractor: TimetableExtractor,
    teacher_map: dict,
    student_info: dict,
    profile: ProfileData,
    user_id: str,
    results_counter: dict,
    homework_fetch_manager: ConcurrencyManager,
    force_max_concurrency: bool,
    progress_bar: tqdm_asyncio,  # Added progress bar
    week_fetch_manager: ConcurrencyManager,  # Added week manager for postfix
    update_postfix_func: callable,  # Added postfix update function
):
    while True:
        try:
            item = await process_queue.get()
            if item is None:  # Sentinel value indicates completion
                process_queue.task_done()
                break
            offset, html_content = item
            try:
                # 1. Parse main timetable HTML
                timetable_data, homework_ids = parse_timetable_html(
                    html_content, teacher_map=teacher_map
                )
                html_content = None  # Dereference large HTML string after parsing
                # 2. Fetch associated homework
                homework_map = await extractor.fetch_homework_for_lessons(
                    homework_ids,
                    concurrency_manager=homework_fetch_manager,  # Pass manager
                    force_max_concurrency=force_max_concurrency,  # Pass flag
                )
                # 3. Merge homework into events
                for event in timetable_data.get("events", []):
                    lesson_id = event.get("lessonId")
                    if lesson_id and lesson_id in homework_map:
                        event["description"] = homework_map[lesson_id]
                # 4. Overwrite studentInfo with profile data if provided
                if student_info:
                    timetable_data["studentInfo"] = student_info
                # 5. Save the result
                output_dir_path = profile.weeks_dir
                await save_timetable_export(
                    timetable_data,
                    output_dir=str(output_dir_path),
                    user_id=user_id,  # Note: user_id is not actually used by save_timetable_export anymore
                )
                # save_path variable removed as it was unused
                results_counter["success"] += 1
                progress_bar.update(1)  # Update progress bar
                await update_postfix_func()  # Update postfix after successful processing
            except Exception as e:
                tqdm.tqdm.write(f"[Consumer] ERROR processing week {offset}: {e}")
                results_counter["failure"] += 1
            finally:
                process_queue.task_done()  # Signal task completion for this item
        except asyncio.CancelledError:
            tqdm.tqdm.write("Consumer task cancelled.")
            break
        except Exception as e:
            tqdm.tqdm.write(f"Unexpected ERROR in consumer: {e}")
            # Ensure task_done is called even on unexpected errors if an item was retrieved
            if "item" in locals() and item is not None:
                try:
                    process_queue.task_done()
                except ValueError:
                    pass
            break  # Exit loop on unexpected error
# --- End Producer-Consumer ---
async def _extract_weeks_with_extractor(
    app,
    extractor: TimetableExtractor,
    student_id: str,
    teacher_map: dict,
    profile: ProfileData,
    user_id: str,
    concurrency_config: dict,
):
    args = app.args  # Get args from app
    force_max_concurrency = (
        app.force_max_concurrency
    )  # Get the flag from the app object
    lname_value = extractor.api.session_params.get("lname")
    # Retrieve lname and dynamically generated timer from the initialized API client
    lname_value = extractor.api.session_params.get("lname")
    timer_value = extractor.api.session_params.get(
        "timer"
    )  # This should now be the dynamically generated one
    # Load student info (used by consumer)
    try:
        student_info = await profile.load_student_info()
        if not student_info:
            logger.warning(
                f"Loaded student info for profile '{profile.username}' is empty or invalid."
            )
            student_info = None
    except Exception as e:
        logger.error(
            f"Error loading student info for profile '{profile.username}': {e}"
        )
        student_info = None
    # --- Initialize Concurrency Managers ---
    # Moved up to be available for --all-weeks base fetch
    # Determine initial limits based on the flag
    if force_max_concurrency:
        logger.warning(
            "Using --force-max-concurrency: Overriding dynamic limits with predefined maximums."
        )
        initial_week_limit = FORCE_MAX_WEEK_FETCH_CONCURRENCY
        initial_homework_limit = FORCE_MAX_HOMEWORK_FETCH_CONCURRENCY
    else:
        initial_week_limit = concurrency_config.get(
            "week_fetch_limit", DEFAULT_WEEK_FETCH_CONCURRENCY
        )
        initial_homework_limit = concurrency_config.get(
            "homework_fetch_limit", DEFAULT_HOMEWORK_FETCH_CONCURRENCY
        )
    week_fetch_manager = ConcurrencyManager(
        initial_limit=initial_week_limit,
        min_limit=1,
        max_limit=50,  # Max for dynamic adjustment, not the forced max
        name="WeekFetch",
        disabled=force_max_concurrency,  # Disable dynamic adjustments if forced
    )
    homework_fetch_manager = ConcurrencyManager(
        initial_limit=initial_homework_limit,
        min_limit=1,
        max_limit=100,  # Max for dynamic adjustment, not the forced max
        name="HomeworkFetch",
        disabled=force_max_concurrency,  # Disable dynamic adjustments if forced
    )
    # Determine week offsets to process
    if args.teacherupdate and args.skip_timetable:
        logger.info(
            "Teacher mapping updated. Skipping timetable extraction as requested."
        )
        return
    directions = []
    try:
        if args.all_weeks:
            logger.info("Processing all available weeks (--all-weeks)...")
            # Fetch base week HTML to find week links
            # Pass the week_fetch_manager here as well
            base_html = await extractor.fetch_week_html(
                week_offset=0,
                student_id=student_id,
                lname_value=lname_value,
                timer_value=timer_value,
                week_concurrency_manager=week_fetch_manager,
            )
            if not base_html:
                raise RuntimeError(
                    "Could not fetch base week HTML (offset 0) to determine week range."
                )
            soup = BeautifulSoup(base_html, "html.parser")
            week_links = soup.select('a[onclick*="v="]')
            offsets = set()
            for link in week_links:
                match = _RE_WEEK_OFFSET.search(link["onclick"])
                if match:
                    try:
                        offsets.add(int(match.group(1)))
                    except (ValueError, TypeError):
                        logger.warning(
                            f"Could not parse week offset from onclick: {link['onclick']}"
                        )
            if not offsets:
                raise RuntimeError("No week offsets found in base week HTML.")
            min_offset, max_offset = min(offsets), max(offsets)
            logger.info(
                f"Determined week range from HTML: {min_offset} to {max_offset}"
            )
            directions = list(range(min_offset, max_offset + 1))
        elif args.forward:
            logger.warning(
                "--forward functionality is currently disabled. Processing current week only."
            )
            directions = [0]  # Default to current week
        elif args.weekforward > 0 or args.weekbackward > 0:
            logger.info(
                f"Processing specified range: {args.weekbackward} backward, {args.weekforward} forward, including current (0)"
            )
            directions_set = {0}
            for i in range(1, args.weekforward + 1):
                directions_set.add(i)
            for i in range(1, args.weekbackward + 1):
                directions_set.add(-i)
            directions = sorted(list(directions_set))
        else:
            logger.info("No week range specified, processing current week only")
            directions = [0]
    except Exception as e:
        logger.critical(
            f"Failed to determine week range: {e}. Aborting week extraction."
        )
        return  # Stop if we can't determine the weeks
    if not directions:
        logger.info("No week offsets determined to process.")
        return
    total_weeks = len(directions)
    progress_bar = None
    async def _update_progress_bar_postfix():
        if progress_bar:
            week_limit = week_fetch_manager.get_current_limit()
            homework_limit = homework_fetch_manager.get_current_limit()
            postfix_str = f"W Fetch: {week_limit}, H Fetch: {homework_limit}"
            progress_bar.set_postfix_str(
                postfix_str, refresh=False
            )
    try:
        fetch_queue = Queue()
        process_queue = Queue(
            maxsize=DEFAULT_WEEK_PROCESS_CONCURRENCY * 2
        )
        fetch_semaphore = asyncio.Semaphore(
            week_fetch_manager.get_limit()
        )
        results_counter = {"success": 0, "failure": 0}
        for offset in directions:
            await fetch_queue.put(offset)
        progress_bar = tqdm_asyncio(
            total=total_weeks,
            desc="Processing Weeks",
            unit="week",
            smoothing=0.1,
            leave=True,
        )
        await _update_progress_bar_postfix()
        tqdm.tqdm.write(
            f"Starting extraction for {total_weeks} weeks. "
            f"Initial Limits - Week Fetch: {week_fetch_manager.get_limit()}, Homework Fetch: {homework_fetch_manager.get_limit()}, Processors: {concurrency_config.get('week_process_limit', DEFAULT_WEEK_PROCESS_CONCURRENCY)}"
        )
        producer_tasks = []
        num_producers = week_fetch_manager.get_limit()
        for _ in range(num_producers):
            task = asyncio.create_task(
                _week_fetch_producer(
                    fetch_queue,
                    process_queue,
                    extractor,
                    student_id,
                    lname_value,
                    timer_value,
                    fetch_semaphore,
                    week_fetch_manager,
                    force_max_concurrency,  # Pass flag
                )
            )
            producer_tasks.append(task)
        # Create and start consumer tasks
        consumer_tasks = []
        # Use a fixed number of consumers for processing, homework concurrency is handled within the consumer
        # Use the configured or default number of consumers
        num_consumers = concurrency_config.get(
            "week_process_limit", DEFAULT_WEEK_PROCESS_CONCURRENCY
        )
        for _ in range(num_consumers):
            task = asyncio.create_task(
                _week_process_consumer(
                    process_queue,
                    extractor,
                    teacher_map,
                    student_info,
                    profile,
                    user_id,
                    results_counter,
                    homework_fetch_manager,
                    force_max_concurrency,
                    progress_bar,
                    week_fetch_manager,
                    _update_progress_bar_postfix,  # Pass tqdm bar, managers, and helper
                )
            )
            consumer_tasks.append(task)
        # --- Wait for completion ---
        # 1. Wait for all fetch tasks to be picked up and processed by producers
        await fetch_queue.join()
        tqdm.tqdm.write("Fetch queue empty. Signaling producers to stop.")
        # 2. Signal producers to stop by sending sentinel values
        for _ in producer_tasks:
            await fetch_queue.put(None)
        # 3. Wait for producers to finish cleanly
        await asyncio.gather(
            *producer_tasks, return_exceptions=True
        )  # Allow capturing producer errors
        tqdm.tqdm.write("All producer tasks finished.")
        # 4. Wait for all processing tasks to be picked up and processed by consumers
        await process_queue.join()
        tqdm.tqdm.write("Process queue empty. Signaling consumers to stop.")
        # 5. Signal consumers to stop
        for _ in consumer_tasks:
            await process_queue.put(None)
        # 6. Wait for consumers to finish cleanly
        await asyncio.gather(
            *consumer_tasks, return_exceptions=True
        )  # Allow capturing consumer errors
        tqdm.tqdm.write("All consumer tasks finished.")
        # Final summary outside tqdm context might be cleaner
    finally:
        if progress_bar:
            progress_bar.close()
            # Print final summary after closing the bar
            logger.info(
                f"Week processing complete. Success: {results_counter['success']}, Failures: {results_counter['failure']}"
            )
        final_week_limit = week_fetch_manager.get_limit()
        final_homework_limit = homework_fetch_manager.get_limit()
        logger.info(f"Final Week Fetch Limit: {final_week_limit}")
        logger.info(f"Final Homework Fetch Limit: {final_homework_limit}")
        final_config_data = {
            "week_fetch_limit": final_week_limit,
            "homework_fetch_limit": final_homework_limit,
            "week_process_limit": num_consumers,
        }
        if not force_max_concurrency:
            try:
                await profile.save_concurrency_config(final_config_data)
                logger.info(
                    f"Saved final concurrency limits to {profile.concurrency_config_path}"
                )
            except Exception as e:
                logger.error(f"Failed to save final concurrency limits: {e}")
        else:
            logger.warning(
                "Skipping save of concurrency limits due to --force-max-concurrency flag."
            )
````

## File: glasir_timetable/parsers/homework_parser.py
````python
import logging
import re
from typing import Dict
from bs4 import BeautifulSoup, Tag
_RE_SPACE_BEFORE_NEWLINE = re.compile(r" +\n")
_RE_SPACE_AFTER_NEWLINE = re.compile(r"\n +")
logger = logging.getLogger(__name__)
def parse_homework_html(html: str) -> Dict[str, str]:
    result = {}
    try:
        soup = BeautifulSoup(html, "lxml")
        lesson_id_input = soup.select_one(
            'input[type="hidden"][id^="LektionsID"]'
        )
        if not lesson_id_input:
            logger.warning("Could not find LektionsID input field in homework HTML.")
            return result
        lesson_id = lesson_id_input.get("value")
        if not lesson_id:
            logger.warning("LektionsID input field found, but has no value.")
            return result
        homework_header = soup.find("b", string="Heimaarbeiði")
        if not homework_header:
            logger.info(
                f"No 'Heimaarbeiði' header found for lesson {lesson_id}. Assuming no homework."
            )
            return result
        homework_p = homework_header.find_parent("p")
        if not homework_p:
            logger.warning(
                f"Found 'Heimaarbeiði' header but could not find its parent <p> tag for lesson {lesson_id}."
            )
            return result
        def process_node(
            node, is_first_level=False, header_skipped=False, first_br_skipped=False
        ):
            parts = []
            if isinstance(node, str):
                parts.append(node)
            elif isinstance(node, Tag):
                if (
                    is_first_level
                    and not header_skipped
                    and node.name == "b"
                    and node.get_text(strip=True) == "Heimaarbeiði"
                ):
                    return [], True, first_br_skipped
                if (
                    is_first_level
                    and header_skipped
                    and not first_br_skipped
                    and node.name == "br"
                ):
                    return [], header_skipped, True
                if node.name == "br":
                    parts.append("\n")
                elif node.name == "b":
                    inner_parts = []
                    current_header_skipped = header_skipped
                    current_first_br_skipped = first_br_skipped
                    for child in node.children:
                        (
                            child_parts,
                            current_header_skipped,
                            current_first_br_skipped,
                        ) = process_node(
                            child,
                            False,
                            current_header_skipped,
                            current_first_br_skipped,
                        )
                        inner_parts.extend(child_parts)
                    inner = "".join(inner_parts)
                    if inner.strip():
                        parts.append(f"**{inner.strip()}**")
                elif node.name == "i":
                    inner_parts = []
                    current_header_skipped = header_skipped
                    current_first_br_skipped = first_br_skipped
                    for child in node.children:
                        (
                            child_parts,
                            current_header_skipped,
                            current_first_br_skipped,
                        ) = process_node(
                            child,
                            False,
                            current_header_skipped,
                            current_first_br_skipped,
                        )
                        inner_parts.extend(child_parts)
                    inner = "".join(inner_parts)
                    if inner.strip():
                        parts.append(f"*{inner.strip()}*")
                else:
                    current_header_skipped = header_skipped
                    current_first_br_skipped = first_br_skipped
                    for child in node.children:
                        (
                            child_parts,
                            current_header_skipped,
                            current_first_br_skipped,
                        ) = process_node(
                            child,
                            False,
                            current_header_skipped,
                            current_first_br_skipped,
                        )
                        parts.extend(child_parts)
            return parts, header_skipped, first_br_skipped
        markdown_parts = []
        final_header_skipped = False
        final_first_br_skipped = False
        for element in homework_p.contents:
            processed_parts, final_header_skipped, final_first_br_skipped = (
                process_node(
                    element, True, final_header_skipped, final_first_br_skipped
                )
            )
            markdown_parts.extend(processed_parts)
        homework_text = "".join(markdown_parts)
        homework_text = _RE_SPACE_BEFORE_NEWLINE.sub("\n", homework_text)
        homework_text = _RE_SPACE_AFTER_NEWLINE.sub("\n", homework_text)
        homework_text = homework_text.strip()
        if homework_text:
            result[lesson_id] = homework_text
        else:
            logger.info(
                f"Found 'Heimaarbeiði' structure but no subsequent text for lesson {lesson_id}."
            )
    except Exception as e:
        logger.error(f"Error parsing homework HTML: {e}", exc_info=True)
    return result
````

## File: glasir_timetable/parsers/teacher_parser.py
````python
import re
from typing import Dict
from bs4 import BeautifulSoup
from glasir_timetable.shared import logger
_RE_TEACHER_WITH_LINK = re.compile(r"([^<>]+?)\s*\(\s*<a[^>]*?>([A-Z]{2,4})</a>\s*\)")
_RE_TEACHER_NO_LINK = re.compile(r"([^<>]+?)\s*\(\s*([A-Z]{2,4})\s*\)")
def parse_teacher_html(html: str) -> Dict[str, str]:
    teacher_map = {}
    try:
        soup = BeautifulSoup(html, "lxml")
        select_tag = soup.select_one("select")
        if select_tag:
            for option in select_tag.select("option"):
                initials = option.get("value")
                full_name = option.get_text(strip=True)
                if initials and initials != "-1":
                    teacher_map[initials] = full_name
        if not teacher_map:
            compiled_patterns = [_RE_TEACHER_WITH_LINK, _RE_TEACHER_NO_LINK]
            for compiled_pattern in compiled_patterns:
                matches = compiled_pattern.findall(html)
                for match in matches:
                    full_name = match[0].strip()
                    initials = match[1].strip()
                    if initials not in teacher_map:
                        teacher_map[initials] = full_name
    except Exception:
        logger.error("Error parsing teacher HTML")
    return teacher_map
````

## File: glasir_timetable/parsers/timetable_parser.py
````python
import re
from typing import Any, Dict, List, Optional, Tuple
from bs4 import BeautifulSoup
from glasir_timetable.shared import logger
from glasir_timetable.shared.constants import (
    CANCELLED_CLASS_INDICATORS,
    DAY_NAME_MAPPING,
)
from glasir_timetable.shared.date_utils import (
    to_iso_date,
)
from glasir_timetable.shared.formatting import (
    format_academic_year,
    parse_time_range,
)
_RE_STUDENT_INFO = re.compile(
    r"N[æ&aelig;]mingatímatalva:\s*([^,]+),\s*([^\s<]+)", re.IGNORECASE
)
_RE_DATE_RANGE = re.compile(
    r"(\d{1,2}\.\d{1,2}\.\d{4})\s*-\s*(\d{1,2}\.\d{1,2}\.\d{4})"
)
_RE_DAY_DATE = re.compile(r"(\w+)\s+(\d{1,2}/\d{1,2})")
_RE_NOTE_IMG_SRC = re.compile(
    r"note\.gif"
)
def get_timeslot_info(start_col_index):
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
        return {"slot": "N/A", "time": "N/A"}
def parse_timetable_html(
    html: str, teacher_map: Optional[Dict[str, str]] = None
) -> Tuple[Dict[str, Any], List[str]]:
    timetable_data = {"studentInfo": {}, "weekInfo": {}, "events": []}
    homework_ids = []
    if teacher_map is None:
        teacher_map = {}
    try:
        soup = BeautifulSoup(html, "lxml")
        m = _RE_STUDENT_INFO.search(html)
        if m:
            timetable_data["studentInfo"] = {
                "studentName": m.group(1).strip(),
                "class": m.group(2).strip(),
            }
        week_link = soup.select_one("a.UgeKnapValgt")
        if week_link:
            week_text = week_link.get_text(strip=True)
            if week_text.startswith("Vika "):
                timetable_data["weekInfo"]["weekNumber"] = int(
                    week_text.replace("Vika ", "")
                )
        date_range_match = _RE_DATE_RANGE.search(html)
        if date_range_match:
            start_date_str = date_range_match.group(1)
            end_date_str = date_range_match.group(2)
            timetable_data["weekInfo"]["startDate"] = to_iso_date(start_date_str)
            timetable_data["weekInfo"]["endDate"] = to_iso_date(end_date_str)
        table = soup.select_one("table.time_8_16")
        if not table:
            logger.warning("Timetable table not found")
            return timetable_data, homework_ids
        rows = table.select("tr")
        current_day_name_fo = None
        current_date_part = None
        current_year = None
        start_iso_date = timetable_data.get("weekInfo", {}).get("startDate")
        if start_iso_date:
            try:
                current_year = int(start_iso_date.split("-")[0])
                timetable_data["weekInfo"]["year"] = current_year
            except (ValueError, IndexError, TypeError):
                logger.warning(
                    f"Could not parse year from ISO startDate: {start_iso_date}"
                )
                current_year = None
        else:
            current_year = None
        for row in rows:
            cells = row.select("td")
            if not cells:
                continue
            first_cell = cells[0]
            first_cell_text = first_cell.get_text(separator=" ").strip()
            day_match = _RE_DAY_DATE.match(first_cell_text)
            is_day_header = "lektionslinje_1" in first_cell.get(
                "class", []
            ) or "lektionslinje_1_aktuel" in first_cell.get("class", [])
            if is_day_header and day_match:
                current_day_name_fo = day_match.group(1)
                current_date_part = day_match.group(2)
                pass
            elif is_day_header:
                pass
            current_col_index = 0
            day_en = DAY_NAME_MAPPING.get(current_day_name_fo, current_day_name_fo)
            for cell in cells:
                colspan = 1
                try:
                    colspan = int(cell.get("colspan", 1))
                except ValueError:
                    pass
                classes = cell.get("class", [])
                is_lesson = any(
                    cls.startswith("lektionslinje_lesson") for cls in classes
                )
                is_cancelled = any(cls in CANCELLED_CLASS_INDICATORS for cls in classes)
                if is_lesson and current_day_name_fo:
                    a_tags = cell.select("a")
                    if len(a_tags) >= 3:
                        class_code_raw = a_tags[0].get_text(strip=True)
                        teacher_short = a_tags[1].get_text(strip=True)
                        room_raw = a_tags[2].get_text(strip=True)
                        code_parts = class_code_raw.split("-")
                        if code_parts and code_parts[0] == "Várroynd":
                            subject_code = (
                                f"{code_parts[0]}-{code_parts[1]}"
                                if len(code_parts) > 1
                                else code_parts[0]
                            )
                            level = code_parts[2] if len(code_parts) > 2 else ""
                            year_code = code_parts[4] if len(code_parts) > 4 else ""
                        else:
                            subject_code = code_parts[0] if len(code_parts) > 0 else ""
                            level = code_parts[1] if len(code_parts) > 1 else ""
                            year_code = code_parts[3] if len(code_parts) > 3 else ""
                        teacher_full = teacher_map.get(teacher_short, teacher_short)
                        location = room_raw.replace("st.", "").strip()
                        if colspan >= 90:
                            time_info = {"slot": "All day", "time": "08:10-15:25"}
                        else:
                            time_info = get_timeslot_info(current_col_index)
                        iso_date = None
                        if current_date_part and current_year:
                            iso_date = to_iso_date(current_date_part, current_year)
                        elif current_date_part:
                            logger.warning(
                                f"Cannot determine ISO date for '{current_date_part}' - year is missing."
                            )
                        start_time, end_time = parse_time_range(time_info["time"])
                        lesson_id = None
                        lesson_span = cell.select_one('span[id^="MyWindow"][id$="Main"]')
                        if lesson_span and lesson_span.get("id"):
                            span_id = lesson_span["id"]
                            if len(span_id) > 12:
                                lesson_id = span_id[8:-4]
                            else:
                                logger.warning(
                                    f"Found span with unexpected ID format: {span_id}"
                                )
                        else:
                            # Log the cell content for debugging if the span is not found
                            logger.warning(
                                f"Could not find lesson ID span in cell: {cell.prettify()}"
                            )
                        # --- End New Lesson ID Extraction Logic ---
                        lesson = {
                            "title": subject_code,
                            "level": level,
                            "year": format_academic_year(year_code),
                            "date": iso_date,  # Use the converted ISO date
                            "dayOfWeek": day_en,
                            "teacher": (
                                teacher_full.split(" (")[0]
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
                            "lessonId": lesson_id,  # Assign the extracted ID
                            "hasHomeworkNote": False, # Default value
                        }
                        # Check for homework icon separately to populate homework_ids
                        # Use select_one with attribute selector (contains 'note.gif')
                        note_img = cell.select_one(
                            'input[type="image"][src*="note.gif"]'
                        )
                        if note_img:
                            lesson["hasHomeworkNote"] = True
                            if lesson_id:
                                homework_ids.append(lesson_id)
                            else:
                                logger.warning(f"Homework note found, but no lessonId extracted for cell: {cell.prettify()}")
                        timetable_data["events"].append(lesson)
                current_col_index += colspan
    except Exception as e:
        logger.error(f"Error parsing timetable HTML: {e}", exc_info=True)
    return timetable_data, homework_ids
````

## File: glasir_timetable/shared/__init__.py
````python
import logging
logger = logging.getLogger("glasir_timetable")
````

## File: glasir_timetable/shared/concurrency_manager.py
````python
import logging
import math
import time
from typing import Optional
logger = logging.getLogger(__name__)
class ConcurrencyManager:
    def __init__(
        self,
        initial_limit: int,
        min_limit: int = 1,
        max_limit: int = 500,
        increase_step: int = 1,
        decrease_factor: float = 0.5,
        success_threshold: int = 10,
        failure_cooldown_sec: float = 5.0,
        name: Optional[str] = None,
        disabled: bool = False,
    ):
        if not (0 < min_limit <= initial_limit <= max_limit):
            raise ValueError(
                "Concurrency limits invalid: min <= initial <= max must hold."
            )
        if not (0 < decrease_factor < 1):
            raise ValueError("Decrease factor must be between 0 and 1.")
        if increase_step <= 0:
            raise ValueError("Increase step must be positive.")
        if success_threshold <= 0:
            raise ValueError("Success threshold must be positive.")
        if failure_cooldown_sec < 0:
            raise ValueError("Failure cooldown cannot be negative.")
        self.min_limit = min_limit
        self.max_limit = max_limit
        self.increase_step = increase_step
        self.decrease_factor = decrease_factor
        self.success_threshold = success_threshold
        self.failure_cooldown_sec = failure_cooldown_sec
        self.name = name or "ConcurrencyManager"
        self.disabled = disabled
        self._current_limit = float(
            initial_limit
        )
        self._success_streak = 0
        self._last_failure_time = 0.0
        log_message = (
            f"[{self.name}] Initialized: initial={initial_limit}, min={min_limit}, "
            f"max={max_limit}, inc_step={increase_step}, dec_factor={decrease_factor}, "
            f"succ_thresh={success_threshold}, fail_cooldown={failure_cooldown_sec}s"
        )
        if self.disabled:
            log_message += " (Dynamic adjustments DISABLED)"
        logger.info(log_message)
    def get_limit(self) -> int:
        return math.floor(self._current_limit)
    def get_current_limit(self) -> float:
        return self._current_limit
    def report_success(self) -> None:
        self._success_streak += 1
        if self.disabled:
            return
        self._success_streak += 1
        current_time = time.monotonic()
        if current_time < self._last_failure_time + self.failure_cooldown_sec:
            # so we don't increase immediately after cooldown based on old successes
            self._success_streak = 0
            return
        if self._success_streak >= self.success_threshold:
            new_limit = min(self._current_limit + self.increase_step, self.max_limit)
            if new_limit > self._current_limit:
                old_limit_int = self.get_limit()
                self._current_limit = new_limit
                logger.info(
                    f"[{self.name}] Limit increased: {old_limit_int} -> {self.get_limit()} "
                    f"(success streak: {self._success_streak})"
                )
            self._success_streak = 0
    def report_failure(self) -> None:
        if self.disabled:
            logger.warning(
                f"[{self.name}] Failure reported but adjustments are disabled."
            )
            return
        self._success_streak = 0
        new_limit = max(self._current_limit * self.decrease_factor, self.min_limit)
        if new_limit < self._current_limit:
            old_limit_int = self.get_limit()
            self._current_limit = new_limit
            current_time = time.monotonic()
            self._last_failure_time = current_time
            logger.warning(
                f"[{self.name}] Limit decreased: {old_limit_int} -> {self.get_limit()} "
                f"(failure detected)"
            )
        else:
            logger.warning(
                f"[{self.name}] Failure detected but limit already at minimum ({self.get_limit()})"
            )
    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(name='{self.name}', "
            f"current={self.get_limit()}, min={self.min_limit}, max={self.max_limit}, "
            f"success_streak={self._success_streak}/{self.success_threshold})"
        )
````

## File: glasir_timetable/shared/constants.py
````python
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
GLASIR_BASE_URL = "https://tg.glasir.fo"
GLASIR_TIMETABLE_URL = f"{GLASIR_BASE_URL}/132n/"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}
TEACHER_MAP_CACHE_TTL = 86400
DEFAULT_WEEK_FETCH_CONCURRENCY = (
    5
)
DEFAULT_HOMEWORK_FETCH_CONCURRENCY = 20
DEFAULT_WEEK_PROCESS_CONCURRENCY = (
    4
)
FORCE_MAX_WEEK_FETCH_CONCURRENCY = 10
FORCE_MAX_HOMEWORK_FETCH_CONCURRENCY = 30
CONCURRENCY_CONFIG_FILENAME = "concurrency_config.json"
````

## File: glasir_timetable/shared/date_utils.py
````python
import re
from datetime import datetime
from functools import lru_cache
from typing import Dict, Optional, Tuple
PERIOD_DATE_FULL = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")
PERIOD_DATE_SHORT = re.compile(r"(\d{1,2})\.(\d{1,2})")
HYPHEN_DATE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
SLASH_DATE_SHORT = re.compile(r"(\d{1,2})/(\d{1,2})")
SLASH_DATE_WITH_YEAR = re.compile(r"(\d{1,2})/(\d{1,2})-(\d{4})")
#     Detect the format of a date string.
#     ... (rest of docstring and code) ...
#     """
@lru_cache(maxsize=256)
def parse_date(date_str: str, year: Optional[int] = None) -> Optional[Dict[str, str]]:
    if not date_str:
        return None
    if year is None:
        year = datetime.now().year
    # Handle period format (DD.MM.YYYY or DD.MM)
    match = PERIOD_DATE_FULL.match(date_str)
    if match:
        day, month, year = match.groups()
        return {"day": day.zfill(2), "month": month.zfill(2), "year": year}
    match = PERIOD_DATE_SHORT.match(date_str)
    if match:
        day, month = match.groups()
        return {"day": day.zfill(2), "month": month.zfill(2), "year": str(year)}
    # Handle hyphen format (YYYY-MM-DD)
    match = HYPHEN_DATE.match(date_str)
    if match:
        year, month, day = match.groups()
        return {"day": day.zfill(2), "month": month.zfill(2), "year": year}
    # Handle slash format (DD/MM)
    match = SLASH_DATE_SHORT.match(date_str)
    if match:
        # Assume DD/MM format (European)
        day, month = match.groups()
        return {"day": day.zfill(2), "month": month.zfill(2), "year": str(year)}
    # Handle DD/MM-YYYY format (like 24/3-2025)
    match = SLASH_DATE_WITH_YEAR.match(date_str)
    if match:
        day, month, year = match.groups()
        return {"day": day.zfill(2), "month": month.zfill(2), "year": year}
    # If we got here, we couldn't parse the date
    return None
def format_date(
    date_dict: Optional[Dict[str, str]], output_format: str = "hyphen"
) -> Optional[str]:
    if not date_dict:
        return None
    required_keys = ["year", "month", "day"]
    if not all(key in date_dict for key in required_keys):
        return None
    year = date_dict["year"]
    month = date_dict["month"]
    day = date_dict["day"]
    if output_format == "hyphen":
        return f"{year}-{month}-{day}"
    elif output_format == "period":
        return f"{day}.{month}.{year}"
    elif output_format == "slash":
        return f"{day}/{month}/{year}"
    elif output_format == "filename":
        return f"{month}.{day}"
    elif output_format == "iso":
        return f"{year}-{month}-{day}"
    else:
        return None
@lru_cache(maxsize=128)
def convert_date_format(
    date_str: str, output_format: str = "hyphen", year: Optional[int] = None
) -> Optional[str]:
    parsed = parse_date(date_str, year)
    if parsed:
        return format_date(parsed, output_format)
    return None
#     Check if a string is a valid date in any of the supported formats.
#     ... (rest of docstring and code) ...
#     """
#     Format dates specifically for the timetable filename format.
#     ... (rest of docstring and code) ...
#     """
@lru_cache(maxsize=128)
def to_iso_date(date_str: str, year: Optional[int] = None) -> Optional[str]:
    if not date_str:
        return None
    return convert_date_format(date_str, "iso", year)
def parse_time_range(time_range: str) -> Tuple[Optional[str], Optional[str]]:
    if not time_range or "-" not in time_range:
        return None, None
    parts = time_range.split("-")
    if len(parts) != 2:
        return None, None
    return parts[0].strip(), parts[1].strip()
````

## File: glasir_timetable/shared/error_utils.py
````python
import contextlib
import traceback
from glasir_timetable import add_error, logger
class GlasirError(Exception):
_console_listener_registry = {"attached_pages": set(), "listeners": {}}
@contextlib.asynccontextmanager
async def error_screenshot_context(
    page,
    screenshot_name: str,
    error_type: str = "general_errors",
    take_screenshot: bool = False,
):
    try:
        yield
    except Exception as e:
        logger.error(f"Error: {e}")
        screenshot_path = None
        if take_screenshot:
            screenshot_path = f"error_{screenshot_name}.png"
            logger.warning(f"Taking a screenshot for debugging: {screenshot_path}")
            try:
                await page.screenshot(path=screenshot_path)
                logger.info(f"Screenshot saved to {screenshot_path}")
            except Exception as screenshot_error:
                logger.error(f"Failed to take screenshot: {screenshot_error}")
        error_data = {"traceback": traceback.format_exc()}
        if screenshot_path:
            error_data["screenshot"] = screenshot_path
        add_error(error_type, str(e), error_data)
        raise
def register_console_listener(page, listener=None):
    page_id = id(page)
    if page_id in _console_listener_registry["attached_pages"]:
        logger.debug(f"Console listener already attached to page {page_id}")
        return
    if listener is None:
        listener = default_console_listener
    _console_listener_registry["listeners"][page_id] = listener
    page.on("console", listener)
    _console_listener_registry["attached_pages"].add(page_id)
    logger.debug(f"Console listener attached to page {page_id}")
def default_console_listener(msg):
    message_type = msg.type
    text = msg.text
    if message_type == "error":
        logger.error(f"Console error: {text}")
        add_error("console_errors", text)
    elif message_type == "warning":
        logger.warning(f"Console warning: {text}")
    else:
        logger.debug(f"Console {message_type}: {text}")
````

## File: glasir_timetable/shared/formatting.py
````python
from functools import lru_cache
@lru_cache()
def format_academic_year(year_code):
    if len(year_code) == 4:
        return f"20{year_code[:2]}-20{year_code[2:]}"
    return year_code
def parse_time_range(time_range_str):
    return time_range_str, time_range_str
````

## File: glasir_timetable/storage/exporter.py
````python
import os
from datetime import datetime
from typing import Any, Dict, Optional
import aiofiles
import orjson
from glasir_timetable.shared import logger
from glasir_timetable.shared.date_utils import to_iso_date
async def save_json(data: Dict[str, Any], path: str) -> bool:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            options = orjson.OPT_INDENT_2 | orjson.OPT_APPEND_NEWLINE
            await f.write(orjson.dumps(data, option=options).decode("utf-8"))
        logger.info("Saved JSON successfully")
        return True
    except Exception:
        logger.error("Failed to save JSON")
        return False
async def save_timetable_export(
    timetable_data: Dict[str, Any],
    output_dir: str,
    filename: Optional[str] = None,
    user_id: Optional[str] = None,
) -> str:
    if not filename:
        week_info = timetable_data.get("weekInfo", {})
        start_date_iso = week_info.get("startDate")
        try:
            if start_date_iso:
                date_obj = datetime.fromisoformat(start_date_iso)
                iso_year, iso_week, _ = date_obj.isocalendar()
                filename = f"{iso_year}-W{iso_week:02d}.json"
            else:
                raise ValueError("Start date is missing in weekInfo")
        except (ValueError, TypeError) as e:
            logger.warning(
                f"Could not determine ISO week/year from startDate '{start_date_iso}' ({e}). Falling back."
            )
            year = week_info.get("year")
            week_num = week_info.get("weekNumber")
            if year and isinstance(week_num, int):
                filename = (
                    f"{year}-W{week_num:02d}.json"
                )
                logger.warning(f"Using originally parsed year/week: {filename}")
            else:
                logger.warning("Falling back to old filename format with dates.")
                week_num_str = str(week_num) if week_num is not None else "unknown"
                end_date_str = week_info.get("endDate")
                end_date_iso = to_iso_date(end_date_str) if end_date_str else "unknown"
                start_date_iso_fallback = start_date_iso or "unknown"
                end_date_iso_fallback = end_date_iso or "unknown"
                filename = f"week_{week_num_str}_{start_date_iso_fallback}_to_{end_date_iso_fallback}.json"
    user_dir = output_dir
    os.makedirs(user_dir, exist_ok=True)
    path = os.path.join(user_dir, filename)
    await save_json(timetable_data, path)
    return path
````

## File: glasir_timetable/storage/profile_manager.py
````python
from pathlib import Path
from typing import Any, Dict, List, Optional
import aiofiles
import orjson
from ..shared.constants import DEFAULT_HOMEWORK_FETCH_CONCURRENCY
from ..shared.constants import DEFAULT_WEEK_FETCH_CONCURRENCY
from ..shared.constants import (
    DEFAULT_WEEK_PROCESS_CONCURRENCY,
)
from ..shared.constants import CONCURRENCY_CONFIG_FILENAME
# We will remove the old accounts directory later.
# Let's define the structure needed directly for now.
class ProfileData:
    def __init__(self, username: str, base_dir: Path):
        self.username = username
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.credentials_path = self.base_dir / "credentials.json"
        self.cookies_path = self.base_dir / "cookies.json"
        self.student_info_path = self.base_dir / "student-id.json"
        self.weeks_dir = (
            self.base_dir / "weeks"
        )
        self.concurrency_config_path = self.base_dir / CONCURRENCY_CONFIG_FILENAME
    async def _load_json(self, path: Path) -> Optional[Dict[str, Any]]:
        if not path.exists():
            return None
        try:
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                content = await f.read()
                return orjson.loads(content)
        except (orjson.JSONDecodeError, IOError) as e:
            print(f"Error loading JSON from {path}: {e}")
            return None
    async def _save_json(self, path: Path, data: Dict[str, Any]) -> None:
        try:
            self.base_dir.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                options = orjson.OPT_INDENT_2 | orjson.OPT_APPEND_NEWLINE
                await f.write(orjson.dumps(data, option=options).decode("utf-8"))
        except IOError as e:
            print(f"Error saving JSON to {path}: {e}")
    async def load_credentials(self) -> Optional[Dict[str, Any]]:
        return await self._load_json(self.credentials_path)
    async def save_credentials(self, credentials: Dict[str, Any]) -> None:
        await self._save_json(self.credentials_path, credentials)
    async def load_cookies(self) -> Optional[Dict[str, Any]]:
        return await self._load_json(self.cookies_path)
    async def save_cookies(self, cookies: Dict[str, Any]) -> None:
        await self._save_json(self.cookies_path, cookies)
    async def load_student_info(self) -> Optional[Dict[str, Any]]:
        return await self._load_json(self.student_info_path)
    async def save_student_info(self, info: Dict[str, Any]) -> None:
        await self._save_json(self.student_info_path, info)
    async def load_concurrency_config(self) -> Dict[str, int]:
        config_data = await self._load_json(self.concurrency_config_path)
        if config_data is None:
            return {
                "week_fetch_limit": DEFAULT_WEEK_FETCH_CONCURRENCY,
                "homework_fetch_limit": DEFAULT_HOMEWORK_FETCH_CONCURRENCY,
                "week_process_limit": DEFAULT_WEEK_PROCESS_CONCURRENCY,
            }
        return {
            "week_fetch_limit": config_data.get(
                "week_fetch_limit", DEFAULT_WEEK_FETCH_CONCURRENCY
            ),  # Corrected name
            "homework_fetch_limit": config_data.get(
                "homework_fetch_limit", DEFAULT_HOMEWORK_FETCH_CONCURRENCY
            ),  # Corrected name
            "week_process_limit": config_data.get(
                "week_process_limit", DEFAULT_WEEK_PROCESS_CONCURRENCY
            ),  # Added loading with default
        }
    async def save_concurrency_config(self, config_data: Dict[str, int]) -> None:
        await self._save_json(self.concurrency_config_path, config_data)
    def __repr__(self):
        return f"<ProfileData(username={self.username}, base_dir={self.base_dir})>"
class ProfileManager:
    _instance: Optional["ProfileManager"] = None
    def __init__(self, accounts_root: Optional[str | Path] = None):
        if accounts_root:
            self.accounts_root = Path(accounts_root)
        else:
            # Determine default path relative to project structure if needed
            # Assuming a standard project layout where this file is in storage/
            project_root = Path(__file__).parent.parent.parent
            self.accounts_root = project_root / "glasir_timetable" / "accounts"
            # Fallback if structure is different (less robust)
        self.accounts_root.mkdir(parents=True, exist_ok=True)
        self._profiles_cache: Dict[str, ProfileData] = {}  # Cache loaded profiles
    @classmethod
    def get_instance(
        cls, accounts_root: Optional[str | Path] = None
    ) -> "ProfileManager":
        if cls._instance is None:
            cls._instance = ProfileManager(accounts_root=accounts_root)
        elif accounts_root is not None and cls._instance.accounts_root != Path(
            accounts_root
        ):
            # If called again with a different root, re-initialize (or raise error)
            # This handles cases like testing where a different root might be needed
            # TODO: Consider if this re-initialization is the desired behavior for a singleton
            print(
                f"Warning: Re-initializing ProfileManager singleton with new root: {accounts_root}"
            )
            cls._instance = ProfileManager(accounts_root=accounts_root)
        return cls._instance
    def list_profiles(self) -> List[str]:
        return [
            d.name
            for d in self.accounts_root.iterdir()
            if d.is_dir()
            and not d.name.startswith(".")
            and d.name
            not in ("global", "__pycache__")  # Exclude common non-profile dirs
        ]
    def profile_exists(self, username: str) -> bool:
        return (self.accounts_root / username).is_dir()
    def load_profile(self, username: str) -> ProfileData:
        if not self.profile_exists(username):
            raise FileNotFoundError(
                f"Profile directory not found for username: {username}"
            )
        if username in self._profiles_cache:
            return self._profiles_cache[username]
        profile_dir = self.accounts_root / username
        profile = ProfileData(username, base_dir=profile_dir)
        self._profiles_cache[username] = profile
        return profile
    async def create_profile(
        self, username: str, credentials: Optional[Dict] = None
    ) -> ProfileData:
        profile_dir = self.accounts_root / username
        profile_dir.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
        # Use load_profile to potentially get from cache or create ProfileData instance
        # Need to handle case where load_profile raises FileNotFoundError if dir *just* created
        # Let's adjust logic slightly: create ProfileData directly if not in cache
        if username in self._profiles_cache:
            profile = self._profiles_cache[username]
        else:
            profile = ProfileData(username, base_dir=profile_dir)
            self._profiles_cache[username] = profile
        if credentials:
            await profile.save_credentials(credentials)
        if not profile.student_info_path.exists():
            await profile.save_student_info({})
        profile.weeks_dir.mkdir(exist_ok=True)
        return profile
````

## File: glasir_timetable/__init__.py
````python
__all__ = [
    "logger",
    "add_error",
    "get_error_summary",
    "clear_errors",
    "update_stats",
    "configure_raw_responses",
]
__version__ = "1.1.0"
import logging
import os
error_collection = {
    "homework_errors": [],
    "navigation_errors": [],
    "extraction_errors": [],
    "general_errors": [],
    "javascript_errors": [],
    "console_errors": [],
    "auth_errors": [],
    "resource_errors": [],
}
error_config = {
    "collect_details": False,
    "collect_tracebacks": False,
    "error_limit": 100,
}
raw_response_config = {
    "save_enabled": False,
    "directory": "glasir_timetable/raw_responses/",
    "save_request_details": False,
}
raw_response_config["save_enabled"] = False
stats = {
    "total_weeks": 0,
    "processed_weeks": 0,
    "start_time": None,
    "homework_success": 0,
    "homework_failed": 0,
}
def setup_logging(level=logging.INFO):
    logger = logging.getLogger("glasir_timetable")
    logger.setLevel(level)
    if not logger.handlers:
        class TqdmLoggingHandler(logging.Handler):
            def emit(self, record):
                try:
                    msg = self.format(record)
                    from tqdm import tqdm
                    tqdm.write(msg)
                except Exception:
                    self.handleError(record)
        console_handler = TqdmLoggingHandler()
        console_handler.setLevel(level)
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    return logger
logger = setup_logging()
def add_error(error_type, message, details=None):
    if error_type not in error_collection:
        error_collection[error_type] = []
    if len(error_collection[error_type]) >= error_config["error_limit"]:
        return
    error_data = {"message": message}
    # Only include details if configured to do so
    if error_config["collect_details"] and details:
        # Filter out tracebacks if not configured to collect them
        if not error_config["collect_tracebacks"] and details.get("traceback"):
            details = {k: v for k, v in details.items() if k != "traceback"}
        error_data["details"] = details
    error_collection[error_type].append(error_data)
def get_error_summary():
    total_errors = sum(len(errors) for errors in error_collection.values())
    return {
        "total": total_errors,
        "by_type": {k: len(v) for k, v in error_collection.items() if len(v) > 0},
    }
def clear_errors():
    for key in error_collection:
        error_collection[key] = []
def update_stats(key, value=1, increment=True):
    if increment and key in stats:
        stats[key] += value
    else:
        stats[key] = value
def configure_raw_responses(
    save: bool, directory: str = None, save_request_details: bool = False
):
    raw_response_config["save_enabled"] = save
    raw_response_config["save_request_details"] = save_request_details
    if directory is None:
        directory = os.path.join("output", "raw_responses")
    raw_response_config["directory"] = directory
    # Create the directory if it doesn't exist and saving is enabled
    if save:
        import os
        os.makedirs(directory, exist_ok=True)
        logger.info(f"Raw responses will be saved to: {directory}")
        logger.info(f"Raw response saving enabled. Directory: {directory}")
    else:
        logger.info("Raw response saving is disabled.")
````

## File: glasir_timetable/models.py
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
        frozen = True
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
    year: str
    date: str
    day: str
    teacher: str
    teacher_short: str = Field(..., alias="teacherShort")
    location: str
    time_slot: Union[int, str] = Field(..., alias="timeSlot")
    start_time: str = Field(..., alias="startTime")
    end_time: str = Field(..., alias="endTime")
    time_range: str = Field(..., alias="timeRange")
    cancelled: bool = False
    lesson_id: Optional[str] = Field(None, alias="lessonId")
    description: Optional[str] = None
    @validator("date")
    def validate_date_format(cls, v):
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
        frozen = True
        json_schema_extra = {
            "example": {
                "title": "evf",
                "level": "A",
                "year": "2024-2025",
                "date": "2025-03-24",
                "day": "Monday",
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
        frozen = True
    pass
````

## File: __main__.py
````python
import asyncio
import sys
from main import main
if __name__ == "__main__":
    asyncio.run(main())
````

## File: .gitignore
````
# Byte-compiled / optimized / DLL files
__pycache__/
*.py[cod]
*$py.class

# C extensions
*.so

# Distribution / packaging
dist/
build/
*.egg-info/
*.egg

# Virtual environments
venv/
env/
ENV/
.env/
.venv/

# JSON files (credentials and cache)
*.json


# macOS system files
.DS_Store
.AppleDouble
.LSOverride
._*

# IDE files
.idea/
.vscode/
*.swp
*.swo
.cursor/
.cursorignore
.cursorindexingignore

# Testing
.pytest_cache/
htmlcov/
.tox/
.coverage
.coverage.*
.cache/
nosetests.xml
coverage.xml
*.cover

# Logs and databases
*.log
*.sqlite
*.db

# Local development settings
.env

# Project specific
weeks/
.ai/
.specstory/

# Documentation and notes that shouldn't be in the repo
notepad_context/
report.md
next_steps.md 
cline_task_apr-6-2025_11-19-14-pm.md
/output/
glasir_login_network_log.txt
````

## File: INSTALLATION.md
````markdown
# Installation Instructions

---

## Prerequisites

- Python 3.7 or higher
- Playwright (for login and HTML parsing)
- A valid Glasir account

---

## Step 1: Install Dependencies

```bash
pip3 install -r requirements.txt
python3 -m playwright install chromium
```

---

## Step 2: Clone and Setup

```bash
git clone https://github.com/yourusername/glasir_timetable.git
cd glasir_timetable

# Optional: create credentials file
echo '{"username": "your_username", "password": "your_password"}' > glasir_timetable/credentials.json
```

If no credentials file is created, you will be prompted on first run.

---

## Step 3: Run the Application

```bash
# Extract current week only
python3 -m glasir_timetable.main

# Extract current week plus 2 weeks forward and 2 weeks backward
python3 -m glasir_timetable.main --weekforward 2 --weekbackward 2

# Extract all available weeks
python3 -m glasir_timetable.main --all-weeks
```

---

## Authentication Details

- First login uses Playwright to authenticate and save cookies.
- Subsequent requests use saved cookies (`cookies.json` by default).
- Cookies refresh automatically when expired.

---

### Per-Account Data Storage

All credentials, cookies, student info, and exported timetable data are stored **per user account** inside `glasir_timetable/accounts/USERNAME/`. This allows you to manage multiple Glasir accounts independently, with separate login sessions and data exports for each user.


---

## Advanced Configuration

### Cookie Authentication

Enabled by default. Disable refresh with:

```bash
python3 -m glasir_timetable.main --no-cookie-refresh
```

### Custom Output Directory

```bash
python3 -m glasir_timetable.main --output-dir ~/my_timetable_data
```

### Update Teacher Map

```bash
python3 -m glasir_timetable.main --teacherupdate --skip-timetable
```

### Debugging and Logging

```bash
# Enable detailed logging
python3 -m glasir_timetable.main --log-level DEBUG --collect-error-details --collect-tracebacks

# Save logs to file
python3 -m glasir_timetable.main --log-file timetable_extraction.log

# Enable screenshots on errors
python3 -m glasir_timetable.main --enable-screenshots
```

---

## Docker Usage (Optional)

```bash
docker build -t glasir_timetable .
docker run -v $(pwd)/data:/app/data glasir_timetable --output-dir /app/data
```

---

## Troubleshooting

### Authentication Issues

- Check credentials
- Delete `cookies.json` to force fresh login
- Verify internet connection

### Extraction Issues

- Retry later if Glasir is down
- Check logs for errors
- Verify account access

### Playwright Browser Issues

```bash
python3 -m playwright install --force
```

---

## Developer Setup (Brief)

- Use a **virtual environment**:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 -m playwright install chromium
```

- **Run tests** (if available):

```bash
pytest
```

- Follow code style and submit pull requests for contributions.

---

## Next Steps

See [README.md](README.md) for features, architecture, and usage details.
````

## File: main.py
````python
import os
import json
import asyncio
import sys
import argparse
import re
import logging
import time
from pathlib import Path
from datetime import datetime, timedelta
import getpass
if __name__ == "__main__":
    project_root = os.path.abspath(os.path.dirname(__file__))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
# Now the imports will work both when run as a script and when imported as a module
# Keep necessary high-level imports
from glasir_timetable import logger, setup_logging, stats, update_stats, clear_errors # Removed unused imports
# Imports moved to specific modules (auth, api, extractors, interface, etc.)
# Removed imports from core.*, data.*, and unused shared.*
# Imports for the current main structure
from glasir_timetable.interface.cli import parse_args, select_account
from glasir_timetable.interface.config_manager import load_config
from glasir_timetable.interface.application import Application
from glasir_timetable.interface.orchestrator import run_extraction
from glasir_timetable.storage.profile_manager import ProfileManager # Use ProfileManager for account/profile handling
# Removed local duplicate function is_full_auth_data_valid (logic now in config_manager)
# Removed local duplicate function generate_credentials_file (handled by profile/manager)
# Removed local duplicate function prompt_for_credentials (handled by interface.cli)
async def main():
    # Initialize statistics
    clear_errors()  # Clear any errors from previous runs
    update_stats("start_time", time.time(), increment=False)
    args = parse_args() # Use imported function
    # If no log file provided, use default output/logs/glasir_timetable.log
    if not args.log_file:
        log_dir = os.path.join("output", "logs")
        os.makedirs(log_dir, exist_ok=True)
        args.log_file = os.path.join(log_dir, "glasir_timetable.log")
    # Ensure directory for log file exists (handles custom paths)
    log_dir = os.path.dirname(args.log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    # Generate date string for log filename
    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    # Create dated log filename
    base_log_file = args.log_file
    if base_log_file.endswith('.log'):
        dated_log_file = base_log_file[:-4] + f"_{date_str}.log"
    else:
        dated_log_file = base_log_file + f"_{date_str}.log"
    # Create latest log filename in same directory
    latest_log_file = os.path.join(log_dir, "latest.log")
    # Configure logging based on command-line arguments
    log_level = getattr(logging, args.log_level)
    if args.log_file:
        formatter = logging.Formatter('[%(asctime)s] %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        # Handler for dated log file (append mode)
        dated_handler = logging.FileHandler(dated_log_file, mode='a')
        dated_handler.setFormatter(formatter)
        logger.addHandler(dated_handler)
        # Handler for latest.log (overwrite mode)
        latest_handler = logging.FileHandler(latest_log_file, mode='w')
        latest_handler.setFormatter(formatter)
        logger.addHandler(latest_handler)
    # Set the log level
    logger.setLevel(log_level)
    for handler in logger.handlers:
        handler.setLevel(log_level)
    # ---- ACCOUNT SELECTION ----
    profile_manager = ProfileManager.get_instance() # Get instance for checking
    if args.account:
        # Account specified via command line
        selected_username = args.account
        profile_created = False # Assume existing profile when specified via arg
        logger.info(f"Account '{selected_username}' specified via --account argument.")
        # Validate if the specified profile exists
        if not profile_manager.profile_exists(selected_username):
            logger.error(f"Error: Account profile '{selected_username}' specified via --account does not exist.")
            sys.exit(1) # Exit gracefully
        else:
            logger.debug(f"Validated existence of profile: {selected_username}")
    else:
        # No account specified, use interactive selection
        logger.debug("No --account argument provided, proceeding with interactive selection.")
        # Use imported function
        selected_username, profile_created = await select_account() # Capture the tuple
    if selected_username is None:
        logger.error("No accounts found. Please create an account before running the timetable extraction.")
        return
    # Use imported function
    # Pass the profile_created flag to load_config
    config = await load_config(args, selected_username, profile_created=profile_created)
    # Removed outdated Playwright setup and service factory logic.
    # This is now handled within the Application/Orchestrator structure.
    from glasir_timetable.interface.application import Application
    # Instantiate Application with the loaded config
    app = Application(config)
    # Run the main extraction process via the orchestrator
    await run_extraction(app)
# Execution completed
update_stats("end_time", time.time(), increment=False)
start_time = stats.get("start_time")
end_time = stats.get("end_time")
if start_time is None or end_time is None:
    elapsed_time = 0.0
else:
    elapsed_time = end_time - start_time
logger.info(f"Execution completed in {elapsed_time:.2f} seconds")
if __name__ == "__main__":
    import argparse
    import sys
    import asyncio
    import cProfile
    import pstats
    import io
    from pathlib import Path
    # Ensure project root is in sys.path (redundant if first block ran, but safe)
    project_root = os.path.abspath(os.path.dirname(__file__))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    # Install uvloop for potential performance gains
    try:
        import uvloop
        uvloop.install()
        logger.info("Using uvloop for asyncio event loop.")
    except ImportError:
        logger.warning("uvloop not found, using standard asyncio event loop.")
        pass # Fallback to standard asyncio loop if uvloop is not installed
    # Check for --profile argument *without* consuming other arguments
    profile_enabled = "--profile" in sys.argv
    if profile_enabled:
        # Remove --profile so it doesn't interfere with the main parser
        sys.argv.remove("--profile")
    if profile_enabled:
        profile_output = "profile_output.prof"
        pr = cProfile.Profile()
        pr.enable()
        try:
            asyncio.run(main())
        finally:
            pr.disable()
            s = io.StringIO()
            ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
            ps.print_stats(30)
            print("Profiling results (top 30 by cumulative time):")
            print(s.getvalue())
            ps.dump_stats(profile_output)
            print(f"Full profile data saved to {profile_output}")
    else:
        asyncio.run(main())
````

## File: pyproject.toml
````toml
[tool.poetry]
name = "glasir_timetable"
version = "0.1.0"
description = "Extracts timetable data from the Glasir website and saves it in JSON format"
authors = ["Your Name <your.email@example.com>"]
readme = "README.md"
packages = [{include = "glasir_timetable"}]

[tool.poetry.dependencies]
python = "^3.8"
playwright = "^1.40.0"
beautifulsoup4 = "^4.12.0"
tqdm = "^4.66.0"
requests = "^2.31.0"
python-dotenv = "^1.0.0"
pydantic = "^2.0.0"
lxml = "^4.9.0"
httpx = "^0.25.0"
cachetools = "^5.3.3" # Added for TTL caching
orjson = "^3.0.0"
uvloop = "^0.17.0" # Added for performance
aiofiles = "^23.2.1" # Added for async file I/O

[tool.poetry.group.dev.dependencies]
pytest = "^7.4.0"
pytest-asyncio = "^0.21.1"
black = "^23.7.0"
isort = "^5.12.0"
mypy = "^1.5.1"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"

[tool.poetry.scripts]
glasir = "glasir_timetable.main:main"
````

## File: README.md
````markdown
# Glasir Timetable Exporter

A powerful tool for extracting, processing, and exporting timetable data from Glasir's internal timetable system.

---

## Overview

This application authenticates with Glasir's system, fetches timetable and homework data via internal APIs, and exports the data as structured JSON files. It supports parallel extraction, teacher mapping, and flexible week range selection.

The tool uses a hybrid approach. It **automatically operates in an API-only mode** using `httpx` when valid authentication data (cookies and student info) is found for the selected profile, significantly speeding up extraction. If valid data is missing or expired, it seamlessly falls back to using Playwright browser automation for login and initial data retrieval. It caches teacher mappings and student info to optimize subsequent runs. All data, cookies, and credentials are stored per account under dedicated directories, enabling seamless management of multiple user accounts.

---

## Features

- **Automatic Hybrid Extraction:** Uses fast `httpx` API calls when possible (valid cookies/student info found), seamlessly falling back to Playwright browser automation for login/data retrieval only when necessary.
- **Efficient Authentication:** Reuses saved cookies and student info to bypass repeated Playwright logins.
- **Parallel fetching** of timetable and homework for multiple weeks.
- **Teacher initials resolution** with caching.
- **Homework integration** merged into timetable events.
- **Export to JSON** for easy integration with other tools.
- **Configurable week ranges** (current, past, future, or all).
- **Robust error handling** and detailed logging.
- **CLI interface** with comprehensive options.
- **Per-account data and cookie management** for multiple users.
- **Caching of teacher maps and student info** to optimize repeated runs.

---

## Architecture

The system features a modular architecture separating concerns like authentication, API interaction, data parsing, and storage.

For a detailed explanation and diagrams, see the [Architecture Documentation](docs/architecture.md).

---

## Usage

Basic example to extract the current week, plus 2 weeks forward and 2 weeks backward:

```bash
python3 -m glasir_timetable --weekforward 2 --weekbackward 2
```

### Command-line Options

- `--username`: Glasir username (without @glasir.fo)
- `--password`: Glasir password
- `--credentials-file`: JSON file with credentials (default: `glasir_timetable/accounts/<username>/credentials.json`)
- `--weekforward`: Weeks forward to extract
- `--weekbackward`: Weeks backward to extract
- `--all-weeks`: Extract all available weeks
- `--output-dir`: Directory for exports (default: `output/`)
- `--headless`: Run browser headless (default: true)
- `--log-level`: Logging level (e.g., INFO, DEBUG)
- `--log-file`: Log to a specified file
- `--collect-error-details`: Collect detailed error info
- `--collect-tracebacks`: Collect tracebacks
- `--enable-screenshots`: Save screenshots on browser errors
- `--error-limit`: Max errors per category before stopping
- `--use-cookies`: Use saved cookies for login (default: true)
- `--cookie-path`: Path for cookies file (default: `glasir_timetable/accounts/<username>/cookies.json`)
- `--no-cookie-refresh`: Disable automatic cookie refresh
- `--teacherupdate`: Force update of the teacher cache
- `--skip-timetable`: Skip timetable extraction (e.g., only fetch homework)

---

## Output Format

Exports JSON files per week to the specified output directory. Example (`output/week_2023_10.json`):

```json
{
  "weekInfo": {
    "weekNumber": 10,
    "year": 2023,
    "startDate": "2023-03-06",
    "endDate": "2023-03-12"
  },
  "events": [
    {
      "lessonId": "1234567",
      "startTime": "08:15",
      "endTime": "10:00",
      "dayOfWeek": 1, // Monday
      "subject": "Mathematics",
      "room": "A1.02",
      "teacher": "John Doe",
      "teacherInitials": "JDO",
      "description": "Homework: Complete exercises 1-10 on page 42"
    }
    // ... more events
  ]
}
```

---

## Installation

See [INSTALLATION.md](INSTALLATION.md) for detailed setup instructions.

---

## Testing

The project uses `pytest` for running tests. Mocks are utilized to isolate components during unit testing.

For details on the testing strategy and how to run tests, see the [Testing Documentation](docs/testing.md).

---

## Contributing

Contributions are welcome! Please fork the repository, create a feature branch, and submit a pull request.

---

## License

MIT License. See the LICENSE file for details.
````

## File: requirements.txt
````
playwright>=1.40.0
beautifulsoup4>=4.12.0
httpx>=0.25.0
lxml>=4.9.0
orjson>=3.0.0
requests>=2.31.0
tqdm>=4.66.0
uvloop>=0.17.0 # Added for performance

# Additional utility packages (optional, but recommended)
python-dotenv>=1.0.0
pydantic>=2.0.0
````
