**Project Goal:** Create a simple web API that extracts student timetable information from the Glasir website. The API will accept user identification (`username`, `student_id`) and authentication cookies, interact with the Glasir backend, and return timetable data in JSON format.

**Core Technologies:**

*   **Web Framework:** FastAPI
*   **HTTP Client:** `httpx`
*   **HTML Parsing:** `BeautifulSoup4`, `lxml`
*   **JSON Handling:** `orjson`
*   **Data Modeling/Validation:** `pydantic`

---

## Phase 0: Project Setup, Core Logic Integration & Cleanup

**Goal:** Set up the basic API project structure, copy essential code from the original Glasir scraper project, install dependencies, and explicitly remove any copied code that is not needed for the API's core function (fetching and parsing timetable data).

**Tasks:**

1.  **Create Project Directory and Virtual Environment:**
    ```bash
    mkdir glasir_api
    cd glasir_api
    python -m venv venv
    # Activate the virtual environment
    # Windows: venv\Scripts\activate
    # Linux/macOS: source venv/bin/activate
    ```
2.  **Create Initial File Structure:**
    ```bash
    touch main.py requirements.txt
    mkdir core models
    touch core/__init__.py core/client.py core/constants.py core/date_utils.py core/extractor.py core/parsers.py core/service.py core/session.py
    touch models/__init__.py models/models.py
    ```
3.  **Install Dependencies:**
    ```bash
    pip install fastapi uvicorn httpx beautifulsoup4 lxml orjson pydantic
    pip freeze > requirements.txt
    ```
4.  **Copy Essential Code from Original Project:**
    *   **Models:** Copy the content of the original `models.py` (containing Pydantic models like `Event`, `WeekInfo`, `TimetableData`, etc.) into `glasir_api/models/models.py`.
    *   **API Client:** Copy the content of the original `api/client.py` (containing the `AsyncApiClient` class) into `glasir_api/core/client.py`.
    *   **Extractor:** Copy the content of the original `extractors/timetable_extractor.py` (containing `TimetableExtractor`) into `glasir_api/core/extractor.py`.
    *   **Parsers:**
        *   Copy relevant parsing functions (e.g., `parse_timetable_html`, `parse_homework_html`, `parse_teachers`, `merge_homework_into_events`) from the original `parsers/` directory into `glasir_api/core/parsers.py`. Combine them into this single file.
        *   Copy the function to parse available week offsets from HTML (if it exists, otherwise it will be created later) into `glasir_api/core/parsers.py`.
    *   **Session Utils:** Copy the `extract_session_params_from_html` and `generate_timestamp_timer` functions from the original `auth/session_params.py` (or wherever they reside) into `glasir_api/core/session.py`.
    *   **Constants:** Copy essential constants (URLs like `GLASIR_TIMETABLE_URL`, `GLASIR_WEEK_URL`, `GLASIR_HOMEWORK_URL`, `GLASIR_TEACHERS_URL`, CSS selectors, etc.) from the original `shared/constants.py` into `glasir_api/core/constants.py`.
    *   **Date Utils:** Copy utility functions for date/time handling from the original `shared/date_utils.py` into `glasir_api/core/date_utils.py`.
5.  **Adjust Imports:**
    *   Carefully review *all* copied files (`client.py`, `extractor.py`, `parsers.py`, `session.py`, `constants.py`, `date_utils.py`, `models.py`).
    *   Update all `import` statements to use the new project structure. Examples:
        *   `from models.models import TimetableData`
        *   `from core.constants import GLASIR_TIMETABLE_URL`
        *   `from .client import AsyncApiClient` (if importing within the `core` directory)
6.  **Clean Up Copied Code (Remove Unused Functions/Classes):**
    *   **`core/client.py` (`AsyncApiClient`):** Review its methods. Keep methods related to generic GET/POST requests used by the extractor. Remove any methods specifically tied to login flows or other features not needed by this API.
    *   **`core/extractor.py` (`TimetableExtractor`):** Keep methods like `fetch_week_html`, `fetch_homework_for_lessons`, `fetch_teachers_map`. Remove methods related to fetching data not directly used for the timetable (e.g., perhaps specific course lists if not needed). Ensure it uses the `AsyncApiClient`.
    *   **`core/parsers.py`:** Keep only the functions required for parsing timetable tables, homework details, teacher names, merging homework, and extracting week offsets. Remove any parsers for unrelated pages or data.
    *   **`core/session.py`:** Keep only `extract_session_params_from_html` and `generate_timestamp_timer`. Remove anything else related to credential handling or session saving/loading.
    *   **`core/constants.py`:** Remove any constants related to login selectors, file paths, unused URLs, or configuration keys.
    *   **`core/date_utils.py`:** Remove any date functions not used by the timetable/homework parsing logic.
    *   **`models/models.py`:** Keep all Pydantic models directly related to the timetable structure (`Event`, `WeekInfo`, `TimetableData`, `Teacher`, etc.). Remove models related to configuration, login status, or other unused data structures.
7.  **Basic FastAPI App Setup (`main.py`):**
    *   Import `FastAPI` from `fastapi`.
    *   Create an app instance: `app = FastAPI()`.
    *   Add a placeholder root endpoint for testing:
        ```python
        from fastapi import FastAPI
        from fastapi.responses import ORJSONResponse # Use faster JSON library

        app = FastAPI(default_response_class=ORJSONResponse)

        @app.get("/")
        async def read_root():
            return {"message": "Glasir API - Phase 0 Setup Complete"}
        ```
8.  **Verify Setup:**
    *   Ensure the virtual environment is active.
    *   Run the server: `uvicorn main:app --reload --host 0.0.0.0 --port 8000`
    *   Open `http://127.0.0.1:8000` in your browser. You should see the JSON message `{"message": "Glasir API - Phase 0 Setup Complete"}`.
    *   Check the terminal for any import errors during startup. Fix them if necessary.

**Deliverable:** A runnable FastAPI project with cleaned core logic copied from the original scraper, ready for implementing the first endpoint. Unused code from the original project should be removed.

---

## Phase 1: Implement Single Week Timetable Endpoint

**Goal:** Create the first functional endpoint (`GET /profiles/{username}/weeks/{offset}`) that accepts necessary inputs and returns the timetable data for a single specified week.

**Tasks:**

1.  **Define Core Service Logic (`core/service.py`):**
    *   Import necessary modules: `httpx`, `orjson`, `asyncio`.
    *   Import relevant classes/functions from `.client`, `.constants`, `.date_utils`, `.extractor`, `.parsers`, `.session`.
    *   Import `TimetableData` from `models.models`.
    *   **Helper Function `_fetch_and_process_week`:**
        *   Define `async def _fetch_and_process_week(offset: int, extractor: TimetableExtractor, student_id: str, teacher_map: dict) -> dict | None:`
        *   Inside:
            *   Call `extractor.fetch_week_html(offset, student_id)` -> `week_html`. Handle potential `httpx` errors or empty responses gracefully (return `None`).
            *   Call `parsers.parse_timetable_html(week_html, teacher_map)` -> `timetable_data`, `homework_ids`. Handle parsing errors (return `None`).
            *   If `homework_ids`: Call `extractor.fetch_homework_for_lessons(homework_ids, student_id)` -> `homework_map`. Handle errors.
            *   If `homework_map`: Call `parsers.merge_homework_into_events(timetable_data['events'], homework_map)`.
            *   Return the processed `timetable_data` dictionary.
    *   **Helper Function `_setup_extractor`:**
        *   Define `async def _setup_extractor(cookies_str: str) -> tuple[TimetableExtractor, dict] | None:`
        *   Inside:
            *   Parse `cookies_str` into a `dict` (handle `key=value; key2=value2`). If invalid, return `None`.
            *   Use `httpx.AsyncClient` with parsed cookies to perform a `GET` request to `constants.GLASIR_TIMETABLE_URL` to fetch `initial_html`. Handle `httpx.RequestError`, `httpx.HTTPStatusError`. If error, return `None`.
            *   Extract `lname` using `session.extract_session_params_from_html(initial_html)`. If not found, return `None`.
            *   Generate `timer` using `session.generate_timestamp_timer()`.
            *   Initialize `api_client = AsyncApiClient(cookies=parsed_cookies, lname=lname, timer=timer)`.
            *   Initialize `extractor = TimetableExtractor(api_client)`.
            *   Fetch `teacher_map = await extractor.fetch_teachers_map()`. Handle errors (return `None`).
            *   Return `(extractor, teacher_map)`.
            *   *Important:* This function *does not* close the `api_client`. The caller is responsible.
2.  **Create API Endpoint (`main.py`):**
    *   Import `HTTPException`, `Header`, `Query`, `Path` from `fastapi`.
    *   Import `Annotated` from `typing`.
    *   Import `TimetableData` from `models.models`.
    *   Import `_setup_extractor`, `_fetch_and_process_week` from `core.service`.
    *   Import `httpx`.
    *   Define the endpoint:
        ```python
        # --- At the top of main.py ---
        from fastapi import FastAPI, HTTPException, Header, Query, Path
        from fastapi.responses import ORJSONResponse
        from typing import Annotated, Optional # Optional might be needed if cookie can be truly optional
        import httpx

        from models.models import TimetableData
        from core.service import _setup_extractor, _fetch_and_process_week
        # Assume TimetableExtractor is needed for type hinting or cleanup
        from core.extractor import TimetableExtractor

        app = FastAPI(default_response_class=ORJSONResponse)

        @app.get("/") # Keep the root endpoint
        async def read_root():
            return {"message": "Glasir API"}

        # --- Add the new endpoint ---
        @app.get(
            "/profiles/{username}/weeks/{offset}",
            response_model=TimetableData, # Automatically validates/serializes output
            response_model_exclude_none=True, # Don't include None values in JSON response
            summary="Get timetable for a specific week offset"
        )
        async def get_week_by_offset(
            username: Annotated[str, Path(description="Identifier for the user profile")],
            offset: Annotated[int, Path(description="Week offset (0=current, 1=next, -1=previous)")],
            student_id: Annotated[str, Query(description="The student's unique ID from Glasir")],
            cookie: Annotated[str | None, Header(description="Glasir authentication cookies (e.g., 'ASP.NET_SessionId=...; studentid=...')")] = None
        ):
            if not cookie:
                raise HTTPException(status_code=400, detail="Cookie header is required")
            if not student_id:
                 raise HTTPException(status_code=400, detail="student_id query parameter is required")

            extractor_tuple = None
            try:
                # Setup client, extractor, and get teacher map
                extractor_tuple = await _setup_extractor(cookie)
                if extractor_tuple is None:
                    raise HTTPException(status_code=502, detail="Failed initial setup: Could not get session parameters or teacher map from Glasir.")

                extractor, teacher_map = extractor_tuple

                # Fetch and process the specific week
                processed_data = await _fetch_and_process_week(offset, extractor, student_id, teacher_map)

                if processed_data is None:
                    raise HTTPException(status_code=404, detail=f"Timetable data not found or failed to process for offset {offset}.")

                # Add basic student info
                processed_data['student_info'] = {'student_id': student_id, 'username': username}

                # Validate and return using Pydantic model
                return TimetableData(**processed_data)

            except httpx.HTTPStatusError as e:
                 # Handle errors from underlying HTTP calls during week/homework fetch
                 status = e.response.status_code
                 url = e.request.url
                 raise HTTPException(status_code=502, detail=f"Glasir backend error ({status}) for URL: {url}")
            except httpx.RequestError as e:
                 # Handle network errors
                 url = e.request.url
                 raise HTTPException(status_code=504, detail=f"Network error communicating with Glasir URL: {url}")
            except Exception as e:
                 # Catch-all for unexpected errors (parsing, validation, etc.)
                 # In production, log this properly: print(f"ERROR: {e}", file=sys.stderr)
                 raise HTTPException(status_code=500, detail=f"Internal server error: {type(e).__name__}")
            finally:
                # Ensure the httpx client is closed
                if extractor_tuple and extractor_tuple[0] and extractor_tuple[0].api_client:
                    await extractor_tuple[0].api_client.close()
        ```
3.  **Run and Test:**
    *   Start the server: `uvicorn main:app --reload --host 0.0.0.0 --port 8000`
    *   Use `curl` or a GUI tool (Postman, Insomnia):
        *   Method: `GET`
        *   URL: `http://127.0.0.1:8000/profiles/your_username/weeks/0?student_id=YOUR_STUDENT_ID` (replace placeholders)
        *   Headers: Add `Cookie` header with valid Glasir session cookies.
    *   Verify: Check for a successful JSON response matching `TimetableData`. Test different offsets (e.g., 1, -1). Test error cases (missing cookie, invalid offset - though offset validity is mostly handled by Glasir).

**Deliverable:** A runnable API server that can successfully fetch and return the timetable for a single week specified by its offset.

---

## Phase 2: Authentication Helper Script

**Goal:** Create an independent Python script using Playwright that automates the process of obtaining necessary authentication details from Glasir after a manual login. The script will:
1.  Open a browser window to the Glasir login page (`https://tg.glasir.fo`).
2.  Pause execution, requiring the user to manually log in within the opened browser window.
3.  Wait for successful login confirmation by detecting navigation to the main timetable page (URL pattern `https://tg.glasir.fo/132n/**`) and the presence of the timetable element (`table.time_8_16`).
4.  Once login is confirmed, extract the required authentication cookies (e.g., `ASP.NET_SessionId`, `studentid`) from the browser's context.
5.  Extract the `student_id` from the page content (using appropriate selectors or regex, similar to the original scraper's logic if applicable).
6.  Print the extracted cookies (formatted as a single string suitable for an HTTP `Cookie` header) and the `student_id` to the standard output (console).
7.  The script must be self-contained, managing its own dependencies (primarily `playwright`), and runnable independently of the `glasir_api` project.

**Tasks:**

1.  **Create Script File:** Initialize a new Python file (e.g., `get_glasir_auth.py`).
2.  **Add Dependencies:** Define requirements (e.g., in a `requirements-auth.txt` or directly mention `pip install playwright`). Ensure Playwright browsers are installed (`playwright install`).
3.  **Implement Playwright Logic:**
    *   Import necessary Playwright modules.
    *   Write code to launch a browser (non-headless).
    *   Navigate to the Glasir login URL.
    *   Implement a mechanism to pause the script and prompt the user to log in manually in the browser.
    *   Implement the waiting logic to detect successful login (wait for URL change and specific element).
4.  **Implement Extraction Logic:**
    *   Once logged in, use Playwright's context methods to retrieve all cookies.
    *   Filter/format the cookies into the required single-string format for the `Cookie` header.
    *   Use Playwright's page methods (selectors, potentially regex on content) to find and extract the `student_id`.
5.  **Implement Output:**
    *   Print the formatted cookie string to the console.
    *   Print the extracted `student_id` to the console.
    *   Ensure the browser is closed properly upon completion or error.
6.  **Add User Instructions:** Include comments or print statements guiding the user on when to log in and what the script is doing.

**Deliverable:** A standalone Python script (e.g., `get_glasir_auth.py`) that, when run, guides the user through a manual login on the Glasir website and outputs the necessary authentication cookies and `student_id` to the console.

---

## Phase 3: API Endpoint Testing

**Goal:** Verify the Phase 1 API endpoint (`/profiles/{username}/weeks/{offset}`) using the authentication helper script created in Phase 2.

**Tasks:**

*   Modify the `get_glasir_auth.py` script:
    *   Prompt the user for their Glasir username *before* launching the browser.
    *   After extracting cookies and student ID, use the `httpx` library (add it as a dependency for the script) to send a `GET` request to the running `glasir_api` endpoint: `http://127.0.0.1:8000/profiles/{username}/weeks/0?student_id={student_id}`.
    *   Include the extracted cookie string in the `Cookie` header of the request.
    *   Print the JSON response received from the API.
*   Run the `glasir_api` server (`uvicorn glasir_api.main:app --reload --host 0.0.0.0 --port 8000`).
*   Run the modified `get_glasir_auth.py` script, log in manually, and observe the output.

**Deliverable:** An updated `get_glasir_auth.py` script capable of testing the API endpoint, and confirmation (via user observation or script output) that the endpoint returns valid timetable data when provided with correct authentication details.

---

## Phase 4: Implement Multi-Week Endpoints (All & Current Forward)

**Goal:** Add two new endpoints: one to get *all* available weeks (`/weeks/all`) and another for the *current week and all future weeks* (`/weeks/current_forward`). This involves fetching the list of available weeks and processing multiple weeks concurrently.

**Tasks:**

1.  **Implement Offset Parsing (`core/parsers.py`):**
    *   Ensure a function `parse_available_offsets(html: str) -> list[int]` exists. It should take the HTML content of a timetable page (usually fetched with offset 0) and extract all the integer week offsets available in the Glasir UI's navigation/dropdown. Handle potential parsing errors robustly (e.g., return an empty list or raise a specific error).
2.  **Update Service Logic (`core/service.py`):**
    *   Import `asyncio`.
    *   Import `parse_available_offsets` from `.parsers`.
    *   **Implement `get_multiple_weeks` Core Logic:**
        *   Define `async def get_multiple_weeks(username: str, student_id: str, cookies_str: str, requested_offsets: list[int]) -> list[TimetableData]:`
        *   This function will be the shared logic for fetching several weeks.
        *   Use `_setup_extractor(cookies_str)` to get `extractor` and `teacher_map`. Handle `None` return (raise an exception).
        *   Create `asyncio` tasks: `tasks = [_fetch_and_process_week(offset, extractor, student_id, teacher_map) for offset in requested_offsets]`
        *   Run tasks concurrently: `results = await asyncio.gather(*tasks, return_exceptions=True)`
        *   Process `results`:
            *   Initialize `timetables = []`.
            *   Iterate through `results`. If a result is an `Exception`, log it (e.g., `print(f"Warning: Failed offset {offset}: {result}")`) and continue. If `None`, skip.
            *   If valid `processed_data` dict:
                *   Add student info: `processed_data['student_info'] = {'student_id': student_id, 'username': username}`
                *   Validate using Pydantic: `timetables.append(TimetableData(**processed_data))`. Handle validation errors (log/skip).
        *   Sort the final list: `timetables.sort(key=lambda t: t.week_info.offset)`.
        *   Return `timetables`.
        *   *Crucially:* Ensure the `extractor.api_client` is closed using a `try...finally` block around the core logic.
3.  **Add API Endpoints (`main.py`):**
    *   Import `List` from `typing`.
    *   Import `get_multiple_weeks` from `core.service`.
    *   Import `parse_available_offsets` from `core.parsers`.
    *   **Endpoint for All Weeks:**
        ```python
        # At top: from typing import List
        # At top: from core.parsers import parse_available_offsets
        # At top: from core.service import get_multiple_weeks

        @app.get(
            "/profiles/{username}/weeks/all",
            response_model=List[TimetableData],
            response_model_exclude_none=True,
            summary="Get timetables for ALL available weeks"
        )
        async def get_all_weeks(
            username: Annotated[str, Path(description="Identifier for the user profile")],
            student_id: Annotated[str, Query(description="The student's unique ID from Glasir")],
            cookie: Annotated[str | None, Header(description="Glasir authentication cookies")] = None
        ):
            if not cookie: raise HTTPException(status_code=400, detail="Cookie header is required")
            if not student_id: raise HTTPException(status_code=400, detail="student_id query parameter is required")

            extractor_tuple = None
            try:
                # Setup client - need it temporarily to fetch base week for offsets
                extractor_tuple = await _setup_extractor(cookie)
                if extractor_tuple is None:
                    raise HTTPException(status_code=502, detail="Failed initial setup for getting offsets.")

                extractor, _ = extractor_tuple # Don't need teacher_map yet

                # Fetch base week HTML (offset 0) to find available weeks
                base_week_html = await extractor.fetch_week_html(0, student_id)
                if not base_week_html:
                     raise HTTPException(status_code=502, detail="Could not fetch base week HTML to determine available weeks.")

                # Parse offsets
                available_offsets = parse_available_offsets(base_week_html)
                if not available_offsets:
                    # Maybe return empty list or error? Let's error for now.
                    raise HTTPException(status_code=502, detail="Could not parse available week offsets from Glasir page.")

                # Now fetch all determined weeks using the shared service function
                # Re-use the extractor/client from the initial setup
                timetables = await get_multiple_weeks(username, student_id, cookie, available_offsets) # Pass cookie again for re-setup inside
                return timetables

            except httpx.HTTPStatusError as e:
                 raise HTTPException(status_code=502, detail=f"Glasir backend error ({e.response.status_code}) for URL: {e.request.url}")
            except httpx.RequestError as e:
                 raise HTTPException(status_code=504, detail=f"Network error communicating with Glasir URL: {e.request.url}")
            except Exception as e:
                 # print(f"ERROR: {e}", file=sys.stderr) # Proper logging later
                 raise HTTPException(status_code=500, detail=f"Internal server error: {type(e).__name__}")
            finally:
                 # Close the client used for fetching offsets if it was created
                 if extractor_tuple and extractor_tuple[0] and extractor_tuple[0].api_client:
                      await extractor_tuple[0].api_client.close()
                 # Note: get_multiple_weeks handles closing its own client internally
        ```
    *   **Endpoint for Current + Future Weeks:**
        ```python
        @app.get(
            "/profiles/{username}/weeks/current_forward",
            response_model=List[TimetableData],
            response_model_exclude_none=True,
            summary="Get timetables for Current week (0) and all Future weeks"
        )
        async def get_current_and_forward_weeks(
            username: Annotated[str, Path(description="Identifier for the user profile")],
            student_id: Annotated[str, Query(description="The student's unique ID from Glasir")],
            cookie: Annotated[str | None, Header(description="Glasir authentication cookies")] = None
        ):
            if not cookie: raise HTTPException(status_code=400, detail="Cookie header is required")
            if not student_id: raise HTTPException(status_code=400, detail="student_id query parameter is required")

            extractor_tuple = None
            try:
                # Setup client for fetching offsets
                extractor_tuple = await _setup_extractor(cookie)
                if extractor_tuple is None: raise HTTPException(status_code=502, detail="Failed initial setup.")
                extractor, _ = extractor_tuple

                # Fetch base week and parse offsets
                base_week_html = await extractor.fetch_week_html(0, student_id)
                if not base_week_html: raise HTTPException(status_code=502, detail="Could not fetch base week HTML.")
                available_offsets = parse_available_offsets(base_week_html)
                if not available_offsets: raise HTTPException(status_code=502, detail="Could not parse offsets.")

                # Filter for current (0) and future (+) offsets
                current_forward_offsets = [o for o in available_offsets if o >= 0]
                if not current_forward_offsets:
                    return [] # No current or future weeks found

                # Fetch the filtered weeks
                timetables = await get_multiple_weeks(username, student_id, cookie, current_forward_offsets)
                return timetables

            # ... (copy except httpx/Exception/finally block from /all endpoint) ...
            except httpx.HTTPStatusError as e:
                 raise HTTPException(status_code=502, detail=f"Glasir backend error ({e.response.status_code}) for URL: {e.request.url}")
            except httpx.RequestError as e:
                 raise HTTPException(status_code=504, detail=f"Network error communicating with Glasir URL: {e.request.url}")
            except Exception as e:
                 raise HTTPException(status_code=500, detail=f"Internal server error: {type(e).__name__}")
            finally:
                if extractor_tuple and extractor_tuple[0] and extractor_tuple[0].api_client:
                     await extractor_tuple[0].api_client.close()

        ```
4.  **Run and Test:**
    *   Restart the server.
    *   Test `/profiles/{username}/weeks/all?student_id=...` and `/profiles/{username}/weeks/current_forward?student_id=...` with valid cookies.
    *   Verify they return lists of `TimetableData`. Check the sorting and filtering (for `current_forward`).
    *   Re-test the single week endpoint to ensure it wasn't broken.

**Deliverable:** A runnable API server with three endpoints: single week, all weeks, and current+future weeks.

---

## Phase 5: Implement N Future Weeks Endpoint

**Goal:** Add the final endpoint (`/weeks/forward/{count}`) to fetch the current week (0) plus a specified number of future weeks.

**Tasks:**

1.  **Add API Endpoint (`main.py`):**
    *   This endpoint doesn't need offset parsing; it generates the required offsets directly.
    *   Define the endpoint:
        ```python
        @app.get(
            "/profiles/{username}/weeks/forward/{count}",
            response_model=List[TimetableData],
            response_model_exclude_none=True,
            summary="Get Current week (0) + {count} Future weeks"
        )
        async def get_n_forward_weeks(
            username: Annotated[str, Path(description="Identifier for the user profile")],
            count: Annotated[int, Path(description="Number of future weeks to fetch (e.g., 4 means weeks 0, 1, 2, 3, 4)")],
            student_id: Annotated[str, Query(description="The student's unique ID from Glasir")],
            cookie: Annotated[str | None, Header(description="Glasir authentication cookies")] = None
        ):
            if not cookie: raise HTTPException(status_code=400, detail="Cookie header is required")
            if not student_id: raise HTTPException(status_code=400, detail="student_id query parameter is required")
            if count < 0:
                raise HTTPException(status_code=400, detail="Count must be a non-negative integer.")

            try:
                # Generate the list of offsets: 0, 1, ..., count
                offsets_to_fetch = list(range(count + 1))

                # Use the existing service function to fetch these specific weeks
                timetables = await get_multiple_weeks(username, student_id, cookie, offsets_to_fetch)
                return timetables

            except httpx.HTTPStatusError as e:
                 raise HTTPException(status_code=502, detail=f"Glasir backend error ({e.response.status_code}) for URL: {e.request.url}")
            except httpx.RequestError as e:
                 raise HTTPException(status_code=504, detail=f"Network error communicating with Glasir URL: {e.request.url}")
            except Exception as e:
                 # print(f"ERROR: {e}", file=sys.stderr) # Proper logging later
                 raise HTTPException(status_code=500, detail=f"Internal server error: {type(e).__name__}")
             # Note: get_multiple_weeks handles closing its own client internally
        ```
2.  **Run and Test:**
    *   Restart the server.
    *   Test `/profiles/{username}/weeks/forward/{count}?student_id=...` with various non-negative `count` values (0, 1, 5, etc.).
    *   Verify it returns the correct number of weeks (`count` + 1).
    *   Test with `count=-1` to ensure the 400 error is returned.

**Deliverable:** A runnable API server with all four required timetable endpoints functional.

---

## Phase 6: Refinement and Documentation

**Goal:** Improve the robustness and usability of the API with basic logging, refined error handling, and clear documentation.

**Tasks:**

1.  **Basic Logging:**
    *   Replace `print()` statements used for errors/warnings with Python's `logging`.
    *   In `main.py`, add basic config at the top:
        ```python
        import logging
        import sys # for stderr logging if needed

        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        ```
    *   In `except Exception as e:` blocks, use `logging.exception("An unexpected error occurred:")` or `logging.error(f"Error processing request: {e}", exc_info=True)`.
    *   In `core/service.py` (e.g., when processing results in `get_multiple_weeks`), use `logging.warning(f"Failed to process offset {offset}: {result}")` for caught exceptions per task.
2.  **Error Handling Review:**
    *   Ensure HTTPExceptions have appropriate status codes (400 for bad client input, 404 for not found, 502 for bad gateway/backend error, 504 for gateway timeout/network error, 500 for internal server error).
    *   Add more specific error messages where helpful (e.g., "Failed to extract lname from Glasir page" vs. generic "Failed initial setup").
3.  **Finalize `requirements.txt`:**
    *   Run `pip freeze > requirements.txt` one last time to capture the exact versions of all dependencies.
4.  **Create `README.md`:**
    *   Create a `README.md` file in the project root.
    *   Include:
        *   Project purpose.
        *   How to set up the virtual environment and install dependencies (`pip install -r requirements.txt`).
        *   How to run the API server (`uvicorn main:app --reload --host 0.0.0.0 --port 8000`).
        *   Detailed usage instructions for *each* endpoint:
            *   HTTP Method (GET)
            *   Path (e.g., `/profiles/{username}/weeks/{offset}`)
            *   Path Parameters (e.g., `username`, `offset`, `count`)
            *   Query Parameters (e.g., `student_id`)
            *   Required Headers (`Cookie`)
            *   Example `curl` command.
            *   Description of the expected JSON response (mentioning it follows `TimetableData` or `List[TimetableData]`).

**Deliverable:** A cleaned-up, runnable API server with basic logging and a helpful `README.md` file explaining installation and usage.