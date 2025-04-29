# glasir_api/core/extractor.py
import asyncio
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime # Import datetime
import aiofiles # For async file saving
from pathlib import Path # For path handling
import time # For timestamping filenames

from cachetools import TTLCache, cached

# Use relative imports for components within the 'glasir_api' package
from .client import AsyncApiClient
from .parsers import parse_homework_html, parse_teacher_html
from .constants import TEACHER_MAP_CACHE_TTL

# Placeholder for ConcurrencyManager if it's defined elsewhere or added later
ConcurrencyManager = Any

# Basic logging setup
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(name)s - %(message)s')
log = logging.getLogger(__name__)

# Directory for saving debug HTML
DEBUG_HTML_DIR = Path("debug_html")
DEBUG_HTML_DIR.mkdir(exist_ok=True) # Create dir if it doesn't exist

# Cache for teacher map to avoid frequent lookups
teacher_cache: TTLCache = TTLCache(maxsize=1, ttl=TEACHER_MAP_CACHE_TTL)

class TimetableExtractor:
    """
    Extracts timetable, homework, and teacher data from the Glasir system
    using an AsyncApiClient.
    """

    def __init__(self, api_client: AsyncApiClient, lname: Optional[str] = None, save_debug_html: bool = False):
        """
        Initializes the TimetableExtractor.

        Args:
            api_client: An instance of AsyncApiClient configured for the Glasir API.
            lname: The extracted 'lname' session parameter.
            save_debug_html: If True, saves raw HTML responses to the 'debug_html' directory. Defaults to False.
        """
        self.api = api_client
        self.lname = lname # Store lname
        self.save_debug_html = save_debug_html # Store the flag
        log.info(f"TimetableExtractor initialized with lname: {self.lname}, save_debug_html: {self.save_debug_html}")

    @cached(teacher_cache)
    async def fetch_teacher_map(self) -> Dict[str, str]:
        """
        Fetches the teacher initials to full name mapping from the API.
        Results are cached for TEACHER_MAP_CACHE_TTL seconds.

        Returns:
            A dictionary mapping teacher initials (str) to full names (str).
            Returns an empty dictionary on failure.
        """
        log.info("Fetching fresh teacher map from API (or using cache)...")
        try:
            # Generate fresh timer and prepare data payload
            timer = str(int(datetime.now().timestamp() * 1000))
            data = {
                "fname": "Henry", # This payload might need verification/update
                "lname": self.lname,
                "timer": timer,
            }
            log.debug(f"Fetching teacher map with data: {data}")
            resp = await self.api.post(
                "/i/teachers.asp",
                data=data
                # inject_params removed
            )
            # --- Add HTML saving (conditional) ---
            if self.save_debug_html:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = DEBUG_HTML_DIR / f"teachers_{timestamp}_{resp.status_code}.html"
                try:
                    async with aiofiles.open(filename, "w", encoding='utf-8') as f:
                        await f.write(f"<!-- URL: {resp.url} -->\n<!-- Status: {resp.status_code} -->\n{resp.text}")
                    log.info(f"Saved debug HTML for teacher map to {filename}")
                except Exception as save_err:
                    log.error(f"Failed to save debug HTML for teacher map: {save_err}")
            # --- End HTML saving ---
            resp.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            teacher_data = parse_teacher_html(resp.text)
            log.info(f"Successfully fetched and parsed teacher map ({len(teacher_data)} entries).")
            return teacher_data
        except httpx.HTTPStatusError as e:
            log.error(f"HTTP error fetching teacher map: {e}", exc_info=True)
            return {}
        except httpx.RequestError as e:
            log.error(f"Network error fetching teacher map: {e}", exc_info=True)
            return {}
        except Exception as e:
            log.error(f"Failed to fetch or parse teacher map: {e}", exc_info=True)
            # Return empty dict on failure, which will also be cached
            return {}

    async def fetch_week_html(
        self,
        offset: int, # Add offset parameter here
        student_id: Optional[str] = None, # Keep student_id
        # lname_value and timer_value removed from signature
        week_concurrency_manager: Optional[ConcurrencyManager] = None,
        force_max_concurrency: bool = False,
    ) -> str:
        """
        Fetches the raw HTML content for a specific timetable week.

        Args:
            offset: The week offset relative to the current week (0 = current).
            student_id: The student's identifier (GUID).
            # lname_value and timer_value removed from docstring
            week_concurrency_manager: Optional ConcurrencyManager for rate limiting.
            force_max_concurrency: If True, forces max concurrency.

        Returns:
            The HTML content as a string, or an empty string on failure.
        """
        log.debug(f"Fetching HTML for week offset: {offset}")
        try:
            # Generate fresh timer and construct payload
            timer = str(int(datetime.now().timestamp() * 1000))
            data = {
                "fname": "Henry", # Seems constant, verify if needed
                "q": "stude",     # Seems constant, verify if needed
                "v": str(offset), # Use the offset parameter
                "lname": self.lname, # Use stored lname
                "timex": timer,      # Use fresh timer (note: key is 'timex' here, not 'timer')
            }
            if student_id:
                data["id"] = student_id

            log.debug(f"Fetching week HTML with data: {data}")
            resp = await self.api.post(
                "/i/udvalg.asp", # Endpoint for fetching week data
                data=data,
                # inject_params removed
                concurrency_manager=week_concurrency_manager,
                force_max_concurrency=force_max_concurrency,
            )
            # Log response headers
            log.debug(f"Response headers for week {offset}: {resp.headers}")
            # --- Add HTML saving (conditional) ---
            if self.save_debug_html:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = DEBUG_HTML_DIR / f"week_{offset}_{timestamp}_{resp.status_code}.html"
                try:
                    async with aiofiles.open(filename, "w", encoding='utf-8') as f:
                        await f.write(f"<!-- URL: {resp.url} -->\n<!-- Status: {resp.status_code} -->\n{resp.text}")
                    log.info(f"Saved debug HTML for week {offset} to {filename}")
                except Exception as save_err:
                    log.error(f"Failed to save debug HTML for week {offset}: {save_err}")
            # --- End HTML saving ---
            # Check for redirect *after* potential saving, before returning text
            if resp.status_code >= 300 and resp.status_code < 400:
                 log.warning(f"Received redirect status {resp.status_code} for week {offset}. Content might be login page.")
                 # Optionally raise an error here or let the parser fail later
                 # For now, we'll return the (likely login page) text and let the parser fail downstream
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
        """
        Fetches homework details for a list of lesson IDs concurrently.

        Args:
            lesson_ids: A list of lesson ID strings.
            student_id: The student's identifier (GUID) - added, though maybe not used in payload.
            concurrency_manager: Optional ConcurrencyManager for rate limiting.
            force_max_concurrency: If True, forces max concurrency.

        Returns:
            A dictionary mapping lesson IDs (str) to their homework text (str).
            Lessons with errors or no homework are omitted.
        """
        results: Dict[str, str] = {}
        if not lesson_ids:
            log.debug("No lesson IDs provided for homework fetching.")
            return results

        log.debug(f"Fetching homework for {len(lesson_ids)} lessons.")

        async def fetch_one(lesson_id: str, force_flag: bool):
            """Fetches homework for a single lesson ID."""
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
                    "/i/note.asp", # Endpoint for fetching notes/homework
                    data=data,
                    # inject_params removed
                    concurrency_manager=concurrency_manager,
                    force_max_concurrency=force_flag,
                )
                # --- Add HTML saving (conditional) ---
                if self.save_debug_html:
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    filename = DEBUG_HTML_DIR / f"homework_{lesson_id}_{timestamp}_{resp.status_code}.html"
                    try:
                        async with aiofiles.open(filename, "w", encoding='utf-8') as f:
                            await f.write(f"<!-- URL: {resp.url} -->\n<!-- Status: {resp.status_code} -->\n{resp.text}")
                        log.info(f"Saved debug HTML for homework {lesson_id} to {filename}")
                    except Exception as save_err:
                        log.error(f"Failed to save debug HTML for homework {lesson_id}: {save_err}")
                # --- End HTML saving ---
                # Check for redirect *after* potential saving
                if resp.status_code >= 300 and resp.status_code < 400:
                    log.warning(f"Received redirect status {resp.status_code} for homework {lesson_id}. Content might be login page.")
                    # Skip parsing if redirected
                    return # Exit fetch_one for this lesson
                elif resp.status_code >= 400:
                    resp.raise_for_status() # Raise for client/server errors

                # Parse the HTML response to get homework text
                parsed_homework = parse_homework_html(resp.text)
                if lesson_id in parsed_homework:
                    results[lesson_id] = parsed_homework[lesson_id]
                    # log.debug(f"Successfully fetched homework for lesson {lesson_id}") # Removed: Too verbose
                # else:
                # log.debug(f"No homework found for lesson {lesson_id} after parsing.")

            except Exception as e:
                log.warning(f"Failed to fetch homework for lesson {lesson_id}: {e}")
                # Optionally log traceback: log.warning(..., exc_info=True)

        # Create and run tasks concurrently
        # Pass the force_max_concurrency flag to each fetch_one task
        tasks = [fetch_one(lid, force_max_concurrency) for lid in lesson_ids]
        await asyncio.gather(*tasks)

        log.info(f"Finished fetching homework. Found details for {len(results)}/{len(lesson_ids)} lessons.")
        return results