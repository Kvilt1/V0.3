
# glasir_api/core/parsers.py
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from dataclasses import dataclass, field # Add dataclass import
from typing import Any, Dict, List, Optional, Tuple # Moved import here

# --- Dataclasses ---

@dataclass
class ParseResult:
    """Holds the result of parsing HTML content."""
    status: str # e.g., 'Success', 'ParseFailed', 'StructureError'
    data: Optional[Dict[str, Any]] = None # Parsed data (e.g., events, week_info)
    warnings: List[str] = field(default_factory=list)
    error_message: Optional[str] = None

from bs4 import BeautifulSoup, Tag

# Use relative imports for components within the 'glasir_api.core' package
from .constants import CANCELLED_CLASS_INDICATORS, DAY_NAME_MAPPING
from .date_utils import to_iso_date, parse_time_range # Added parse_time_range
from .formatting import format_academic_year
from ..models.models import Event # Import the Event model using relative path

# Basic logging setup
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(name)s - %(message)s')
log = logging.getLogger(__name__)

class GlasirParserError(Exception):
    """Base exception for parser-related errors."""
    def __init__(self, message: str, html_content: Optional[str] = None):
        super().__init__(message)
        # Optionally store the problematic HTML for debugging
        self.html_content = html_content

    def __str__(self) -> str:
        # Optionally add more context to the error message if needed
        return super().__str__()
# --- Homework Parser ---
_RE_SPACE_BEFORE_NEWLINE = re.compile(r" +\n")
_RE_SPACE_AFTER_NEWLINE = re.compile(r"\n +")

def parse_homework_html(html: str) -> Dict[str, str]:
    """
    Parses the HTML content of a homework/note page to extract the homework text
    associated with a lesson ID.

    Args:
        html: The HTML content string.

    Returns:
        A dictionary mapping the lesson ID (str) to the extracted homework text (str).
        Returns an empty dictionary if the lesson ID or homework text cannot be found.
    """
    result = {}
    lesson_id = None # Initialize lesson_id for error logging
    try:
        soup = BeautifulSoup(html, "lxml") # Use lxml for potentially faster parsing
        # Find the hidden input field containing the lesson ID
        lesson_id_input = soup.select_one(
            'input[type="hidden"][id^="LektionsID"]'
        )
        if not lesson_id_input:
            log.warning("Could not find LektionsID input field in homework HTML.")
            return result

        lesson_id = lesson_id_input.get("value")
        if not lesson_id:
            log.warning("LektionsID input field found, but has no value.")
            return result

        # Find the 'Heimaarbeiði' (Homework) header
        homework_header = soup.find("b", string="Heimaarbeiði")
        if not homework_header:
            # It's common for lessons to have no homework, so log as debug
            log.debug(
                f"No 'Heimaarbeiði' header found for lesson {lesson_id}. Assuming no homework."
            )
            return result # No homework section found

        # Find the parent <p> tag containing the homework text
        homework_p = homework_header.find_parent("p")
        if not homework_p:
            log.warning(
                f"Found 'Heimaarbeiði' header but could not find its parent <p> tag for lesson {lesson_id}."
            )
            return result

        # --- Internal function to process nodes recursively into Markdown ---
        def process_node(
            node, is_first_level=False, header_skipped=False, first_br_skipped=False
        ):
            """Recursively processes HTML nodes into Markdown-like text parts."""
            parts = []
            current_header_skipped = header_skipped
            current_first_br_skipped = first_br_skipped

            if isinstance(node, str):
                # Append text nodes directly
                parts.append(node)
            elif isinstance(node, Tag):
                # Skip the "Heimaarbeiði" header itself at the top level
                if (
                    is_first_level
                    and not current_header_skipped
                    and node.name == "b"
                    and node.get_text(strip=True) == "Heimaarbeiði"
                ):
                    return [], True, current_first_br_skipped # Mark header as skipped

                # Skip the first <br> immediately after the header at the top level
                if (
                    is_first_level
                    and current_header_skipped
                    and not current_first_br_skipped
                    and node.name == "br"
                ):
                    return [], current_header_skipped, True # Mark first <br> as skipped

                # Convert tags to Markdown or process children
                if node.name == "br":
                    parts.append("\n")
                elif node.name == "b": # Bold
                    inner_parts = []
                    temp_header_skipped = current_header_skipped
                    temp_br_skipped = current_first_br_skipped
                    for child in node.children:
                        child_res = process_node(
                            child, False, temp_header_skipped, temp_br_skipped
                        )
                        inner_parts.extend(child_res[0])
                        # Propagate skipped status from children
                        temp_header_skipped = child_res[1]
                        temp_br_skipped = child_res[2]
                    inner = "".join(inner_parts).strip()
                    if inner: parts.append(f"**{inner}**")
                    # Update main skipped status based on processing children
                    current_header_skipped = temp_header_skipped
                    current_first_br_skipped = temp_br_skipped
                elif node.name == "i": # Italic
                    inner_parts = []
                    temp_header_skipped = current_header_skipped
                    temp_br_skipped = current_first_br_skipped
                    for child in node.children:
                        child_res = process_node(
                            child, False, temp_header_skipped, temp_br_skipped
                        )
                        inner_parts.extend(child_res[0])
                        temp_header_skipped = child_res[1]
                        temp_br_skipped = child_res[2]
                    inner = "".join(inner_parts).strip()
                    if inner: parts.append(f"*{inner}*")
                    current_header_skipped = temp_header_skipped
                    current_first_br_skipped = temp_br_skipped
                else: # Process children of other tags
                    temp_header_skipped = current_header_skipped
                    temp_br_skipped = current_first_br_skipped
                    for child in node.children:
                        child_res = process_node(
                            child, False, temp_header_skipped, temp_br_skipped
                        )
                        parts.extend(child_res[0])
                        temp_header_skipped = child_res[1]
                        temp_br_skipped = child_res[2]
                    current_header_skipped = temp_header_skipped
                    current_first_br_skipped = temp_br_skipped


            return parts, current_header_skipped, current_first_br_skipped
        # --- End internal function ---

        markdown_parts = []
        final_header_skipped = False
        final_first_br_skipped = False
        # Process all direct children of the homework <p> tag
        for element in homework_p.contents:
            processed_parts, final_header_skipped, final_first_br_skipped = (
                process_node(
                    element, True, final_header_skipped, final_first_br_skipped
                )
            )
            markdown_parts.extend(processed_parts)

        # Join parts and clean up whitespace
        homework_text = "".join(markdown_parts)
        homework_text = _RE_SPACE_BEFORE_NEWLINE.sub("\n", homework_text)
        homework_text = _RE_SPACE_AFTER_NEWLINE.sub("\n", homework_text)
        homework_text = homework_text.strip()

        if homework_text:
            result[lesson_id] = homework_text
            log.debug(f"Extracted homework for lesson {lesson_id}")
        else:
            # Log if structure was found but no text followed
            log.debug(
                f"Found 'Heimaarbeiði' structure but no subsequent text for lesson {lesson_id}."
            )

    except Exception as e:
        log.error(f"Error parsing homework HTML for lesson ID '{lesson_id if lesson_id else 'unknown'}': {e}", exc_info=True)

    return result

# --- Teacher Parser ---
_RE_TEACHER_WITH_LINK = re.compile(r"([^<>]+?)\s*\(\s*<a[^>]*?>([A-Z]{2,4})</a>\s*\)")
_RE_TEACHER_NO_LINK = re.compile(r"([^<>]+?)\s*\(\s*([A-Z]{2,4})\s*\)")

def parse_teacher_html(html: str) -> Dict[str, str]:
    """
    Parses HTML containing teacher information (typically from a dropdown or list)
    to create a mapping from teacher initials to their full names.

    Args:
        html: The HTML content string.

    Returns:
        A dictionary mapping teacher initials (str) to full names (str).
    """
    teacher_map = {}
    try:
        soup = BeautifulSoup(html, "lxml")
        # First, try parsing a <select> element (common for teacher lists)
        select_tag = soup.select_one("select")
        if select_tag:
            for option in select_tag.select("option"):
                initials = option.get("value")
                full_name = option.get_text(strip=True)
                # Ignore placeholder options (like value="-1")
                if initials and initials != "-1" and full_name:
                    teacher_map[initials] = full_name
            log.debug(f"Parsed {len(teacher_map)} teachers from <select> tag.")

        # If no teachers found in <select>, try regex patterns as a fallback
        if not teacher_map:
            log.debug("No <select> tag found or no teachers parsed, trying regex fallback.")
            compiled_patterns = [_RE_TEACHER_WITH_LINK, _RE_TEACHER_NO_LINK]
            for compiled_pattern in compiled_patterns:
                matches = compiled_pattern.findall(html)
                for match in matches:
                    # Ensure both name and initials were captured
                    if len(match) == 2:
                        full_name = match[0].strip()
                        initials = match[1].strip()
                        # Add only if not already found (prefer <select> results if any)
                        if initials and full_name and initials not in teacher_map:
                            teacher_map[initials] = full_name
            log.debug(f"Parsed {len(teacher_map)} teachers using regex fallback.")

    except Exception as e:
        log.error(f"Error parsing teacher HTML: {e}", exc_info=True)

    if not teacher_map:
        log.warning("Could not parse any teacher information from the provided HTML.")

    return teacher_map


# --- Result Structures ---
# Removed ParseResult dataclass as it's no longer used by parse_week_html


# --- Timetable Parser ---
# Regex for student info (Name, Class) - made slightly more robust
# Regex updated to capture name potentially containing commas, stopping before the last comma,
# and capturing the class after the last comma.
# Regex refined: Capture name (non-greedy) and class after the colon and comma. Applied to the text content *after* finding the correct TD.
# Regex refined: Capture name (non-greedy) and class (alphanumeric) directly after the prefix. Applied to the full text content of the TD.
# Regex refined: Capture name (non-greedy) and class (allowing spaces) after the prefix. Applied to the full text content of the TD.
_RE_STUDENT_INFO = re.compile(
    r"N[æ&aelig;]mingatímatalva\s*:\s*(.*?)\s*,\s*([\w\s]+)\b"
) # Example: "Næmingatímatalva : Rókur Kvilt Meitilberg , 22y" -> ('Rókur Kvilt Meitilberg', '22y')
_RE_DATE_RANGE = re.compile(
    r"(\d{1,2}\.\d{1,2}\.\d{4})\s*-\s*(\d{1,2}\.\d{1,2}\.\d{4})"
)
_RE_DAY_DATE = re.compile(r"(\w+)\s+(\d{1,2}/\d{1,2})") # Faroese day name + DD/MM

def get_timeslot_info(start_col_index: int) -> Dict[str, str]:
    """
    Determines the time slot number and time range based on the starting
    column index within the Glasir timetable HTML structure.

    Args:
        start_col_index: The starting column index (assumed 1-based) of the lesson cell.

    Returns:
        A dictionary with "slot" (str) and "time" (str, HH:MM-HH:MM).
        Returns "N/A" if the index doesn't match known slots.
    """
    # These ranges seem based on the original implementation's logic.
    # Verification against actual HTML structure is recommended.
    if 2 <= start_col_index <= 25:
        return {"slot": "1", "time": "08:10-09:40"}
    elif 26 <= start_col_index <= 50:
        return {"slot": "2", "time": "10:05-11:35"}
    elif 51 <= start_col_index <= 71:
        return {"slot": "3", "time": "12:10-13:40"}
    elif 72 <= start_col_index <= 90:
        return {"slot": "4", "time": "13:55-15:25"}
    elif 91 <= start_col_index <= 111:
        return {"slot": "5", "time": "15:30-17:00"}
    elif 112 <= start_col_index <= 131:
        return {"slot": "6", "time": "17:15-18:45"}
    else:
        log.warning(f"Unknown timeslot for start column index: {start_col_index}")
        return {"slot": "N/A", "time": "N/A"}

def parse_week_html(
    html_content: Optional[str], teacher_map: Optional[Dict[str, str]] = None
) -> List[Event]: # Return List[Event] directly
    """
    Parses the main timetable HTML page to extract individual lesson events.

    Args:
        html_content: The HTML content string of the timetable page, or None.
        teacher_map: An optional dictionary mapping teacher initials to full names.

    Returns:
        A list of Event objects parsed from the HTML. Returns an empty list if
        no events are found or if the HTML indicates no events for the week.

    Raises:
        GlasirParserError: If the input HTML is empty/None, if the main timetable
                           structure is missing or invalid, or if a critical error
                           occurs during parsing (e.g., failure to parse essential event data).
    """
    if not html_content or not html_content.strip(): # Check for None or effectively empty string
        log.warning("parse_week_html received None or empty HTML content.")
        # // TDD Anchor: Test parse failure with empty/None input
        raise GlasirParserError("Input HTML content is empty or invalid", html_content=html_content)

    teacher_map = teacher_map or {} # Ensure teacher_map is a dict
    warnings: List[str] = [] # Initialize warnings list (still useful for logging)
    # Removed student_info_dict and week_info_dict as they are not returned
    events_list: List[Event] = []
    homework_ids_list: List[str] = [] # Keep for internal logic if needed
    # Store parsed week/student info locally for inclusion in result data
    parsed_student_info = {}
    parsed_week_info = {} # Initialize parsed_week_info

    try:
        log.debug("Attempting to parse HTML using 'lxml'")
        soup = BeautifulSoup(html_content, "lxml")

        # --- Extract Student Info (Keep for logging/context if needed, but not returned) ---
        student_info_td = soup.find(lambda tag: tag.name == 'td' and 'Næmingatímatalva' in tag.get_text())
        student_name = None
        student_class = None
        if student_info_td:
            # Extract text more robustly, handling nested tags
            full_text = student_info_td.get_text(separator=' ', strip=True)
            # Attempt to match the refined regex on the full text
            student_info_match = _RE_STUDENT_INFO.search(full_text)
            if student_info_match:
                student_name = student_info_match.group(1).strip()
                # The class might have extra text after it (like '<'), remove potential trailing non-alphanumeric/space chars
                student_class_raw = student_info_match.group(2).strip()
                # Clean up class - remove anything after the expected pattern (e.g., '22y < table ...')
                class_match = re.match(r"([\w\s]+)", student_class_raw)
                student_class = class_match.group(1).strip() if class_match else student_class_raw

                parsed_student_info = {"studentName": student_name, "class": student_class} # Store parsed info using correct keys
                log.debug(f"Parsed student info (regex on full text): Name='{student_name}', Class='{student_class}'")
            else:
                 warnings.append(f"Regex failed to parse student info from TD text: '{full_text}'")
                 log.warning(f"Student info regex failed on text: '{full_text}'") # Log the text that failed
        else:
            warnings.append("Could not find TD containing 'Næmingatímatalva'.")
            log.warning("Could not find TD containing 'Næmingatímatalva'.")

        # Check if parsing succeeded and log warning if not
        if not student_name or not student_class:
             # Combine warnings if both methods failed
             if not student_info_td: # If TD wasn't found initially
                 pass # Warning already added
             elif not student_info_match: # If TD was found but regex failed
                 pass # Warning already added
             else: # Should not happen if regex matched, but defensively add warning
                 warnings.append("Failed to parse student name and/or class after finding TD.")
             log.warning("Failed to parse student name/class.") # Keep general warning

        # --- Extract Week Info ---
        # Prioritize parsing dates first to determine the correct ISO year and week
        iso_start_date = None
        iso_end_date = None
        iso_year = None
        iso_week_number = None

        date_range_match = _RE_DATE_RANGE.search(html_content)
        if date_range_match:
            start_date_str = date_range_match.group(1)
            end_date_str = date_range_match.group(2)
            iso_start_date = to_iso_date(start_date_str)
            iso_end_date = to_iso_date(end_date_str)

            if iso_start_date:
                parsed_week_info['startDate'] = iso_start_date
                try:
                    # Use isocalendar() to get the correct ISO year and week number
                    start_dt = datetime.strptime(iso_start_date, "%Y-%m-%d")
                    iso_calendar = start_dt.isocalendar()
                    iso_year = iso_calendar.year
                    iso_week_number = iso_calendar.week
                    parsed_week_info['year'] = iso_year
                    parsed_week_info['weekNumber'] = iso_week_number
                    log.debug(f"Derived ISO year={iso_year}, week={iso_week_number} from start date {iso_start_date}")
                except ValueError as e:
                    warnings.append(f"Could not parse ISO start date '{iso_start_date}' for isocalendar: {e}")
            else:
                warnings.append(f"Could not parse start date '{start_date_str}' to ISO format.")

            if iso_end_date:
                 parsed_week_info['endDate'] = iso_end_date
            else:
                 warnings.append(f"Could not parse end date '{end_date_str}' to ISO format.")
        else:
            warnings.append("Could not parse date range (DD.MM.YYYY - DD.MM.YYYY) from HTML.")
            # If date range fails, we cannot reliably determine week/year
            log.error("Critical failure: Could not parse date range to determine week/year.")
            # Consider returning ParseFailed here if date range is essential
            # return ParseResult(status='ParseFailed', error_message="Could not parse date range", warnings=warnings)


        # Attempt to parse week number from link text as a fallback/validation check (optional)
        week_link = soup.select_one("a.UgeKnapValgt")
        week_number_from_link = None
        if week_link:
            week_text = week_link.get_text(strip=True)
            if week_text.startswith("Vika "):
                try:
                    week_number_from_link = int(week_text.replace("Vika ", ""))
                    # Optionally validate against iso_week_number if both were found
                    if iso_week_number is not None and week_number_from_link != iso_week_number:
                        warning_msg = f"Week number mismatch: Link text '{week_text}' ({week_number_from_link}) vs isocalendar ({iso_week_number}). Using isocalendar result."
                        warnings.append(warning_msg)
                        log.warning(warning_msg)
                    # If isocalendar failed but link parsing worked, maybe use it as fallback?
                    # elif iso_week_number is None:
                    #     parsed_week_info['weekNumber'] = week_number_from_link
                    #     warnings.append(f"Using week number {week_number_from_link} from link text as fallback.")

                except ValueError:
                    warnings.append(f"Could not parse week number from link text: '{week_text}'")
            else:
                warnings.append(f"Selected week link text format unexpected: '{week_text}'")
        else:
            warnings.append("Could not find selected week link (a.UgeKnapValgt) in HTML.")

        # Ensure essential week info was parsed before proceeding
        if 'year' not in parsed_week_info or 'weekNumber' not in parsed_week_info:
             log.error("Failed to determine essential week info (year/weekNumber). Cannot proceed reliably.")
             # Return ParseFailed if year/weekNumber are critical
             return ParseResult(status='ParseFailed', error_message="Failed to determine year/weekNumber", warnings=warnings)


        log.debug(f"Final Parsed week info (for context): {parsed_week_info}")

        # --- Extract Events from Table ---
        table = soup.select_one("table.time_8_16")
        if not table:
             log.warning("Timetable table (table.time_8_16) not found in HTML.")
             possible_no_events_tags = soup.select('p, div.alert, td.header')
             no_events_found_text = None
             for tag in possible_no_events_tags:
                 text = tag.get_text(strip=True).lower()
                 if "ongi skeið" in text or "frídagur" in text or "eingin undirvísing" in text:
                     no_events_found_text = tag.get_text(strip=True)
                     log.info(f"Found explicit 'no events' message: '{no_events_found_text}'")
                     break

             if no_events_found_text:
                 log.info("Returning successful ParseResult (no events) due to explicit message.")
                 return ParseResult(status='Success', data={'events': [], 'week_info': parsed_week_info, 'student_info': parsed_student_info}, warnings=warnings)
             else:
                 error_msg = "Could not find main schedule container (table.time_8_16) and no explicit 'no events' message detected."
                 log.error(error_msg)
                 # Return ParseResult indicating failure
                 return ParseResult(status='ParseFailed', error_message=error_msg, warnings=warnings)

        log.debug(f"Successfully located timetable table using 'table.time_8_16'.")

        rows = table.select("tr")
        current_day_name_fo: Optional[str] = None
        current_date_part: Optional[str] = None

        for row_index, row in enumerate(rows):
            cells = row.select("td")
            if not cells: continue

            first_cell = cells[0]
            first_cell_text = first_cell.get_text(separator=" ", strip=True)
            day_match = _RE_DAY_DATE.match(first_cell_text)
            is_day_header = "lektionslinje_1" in first_cell.get("class", []) or "lektionslinje_1_aktuel" in first_cell.get("class", [])

            if is_day_header:
                # Only attempt regex match if the text is not empty
                if first_cell_text and day_match:
                    current_day_name_fo = day_match.group(1)
                    current_date_part = day_match.group(2)
                    log.debug(f"Row {row_index}: Set day context: Day='{current_day_name_fo}', Date='{current_date_part}'")
                else:
                    # Log warning if it's a header but regex failed (or text was empty)
                    warning_msg = f"Row {row_index}: Day header identified, but regex failed or text empty: '{first_cell_text}'. Resetting day context."
                    log.warning(warning_msg)
                    warnings.append(warning_msg)
                    current_day_name_fo = None
                    current_date_part = None
            # Removed the 'elif not day_match' as the logic is handled within 'if is_day_header'

            # This check remains to ensure context is valid before processing cells
            if not current_day_name_fo or not current_date_part:
                 log.debug(f"Skipping row {row_index} cell processing - invalid day context.")
                 continue

            log.debug(f"Processing row index {row_index} for day: {current_day_name_fo}")
            current_col_index = 1
            day_en = DAY_NAME_MAPPING.get(current_day_name_fo, current_day_name_fo)

            for cell_index, cell in enumerate(cells):
                 if cell_index == 0:
                      try: colspan = int(cells[0].get("colspan", 1))
                      except ValueError: colspan = 1
                      current_col_index += colspan
                      continue

                 try: colspan = int(cell.get("colspan", 1))
                 except (ValueError, TypeError):
                     warnings.append(f"Row {row_index}, Cell {cell_index}: Could not parse colspan '{cell.get('colspan')}'")
                     colspan = 1

                 classes = cell.get("class", [])
                 is_lesson = False
                 lesson_class_pattern = re.compile(r"lektionslinje_lesson\d+")
                 if isinstance(classes, list):
                     for cls in classes:
                          if lesson_class_pattern.match(cls): is_lesson = True; break
                 elif isinstance(classes, str):
                     if lesson_class_pattern.match(classes): is_lesson = True

                 is_cancelled = any(cls in CANCELLED_CLASS_INDICATORS for cls in classes if isinstance(cls, str))

                 if is_lesson:
                     a_tags = cell.select("a")
                     if len(a_tags) >= 3:
                         class_code_raw = a_tags[0].get_text(strip=True)
                         teacher_short = a_tags[1].get_text(strip=True)
                         room_raw = a_tags[2].get_text(strip=True)

                         # --- Parse Subject Code ---
                         # Regex to extract subject and level from the first part (e.g., "BV3" -> "BV", "3" or "MATB" -> "MAT", "B")
                         _RE_SUBJECT_LEVEL = re.compile(r"^([a-zA-Z]+)(\d*|[A-Z]?)$")
                         code_parts = class_code_raw.split("-")
                         subject_code = class_code_raw # Default
                         level = ""
                         year_code = ""
                         if code_parts:
                             # Handle specific "Várroynd" format
                             if code_parts[0] == "Várroynd" and len(code_parts) > 4:
                                 subject_code = f"{code_parts[0]}-{code_parts[1]}"
                                 level = code_parts[2]
                                 year_code = code_parts[4]
                             # Handle standard format like SUBJ-LVL-TEAM-YEAR
                             elif len(code_parts) > 3:
                                 subject_code = code_parts[0]
                                 level = code_parts[1]
                                 year_code = code_parts[3]
                             # Handle format like SUBJLEVEL-YEARCODE-CLASSLIKE (e.g., BV3-2425-22y)
                             elif len(code_parts) == 3:
                                 subject_level_match = _RE_SUBJECT_LEVEL.match(code_parts[0])
                                 if subject_level_match:
                                     subject_code = subject_level_match.group(1)
                                     level = subject_level_match.group(2) or "" # Assign level or empty string
                                 else:
                                     subject_code = code_parts[0] # Fallback if regex fails
                                     level = ""
                                 year_code = code_parts[1] # Year code is the second part
                                 # The third part (class-like) is ignored
                                 log.debug(f"Parsed subject format '{class_code_raw}' as SUBJLEVEL-YEARCODE-CLASSLIKE")
                             # Fallback if format is unexpected
                             else:
                                 warnings.append(f"Row {row_index}, Cell {cell_index}: Unexpected subject code format: {class_code_raw}")
                                 log.warning(f"Unexpected subject code format encountered: {class_code_raw}")

                         teacher_full = teacher_map.get(teacher_short, teacher_short)
                         location = room_raw.replace("st.", "").strip()

                         if colspan >= 90: time_info = {"slot": "All day", "time": "08:10-15:25"}
                         else: time_info = get_timeslot_info(current_col_index)

                         iso_date = None
                         # Use the iso_year derived earlier from isocalendar()
                         if current_date_part and iso_year:
                             iso_date = to_iso_date(current_date_part, iso_year)
                         elif current_date_part: warnings.append(f"Row {row_index}, Cell {cell_index}: Cannot determine ISO date for '{current_date_part}' - year missing.")

                         start_time, end_time = parse_time_range(time_info["time"])

                         lesson_id = None
                         lesson_span = cell.select_one('span[id^="MyWindow"][id$="Main"]')
                         if lesson_span and lesson_span.get("id"):
                             span_id = lesson_span["id"]
                             if len(span_id) > 12: lesson_id = span_id[8:-4]
                             else: warnings.append(f"Row {row_index}, Cell {cell_index}: Found lesson span with unexpected ID format: {span_id}")
                         else: warnings.append(f"Row {row_index}, Cell {cell_index}: Could not find lesson ID span for {subject_code} on {iso_date}")

                         has_homework_note = False
                         note_img = cell.select_one('input[type="image"][src*="note.gif"]')
                         if note_img:
                             has_homework_note = True
                             if lesson_id: homework_ids_list.append(lesson_id)
                             else: warnings.append(f"Row {row_index}, Cell {cell_index}: Homework note found, but no lessonId extracted for {subject_code} on {iso_date}")

                         # --- Assemble Event ---
                         try:
                             event_data = {
                                 "title": subject_code, "level": level, "year": format_academic_year(year_code),
                                 "date": iso_date, "dayOfWeek": day_en,
                                 "teacher": (teacher_full.split(" (")[0] if " (" in teacher_full else teacher_full),
                                 "teacherShort": teacher_short, "location": location,
                                 "timeSlot": time_info["slot"], "startTime": start_time, "endTime": end_time,
                                 "timeRange": time_info["time"], "cancelled": is_cancelled,
                                 "lessonId": lesson_id, "hasHomeworkNote": has_homework_note,
                                 "description": None,
                             }
                             # // TDD Anchor: Test parse with partial data warnings
                             # Raise error if critical data is missing (e.g., date, times) before creating Event
                             if not iso_date or not start_time or not end_time:
                                 raise ValueError(f"Missing critical date/time info (Date: {iso_date}, Start: {start_time}, End: {end_time})")

                             event = Event(**event_data)
                             events_list.append(event)
                         except Exception as event_err:
                             # // TDD Anchor: Test parse with partial data warnings (Raise error)
                             error_msg = f"Failed to assemble/validate event for cell {cell_index} ({subject_code} on {iso_date}): {event_err}"
                             log.error(f"      {error_msg}", exc_info=True)
                             # Instead of raising, append warning and continue if possible,
                             # or return ParseFailed if it's critical
                             warnings.append(error_msg)
                             # Decide if this error prevents further parsing or just skips the event
                             # For now, let's skip the event by not adding it to events_list

                     else: # Not enough <a> tags
                         warnings.append(f"Row {row_index}, Cell {cell_index}: Lesson cell identified, but found only {len(a_tags)} links. Skipping.")
                         log.warning(f"      Skipping lesson cell {cell_index} in row {row_index} due to insufficient links.")

                 # Advance column index regardless of whether it was a lesson or not
                 current_col_index += colspan

        # Log warnings collected during parsing
        if warnings:
            log.warning(f"Parsing completed with {len(warnings)} warnings:")
            for warn_msg in warnings:
                log.warning(f"  - {warn_msg}")

        # --- Return final list of events ---
        if events_list:
            log.info(f"Parsing finished. Extracted {len(events_list)} events.")
            return ParseResult(status='Success', data={'events': events_list, 'week_info': parsed_week_info, 'student_info': parsed_student_info}, warnings=warnings)
        else:
            log.info("Parsing finished. Valid structure found, but no events were extracted.")
            return ParseResult(status='Success', data={'events': [], 'week_info': parsed_week_info, 'student_info': parsed_student_info}, warnings=warnings)

    except (ImportError, AttributeError, TypeError, ValueError) as structure_err:
         # Catch errors suggesting the HTML structure was invalid or unexpected by BeautifulSoup/lxml
         msg = f"Invalid HTML structure or parsing error: {structure_err}"
         log.error(msg, exc_info=True)
         return ParseResult(status='StructureError', error_message=msg, warnings=warnings)
    except Exception as e:
        # Catch any other unexpected errors during parsing
        msg = f"An unexpected error occurred during parsing: {e}"
        log.error(msg, exc_info=True)
        return ParseResult(status='ParseFailed', error_message=msg, warnings=warnings)




# --- Homework Merging ---

def merge_homework_into_events(events: List[Event], homework_map: Dict[str, str]): # Keep List[Event]
    """
    Merges fetched homework text into the corresponding timetable events.

    Args:
        events: A list of event dictionaries parsed from the timetable.
        homework_map: A dictionary mapping lesson IDs (str) to homework text (str).
    """
    if not homework_map:
        log.debug("No homework map provided, skipping merge.")
        return # Nothing to merge

    merged_count = 0
    for event in events:
        # Access attributes directly on the Pydantic model instance
        lesson_id = event.lesson_id
        if lesson_id and lesson_id in homework_map:
            homework_text = homework_map[lesson_id]
            event.description = homework_text # Modify the Pydantic model instance
            log.debug(f"Merged homework for lesson ID {lesson_id} into event '{event.title}'")
            merged_count += 1
        elif lesson_id:
            # Log if homework was expected (note present) but not found in map
            if event.has_homework_note:
                log.debug(f"Homework note present for lesson ID {lesson_id}, but no text found in homework_map.")
            pass # Explicitly do nothing if homework is not found for a lesson ID

    log.info(f"Merged homework descriptions into {merged_count} events.")
# --- Available Weeks Offset Parser ---
_RE_WEEK_OFFSET = re.compile(r"v=(-?\d+)") # Reverted: Extracts the offset value 'v' from onclick

def parse_available_offsets(html: Optional[str]) -> List[int]: # Allow Optional[str]
    """
    Parses the timetable HTML to find all available week offsets from navigation links.

    Args:
        html: The HTML content string of a timetable page.

    Returns:
        A sorted list of unique integer week offsets found in the navigation.
        Returns an empty list if parsing fails or no offsets are found.
    """
    if not html: # Add check for empty input
        log.warning("parse_available_offsets received empty HTML.")
        return []

    offsets = set()
    try:
        soup = BeautifulSoup(html, "lxml")
        # Find all anchor tags with an onclick attribute containing 'v='
        # These are typically used for week navigation.
        nav_links = soup.select('a[onclick*="v="]') # Reverted: Select links with 'v=' in onclick

        if not nav_links:
            log.warning("No week navigation links ('a[onclick*=v=]') found in HTML.")
            return []

        for link in nav_links:
            onclick_attr = link.get("onclick")
            if onclick_attr:
                match = _RE_WEEK_OFFSET.search(onclick_attr)
                if match:
                    try:
                        offset = int(match.group(1))
                        offsets.add(offset)
                    except (ValueError, IndexError):
                        log.warning(f"Could not parse integer offset from onclick: {onclick_attr}")
                else:
                    # This might happen for other types of skemaVis calls, ignore them.
                    log.debug(f"Regex did not match expected offset pattern in onclick: {onclick_attr}")

    except Exception as e:
        log.error(f"Error parsing available week offsets from HTML: {e}", exc_info=True)
        return [] # Return empty list on critical error

    if not offsets:
        log.warning("Parsed HTML but found no valid week offsets in navigation links.")

    sorted_offsets = sorted(list(offsets))
    log.info(f"Found {len(sorted_offsets)} unique week offsets: {sorted_offsets}")
    return sorted_offsets