# glasir_auth_tool/get_auth.py
# Requirements: playwright, httpx, aiofiles (pip install playwright httpx aiofiles)
#               Browser binaries (python -m playwright install)
import asyncio
import re
import json
import argparse
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from playwright.async_api import async_playwright, Error as PlaywrightError
import httpx
import aiofiles

# --- Constants ---
SCRIPT_DIR = Path(__file__).parent.resolve()
COOKIES_FILE = SCRIPT_DIR / "cookies.json"
STUDENT_ID_FILE = SCRIPT_DIR / "student_id.txt"
ACCESS_CODE_FILE = SCRIPT_DIR / "access_code.txt"

# Regex to find the student GUID in the page content
_RE_GUID = re.compile(
    r"[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}"
)

API_BASE = "http://127.0.0.1:8000"

# --- Data Storage Helpers ---

async def load_data() -> Tuple[Optional[str], Optional[List[Dict[str, Any]]], Optional[str]]:
    """Loads student_id, cookies, and access_code from local files."""
    student_id = None
    cookies = None
    access_code = None

    if STUDENT_ID_FILE.exists():
        try:
            async with aiofiles.open(STUDENT_ID_FILE, "r") as f:
                student_id = (await f.read()).strip()
        except Exception as e:
            print(f"Warning: Could not read student ID file: {e}")

    if COOKIES_FILE.exists():
        try:
            async with aiofiles.open(COOKIES_FILE, "r") as f:
                cookies = json.loads(await f.read())
        except Exception as e:
            print(f"Warning: Could not read or parse cookies file: {e}")

    if ACCESS_CODE_FILE.exists():
        try:
            async with aiofiles.open(ACCESS_CODE_FILE, "r") as f:
                access_code = (await f.read()).strip()
        except Exception as e:
            print(f"Warning: Could not read access code file: {e}")

    return student_id, cookies, access_code

async def save_data(student_id: str, cookies: List[Dict[str, Any]], access_code: str) -> None:
    """Saves student_id, cookies, and access_code to local files."""
    try:
        
        async with aiofiles.open(STUDENT_ID_FILE, "w") as f:
            await f.write(student_id)
    except Exception as e:
        print(f"Error saving student ID: {e}")

    try:
        async with aiofiles.open(COOKIES_FILE, "w") as f:
            await f.write(json.dumps(cookies, indent=2))
    except Exception as e:
        print(f"Error saving cookies: {e}")

    try:
        async with aiofiles.open(ACCESS_CODE_FILE, "w") as f:
            await f.write(access_code)
    except Exception as e:
        print(f"Error saving access code: {e}")

# --- Playwright Login and Initial Sync ---

async def perform_playwright_login_and_initial_sync() -> Tuple[Optional[str], Optional[List[Dict[str, Any]]], Optional[str]]:
    """
    Launches Playwright for user login, extracts student_id and cookies,
    then calls /sync/initial to obtain access_code. Saves all three.
    """
    cookies = None
    student_id = None
    access_code = None

    async with async_playwright() as p:
        browser = None
        try:
            print("Launching browser for Glasir login...")
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
                print("Calling /sync/initial to obtain access code...")
                access_code = await call_initial_sync(student_id, cookies)
                if access_code:
                    await save_data(student_id, cookies, access_code)
                    print("Initial sync successful. Data saved.")
                else:
                    print("Initial sync failed. Could not obtain access code.")
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

    return student_id, cookies, access_code

async def call_initial_sync(student_id: str, cookies: List[Dict[str, Any]]) -> Optional[str]:
    """
    Calls the /sync/initial API endpoint with student_id and cookies.
    Returns the access_code if successful, else None.
    """
    url = f"{API_BASE}/sync/initial"
    payload = {
        "student_id": student_id,
        "cookies": cookies
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=30.0)
            if resp.status_code == 201:
                data = resp.json()
                access_code = data.get("access_code")
                if access_code:
                    print("Received access code from /sync/initial.")
                    return access_code
                else:
                    print("No access_code in response.")
            elif resp.status_code == 401:
                print("Initial sync failed: Invalid cookies (401).")
            elif resp.status_code == 409:
                print("Initial sync failed: User already exists (409).")
            else:
                print(f"Initial sync failed: {resp.status_code} {resp.text}")
    except httpx.RequestError as exc:
        print(f"Network error during initial sync: {exc}")
    except Exception as e:
        print(f"Unexpected error during initial sync: {e}")
    return None

# --- Session Refresh Logic ---

async def perform_session_refresh(student_id: str) -> bool:
    """
    Refreshes the session by obtaining new cookies and calling /session/refresh.
    Returns True on success, False on failure.
    """
    print("Refreshing session: launching browser to obtain new cookies.")
    # Option A: Use Playwright to get new cookies
    cookies = None
    async with async_playwright() as p:
        browser = None
        try:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()
            print("Navigate to Glasir and log in if needed, then go to your timetable page.")
            await page.goto("https://tg.glasir.fo", timeout=60000)
            await page.wait_for_url("https://tg.glasir.fo/132n/**", timeout=0)
            await page.wait_for_selector("table.time_8_16", state="visible", timeout=0)
            cookies = await context.cookies()
        except Exception as e:
            print(f"Error during Playwright session refresh: {e}")
        finally:
            if browser:
                await browser.close()
            print("Browser closed after refresh.")

    if not cookies:
        print("Failed to obtain new cookies for session refresh.")
        return False

    # Add a dummy query parameter 'req=refresh_session' to satisfy potential validation
    url = f"{API_BASE}/session/refresh?req=refresh_session"
    # Serialize the cookies list into a JSON string to match the API model expectation
    cookies_json_string = json.dumps(cookies)
    payload = {
        "student_id": student_id,
        "new_cookies": cookies_json_string # Send the JSON string
    }
    try:
        async with httpx.AsyncClient() as client:
            # Send the payload as JSON. FastAPI will parse the JSON body,
            # and Pydantic will validate the 'new_cookies' field as a string.
            resp = await client.post(url, json=payload, timeout=30.0)
            if resp.status_code == 200:
                data = resp.json()
                new_access_code = data.get("access_code") or data.get("new_access_code")
                if new_access_code:
                    await save_data(student_id, cookies, new_access_code)
                    print("Session refresh successful. Data updated.")
                    return True
                else:
                    print("No access_code in refresh response.")
            elif resp.status_code == 401:
                print("Session refresh failed: Invalid new cookies (401).")
            elif resp.status_code == 404:
                print("Session refresh failed: User not found (404).")
            else:
                print(f"Session refresh failed: {resp.status_code} {resp.text}")
    except httpx.RequestError as exc:
        print(f"Network error during session refresh: {exc}")
    except Exception as e:
        print(f"Unexpected error during session refresh: {e}")
    return False

# --- API Test Logic ---

async def make_api_call(access_code: str, endpoint: str, student_id: str, fetch_full_schedule: bool = False) -> None:
    """
    Makes an API call to the specified endpoint using the access_code for authentication.
    Handles 401/cookie expiration by attempting automatic refresh.
    If fetch_full_schedule is True:
        - If current_weeks.json is missing/invalid, fetches 'weeks/all' as baseline.
        - Otherwise, fetches the specified endpoint and saves to current_weeks.json only if changed.
    """
    if not all([access_code, student_id, endpoint]):
        print("Missing data for API call. Skipping.")
        return

    original_endpoint = endpoint # Store the originally requested endpoint
    api_url = None
    body = None
    output_filename = None

    # --- Logic for Fetch Full Schedule Mode ---
    if fetch_full_schedule:
        loaded_data = None
        needs_baseline_fetch = False
        try:
            if await aiofiles.os.path.exists(CURRENT_WEEKS_FILE):
                async with aiofiles.open(CURRENT_WEEKS_FILE, "r", encoding='utf-8') as f:
                    loaded_data = json.loads(await f.read())
            else:
                needs_baseline_fetch = True
                print(f"'{CURRENT_WEEKS_FILE}' not found. Will fetch baseline ('weeks/all').")
        except (json.JSONDecodeError, Exception) as e:
            needs_baseline_fetch = True
            print(f"Warning: Error reading/parsing existing '{CURRENT_WEEKS_FILE}': {e}. Will fetch baseline ('weeks/all').")

        if needs_baseline_fetch:
            # Override endpoint to fetch the baseline 'weeks/all'
            endpoint_to_call = "weeks/all"
            print(f"Fetching baseline data from endpoint: {endpoint_to_call}")
            api_url = f"{API_BASE}/sync"
            body = {"student_id": student_id, "offsets": "all"}
            output_filename = CURRENT_WEEKS_FILE # Always save baseline
        else:
            # Use the originally requested endpoint for comparison
            endpoint_to_call = original_endpoint
            print(f"Fetching data from requested endpoint for comparison: {endpoint_to_call}")
            # Parse the original endpoint to get api_url and body
            if original_endpoint == "week/0":
                 api_url = f"{API_BASE}/sync"; body = {"student_id": student_id, "offsets": [0]}
            elif original_endpoint == "weeks/all":
                 api_url = f"{API_BASE}/sync"; body = {"student_id": student_id, "offsets": "all"}
            elif original_endpoint == "weeks/current_forward":
                 api_url = f"{API_BASE}/sync"; body = {"student_id": student_id, "offsets": "current_forward"}
            elif original_endpoint.startswith("weeks/forward/"):
                 try:
                     count = int(original_endpoint.split('/')[-1])
                     if count < 0: raise ValueError("Count cannot be negative")
                     api_url = f"{API_BASE}/sync"; body = {"student_id": student_id, "offsets": list(range(count))}
                 except (ValueError, IndexError):
                     print(f"Error: Invalid format for forward weeks endpoint: {original_endpoint}")
                     return
            else:
                 print(f"Error: Unknown original endpoint '{original_endpoint}' during fetch logic.")
                 return
            output_filename = CURRENT_WEEKS_FILE # Target file for potential update

    # --- Logic for Diff Mode (or if fetch_full_schedule is False) ---
    else:
        endpoint_to_call = original_endpoint # Use the provided endpoint
        # Parse endpoint to determine URL, body, and specific output file
        if endpoint_to_call == "week/0":
            api_url = f"{API_BASE}/sync"
            body = {"student_id": student_id, "offsets": [0]}
            output_filename = SCRIPT_DIR / "api_response_week_0.json"
        elif endpoint_to_call == "weeks/all":
            api_url = f"{API_BASE}/sync"
            body = {"student_id": student_id, "offsets": "all"}
            output_filename = SCRIPT_DIR / "api_response_all.json"
        elif endpoint_to_call == "weeks/current_forward":
            api_url = f"{API_BASE}/sync"
            body = {"student_id": student_id, "offsets": "current_forward"}
            output_filename = SCRIPT_DIR / "api_response_current_forward.json"
        elif endpoint_to_call.startswith("weeks/forward/"):
            try:
                count_str = endpoint_to_call.split('/')[-1]
                count = int(count_str)
                if count < 0:
                    print(f"Error: Count for forward weeks cannot be negative ({count}).")
                    return
                api_url = f"{API_BASE}/sync"
                body = {"student_id": student_id, "offsets": list(range(count))}
                output_filename = SCRIPT_DIR / f"api_response_forward_{count}.json"
            except (ValueError, IndexError):
                print(f"Error: Invalid format for forward weeks endpoint: {endpoint_to_call}")
                return
        else:
            print(f"Error: Unknown endpoint '{endpoint_to_call}'.")
            return

    # --- Execute API Call ---
    if not api_url or not body:
         print("Error: Could not determine API URL or body.")
         return

    headers = {"X-Access-Code": access_code}
    print(f"Target Endpoint: {endpoint_to_call} {'(Fetching Full Schedule)' if fetch_full_schedule else '(Fetching Diffs)'}")
    print(f"Output File: {output_filename}")

    try:
        async with httpx.AsyncClient() as client:
            print(f"Sending POST request to: {api_url}")
            response = await client.post(api_url, headers=headers, json=body, timeout=60.0) # Increased timeout
            print(f"API Response Status Code: {response.status_code}")

            if response.status_code == 200:
                try:
                    response_data = response.json()
                    print("\nAPI Response received successfully.")

                    if fetch_full_schedule:
                        if needs_baseline_fetch:
                            print(f"Saving baseline data to '{CURRENT_WEEKS_FILE}'.")
                            try:
                                 async with aiofiles.open(CURRENT_WEEKS_FILE, "w", encoding='utf-8') as f:
                                     await f.write(json.dumps(response_data, indent=2, ensure_ascii=False))
                                 print(f"Successfully saved baseline schedule to {CURRENT_WEEKS_FILE}")
                            except Exception as e:
                                 print(f"\nError saving baseline schedule to {CURRENT_WEEKS_FILE}: {e}")
                        else:
                            # Compare with loaded_data
                            if response_data == loaded_data:
                                print(f"No schedule changes detected compared to '{CURRENT_WEEKS_FILE}'. File remains unchanged.")
                            else:
                                print(f"Schedule changes detected. Updating '{CURRENT_WEEKS_FILE}'.")
                                try:
                                    async with aiofiles.open(CURRENT_WEEKS_FILE, "w", encoding='utf-8') as f:
                                        await f.write(json.dumps(response_data, indent=2, ensure_ascii=False))
                                    print(f"Successfully updated schedule in {CURRENT_WEEKS_FILE}")
                                except Exception as e:
                                    print(f"\nError updating schedule in {CURRENT_WEEKS_FILE}: {e}")
                    else: # Original diff mode: save to specific file
                        try:
                            async with aiofiles.open(output_filename, "w", encoding='utf-8') as f:
                                await f.write(json.dumps(response_data, indent=2, ensure_ascii=False))
                            print(f"\nAPI diff response saved to {output_filename}")
                        except Exception as e:
                            print(f"\nError saving API diff response to {output_filename}: {e}")

                except json.JSONDecodeError:
                    print("\nError: Could not decode JSON response from API.")
                    print("Response Text:", response.text)
            elif response.status_code == 401:
                # Check for expired cookies error code
                try:
                    data = response.json()
                    if data.get("error_code") == "COOKIES_EXPIRED":
                        print("Session expired. Attempting automatic refresh...")
                        # Need student_id for refresh, load it if not already available
                        current_student_id, _, _ = await load_data()
                        if not current_student_id:
                            print("No student_id found for refresh.")
                            return
                        success = await perform_session_refresh(current_student_id)
                        if success:
                            print("Refresh successful. Retrying API call...")
                            _, _, new_access_code = await load_data()
                            if new_access_code:
                                # Retry with the original endpoint and mode
                                await make_api_call(new_access_code, original_endpoint, current_student_id, fetch_full_schedule)
                            else:
                                print("Could not load new access code after refresh.")
                        else:
                            print("Automatic refresh failed. Please run with --refresh manually.")
                        return # Exit after handling refresh attempt
                except Exception as e:
                    print(f"Error processing 401 response: {e}") # Log potential JSON errors etc.
                    pass # Fall through to generic 401 message if parsing fails
                print("\nAPI request failed with 401 Unauthorized.")
                print("Response Text:", response.text)
            else:
                print(f"\nAPI request failed with status code {response.status_code}.")
                print("Response Text:", response.text)

    except httpx.RequestError as exc:
        print(f"\nAn error occurred while requesting {exc.request.url!r}: {exc}")
    except httpx.HTTPStatusError as exc:
        print(f"\nError response {exc.response.status_code} while requesting {exc.request.url!r}.")
        print("Response Text:", exc.response.text)
    except Exception as e:
        print(f"\nAn unexpected error occurred during API call: {e}")

# --- Main CLI ---

async def main():
    """Main function to manage Glasir authentication and API testing."""
    parser = argparse.ArgumentParser(
        description="Glasir Auth Tool: Manage authentication and test Glasir API endpoints."
    )
    parser.add_argument(
        "--force-initial-sync",
        action="store_true",
        help="Force a new login and initial sync, ignoring any saved data."
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh the session (get new cookies and access code)."
    )
    parser.add_argument(
        "--test-all",
        action="store_true",
        help="Test all endpoints (week/0, weeks/all, weeks/current_forward) sequentially."
    )
    args = parser.parse_args()

    # Dependency check
    try:
        import aiofiles
    except ImportError:
        print("Error: 'aiofiles' package is required. Please install it (`pip install aiofiles`)")
        return

    # --- Session Refresh Flow ---
    if args.refresh:
        student_id, _, _ = await load_data()
        if not student_id:
            print("No student_id found. Cannot refresh session.")
            return
        success = await perform_session_refresh(student_id)
        print("Session refresh completed." if success else "Session refresh failed.")
        return

    # --- Initial Sync Flow ---
    student_id = None
    cookies = None
    access_code = None

    if args.force_initial_sync:
        print("--force-initial-sync specified. Skipping saved data and initiating Playwright login + initial sync...")
        student_id, cookies, access_code = await perform_playwright_login_and_initial_sync()
    else:
        print("Checking for existing authentication data...")
        student_id, cookies, access_code = await load_data()
        if all([student_id, cookies, access_code]):
            print("Existing data found:")
            print(f"  Student ID: {student_id}")
            print(f"  Cookies: Loaded ({len(cookies) if isinstance(cookies, list) else 'Invalid Format'})")
            print(f"  Access Code: {access_code[:8]}... (truncated)")
            print("Using existing data.")
        else:
            print("Existing data incomplete or not found. Starting Playwright login + initial sync...")
            student_id, cookies, access_code = await perform_playwright_login_and_initial_sync()

    if not all([student_id, cookies, access_code]):
        print("Failed to obtain authentication data via Playwright and initial sync. Exiting.")
        return

    # --- Endpoint Selection or Testing ---
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

        for endpoint in endpoints_to_call:
            print(f"\n--- Calling Endpoint: {endpoint} ---")
            await make_api_call(access_code, endpoint, student_id) # Always diff mode now
            if endpoint != endpoints_to_call[-1]:
                print("\nWaiting a moment before next test...")
                await asyncio.sleep(2)
    else:
        # --- Interactive Endpoint Selection Flow (Diff Mode) ---
        endpoints_to_call = []
        print("\nSelect the API endpoint to call (Diff Mode):")
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

        # --- API Call(s) for Interactive Mode ---
        if not endpoints_to_call:
            print("No endpoint selected. Exiting.")
        else:
            for endpoint in endpoints_to_call:
                print(f"\n--- Calling Endpoint: {endpoint} ---")
                await make_api_call(access_code, endpoint, student_id) # Always diff mode now

    print("\nScript finished.")

if __name__ == "__main__":
    asyncio.run(main())