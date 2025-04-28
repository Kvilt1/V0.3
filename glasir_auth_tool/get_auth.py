# glasir_auth_tool/get_auth.py
# Requirements: playwright, httpx, aiofiles (pip install playwright httpx aiofiles)
#               Browser binaries (python -m playwright install)
import asyncio
import re
import json
import os
import argparse
from pathlib import Path
from playwright.async_api import async_playwright, Error as PlaywrightError
import httpx
import aiofiles # Import aiofiles

# --- Constants ---
SCRIPT_DIR = Path(__file__).parent.resolve()
USERNAME_FILE = SCRIPT_DIR / "username.txt"
COOKIES_FILE = SCRIPT_DIR / "cookies.json"
STUDENT_ID_FILE = SCRIPT_DIR / "student_id.txt"
# API_RESPONSE_FILE = SCRIPT_DIR / "api_response.json" # No longer a single constant file

# Regex to find the student GUID in the page content
_RE_GUID = re.compile(
    r"[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}"
)

# --- Helper Functions ---

async def load_data():
    """Loads existing authentication data from files."""
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
                cookies = json.loads(await f.read()) # Load as JSON object
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
    """Saves authentication data to files."""
    try:
        async with aiofiles.open(USERNAME_FILE, "w") as f:
            await f.write(username)
    except Exception as e:
        print(f"Error saving username: {e}")

    try:
        async with aiofiles.open(COOKIES_FILE, "w") as f:
            await f.write(json.dumps(cookies, indent=2)) # Save as JSON object
    except Exception as e:
        print(f"Error saving cookies: {e}")

    try:
        async with aiofiles.open(STUDENT_ID_FILE, "w") as f:
            await f.write(student_id)
    except Exception as e:
        print(f"Error saving student ID: {e}")

async def perform_playwright_login():
    """Handles the Playwright login process and data extraction."""
    username = None
    cookies = None
    student_id = None

    async with async_playwright() as p:
        browser = None
        try:
            # --- User Input ---
            username_input = input("Please enter your Glasir username: ").strip()
            if not username_input:
                print("Username cannot be empty. Exiting.")
                return None, None, None # Indicate failure

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

            cookies = await context.cookies() # Get cookies as list of dicts
            content = await page.content()
            guid_match = _RE_GUID.search(content)
            student_id = guid_match.group(0).strip() if guid_match else None

            if cookies and student_id:
                print("Playwright login and data extraction successful.")
                username = username_input # Use the username provided by the user
                await save_data(username, cookies, student_id) # Save the extracted data
            else:
                print("Error: Could not extract cookies or student ID after login.")
                return None, None, None # Indicate failure

        except PlaywrightError as e:
            print(f"\nAn error occurred during Playwright operation: {e}")
            return None, None, None # Indicate failure
        except Exception as e:
            print(f"\nAn unexpected error occurred during Playwright login: {e}")
            return None, None, None # Indicate failure
        finally:
            if browser:
                await browser.close()
            print("Browser closed.")

    return username, cookies, student_id

async def make_api_call(username: str, cookies: list, student_id: str, endpoint: str):
    """Makes the API call to the specified endpoint using the provided auth data."""
    if not all([username, cookies, student_id]):
        print("Missing data for API call. Skipping.")
        return

    print("\n" + "="*50)
    print("Attempting API Call...")
    print("="*50)

    # Convert cookies list of dicts to header string
    cookie_string = "; ".join([f"{c['name']}={c['value']}" for c in cookies])

    # Construct API URL based on the chosen endpoint
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
                    # --- Save API Response ---
                    try:
                        async with aiofiles.open(output_filename, "w", encoding='utf-8') as f:
                            # Add ensure_ascii=False to prevent escaping non-ASCII characters
                            await f.write(json.dumps(response_data, indent=2, ensure_ascii=False))
                        print(f"\nAPI response saved to {output_filename}")
                    except Exception as e:
                        print(f"\nError saving API response to {output_filename}: {e}")
                    # --- End Save API Response ---
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
    """Main function to get auth data and make API call."""

    # --- Argument Parsing ---
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
    cookies = None # Initialize to None
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
            # Check if cookies is a list before getting len
            print(f"  Cookies: Loaded ({len(cookies) if isinstance(cookies, list) else 'Invalid Format'})")
            print(f"  Student ID: {student_id}")
            print("Using existing data.")
        else:
            print("Existing data incomplete or not found. Starting Playwright login...")
            username, cookies, student_id = await perform_playwright_login()

    # Check if login (forced or fallback) was successful
    if not all([username, cookies, student_id]):
            print("Failed to obtain authentication data via Playwright. Exiting.")
            return # Exit if Playwright failed

    # --- Endpoint Selection or Testing ---
    endpoints_to_call = []
    if args.test_all:
        print("\n--test-all specified. Testing all endpoints (will prompt for count)...")
        # Prompt for count even in test-all mode for the forward endpoint
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
        # Interactive Selection
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
                            return # Exit if count input is cancelled
                    break # Exit outer loop once count is obtained
                else:
                    print("Invalid choice. Please enter 1, 2, 3, or 4.")
            except EOFError: # Handle Ctrl+D or similar
                print("\nOperation cancelled by user.")
                return
            except KeyboardInterrupt: # Handle Ctrl+C
                print("\nOperation cancelled by user.")
                return

    # --- API Call(s) ---
    if not endpoints_to_call:
        print("No endpoint selected or specified. Exiting.")
    else:
        for endpoint in endpoints_to_call:
            print(f"\n--- Calling Endpoint: {endpoint} ---")
            await make_api_call(username, cookies, student_id, endpoint)
            if args.test_all and endpoint != endpoints_to_call[-1]:
                print("\nWaiting a moment before next test...")
                await asyncio.sleep(2) # Brief pause between tests

    print("\nScript finished.")


if __name__ == "__main__":
    # Add the directory containing this script to sys.path if needed,
    # although it's generally better to run scripts as modules if imports become complex.
    # import sys
    # sys.path.append(str(SCRIPT_DIR))
    asyncio.run(main())