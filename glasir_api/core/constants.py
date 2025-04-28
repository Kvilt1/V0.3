# glasir_api/core/constants.py

# --- API Endpoints ---
GLASIR_BASE_URL = "https://tg.glasir.fo"
# Specific endpoint for the main timetable page (adjust if needed)
GLASIR_TIMETABLE_URL = f"{GLASIR_BASE_URL}/132n/"
# Note: Other endpoints like /i/teachers.asp, /i/udvalg.asp, /i/note.asp
# are used directly in the client/extractor but could be defined here if preferred.

# --- HTTP Headers ---
# Default headers for making requests, mimicking a browser
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Content-Type": "application/x-www-form-urlencoded", # Common for Glasir POST requests
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    # Add other headers like 'Referer' or 'Accept-Language' if necessary
}

# --- Parsing Constants ---
# Mapping from Faroese day names found in HTML to English standard names
DAY_NAME_MAPPING = {
    "Mánadagur": "Monday",
    "Týsdagur": "Tuesday",
    "Mikudagur": "Wednesday",
    "Hósdagur": "Thursday",
    "Fríggjadagur": "Friday",
    "Leygardagur": "Saturday", # Included for completeness, may not appear in timetable
    "Sunnudagur": "Sunday",   # Included for completeness, may not appear in timetable
}

# CSS classes used in the timetable HTML to indicate a cancelled lesson
# These might need updating if the website changes.
CANCELLED_CLASS_INDICATORS = [
    "lektionslinje_lesson1", # These seem like specific cancellation types
    "lektionslinje_lesson2",
    "lektionslinje_lesson3",
    "lektionslinje_lesson4",
    "lektionslinje_lesson5",
    "lektionslinje_lesson7",
    "lektionslinje_lesson10",
    "lektionslinje_lessoncancelled", # Generic cancellation class
]

# --- Caching ---
# Time-to-live (TTL) in seconds for the teacher map cache
TEACHER_MAP_CACHE_TTL = 86400 # 24 hours

# Add other relevant constants below as needed, e.g., specific selectors if used frequently.