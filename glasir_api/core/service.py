import httpx
import asyncio
import logging
from typing import Dict, Tuple, Optional, List # Added List
from datetime import datetime
from fastapi import HTTPException # Added HTTPException
from pydantic import ValidationError # Added ValidationError

# Core module imports (using relative paths)
from .client import AsyncApiClient
from .constants import GLASIR_TIMETABLE_URL, GLASIR_BASE_URL # Import GLASIR_BASE_URL
# Removed incorrect import: from .date_utils import generate_timestamp_timer
from .extractor import TimetableExtractor
from .parsers import parse_timetable_html, merge_homework_into_events # Assuming these exist from Phase 0
from .session import extract_session_params_from_html # Assuming this exists from Phase 0

# Model import
from ..models.models import TimetableData # Corrected to relative import

# Setup module logger
log = logging.getLogger(__name__)

async def _fetch_and_process_week(offset: int, extractor: TimetableExtractor, student_id: str, teacher_map: dict) -> Optional[Dict]:
    """
    Fetches timetable HTML for a specific week, parses it, fetches related homework,
    and merges the homework data into the timetable events.

    Args:
        offset: The week offset to fetch.
        extractor: An initialized TimetableExtractor instance.
        student_id: The student's ID.
        teacher_map: A dictionary mapping teacher initials to full names.

    Returns:
        A dictionary containing the processed timetable data for the week,
        or None if fetching or parsing fails.
    """
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
            if homework_map: # Only merge if homework was successfully fetched
                merge_homework_into_events(timetable_data['events'], homework_map)
            else:
                log.warning(f"Failed to fetch homework details for week offset {offset}, student {student_id}. Proceeding without homework.")

        return timetable_data

    except httpx.RequestError as e:
        log.error(f"Network error fetching week {offset} for student {student_id}: {e.request.url}", exc_info=True)
        return None # Keep returning None for concurrent handling
    except httpx.HTTPStatusError as e:
        log.error(f"HTTP error {e.response.status_code} fetching week {offset} for student {student_id}: {e.request.url}", exc_info=True)
        return None # Keep returning None
    except Exception as e:
        log.error(f"Unexpected error processing week {offset} for student {student_id}", exc_info=True)
        return None # Keep returning None


async def _setup_extractor(cookies_str: str, shared_client: httpx.AsyncClient) -> Tuple[TimetableExtractor, dict, str]: # Return type changed
    """
    Sets up the TimetableExtractor using provided cookies and a shared HTTP client.
    Fetches initial session parameters (lname) and the teacher map using the shared client.

    Args:
        cookies_str: The raw cookie string from the request header.
        shared_client: The pre-configured httpx.AsyncClient managed by the application lifespan.

    Returns:
        A tuple containing the initialized TimetableExtractor, the teacher map, and the extracted lname.
        Raises HTTPException if setup fails at any step (e.g., invalid cookies, auth failure, network error, parsing error).
        The shared_client's lifecycle is managed externally (e.g., by FastAPI lifespan).
    """
    # api_client: Optional[AsyncApiClient] = None # No longer needed here
    try:
        # 1. Parse cookies
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

        # 2. Fetch initial HTML for session params using the shared client
        # Pass cookies specifically for this request, don't modify shared client's default cookies
        # Explicitly disable redirects to catch initial auth failures
        response = await shared_client.get(GLASIR_TIMETABLE_URL, cookies=parsed_cookies, follow_redirects=False)

        # Check if the initial request was successful (200 OK) or a redirect (auth failure)
        if response.status_code != 200:
            log.error(f"Initial GET to {GLASIR_TIMETABLE_URL} failed authentication. Status: {response.status_code}. Check cookies/session.")
            # Log headers if needed: log.debug(f"Response headers: {response.headers}")
            raise HTTPException(status_code=401, detail="Authentication failed with Glasir. Check credentials/cookie.")

        # Only proceed if status is 200 OK
        # response.raise_for_status() # Let the HTTPStatusError handler below catch other errors
        initial_html = response.text

        # 3. Extract lname
        lname = extract_session_params_from_html(initial_html)
        if not lname:
            log.error("Could not extract 'lname' session parameter from Glasir page during setup.")
            raise HTTPException(status_code=502, detail="Failed to extract session parameters from Glasir response.")

        # 4. Initialize API Client and Extractor using the shared client
        # Pass only cookies and the external client. Session params (lname, timer) handled by extractor.
        # Timer is removed here, will be generated per-request in extractor.
        api_client = AsyncApiClient(
            base_url=GLASIR_BASE_URL,      # Use the correct base URL (without /132n/)
            cookies=parsed_cookies,       # Pass parsed cookies for this specific client wrapper
            # session_params removed from client initialization
            external_client=shared_client # Pass the shared client
        )
        # Pass lname to the extractor constructor
        extractor = TimetableExtractor(api_client, lname=lname) # Pass lname here

        # 5. Fetch teacher map
        teacher_map = await extractor.fetch_teacher_map() # fetch_teacher_map will now handle its own timer/lname
        if teacher_map is None: # Check explicitly for None, as empty dict might be valid
             log.error("Failed to fetch teacher map during setup.")
             raise HTTPException(status_code=502, detail="Failed to fetch teacher map from Glasir.")

        # 6. Return extractor, teacher map, and lname
        return extractor, teacher_map, lname # Return lname as well

    except httpx.RequestError as e:
        log.error(f"Network error during initial setup: {e.request.url}", exc_info=True)
        raise HTTPException(status_code=504, detail=f"Network error during Glasir setup: {e.request.url}")
    except httpx.HTTPStatusError as e:
        log.error(f"HTTP error during initial setup: {e.response.status_code} for URL {e.request.url}", exc_info=True)
        raise HTTPException(status_code=502, detail=f"Glasir backend error ({e.response.status_code}) during setup: {e.request.url}")
    except Exception as e:
        log.error(f"Unexpected error during setup", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Unexpected internal error during setup: {type(e).__name__}")


# --- Multi-Week Service ---

async def get_multiple_weeks(
    username: str, # Keep username for potential future use/logging
    student_id: str,
    cookies_str: str,
    requested_offsets: List[int],
    shared_client: httpx.AsyncClient # Accept the shared client
) -> List[TimetableData]:
    """
    Fetches and processes timetable data for multiple specified week offsets concurrently.

    Args:
        username: The username associated with the request (for logging/context).
        student_id: The student's ID required for fetching data.
        cookies_str: The raw cookie string for authentication.
        requested_offsets: A list of integer week offsets to fetch.
        shared_client: The shared httpx.AsyncClient managed by the application lifespan.

    Returns:
        A list of validated TimetableData objects, sorted by week number.

    Raises:
        HTTPException: If the initial setup (authentication, session param extraction) fails.
    """
    extractor: Optional[TimetableExtractor] = None
    teacher_map: Optional[Dict] = None
    lname: Optional[str] = None
    processed_weeks: List[TimetableData] = []

    try:
        # 1. Setup Extractor using the shared client
        # _setup_extractor now raises exceptions on failure, caught by outer try/except
        extractor, teacher_map, lname = await _setup_extractor(cookies_str, shared_client)
        log.info(f"Extractor setup successful for user {username}, lname: {lname}")

        # 2. Create concurrent tasks for fetching each week
        tasks = []
        if not requested_offsets:
            log.warning(f"No offsets requested for user {username}, student {student_id}.")
            return [] # Return empty list if no offsets are requested

        log.info(f"Creating {len(requested_offsets)} tasks for offsets: {requested_offsets}")
        for offset in requested_offsets:
            # Pass necessary arguments to the worker function
            task = asyncio.create_task(
                _fetch_and_process_week(offset, extractor, student_id, teacher_map)
            )
            tasks.append(task)

        # 3. Run tasks concurrently and gather results
        # return_exceptions=True allows us to handle errors gracefully per task
        results = await asyncio.gather(*tasks, return_exceptions=True)
        log.info(f"Finished gathering results for {len(results)} tasks.")

        # 4. Process results and validate data
        for i, result in enumerate(results):
            offset = requested_offsets[i] # Get corresponding offset for logging
            if isinstance(result, Exception):
                # Log exceptions returned by asyncio.gather
                log.error(f"Task for offset {offset} failed with exception: {result}", exc_info=result)
                # Optionally: Collect errors to return details? For now, just log.
            elif result is None:
                # Log cases where _fetch_and_process_week returned None (internal error)
                log.warning(f"Task for offset {offset} returned None (fetch/parse error).")
            else:
                # Attempt to validate the dictionary result with Pydantic model
                try:
                    validated_data = TimetableData.model_validate(result)
                    processed_weeks.append(validated_data)
                    log.debug(f"Successfully validated and added data for offset {offset}.")
                except ValidationError as e:
                    log.error(f"Validation failed for offset {offset}: {e}")
                    # Log the problematic data structure for debugging
                    log.debug(f"Invalid data structure for offset {offset}: {result}")
                except Exception as e_val:
                    # Catch any other unexpected errors during validation/append
                    log.error(f"Unexpected error processing result for offset {offset}: {e_val}", exc_info=True)

        # 5. Sort results by week number
        # Use a lambda function with a default value for sorting robustness
        processed_weeks.sort(key=lambda x: x.week_info.week_number if x.week_info and x.week_info.week_number is not None else float('inf')) # Corrected: week_info
        log.info(f"Successfully processed and validated {len(processed_weeks)} weeks out of {len(requested_offsets)} requested.")

        return processed_weeks

    except HTTPException:
        # Re-raise HTTPExceptions originating from _setup_extractor
        raise
    except Exception as e:
        # Catch any unexpected errors during the overall process
        log.error(f"Unexpected error in get_multiple_weeks for user {username}: {e}", exc_info=True)
        # Return an empty list or raise a generic server error?
        # Raising a 500 seems appropriate for unexpected failures.
        raise HTTPException(status_code=500, detail=f"An unexpected server error occurred while fetching multiple weeks: {e}")

    # Note: No 'finally' block needed here to close the client,
    # as the shared_client's lifecycle is managed by the FastAPI application lifespan.