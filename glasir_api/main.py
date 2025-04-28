import sys
import httpx
from typing import Annotated, Optional, List, Tuple # Added Tuple
from contextlib import asynccontextmanager # Import asynccontextmanager

from fastapi import FastAPI, HTTPException, Header, Query, Path, Request # Added Request
from fastapi.responses import ORJSONResponse

# Model and Core Service imports
from .models.models import TimetableData
# Import necessary functions and types
from .core.service import _setup_extractor, _fetch_and_process_week, get_multiple_weeks
from .core.parsers import parse_available_offsets # Import the offset parser
from .core.extractor import TimetableExtractor
from .core.constants import GLASIR_TIMETABLE_URL # Import base URL for client setup
import logging # Import logging

# Configure basic logging
# Set level to INFO; use DEBUG in development for more verbosity
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- Lifespan Management ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create a single client instance when the app starts
    # Configure timeouts, limits, etc., as needed here
    # Use the base URL from constants
    client = httpx.AsyncClient(
        base_url=GLASIR_TIMETABLE_URL, # Use the constant base URL
        timeout=30.0, # Example timeout
        follow_redirects=True,
        limits=httpx.Limits(max_keepalive_connections=20, max_connections=100), # Example limits
        http2=True
    )
    logging.info("Lifespan startup: HTTPX client created.") # Use logging
    app.state.http_client = client # Store client in app state

    # --- Explicitly configure parser logger level ---
    # This ensures debug messages from the parser are processed,
    # regardless of the main Uvicorn log level setting (though both should ideally be debug).
    parser_logger = logging.getLogger("glasir_api.core.parsers")
    # Check current handlers to avoid duplicates if lifespan runs multiple times (e.g., with reload)
    if not any(isinstance(h, logging.StreamHandler) for h in parser_logger.handlers):
         # Find the root logger's stream handler to use the same output stream and formatter
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
    """
    Root endpoint for the Glasir API.
    Returns a simple message indicating the API is running.
    """
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
    """
    Retrieves timetable details for a student across ALL available weeks found in the Glasir navigation.

    Fetches the base week (offset 0) to determine available offsets, then fetches all weeks concurrently.
    """
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
    """
    Retrieves timetable details for the current week (offset 0) and all future weeks
    available in the Glasir navigation.

    Fetches the base week (offset 0), parses available offsets, filters for >= 0,
    and then fetches the relevant weeks concurrently.
    """
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
    """
    Retrieves timetable details for the current week (offset 0) up to N future weeks.

    Generates a list of offsets [0, 1, ..., count] and fetches them concurrently.
    """
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
    """
    Retrieves the timetable details for a specific student and week offset using a shared HTTP client.

    Requires valid Glasir authentication cookies and the student's ID.
    """
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
        # Pass the extractor which now uses the shared client internally
        processed_data = await _fetch_and_process_week(offset, extractor, student_id, teacher_map)

        if processed_data is None:
            raise HTTPException(status_code=404, detail=f"Timetable data not found or failed to process for offset {offset}. The offset might be invalid or data unavailable.")

        processed_data['student_info'] = {'student_id': student_id, 'username': username}
        return TimetableData(**processed_data)

    except httpx.HTTPStatusError as e:
         status = e.response.status_code
         # Use e.request.url which is available on the exception
         url = e.request.url
         detail = f"Glasir backend returned an error ({status}) when accessing URL: {url}. Check if Glasir is down or if the request parameters (offset, student_id) are valid."
         raise HTTPException(status_code=502, detail=detail)
    except httpx.RequestError as e:
         # Use e.request.url which is available on the exception
         url = e.request.url
         detail = f"Network error occurred while trying to communicate with Glasir URL: {url}. Check network connectivity and Glasir server status."
         raise HTTPException(status_code=504, detail=detail)
    except Exception as e:
         # Log the full traceback using logging.error with exc_info=True
         logging.error(f"Unexpected internal error in /weeks/{offset} for user {username}", exc_info=True)
         raise HTTPException(status_code=500, detail=f"An unexpected internal server error occurred ({type(e).__name__}).") # Refined detail
    # finally: # No longer need to close client here, lifespan handles it.
        # Optional: Cleanup specific to the extractor if needed, but not the client.
        # if extractor:
        #     # Perform any extractor-specific cleanup if necessary
        #     pass