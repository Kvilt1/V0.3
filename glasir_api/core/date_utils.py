# glasir_api/core/date_utils.py
import logging
import re
from datetime import datetime
from functools import lru_cache
from typing import Dict, Optional, Tuple

# Basic logging setup
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(name)s - %(message)s')
log = logging.getLogger(__name__)

# --- Regular Expressions for Date Parsing ---
# Matches DD.MM.YYYY format
PERIOD_DATE_FULL = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")
# Matches DD.MM format (assumes current year if year not specified)
PERIOD_DATE_SHORT = re.compile(r"(\d{1,2})\.(\d{1,2})")
# Matches YYYY-MM-DD format (ISO standard)
HYPHEN_DATE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
# Matches DD/MM format (assumes current year if year not specified)
SLASH_DATE_SHORT = re.compile(r"(\d{1,2})/(\d{1,2})")
# Matches DD/MM-YYYY format (e.g., "24/3-2025")
SLASH_DATE_WITH_YEAR = re.compile(r"(\d{1,2})/(\d{1,2})-(\d{4})")


@lru_cache(maxsize=256) # Cache results for frequently parsed dates
def parse_date(date_str: str, year: Optional[int] = None) -> Optional[Dict[str, str]]:
    """
    Parses a date string in various known formats into its components.

    Supports formats: DD.MM.YYYY, DD.MM, YYYY-MM-DD, DD/MM, DD/MM-YYYY.
    If year is not provided in the string (DD.MM, DD/MM), it uses the
    provided 'year' argument or defaults to the current system year.

    Args:
        date_str: The date string to parse.
        year: Optional integer year to assume if not present in date_str.

    Returns:
        A dictionary {'day': DD, 'month': MM, 'year': YYYY} or None if parsing fails.
    """
    if not date_str or not isinstance(date_str, str):
        log.debug(f"Invalid input for parse_date: {date_str}")
        return None

    # Determine the default year if not provided
    default_year = year if year is not None else datetime.now().year
    log.debug(f"Parsing date string: '{date_str}' with default year: {default_year}")

    # Try matching different formats
    match = PERIOD_DATE_FULL.match(date_str)
    if match:
        day, month, yr = match.groups()
        log.debug(f"Matched PERIOD_DATE_FULL: d={day}, m={month}, y={yr}")
        return {"day": day.zfill(2), "month": month.zfill(2), "year": yr}

    match = PERIOD_DATE_SHORT.match(date_str)
    if match:
        day, month = match.groups()
        log.debug(f"Matched PERIOD_DATE_SHORT: d={day}, m={month}, using year={default_year}")
        return {"day": day.zfill(2), "month": month.zfill(2), "year": str(default_year)}

    match = HYPHEN_DATE.match(date_str)
    if match:
        yr, month, day = match.groups()
        log.debug(f"Matched HYPHEN_DATE: y={yr}, m={month}, d={day}")
        return {"day": day.zfill(2), "month": month.zfill(2), "year": yr}

    match = SLASH_DATE_SHORT.match(date_str)
    if match:
        day, month = match.groups() # Assuming DD/MM (European)
        log.debug(f"Matched SLASH_DATE_SHORT: d={day}, m={month}, using year={default_year}")
        return {"day": day.zfill(2), "month": month.zfill(2), "year": str(default_year)}

    match = SLASH_DATE_WITH_YEAR.match(date_str)
    if match:
        day, month, yr = match.groups()
        log.debug(f"Matched SLASH_DATE_WITH_YEAR: d={day}, m={month}, y={yr}")
        return {"day": day.zfill(2), "month": month.zfill(2), "year": yr}

    # If no patterns matched
    log.warning(f"Could not parse date string: '{date_str}' with any known format.")
    return None


def format_date(
    date_dict: Optional[Dict[str, str]], output_format: str = "iso"
) -> Optional[str]:
    """
    Formats a date dictionary into a specified string format.

    Args:
        date_dict: A dictionary with 'year', 'month', 'day' keys.
        output_format: The desired output format ('iso', 'hyphen', 'period', 'slash').
                       'iso' and 'hyphen' both produce YYYY-MM-DD.

    Returns:
        The formatted date string or None if input is invalid.
    """
    if not date_dict:
        return None
    required_keys = ["year", "month", "day"]
    if not all(key in date_dict for key in required_keys):
        log.warning(f"Invalid date_dict for formatting: {date_dict}")
        return None

    # Ensure components are strings for formatting
    year = str(date_dict["year"])
    month = str(date_dict["month"]).zfill(2)
    day = str(date_dict["day"]).zfill(2)

    if output_format in ["iso", "hyphen"]:
        return f"{year}-{month}-{day}"
    elif output_format == "period":
        return f"{day}.{month}.{year}"
    elif output_format == "slash":
        return f"{day}/{month}/{year}"
    # Add other formats if needed
    # elif output_format == "filename": # Example from original code
    #     return f"{month}.{day}"
    else:
        log.error(f"Unsupported output format requested: {output_format}")
        return None


@lru_cache(maxsize=128) # Cache conversion results
def convert_date_format(
    date_str: str, output_format: str = "iso", year: Optional[int] = None
) -> Optional[str]:
    """
    Convenience function to parse a date string and format it directly.

    Args:
        date_str: The input date string in a supported format.
        output_format: The desired output format (e.g., 'iso', 'period').
        year: Optional integer year to assume if not present in date_str.

    Returns:
        The date string in the target format, or None if parsing/formatting fails.
    """
    parsed = parse_date(date_str, year)
    if parsed:
        return format_date(parsed, output_format)
    return None


@lru_cache(maxsize=128) # Cache ISO conversion results
def to_iso_date(date_str: str, year: Optional[int] = None) -> Optional[str]:
    """
    Converts a date string from various formats directly to ISO format (YYYY-MM-DD).

    Args:
        date_str: The input date string.
        year: Optional integer year to assume if not present in date_str.

    Returns:
        The date string in ISO format, or None if parsing fails.
    """
    if not date_str:
        return None
    # Directly use convert_date_format with 'iso' as the target
    return convert_date_format(date_str, "iso", year)


def parse_time_range(time_range: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parses a time range string (e.g., "08:10-09:40") into start and end times.

    Args:
        time_range: The time range string.

    Returns:
        A tuple (start_time, end_time). Returns (None, None) if parsing fails.
    """
    if not time_range or not isinstance(time_range, str) or "-" not in time_range:
        log.debug(f"Invalid time range format for parsing: '{time_range}'")
        return None, None

    parts = time_range.split("-")
    if len(parts) == 2:
        start_time = parts[0].strip()
        end_time = parts[1].strip()
        # Basic validation for HH:MM format could be added here if needed
        # Example: re.match(r'^\d{2}:\d{2}$', start_time)
        return start_time, end_time
    else:
        log.warning(f"Could not split time range '{time_range}' into two parts.")
        return None, None