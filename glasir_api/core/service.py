import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import databases
import httpx
from fastapi import HTTPException
from pydantic import ValidationError

# Core module imports (using relative paths)
from .cache_service import (get_teacher_map_from_db,
                            update_teacher_cache_in_db)
from .client import AsyncApiClient,  fetch_glasir_week_html
from .client import AsyncApiClient, fetch_glasir_week_html, GlasirClientError # Added GlasirClientError
from .constants import GLASIR_BASE_URL, GLASIR_TIMETABLE_URL
from .extractor import TimetableExtractor
from .parsers import ( merge_homework_into_events,
                      parse_week_html, GlasirParserError) # Added GlasirParserError
from .session import extract_session_params_from_html

# Model import
from ..models.models import Event, StudentInfo, TimetableData, WeekInfo # Import necessary models

# Setup module logger
log = logging.getLogger(__name__)

# --- Removed Global In-Memory Cache ---

@dataclass
class WeekDataResult:
    """Represents the final result of fetching and parsing data for a single week."""
    status: str # e.g., 'SuccessWithData', 'SuccessNoData', 'FetchFailed', 'ParseFailed'
    data: Optional[TimetableData] = None # The final validated timetable data
    fetch_error_type: Optional[str] = None
    parse_error_type: Optional[str] = None # Corresponds to ParseResult.status when failed
    error_message: Optional[str] = None
    http_status_code: Optional[int] = None
    warnings: List[str] = field(default_factory=list) # Collect warnings from parsing


async def fetch_and_parse_single_week(
    offset: int,
    extractor: TimetableExtractor,
    student_id: str,
    teacher_map: Optional[Dict[str, str]] = None
) -> WeekDataResult: # Return the structured result object
    """
    Fetches and parses timetable data for a single week offset using the provided extractor.

    Args:
        offset: The week offset to fetch.
        extractor: An initialized TimetableExtractor instance.
        student_id: The student's ID.
        teacher_map: Optional dictionary mapping teacher initials to full names for parsing.

    Returns:
        A WeekDataResult object containing the status, data, and any errors/warnings.
    """
    html_content: Optional[str] = None
    parse_result: Optional[Any] = None # Placeholder for ParseResult type if defined
    timetable_data: Optional[TimetableData] = None
    warnings: List[str] = []

    try:
        # 1. Fetch HTML using the extractor
        log.debug(f"Service: Fetching HTML for offset {offset} using extractor...")
        html_content = await extractor.fetch_week_html(offset=offset, student_id=student_id)
        if html_content is None:
            # fetch_week_html should ideally raise on failure, but handle None defensively
            log.error(f"Service: fetch_week_html returned None for offset {offset}.")
            # Determine appropriate error based on extractor's internal state if possible
            return WeekDataResult(status='FetchFailed', error_message="Extractor failed to fetch HTML (returned None).")

        log.debug(f"Service: Successfully fetched HTML for offset {offset}.")

        # 2. Parse HTML
        log.debug(f"Service: Parsing HTML for offset {offset}...")
        # parse_week_html now returns a ParseResult object
        parse_result = parse_week_html(html_content, teacher_map)
        warnings.extend(parse_result.warnings) # Collect warnings

        if parse_result.status == 'Success':
            log.debug(f"Service: Successfully parsed HTML for offset {offset}.")
            parsed_dict = parse_result.data or {} # Use empty dict if data is None

            # 3. Validate and structure data using Pydantic model
            try:
                # Extract student info from the parsed data, providing defaults if missing
                # Ensure student_info exists in the parsed_dict before accessing it
                student_info_parsed = parsed_dict.get('student_info', {})
                student_name = student_info_parsed.get('studentName', None)
                student_class = student_info_parsed.get('class', None)

                # Create StudentInfo object - validation happens here
                student_info_obj = StudentInfo(
                    studentName=student_name, # Use Pydantic field name
                    class_=student_class      # Use Pydantic field name
                )

                # Extract week info from the parsed data
                week_info_parsed = parsed_dict.get('week_info', {})
                week_number = week_info_parsed.get('weekNumber')
                start_date = week_info_parsed.get('startDate')
                end_date = week_info_parsed.get('endDate')
                year = week_info_parsed.get('year')

                # Create WeekInfo object - validation happens here
                week_info_obj = WeekInfo(
                    weekNumber=week_number, # Use Pydantic field name
                    startDate=start_date,   # Use Pydantic field name
                    endDate=end_date,     # Use Pydantic field name
                    year=year,
                    offset=offset # Pass the original offset
                    # weekKey is generated by model_validator
                )

                # Extract events list - it should already contain Event objects from the parser
                events_parsed = parsed_dict.get('events', [])
                # No need to re-validate here if parser already creates Event objects
                events_obj_list: List[Event] = events_parsed # Directly use the list from the parser

                # --- Fetch and Merge Homework ---
                homework_lesson_ids = [
                    event.lesson_id
                    for event in events_obj_list
                    if event.lesson_id and event.has_homework_note
                ]
                if homework_lesson_ids:
                    log.debug(f"Service: Fetching homework for {len(homework_lesson_ids)} lessons in offset {offset}...")
                    try:
                        # Use the same extractor instance passed into the function
                        homework_map = await extractor.fetch_homework_for_lessons(
                            lesson_ids=homework_lesson_ids,
                            student_id=student_id # Pass student_id if needed by extractor logic
                        )
                        if homework_map:
                             log.debug(f"Service: Merging homework for offset {offset}...")
                             # merge_homework_into_events modifies the events_obj_list in place
                             merge_homework_into_events(events_obj_list, homework_map)
                             log.debug(f"Service: Homework merge complete for offset {offset}.")
                        else:
                             log.debug(f"Service: No homework details returned for offset {offset}.")
                    except Exception as hw_exc:
                         log.error(f"Service: Failed to fetch or merge homework for offset {offset}: {hw_exc}", exc_info=True)
                         # Optionally add a warning, but don't fail the whole week parse
                         warnings.append(f"Homework fetching/merging failed: {hw_exc}")
                else:
                     log.debug(f"Service: No lessons with homework notes found for offset {offset}.")
                # --- End Fetch and Merge Homework ---


                # Assemble the final TimetableData (using the potentially modified events_obj_list)
                timetable_data = TimetableData(
                    studentInfo=student_info_obj, # Use Pydantic field name
                    weekInfo=week_info_obj,       # Use Pydantic field name
                    events=events_obj_list        # This list now includes descriptions
                    # formatVersion defaults to 2
                )

                log.debug(f"Service: Successfully validated TimetableData (with homework) for offset {offset}.")
                status = 'SuccessWithData' if timetable_data.events else 'SuccessNoData'
                return WeekDataResult(status=status, data=timetable_data, warnings=warnings)

            except ValidationError as e:
                # Log the specific validation error and the problematic data structure
                log.error(f"Service: Pydantic validation failed for offset {offset}: {e}", exc_info=True)
                log.debug(f"Service: Data causing validation error for offset {offset}: {parsed_dict}") # Log the raw data
                return WeekDataResult(status='ParseFailed', parse_error_type='ValidationError', error_message=str(e), warnings=warnings)
            except Exception as e: # Catch other potential errors during structuring
                 log.error(f"Service: Unexpected error structuring TimetableData for offset {offset}: {e}", exc_info=True)
                 return WeekDataResult(status='ParseFailed', parse_error_type='StructureError', error_message=f"Unexpected error: {e}", warnings=warnings)

        else: # Parse failed (status was not 'Success')
            log.error(f"Service: parse_week_html failed for offset {offset}. Status: {parse_result.status}, Error: {parse_result.error_message}")
            return WeekDataResult(status='ParseFailed', parse_error_type=parse_result.status, error_message=parse_result.error_message, warnings=warnings)

    except GlasirClientError as e:
        log.error(f"Service: Client error fetching offset {offset}: {e}", exc_info=True)
        return WeekDataResult(status='FetchFailed', fetch_error_type=type(e).__name__, http_status_code=e.status_code, error_message=str(e), warnings=warnings)

    except GlasirParserError as e: # Should be caught by ParseResult handling above, but keep defensively
        log.error(f"Service: Parser error processing offset {offset}: {e}", exc_info=True)
        return WeekDataResult(status='ParseFailed', parse_error_type=type(e).__name__, error_message=str(e), warnings=warnings)

    except Exception as e:
        # Catch-all for unexpected errors during service logic
        log.exception(f"Service: Unexpected error processing offset {offset}: {e}")
        return WeekDataResult(status='FetchFailed', fetch_error_type='UnexpectedServiceError', error_message=str(e), warnings=warnings)


async def _setup_extractor(cookies_list: List[Dict[str, Any]], shared_client: httpx.AsyncClient, db: databases.Database) -> Tuple[TimetableExtractor, dict, str]: # Added db param
    """
    Sets up the TimetableExtractor using provided cookies, a shared HTTP client, and a database connection.
    Fetches initial session parameters (lname) and the teacher map (using DB cache) via the shared client.

    Args:
        cookies_list: A list of cookie dictionaries, typically [{'name': ..., 'value': ...}].
        shared_client: The pre-configured httpx.AsyncClient managed by the application lifespan.
        db: The database connection instance. # Added missing db param description

    Returns:
        A tuple containing the initialized TimetableExtractor, the teacher map, and the extracted lname.
        Raises HTTPException if setup fails at any step (e.g., invalid cookies, auth failure, network error, parsing error).
        The shared_client's lifecycle is managed externally (e.g., by FastAPI lifespan).
    """
    # api_client: Optional[AsyncApiClient] = None # No longer needed here
    try:
        # 1. Parse cookies from the list of dictionaries
        parsed_cookies = {}
        if cookies_list:
            for cookie_dict in cookies_list:
                name = cookie_dict.get('name')
                value = cookie_dict.get('value')
                # Ensure both name and value are present and are strings (or convert if needed)
                if name and value is not None:
                    # httpx expects cookies as Dict[str, str]
                    parsed_cookies[str(name)] = str(value)
        if not parsed_cookies:
            log.error("Invalid or empty cookie list provided, or failed to parse cookies during setup.")
            raise HTTPException(status_code=400, detail="Invalid, empty, or unparseable authentication cookies provided.")

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

        # 5. Fetch teacher map (using DB cache)
        log.info("Attempting to retrieve teacher map from DB cache...")
        teacher_map = await get_teacher_map_from_db(db)

        if teacher_map is None:
            log.info("Teacher map not found in DB cache or expired. Fetching from Glasir...")
            try:
                fetched_map = await extractor.fetch_teacher_map()
                if fetched_map is None: # Check explicitly for None
                    log.error("Failed to fetch teacher map during setup (returned None).")
                    raise HTTPException(status_code=502, detail="Failed to fetch teacher map from Glasir.")
                else:
                    log.info(f"Successfully fetched teacher map from Glasir. Map size: {len(fetched_map)}. Updating DB cache...")
                    # Update cache in the background? For now, await it.
                    await update_teacher_cache_in_db(db, fetched_map)
                    log.info("DB cache updated successfully.")
                    teacher_map = fetched_map # Use the newly fetched map
            except Exception as fetch_exc:
                # Catch potential errors during the fetch or cache update
                log.error(f"Error fetching teacher map or updating cache: {fetch_exc}", exc_info=True)
                raise HTTPException(status_code=502, detail=f"Failed to fetch teacher map from Glasir or update cache: {fetch_exc}")
        else:
            log.info("Teacher map successfully retrieved from DB cache.")

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

async def get_multiple_weeks( # Added db param
    username: str,
    student_id: str,
    cookies_list: List[Dict[str, Any]], # Changed from cookies_str
    requested_offsets: List[int],
    shared_client: httpx.AsyncClient,
    db: databases.Database
) -> List[TimetableData]:
    """
    Fetches and processes timetable data for multiple specified week offsets concurrently, using DB cache.

    Args:
        username: The username associated with the request (for logging/context).
        student_id: The student's ID required for fetching data.
        cookies_list: A list of cookie dictionaries for authentication.
        requested_offsets: A list of integer week offsets to fetch.
        shared_client: The shared httpx.AsyncClient managed by the application lifespan.
        db: The database connection instance.

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
        extractor, teacher_map, lname = await _setup_extractor(cookies_list, shared_client, db) # Pass db and cookies_list
        log.info(f"Extractor setup successful for user {username}, lname: {lname}")

        # 2. Create concurrent tasks for fetching each week
        tasks = []
        if not requested_offsets:
            log.warning(f"No offsets requested for user {username}, student {student_id}.")
            return [] # Return empty list if no offsets are requested

        log.info(f"Creating {len(requested_offsets)} tasks for offsets: {requested_offsets}")
        for offset in requested_offsets:
            # Pass necessary arguments to the new worker function
            task = asyncio.create_task(
                fetch_and_parse_single_week(offset, extractor, student_id, teacher_map)
            )
            tasks.append(task)

        # 3. Run tasks concurrently and gather results
        # return_exceptions=True allows us to handle errors gracefully per task
        results = await asyncio.gather(*tasks, return_exceptions=True)
        log.info(f"Finished gathering results for {len(results)} tasks.")

        # 4. Process results, validate data, and collect errors/warnings
        failed_offsets = defaultdict(list) # Key: (error_type, error_message), Value: list of offsets
        warning_summary = defaultdict(list) # Key: warning_message, Value: list of offsets
        task_exceptions = defaultdict(list) # Key: exception_type_str, Value: list of offsets

        for i, result in enumerate(results):
            offset = requested_offsets[i] # Get corresponding offset

            if isinstance(result, Exception):
                exc_type_str = type(result).__name__
                task_exceptions[exc_type_str].append(offset)
                # Log the first occurrence verbosely for debugging context if needed
                if len(task_exceptions[exc_type_str]) == 1:
                     log.error(f"Task for offset {offset} failed with {exc_type_str}: {result}", exc_info=result)
                else:
                     log.debug(f"Task for offset {offset} failed with {exc_type_str} (repeated).")

            elif isinstance(result, WeekDataResult):
                # Collect warnings regardless of status
                for warning in result.warnings:
                    warning_summary[warning].append(offset)

                # Process based on status
                if result.status == 'SuccessWithData' or result.status == 'SuccessNoData':
                    if result.data:
                        processed_weeks.append(result.data)
                    # No error logging needed for success cases here
                elif result.status == 'FetchFailed':
                    error_key = (result.fetch_error_type or "UnknownFetchError", result.error_message or "N/A")
                    failed_offsets[error_key].append(offset)
                elif result.status == 'ParseFailed':
                    error_key = (result.parse_error_type or "UnknownParseError", result.error_message or "N/A")
                    failed_offsets[error_key].append(offset)
                else:
                    # Unknown status from WeekDataResult
                    error_key = ("UnknownStatus", f"Status: {result.status}, Msg: {result.error_message or 'N/A'}")
                    failed_offsets[error_key].append(offset)
            else:
                # Should not happen
                error_key = ("UnexpectedResultType", f"Type: {type(result)}")
                failed_offsets[error_key].append(offset)

        # 5. Log Summary
        total_requested = len(requested_offsets)
        total_successful = len(processed_weeks)
        total_failed = total_requested - total_successful
        log.info(f"Multi-week processing summary: Requested={total_requested}, Successful={total_successful}, Failed={total_failed}")

        if task_exceptions:
            log.warning("Summary of task exceptions during gather:")
            for exc_type, offsets in task_exceptions.items():
                log.warning(f"  - Exception Type '{exc_type}' occurred for offsets: {sorted(list(set(offsets)))}")

        if failed_offsets:
            log.warning("Summary of failed week offsets:")
            for (error_type, error_msg), offsets in failed_offsets.items():
                 # Truncate long error messages for summary
                 truncated_msg = (error_msg[:150] + '...') if error_msg and len(error_msg) > 150 else error_msg
                 log.warning(f"  - Type='{error_type}', Msg='{truncated_msg}': Offsets {sorted(list(set(offsets)))}")

        if warning_summary:
            log.warning("Summary of warnings encountered:")
            for warning, offsets in warning_summary.items():
                 truncated_warning = (warning[:150] + '...') if len(warning) > 150 else warning
                 log.warning(f"  - Warning='{truncated_warning}': Offsets {sorted(list(set(offsets)))}")

        # 6. Sort successful results by week number
        processed_weeks.sort(key=lambda x: x.week_info.week_number if x.week_info and x.week_info.week_number is not None else float('inf'))

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