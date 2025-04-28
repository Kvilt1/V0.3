# glasir_api/core/formatting.py
import logging
from functools import lru_cache
from typing import Optional

# Basic logging setup
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(name)s - %(message)s')
log = logging.getLogger(__name__)

@lru_cache(maxsize=128) # Cache results for efficiency
def format_academic_year(year_code: Optional[str]) -> Optional[str]:
    """
    Formats a 4-digit year code (e.g., '2425') into an academic year string ('2024-2025').

    Args:
        year_code: The 4-digit year code string.

    Returns:
        The formatted academic year string ('YYYY-YYYY'),
        or the original code if input is None, not 4 digits, not numeric,
        or doesn't represent consecutive years.
    """
    if not year_code:
        return None

    if len(year_code) == 4 and year_code.isdigit():
        try:
            start_year = int(f"20{year_code[:2]}")
            end_year = int(f"20{year_code[2:]}")
            # Validate that the end year is exactly one greater than the start year
            if end_year == start_year + 1:
                return f"{start_year}-{end_year}"
            else:
                log.warning(f"Year code '{year_code}' does not represent consecutive years. Returning original.")
                return year_code
        except ValueError:
            log.warning(f"Could not parse year code '{year_code}' as integer parts. Returning original.")
            return year_code
    else:
        log.debug(f"Year code '{year_code}' is not 4 digits or not numeric. Returning original.")
        return year_code