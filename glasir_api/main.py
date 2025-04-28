import sys
import httpx
import os # Add os import
from collections import defaultdict
from typing import Annotated, Optional, List, Tuple, Dict, Any # Added Dict, Any
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import logging
import secrets # Import secrets for access code generation
from datetime import datetime, timezone, timedelta # Import datetime, timezone, timedelta
import json # Import json for serialization

# Database imports
import databases
import sqlalchemy
# Removed create_engine import as Alembic handles schema

from fastapi import FastAPI, HTTPException, Header, Query, Path, Request, status, Depends # Added Request, status, Depends
from fastapi.responses import ORJSONResponse

# Rate Limiting imports
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter
import redis.asyncio as redis

# Model and Core Service imports
from .models.models import TimetableData
from .models.db_models import Base # Import Base from db_models
# Import DB model classes
from .models.db_models import UserSession, WeeklyTimetableState # Import classes
# Import API models
from .models.api_models import InitialSyncRequest, InitialSyncResponse, SyncRequest, SyncResponse, WeekDiff, SessionRefreshRequest
# Import necessary functions and types
from .core.service import _setup_extractor, fetch_and_parse_single_week, get_multiple_weeks # Corrected function name
from .core.parsers import parse_available_offsets # Import the offset parser
from .core.extractor import TimetableExtractor
from .core.constants import GLASIR_TIMETABLE_URL # Import base URL for client setup
from .core.diff_service import calculate_week_diff


# Load environment variables from .env file located in the same directory as this script
# or any parent directory.
load_dotenv()

# --- Database Configuration ---
DATABASE_URL = os.getenv("DATABASE_URL") # Get DB URL from env
if not DATABASE_URL:
    logging.warning("DATABASE_URL environment variable not set. Using default SQLite DB: ./glasir_data.db")
    DATABASE_URL = "sqlite+aiosqlite:///./glasir_data.db" # Default fallback

database = databases.Database(DATABASE_URL)
# Use connect_args for SQLite specific settings like check_same_thread
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
# engine = create_engine(DATABASE_URL, connect_args=connect_args) # Removed: Alembic handles engine creation for migrations
metadata = Base.metadata # Use metadata from the Base defined in db_models

# Configure basic logging
# Set level to DEBUG temporarily for detailed tracing
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__) # Get logger for this module

# --- Lifespan Management ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Lifespan: Application startup sequence initiated.")
    # --- Redis Connection for Rate Limiter (Optional) ---
    rate_limiting_enabled = os.getenv("RATE_LIMITING_ENABLED", "false").lower() == "true"
    app.state.rate_limiting_enabled = rate_limiting_enabled # Store status in app state
    app.state.redis_client = None # Initialize redis client state

    if rate_limiting_enabled:
        log.info("Lifespan startup: Rate limiting is ENABLED. Attempting Redis connection...")
        try:
            # TODO: Make Redis connection details configurable via environment variables
            redis_host = os.getenv("REDIS_HOST", "localhost")
            redis_port = int(os.getenv("REDIS_PORT", 6379))
            redis_db = int(os.getenv("REDIS_DB", 0))
            log.info(f"Lifespan startup: Connecting to Redis at {redis_host}:{redis_port}, DB {redis_db}")
            red = redis.Redis(host=redis_host, port=redis_port, db=redis_db, decode_responses=True)
            await red.ping() # Verify connection
            await FastAPILimiter.init(red)
            app.state.redis_client = red # Store client in state ONLY if successful
            log.info("Lifespan startup: Redis connection successful and FastAPILimiter initialized.")
        except Exception as e:
            log.error(f"Lifespan startup: Redis connection or FastAPILimiter initialization failed: {e}", exc_info=True)
            # Log the error but allow startup to continue. Rate limiting endpoints will fail if called.
            log.warning("Rate limiting endpoints may not function correctly due to Redis connection failure.")
            # Ensure redis_client remains None if connection failed
            app.state.redis_client = None
    else:
        log.info("Lifespan startup: Rate limiting is DISABLED (RATE_LIMITING_ENABLED is not 'true'). Skipping Redis connection.")
        # No need to initialize FastAPILimiter if disabled

    # --- Database Connection ---
    try:
        await database.connect()
        log.info(f"Lifespan startup: Database connection established ({DATABASE_URL})")
        # Create tables if they don't exist (Simple setup, use Alembic for production)
        # Ensure all models inheriting from Base are imported somewhere before this runs
        # metadata.create_all(bind=engine) # Removed: Alembic handles table creation/migration
        log.info("Lifespan startup: Database schema managed by Alembic.")
        app.state.database = database # Store database connection in app state
    except Exception as e:
        log.error(f"Lifespan startup: Database connection failed: {e}", exc_info=True)
        # Exit if DB connection fails? Or allow startup and fail on DB access?
        # For now, log and continue, but endpoints needing DB will fail.
        app.state.database = None # Indicate DB is not available

    # --- HTTP Client Setup ---
    try:
        client = httpx.AsyncClient(
            base_url=GLASIR_TIMETABLE_URL,
            timeout=30.0,
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
            http2=True
        )
        log.info("Lifespan startup: HTTPX client created.")
        app.state.http_client = client
    except Exception as e:
        log.error(f"Lifespan startup: HTTPX client creation failed: {e}", exc_info=True)
        app.state.http_client = None # Indicate client is not available

    # --- Parser Logger Configuration ---
    try:
        parser_logger = logging.getLogger("glasir_api.core.parsers")
        if not any(isinstance(h, logging.StreamHandler) for h in parser_logger.handlers):
            root_logger = logging.getLogger()
            stream_handler = next((h for h in root_logger.handlers if isinstance(h, logging.StreamHandler)), None)
            if stream_handler:
                parser_logger.addHandler(stream_handler)
                parser_logger.setLevel(logging.INFO) # <-- Changed parser logger to INFO
                parser_logger.propagate = False
                log.info("Lifespan startup: Configured 'glasir_api.core.parsers' logger to DEBUG level.")
            else:
                log.warning("Lifespan startup: Could not find root stream handler to configure parser logger.")
        else:
            parser_logger.setLevel(logging.INFO) # <-- Also changed parser logger to INFO
            log.info("Lifespan startup: 'glasir_api.core.parsers' logger handler already exists, ensured level is DEBUG.")
    except Exception as e:
        log.error(f"Lifespan startup: Failed to configure parser logger: {e}", exc_info=True)

    log.info("Lifespan: Application startup sequence complete. Yielding control.")
    yield # Application runs here
    log.info("Lifespan: Application shutdown sequence initiated.")

    # --- Shutdown Logic ---
    # Close the HTTP client
    if hasattr(app.state, 'http_client') and app.state.http_client:
        try:
            if not app.state.http_client.is_closed:
                await app.state.http_client.aclose()
                log.info("Lifespan shutdown: HTTPX client closed.")
            else:
                log.info("Lifespan shutdown: HTTPX client was already closed.")
        except Exception as e:
            log.error(f"Lifespan shutdown: Error closing HTTPX client: {e}", exc_info=True)
    else:
        log.info("Lifespan shutdown: HTTPX client was not initialized or already cleaned up.")

    # Disconnect from the database
    if hasattr(app.state, 'database') and app.state.database:
        try:
            if app.state.database.is_connected:
                await app.state.database.disconnect()
                log.info("Lifespan shutdown: Database connection closed.")
            else:
                log.info("Lifespan shutdown: Database was already disconnected.")
        except Exception as e:
            log.error(f"Lifespan shutdown: Error disconnecting from database: {e}", exc_info=True)
    else:
        log.info("Lifespan shutdown: Database was not initialized or already cleaned up.")

    # Close Redis connection if it was successfully initialized and stored in state
    if hasattr(app.state, 'redis_client') and app.state.redis_client:
        try:
            await app.state.redis_client.close()
            log.info("Lifespan shutdown: Redis client closed.")
        except Exception as e:
            log.error(f"Lifespan shutdown: Error closing Redis client: {e}", exc_info=True)
    else:
        log.info("Lifespan shutdown: Redis client was not initialized or already cleaned up.")

    log.info("Lifespan: Application shutdown sequence complete.")


# --- Custom Dependency for Conditional Rate Limiting ---
def ConditionalRateLimiter(times: int, seconds: int):
    """
    Factory for a FastAPI dependency that applies rate limiting only if
    it's enabled in the application configuration (app.state.rate_limiting_enabled).
    """
    async def dependency(request: Request):
        # Default to False if the state attribute isn't set for some reason
        limiter_enabled = getattr(request.app.state, 'rate_limiting_enabled', False)
        redis_available = getattr(request.app.state, 'redis_client', None) is not None

        if limiter_enabled:
            if redis_available:
                try:
                    # Invoke the actual RateLimiter dependency from fastapi-limiter
                    await RateLimiter(times=times, seconds=seconds)(request)
                    log.debug(f"Rate limit checked for {request.url.path}")
                except Exception as e:
                    # Log if the RateLimiter dependency fails unexpectedly
                    log.error(f"RateLimiter dependency failed unexpectedly: {e}", exc_info=True)
                    # Raise an error to prevent proceeding with a broken limiter state
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Rate limiting configuration error."
                    )
            else:
                # Rate limiting is enabled in config, but Redis connection failed during startup.
                # Block the request as rate limiting cannot be enforced.
                log.warning(f"Blocking request to {request.url.path} because rate limiting is enabled but Redis is unavailable.")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Rate limiting service temporarily unavailable."
                )
        else:
            # Rate limiting is disabled globally, skip the check.
            log.debug(f"Rate limiting skipped (globally disabled) for {request.url.path}")
            pass # Do nothing

    return dependency


# Create the FastAPI app instance with lifespan
app = FastAPI(
    title="Glasir API",
    description="API for fetching and synchronizing Glasir timetable data.",
    version="0.1.0", # Added basic API info
    default_response_class=ORJSONResponse,
    lifespan=lifespan
)

# Note: @app.on_event("startup") is deprecated in favor of lifespan context manager
# The FastAPILimiter initialization is now handled within the lifespan manager above.

@app.get("/")
async def read_root():
    """
    Root endpoint for the Glasir API.
    Returns a simple message indicating the API is running.
    """
    return {"message": "Glasir API is running"}


# --- Phase 2: Initial Synchronization ---

@app.post(
    "/sync/initial",
    response_model=InitialSyncResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initial synchronization for a new user",
    tags=["Synchronization"],
    dependencies=[Depends(ConditionalRateLimiter(times=5, seconds=60))] # Apply conditional rate limiting
)
async def initial_sync(
    request: Request,
    sync_request: InitialSyncRequest
):
    """
    Performs the initial synchronization for a new user.

    - Validates the provided student ID and cookies.
    - Checks if the user already has a session.
    - Fetches all available timetable weeks from Glasir.
    - Creates a new user session with an access code.
    - Stores the fetched timetable data in the database.
    - Returns the access code and the initial timetable data.
    """
    # log.debug("--- DIAG: ENTERING initial_sync function ---") # Removed diagnostic log

    db: databases.Database = request.app.state.database
    http_client: httpx.AsyncClient = request.app.state.http_client

    if not db or not http_client:
        log.error("Initial sync failed: Database or HTTP client not available.")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Core services are unavailable.")

    student_id = sync_request.student_id
    cookies_str = sync_request.cookies

    # --- 1. Check for Existing User Session ---
    try:
        query = UserSession.__table__.select().where(UserSession.__table__.c.student_id == student_id) # Use Class.__table__
        existing_session = await db.fetch_one(query)
        if existing_session:
            log.warning(f"Initial sync attempt failed: User session already exists for student_id {student_id}.")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A session already exists for student ID {student_id}. Use the regular sync endpoint."
            )
    except Exception as e:
        log.error(f"Database error checking for existing session for student {student_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error checking user session.")

    # --- 2. Validate Cookies & Fetch Available Offsets ---
    extractor: Optional[TimetableExtractor] = None
    available_offsets: List[int] = []
    try:
        # Use _setup_extractor to validate cookies implicitly by attempting setup
        # Pass the database connection needed by the updated _setup_extractor
        log.info(f"Attempting extractor setup and cookie validation for student {student_id}...")
        extractor, _, _ = await _setup_extractor(cookies_str, http_client, db)
        log.info(f"Extractor setup successful, cookies appear valid for student {student_id}.")

        # Fetch base week HTML to get available offsets
        log.info(f"Fetching base week HTML (offset 0) for student {student_id} to find available offsets...")
        base_week_html = await extractor.fetch_week_html(offset=0, student_id=student_id)
        if not base_week_html:
            log.error(f"Could not fetch base week HTML (offset 0) for student {student_id}.")
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not fetch base week from Glasir to determine available weeks.")

        available_offsets = parse_available_offsets(base_week_html)
        if not available_offsets:
            # This might be valid if Glasir returns no navigation, but log it.
            log.warning(f"No available week offsets found in Glasir navigation for student {student_id}. Proceeding with empty initial data.")
            # If no offsets, we can technically still create the session, but return empty data.
            # Let's proceed but the fetch below will return empty.

        log.info(f"Found available offsets for student {student_id}: {available_offsets}")

    except HTTPException as e:
        # Re-raise HTTPExceptions from _setup_extractor (e.g., 401 Unauthorized, 502 Bad Gateway)
        log.warning(f"Initial sync failed during cookie validation/setup for student {student_id}: {e.detail}")
        raise e
    except Exception as e:
        log.error(f"Unexpected error during cookie validation or offset fetching for student {student_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error during initial setup.")

    # --- 3. Fetch All Timetable Data ---
    all_fetched_weeks: List[TimetableData] = []
    if available_offsets: # Only fetch if offsets were found
        try:
            log.info(f"Fetching data for {len(available_offsets)} weeks for student {student_id}...")
            # Pass db instance to get_multiple_weeks
            all_fetched_weeks = await get_multiple_weeks(
                username="initial_sync", # Placeholder username for service function context
                student_id=student_id,
                cookies_list=cookies_str, # Corrected keyword argument
                requested_offsets=available_offsets,
                shared_client=http_client,
                db=db # Pass the database connection
            )
            log.info(f"Successfully fetched data for {len(all_fetched_weeks)} weeks for student {student_id}.")
        except HTTPException as e:
            # Handle errors during the multi-week fetch
            log.error(f"Failed to fetch multiple weeks during initial sync for student {student_id}: {e.detail}")
            raise e # Re-raise the exception
        except Exception as e:
            log.error(f"Unexpected error fetching multiple weeks during initial sync for student {student_id}: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error fetching timetable data.")
    else:
         log.info(f"Skipping timetable fetch for student {student_id} as no available offsets were found.")


    # --- 4. Database Transaction: Create Session & Store Timetables ---
    access_code = secrets.token_urlsafe(32) # Secure generation confirmed
    # Use naive UTC time consistent with model defaults (datetime.datetime.utcnow)
    now_utc = datetime.utcnow()

    try:
        async with db.transaction():
            log.info(f"Starting database transaction for initial sync (student {student_id}).")
            # --- Create User Session ---
            session_values = {
                "student_id": student_id,
                "access_code": access_code,
                "access_code_generated_at": now_utc, # Add timestamp for access code generation
                "cookies_json": json.dumps(cookies_str), # Serialize cookies to JSON string
                "created_at": now_utc,
                "last_accessed_at": now_utc,
                "cookies_updated_at": now_utc # Add timestamp for initial cookie set
            }
            log.debug(f"Attempting to insert UserSession with values: {session_values}") # DEBUG LOG
            session_insert_query = UserSession.__table__.insert().values(**session_values) # Use Class.__table__
            await db.execute(session_insert_query)
            log.info(f"User session created for student {student_id}.")

            # --- Store Weekly Timetable States ---
            # Note: Using student_id directly as per current db_models.py
            # If schema changes to use user_session.id, we'd need to fetch the ID after insert.
            if all_fetched_weeks:
                log.info(f"Processing {len(all_fetched_weeks)} fetched weekly timetable states for student {student_id}.")
                unique_weeks_to_store: Dict[str, TimetableData] = {}
                processed_keys = set()

                for week_data in all_fetched_weeks:
                    if not week_data.week_info or week_data.week_info.year is None or week_data.week_info.week_number is None:
                        log.warning(f"Skipping week data processing due to missing week info: Offset {week_data.week_info.offset if week_data.week_info else 'N/A'}")
                        continue # Skip if essential week info is missing

                    # Use the week_key generated by the model validator if available, otherwise generate it
                    week_key = week_data.week_info.week_key or f"{week_data.week_info.year}-W{week_data.week_info.week_number:02d}"

                    if week_key not in processed_keys:
                        unique_weeks_to_store[week_key] = week_data
                        processed_keys.add(week_key)
                    else:
                        log.warning(f"Duplicate week_key '{week_key}' detected (from offset {week_data.week_info.offset}). Skipping duplicate.")

                log.info(f"Storing {len(unique_weeks_to_store)} unique weekly timetable states for student {student_id}.")

                # --- Store Unique Weekly Timetable States ---
                for i, (week_key, week_data) in enumerate(unique_weeks_to_store.items()):
                    log.debug(f"Storing unique week {i+1}/{len(unique_weeks_to_store)} (Key: {week_key})...")

                    try:
                        timetable_json = week_data.model_dump_json()
                        log.debug(f"  Week data serialized successfully.")
                    except Exception as json_err:
                        log.error(f"  Failed to serialize week data for key {week_key}: {json_err}", exc_info=True)
                        continue # Skip this week if serialization fails

                    # Prepare insert statement for this unique week
                    state_values = {
                        "student_id": student_id,
                        "week_key": week_key,
                        "week_data_json": timetable_json,
                        "last_updated_at": now_utc
                    }
                    log.debug(f"  Attempting to insert WeeklyTimetableState with values: {state_values}")
                    state_insert_query = WeeklyTimetableState.__table__.insert().values(**state_values)
                    await db.execute(state_insert_query)
                    log.debug(f"  Successfully inserted state for week_key: {week_key}")

                log.info(f"Finished storing unique weekly states for student {student_id}.")
            else:
                log.info(f"No fetched week data to store for student {student_id}.")

            log.info(f"Database transaction committed successfully for student {student_id}.")

    except Exception as e:
        # Log the specific exception type and message
        log.error(f"Database transaction failed during initial sync for student {student_id}: {type(e).__name__} - {e}", exc_info=True)
        # The transaction will be rolled back automatically by the context manager exit
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save session or timetable data.")

    # --- 5. Return Response ---
    log.info(f"Initial sync completed successfully for student {student_id}. Returning access code and data.")
    return InitialSyncResponse(
        access_code=access_code,
        initial_data=all_fetched_weeks
    )
# --- Phase 3: Subsequent Sync and Per-Week Diffing ---

@app.post(
    "/sync",
    response_model=SyncResponse,
    status_code=status.HTTP_200_OK,
    summary="Subsequent synchronization for an existing user session",
    tags=["Synchronization"]
    # Note: Rate limiting is NOT applied here by default, consider if needed based on usage patterns.
    # If needed, add: dependencies=[Depends(RateLimiter(times=..., seconds=...))]
)
async def sync(
    request: Request,
    sync_request: SyncRequest,
    access_code: Annotated[str | None, Header(alias="X-Access-Code")] = None
):
    """
    Performs subsequent synchronization for an existing user session.
    Validates the session and cookies, fetches only the requested weeks,
    diffs them against the stored state, updates the database, and returns the new data.
    """
    db: databases.Database = request.app.state.database
    http_client: httpx.AsyncClient = request.app.state.http_client

    if not db or not http_client:
        log.error("Sync failed: Database or HTTP client not available.")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Core services are unavailable.")

    # --- 1. Validate Access Code ---
    if not access_code:
        log.warning("Sync attempt failed: Missing X-Access-Code header.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-Access-Code header.")

    # Query UserSession by access_code
    query = UserSession.__table__.select().where(UserSession.__table__.c.access_code == access_code) # Use Class.__table__
    session = await db.fetch_one(query)
    if not session:
        log.warning("Sync attempt failed: Invalid access code.")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid access code.")

    student_id = session["student_id"]
    cookies_json = session["cookies_json"] # Changed column name
    # Use cookies_updated_at if available, otherwise fallback to created_at
    # Access Record attributes using dictionary-style access
    if "cookies_updated_at" in session and session["cookies_updated_at"]:
        cookies_updated_at = session["cookies_updated_at"]
    else:
        cookies_updated_at = session["created_at"] # Fallback

    # --- 2. Check Cookie Freshness ---
    now_utc = datetime.now(timezone.utc)
    # TODO: Make cookie expiry duration configurable
    # Ensure cookies_updated_at is timezone-aware (assuming UTC) before comparison
    if isinstance(cookies_updated_at, datetime) and cookies_updated_at.tzinfo is None:
        cookies_updated_at = cookies_updated_at.replace(tzinfo=timezone.utc)

    if (now_utc - cookies_updated_at) > timedelta(hours=24):
        log.warning("Sync attempt failed: Cookies expired for access code %s", access_code)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"detail": "Cookies expired", "error_code": "COOKIES_EXPIRED"}
        )

    # --- 3. Parse Cookies (for potential _setup_extractor call) ---
    cookies_list: Optional[List[Dict[str, Any]]] = None
    cookies_str_for_fetch: Optional[str] = None # Keep original string format if needed by get_multiple_weeks
    if isinstance(cookies_json, str):
        try:
            # Attempt to parse the JSON string stored in the DB
            cookies_list = json.loads(cookies_json)
            if not isinstance(cookies_list, list):
                 log.warning(f"Parsed cookies_json for student {student_id} is not a list, type: {type(cookies_list)}. Treating as invalid.")
                 cookies_list = None # Invalidate if not a list
            # Keep the original string format as well, in case get_multiple_weeks expects it
            cookies_str_for_fetch = cookies_json
        except json.JSONDecodeError:
             log.warning(f"Could not decode cookies_json for student {student_id}. Treating as invalid.")
             cookies_list = None
             cookies_str_for_fetch = cookies_json # Keep original string for potential legacy use
        except Exception as e:
            log.warning(f"Unexpected error parsing cookies_json for student {student_id}: {e}")
            cookies_list = None
            cookies_str_for_fetch = cookies_json
    else:
        # Should not happen if DB stores JSON string, but handle defensively
        log.warning(f"cookies_json for student {student_id} is not a string (type: {type(cookies_json)}). Cannot parse.")
        cookies_list = None
        cookies_str_for_fetch = str(cookies_json) # Attempt string conversion

    if cookies_list is None and isinstance(sync_request.offsets, str):
        # If parsing failed AND we need it for offset resolution, we cannot proceed.
        log.error(f"Sync failed for student {student_id}: Could not parse stored cookies required for offset resolution based on string '{sync_request.offsets}'.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to parse stored session cookies required for resolving offsets.")

    # --- 4. Determine Target Week Offsets ---
    target_offsets: List[int] = []
    if isinstance(sync_request.offsets, str):
        log.info(f"Resolving offsets for string identifier: '{sync_request.offsets}' for student {student_id}")
        # We already checked cookies_list is valid if offsets is a string
        try:
            # Need extractor to fetch base week HTML
            extractor, _, _ = await _setup_extractor(cookies_list, http_client, db) # Use parsed list
            base_week_html = await extractor.fetch_week_html(offset=0, student_id=student_id)
            if not base_week_html:
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not fetch base week from Glasir to determine available weeks for sync.")

            available_offsets = parse_available_offsets(base_week_html)
            if not available_offsets:
                 log.warning(f"No available offsets found for student {student_id} during sync offset resolution.")
                 target_offsets = [] # Proceed with empty list if none found
            elif sync_request.offsets == "all":
                target_offsets = available_offsets
            elif sync_request.offsets == "current_forward":
                target_offsets = [offset for offset in available_offsets if offset >= 0]
            else:
                # Should be caught by Pydantic Literal validation, but handle defensively
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid string offset identifier: {sync_request.offsets}")

            log.info(f"Resolved offsets for '{sync_request.offsets}': {target_offsets}")

        except HTTPException as e:
            # Re-raise HTTP exceptions from setup/fetch/parse
            raise e
        except Exception as e:
            log.error(f"Error resolving offsets for string '{sync_request.offsets}' for student {student_id}: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error resolving week offsets.")
    else:
        # Offsets provided as a list
        target_offsets = sync_request.offsets
        log.info(f"Using provided list of offsets for student {student_id}: {target_offsets}")


    # --- 5. Fetch New Data for Requested Weeks ---
    # TODO: Refactor get_multiple_weeks to accept cookies_list? For now, use cookies_str_for_fetch
    if not cookies_str_for_fetch:
         # This check might be redundant if cookies_list check above guarantees cookies_str_for_fetch is set
         log.error(f"Sync failed for student {student_id}: Missing cookie string for fetch operation.")
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error preparing cookies for fetch.")

    if not target_offsets:
        log.info(f"No target offsets determined for student {student_id}. Skipping fetch.")
        new_data_list = []
    else:
        try:
            new_data_list = await get_multiple_weeks(
                username="sync",
                student_id=student_id,
                cookies_list=cookies_list, # Pass the parsed list using the correct keyword
                requested_offsets=target_offsets, # Use the determined list
                shared_client=http_client,
                db=db
            )
        except httpx.HTTPStatusError as e:
            log.error(f"Failed to fetch weeks during sync for student {student_id}: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to fetch requested weeks from Glasir.")
        except httpx.RequestError as e:
            log.error(f"Network error during sync for student {student_id}: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Network error fetching requested weeks from Glasir.")
        except Exception as e:
            log.error(f"Failed to fetch weeks during sync for student {student_id}: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to fetch requested weeks from Glasir.")

    # --- 6. Diff and Upsert in DB ---
    diff_results = {}
    # Define timestamp before the transaction block to ensure it's available
    now_utc_update = datetime.utcnow()

    try:
        async with db.transaction():
            for offset in target_offsets: # Use the determined target_offsets list
                new_week_data = next((week for week in new_data_list if week.week_info and week.week_info.offset == offset), None)

                if new_week_data is None:
                    week_key = f"UNKNOWN-{offset}"
                    # Removed individual warning log here, summary will cover it.
                    diff_results[week_key] = {"error": f"Failed to fetch data for week with offset {offset}"}
                    continue

                week_info = new_week_data.week_info
                if not week_info or week_info.year is None or week_info.week_number is None:
                    log.warning(f"Skipping week data due to missing week info: {new_week_data}")
                    week_key = f"UNKNOWN-{offset}"
                    diff_results[week_key] = {"error": "Missing week info"}
                    continue

                week_key = f"{week_info.year}-{week_info.week_number:02d}"

                # Query for existing week state
                select_query = WeeklyTimetableState.__table__.select().where( # Use Class.__table__
                    (WeeklyTimetableState.__table__.c.student_id == student_id) &
                    (WeeklyTimetableState.__table__.c.week_key == week_key)
                )
                old_record = await db.fetch_one(select_query)
                old_week_data = None
                if old_record and old_record["week_data_json"]: # Changed column name
                    try:
                        old_week_data = TimetableData.model_validate_json(old_record["week_data_json"]) # Changed column name
                    except Exception as e:
                        log.warning(f"Failed to parse old week data for {week_key}: {e}")

                try:
                    # Calculate diff
                    week_diff = calculate_week_diff(old_week_data, new_week_data)
                    diff_results[week_key] = week_diff
                except Exception as diff_err:
                    log.error(f"Diff calculation failed for week {week_key}: {diff_err}", exc_info=True)
                    diff_results[week_key] = {"error": f"Diff calculation failed: {diff_err}"}
                    continue

                # Serialize new week data
                new_week_json = new_week_data.model_dump_json()
                # Use the timestamp defined outside the loop

                # Upsert logic: if exists, update; else, insert
                if old_record:
                    update_query = (
                        WeeklyTimetableState.__table__.update() # Use Class.__table__
                        .where(
                            (WeeklyTimetableState.__table__.c.student_id == student_id) &
                            (WeeklyTimetableState.__table__.c.week_key == week_key)
                        )
                        .values(
                            week_data_json=new_week_json, # Changed column name
                            last_updated_at=now_utc_update
                        )
                    )
                    await db.execute(update_query)
                else:
                    insert_query = (
                        WeeklyTimetableState.__table__.insert() # Use Class.__table__
                        .values(
                            student_id=student_id,
                            week_key=week_key,
                            week_data_json=new_week_json, # Changed column name
                            last_updated_at=now_utc_update
                        )
                    )
                    await db.execute(insert_query)

            # Update last_accessed_at in UserSession
            update_session_query = (
                UserSession.__table__.update() # Use Class.__table__
                .where(UserSession.__table__.c.access_code == access_code)
                .values(last_accessed_at=now_utc_update) # Use the same timestamp
            )
            await db.execute(update_session_query)

    except Exception as e:
        log.error(f"Database transaction failed during sync for student {student_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update timetable data.")

    # --- 7. Log Summary of Diff Errors ---
    sync_errors = defaultdict(list)
    for week_key, diff_data in diff_results.items():
        if isinstance(diff_data, dict) and 'error' in diff_data:
            error_msg = diff_data['error']
            # Try to extract offset from week_key (e.g., "UNKNOWN--3" or "2024-15")
            try:
                if week_key.startswith("UNKNOWN-"):
                    offset_str = week_key.split('-')[-1]
                    key_identifier = f"Offset {offset_str}"
                else:
                    key_identifier = f"Week {week_key}" # Use year-week as identifier
            except Exception:
                key_identifier = week_key # Fallback to full key if parsing fails

            sync_errors[error_msg].append(key_identifier)

    if sync_errors:
        log.warning(f"Sync completed with errors for student {student_id}:")
        for error_msg, identifiers in sync_errors.items():
            truncated_msg = (error_msg[:150] + '...') if len(error_msg) > 150 else error_msg
            log.warning(f"  - Error='{truncated_msg}': Affected {identifiers}")
    else:
        log.info(f"Sync completed successfully with no errors in diff results for student {student_id}.")
        # Optional: Log debug level info about successful diffs if needed
        # log.debug(f"Successful diff results: {diff_results}")


    # --- 8. Return the Per-Week Diffs (Final) ---
    return SyncResponse(
        diffs=diff_results,
        # Use naive UTC time consistent with model defaults
        synced_at=datetime.utcnow()
    )

# --- Session Management ---
# --- Dependency Functions ---

async def get_db(request: Request) -> databases.Database:
    """Dependency function to get the database connection from app state."""
    db = getattr(request.app.state, 'database', None)
    if not db:
        log.error("Dependency Error: Database connection not found in application state.")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database service unavailable.")
    return db

async def get_http_client(request: Request) -> httpx.AsyncClient:
    """Dependency function to get the HTTP client from app state."""
    client = getattr(request.app.state, 'http_client', None)
    if not client:
        log.error("Dependency Error: HTTP client not found in application state.")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="HTTP client service unavailable.")
    return client

@app.post(
    "/session/refresh",
    status_code=status.HTTP_200_OK,
    summary="Refresh an existing user session with new cookies and access code",
    tags=["Session Management"],
    dependencies=[Depends(ConditionalRateLimiter(times=5, seconds=60))] # Apply conditional rate limiting
)
async def refresh_session(
    refresh_request: SessionRefreshRequest,
    # Use dedicated dependency functions
    db: databases.Database = Depends(get_db),
    http_client: httpx.AsyncClient = Depends(get_http_client)
):
    """
    Refreshes an existing user session by:
    - Validating the provided student ID and new cookies.
    - Generating a new access code.
    - Updating the user session with the new cookies and access code.
    """
    student_id = refresh_request.student_id
    new_cookies = refresh_request.new_cookies

    # --- 1. Validate Presence of student_id and new_cookies ---
    if not student_id or not new_cookies:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both student_id and new_cookies are required."
        )

    # --- 2. Validate new_cookies by making a test request to Glasir ---
    try:
        # Parse the JSON string back into a list of dictionaries
        try:
            cookies_list = json.loads(new_cookies)
            if not isinstance(cookies_list, list):
                 raise ValueError("Parsed cookies JSON is not a list.")
        except (json.JSONDecodeError, ValueError) as json_err:
            log.error(f"Session refresh failed: Could not parse new_cookies JSON string for student {student_id}: {json_err}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid format for new_cookies: {json_err}"
            )

        # Pass the parsed list to _setup_extractor
        if not db: raise HTTPException(status_code=503, detail="DB connection unavailable.")
        if not http_client: raise HTTPException(status_code=503, detail="HTTP client unavailable.")
        _, _, _ = await _setup_extractor(cookies_list, http_client, db) # Pass the parsed list
        log.info(f"Cookie validation successful for session refresh (student {student_id}).")
    except HTTPException as e:
        # Handle specific HTTPExceptions from _setup_extractor (like 401)
        log.warning(f"Session refresh failed during cookie validation for student {student_id}. Detail: {e.detail}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid new_cookies provided." # Avoid leaking internal error details
        )
    except Exception as e:
        log.error(f"Session refresh failed: Internal error during cookie validation for student {student_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error during cookie validation."
        )

    # --- 3. Query UserSession by student_id ---
    try:
        query = UserSession.__table__.select().where(UserSession.__table__.c.student_id == student_id) # Use Class.__table__
        session = await db.fetch_one(query)
        if not session:
            log.warning(f"Session refresh attempt failed: User session not found for student_id {student_id}.")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User session not found for student ID {student_id}."
            )
    except Exception as e:
        log.error(f"Database error checking for session during refresh for student {student_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error checking user session.")


    # --- 4. Generate a new, secure, unique access_code ---
    new_access_code = secrets.token_urlsafe(32) # Secure generation confirmed
    # Use naive UTC time consistent with model defaults
    now_utc = datetime.utcnow()

    # --- 5. Database Update ---
    try:
        async with db.transaction():
            update_query = (
                UserSession.__table__.update() # Use Class.__table__
                .where(UserSession.__table__.c.student_id == student_id)
                .values(
                    access_code=new_access_code,
                    access_code_generated_at=now_utc, # Track when the code was generated
                    cookies_json=new_cookies, # Store the JSON string directly
                    cookies_updated_at=now_utc, # Track when cookies were last updated
                    last_accessed_at=now_utc # Update last accessed as well
                )
            )
            await db.execute(update_query)
            log.info(f"Session refreshed successfully for student {student_id}.")
    except Exception as e:
        log.error(f"Database transaction failed during session refresh for student {student_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error during session refresh."
        )

    # --- 6. Response ---
    return {"access_code": new_access_code}


    # Reminder for DevOps team to ensure HTTPS is used in production
    # HTTPS is crucial for protecting sensitive data like cookies and access codes

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
    db: databases.Database = request.app.state.database # Get DB connection
    extractor: Optional[TimetableExtractor] = None

    try:
        # 1. Initial Setup (Get extractor, teacher_map, lname)
        # Pass db to _setup_extractor
        if not db: raise HTTPException(status_code=503, detail="DB connection unavailable.")
        if not http_client: raise HTTPException(status_code=503, detail="HTTP client unavailable.")
        setup_result = await _setup_extractor(cookie, http_client, db)
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
        if not db: raise HTTPException(status_code=503, detail="DB connection unavailable.")
        all_weeks_data = await get_multiple_weeks(
            username=username,
            student_id=student_id,
            cookies_str=cookie,
            requested_offsets=available_offsets,
            shared_client=http_client, # Pass the shared client
            db=db # Pass the database connection
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
    db: databases.Database = request.app.state.database # Get DB connection
    extractor: Optional[TimetableExtractor] = None

    try:
        # 1. Initial Setup
        # Pass db to _setup_extractor
        if not db: raise HTTPException(status_code=503, detail="DB connection unavailable.")
        if not http_client: raise HTTPException(status_code=503, detail="HTTP client unavailable.")
        setup_result = await _setup_extractor(cookie, http_client, db)
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
        if not db: raise HTTPException(status_code=503, detail="DB connection unavailable.")
        forward_weeks_data = await get_multiple_weeks(
            username=username,
            student_id=student_id,
            cookies_str=cookie,
            requested_offsets=forward_offsets, # Use filtered list
            shared_client=http_client,
            db=db # Pass the database connection
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
    db: databases.Database = request.app.state.database # Get DB connection

    try:
        # 1. Generate the list of requested offsets
        requested_offsets = list(range(count + 1)) # [0, 1, ..., count]
        logging.info(f"Requesting offsets for N forward weeks ({count}): {requested_offsets}")

        # 2. Call the Multi-Week Service Function
        # No need to fetch base week first, as we explicitly define the offsets
        if not db: raise HTTPException(status_code=503, detail="DB connection unavailable.")
        if not http_client: raise HTTPException(status_code=503, detail="HTTP client unavailable.")
        n_forward_weeks_data = await get_multiple_weeks(
            username=username,
            student_id=student_id,
            cookies_str=cookie,
            requested_offsets=requested_offsets,
            shared_client=http_client,
            db=db # Pass the database connection
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
    db: databases.Database = request.app.state.database # Get DB connection

    extractor: Optional[TimetableExtractor] = None # Only need extractor now
    try:
        # Setup extractor using the shared client and get teacher map
        # _setup_extractor now accepts the shared client and db
        if not db: raise HTTPException(status_code=503, detail="DB connection unavailable.")
        if not http_client: raise HTTPException(status_code=503, detail="HTTP client unavailable.")
        setup_result = await _setup_extractor(cookie, http_client, db)
        if setup_result is None:
            raise HTTPException(status_code=502, detail="Failed initial setup with Glasir: Could not parse cookies, get session parameters, or fetch teacher map.")

        # Unpack the result, ignoring the third value (lname) which is handled by the extractor now
        extractor, teacher_map, _ = setup_result

        # Fetch and process the specific week's timetable data using the new function
        # Note: This endpoint might need rethinking as fetch_and_parse_single_week returns WeekDataResult, not just the data dict.
        # For now, let's assume we want the raw data if successful, or raise error otherwise.
        # This endpoint /profiles/{username}/weeks/{offset} might be deprecated or changed
        # in favor of the sync endpoints which handle the WeekDataResult structure better.
        # Temporarily adapting to call the new function and extract data if successful.
        week_result = await fetch_and_parse_single_week(offset, extractor, student_id, teacher_map)

        if week_result.status not in ['SuccessWithData', 'SuccessNoData'] or week_result.data is None:
             # Handle fetch/parse failures based on the result status
             error_detail = f"Failed to process week offset {offset}. Status: {week_result.status}. Error: {week_result.error_message}"
             log.warning(error_detail)
             # Map status to appropriate HTTP error
             if week_result.status == 'FetchFailed':
                 raise HTTPException(status_code=502, detail=error_detail)
             elif week_result.status == 'ParseFailed':
                  raise HTTPException(status_code=502, detail=error_detail) # Or 500 if it's an internal validation issue
             else: # Other unexpected failures
                 raise HTTPException(status_code=404, detail=f"Timetable data not found or failed to process for offset {offset}.")

        # If successful (with or without data), use the validated TimetableData object
        processed_data = week_result.data # This is now a TimetableData object

        if processed_data is None: # Should be caught above, but double-check
            raise HTTPException(status_code=404, detail=f"Timetable data not found or failed to process for offset {offset}.")

        # The old logic adding student_info here is redundant as TimetableData includes it.
        # processed_data['student_info'] = {'student_id': student_id, 'username': username}
        return processed_data # Return the TimetableData object directly

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