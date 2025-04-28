# glasir_api/core/session.py
import logging
import re
from typing import Dict, Optional

# Basic logging setup
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(name)s - %(message)s')
log = logging.getLogger(__name__)

# Regular expressions to find the 'lname' parameter in different HTML contexts
# Order might matter if multiple patterns could match; prioritize more specific ones if needed.
LNAME_PATTERNS = [
    re.compile(r"lname=([^&\"'\s]+)"), # Common case in URLs or simple assignments
    re.compile(r"xmlhttp\.send\(\"[^\"]*lname=([^&\"'\s]+)\""), # Inside an xmlhttp.send call
    re.compile(r"MyUpdate\('[^']*','[^']*','[^']*',\d+,(\d+)\)"), # Specific JS function call pattern (assuming the last number is lname)
    re.compile(r"name=['\"]lname['\"]\s*value=['\"]([^'\"]+)['\"]"), # Inside an input tag
]

def extract_session_params_from_html(html: str) -> Optional[str]:
    """
    Extracts the 'lname' session parameter from HTML content.

    This parameter is often required for subsequent API calls within the same session.

    Args:
        html: The HTML content string (usually from the main timetable page).

    Returns:
        The extracted 'lname' string value, or None if it cannot be found.
    """
    lname: Optional[str] = None
    log.debug("Attempting to extract 'lname' session parameter from HTML.")

    # Iterate through predefined regex patterns to find 'lname'
    for pattern in LNAME_PATTERNS:
        match = pattern.search(html)
        if match:
            raw_lname = match.group(1) # Extract the captured group
            # Check if the extracted value contains a comma and strip if necessary
            if ',' in raw_lname:
                lname = raw_lname.split(',')[0]
                log.info(f"Successfully extracted raw 'lname': {raw_lname}, using modified 'lname': {lname} (pattern: {pattern.pattern})")
            else:
                lname = raw_lname
                log.info(f"Successfully extracted 'lname': {lname} using pattern: {pattern.pattern}")
            break # Stop searching once found

    if not lname:
        log.warning("Could not extract 'lname' session parameter from the provided HTML.")

    # Return the potentially modified lname string, or None
    return lname