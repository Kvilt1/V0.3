# glasir_api/core/parsers.py
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup, Tag

# Use relative imports for components within the 'glasir_api.core' package
from .constants import CANCELLED_CLASS_INDICATORS, DAY_NAME_MAPPING
from .date_utils import to_iso_date, parse_time_range # Added parse_time_range
from .formatting import format_academic_year # Removed parse_time_range

# Basic logging setup
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(name)s - %(message)s')
log = logging.getLogger(__name__)

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


# --- Timetable Parser ---
# Regex for student info (Name, Class) - made slightly more robust
# Regex updated to capture name potentially containing commas, stopping before the last comma,
# and capturing the class after the last comma.
# Regex refined: Capture name (non-greedy) and class after the colon and comma. Applied to the text content *after* finding the correct TD.
# Regex refined: Capture name (non-greedy) and class (alphanumeric) directly after the prefix. Applied to the full text content of the TD.
_RE_STUDENT_INFO = re.compile(
    r"N[æ&aelig;]mingatímatalva\s*:\s*([^<]+?)\s*,\s*(\w+)"
) # Example: "Næmingatímatalva: Rókur Kvilt Meitilberg, 22y <..." -> ('Rókur Kvilt Meitilberg', '22y')
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

def parse_timetable_html(
    html: str, teacher_map: Optional[Dict[str, str]] = None
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Parses the main timetable HTML page to extract week information, student info,
    and individual lesson events.

    Args:
        html: The HTML content string of the timetable page.
        teacher_map: An optional dictionary mapping teacher initials to full names.

    Returns:
        A tuple containing:
        - timetable_data: A dictionary containing 'studentInfo', 'weekInfo', and 'events'.
        - homework_ids: A list of lesson IDs (str) that have a homework note icon.
    """
    timetable_data: Dict[str, Any] = {"studentInfo": {}, "weekInfo": {}, "events": []}
    homework_ids: List[str] = []
    teacher_map = teacher_map or {} # Ensure teacher_map is a dict

    try:
        # Log the *entire* HTML received by the parser for detailed comparison
        log.debug(f"Parser received FULL HTML:\n{html}\n--- END OF FULL HTML ---")
        # Revert back to lxml parser
        log.debug("Attempting to parse HTML using 'lxml'")
        soup = BeautifulSoup(html, "lxml")

        # --- Extract Student Info (Robust Method: Find TD, then parse text) ---
        student_info_td = soup.find(lambda tag: tag.name == 'td' and 'Næmingatímatalva' in tag.get_text())
        student_name = None
        student_class = None
        if student_info_td:
            # Extract only the initial text node content before the nested table
            initial_text = ""
            for content in student_info_td.contents:
                if isinstance(content, str):
                    initial_text += content
                elif isinstance(content, Tag) and content.name == 'table':
                    break # Stop when the nested table is encountered
                # Ignore other tags like <br> if any before the table
            initial_text = initial_text.strip() # Clean whitespace

            log.debug(f"Extracted initial text from student info TD: '{initial_text}'")

            # Apply the regex to the cleaner initial text
            student_info_match = _RE_STUDENT_INFO.search(initial_text)
            if student_info_match:
                student_name = student_info_match.group(1).strip()
                student_class = student_info_match.group(2).strip()
                log.debug(f"Parsed student info from initial text (regex): Name='{student_name}', Class='{student_class}'")
            else:
                # Fallback if regex fails even on initial text (less likely now)
                log.warning(f"Regex failed on student info initial text: '{initial_text}'. Trying split fallback.")
                parts = initial_text.split(':')
                if len(parts) > 1:
                    name_class_part = parts[1].strip()
                    name_class_split = name_class_part.split(',')
                    if len(name_class_split) > 1:
                        student_name = name_class_split[0].strip()
                        student_class = name_class_split[1].strip()
                        log.debug(f"Parsed student info from initial text (split fallback): Name='{student_name}', Class='{student_class}'")
                    else:
                         log.warning(f"Could not split name/class part after colon using comma: '{name_class_part}'")
                else:
                    log.warning(f"Could not find colon ':' in student info initial text.")
        else:
            log.warning("Could not find TD containing 'Næmingatímatalva'.")

        # Assign to timetable_data if found, otherwise leave empty for validation
        if student_name and student_class:
             timetable_data["studentInfo"] = {
                 "studentName": student_name,
                 "class": student_class,
             }
        else:
             log.error("Failed to parse student name and class after attempting multiple methods.")
             # Keep studentInfo empty

        # --- Extract Week Info (from full soup object and HTML string) ---
        week_info = timetable_data["weekInfo"] # Shorthand
        # Week number from the selected week button (search full soup)
        week_link = soup.select_one("a.UgeKnapValgt") # Search full soup
        if week_link:
            week_text = week_link.get_text(strip=True)
            if week_text.startswith("Vika "):
                try:
                    week_info["weekNumber"] = int(week_text.replace("Vika ", ""))
                except ValueError:
                    log.warning(f"Could not parse week number from text: '{week_text}'")
            else:
                log.warning(f"Selected week link text format unexpected: '{week_text}'")
        else:
            log.warning("Could not find selected week link (a.UgeKnapValgt) in HTML.")

        # Date range and year (search full HTML string)
        date_range_match = _RE_DATE_RANGE.search(html) # Search full HTML
        current_year = None
        if date_range_match:
            start_date_str = date_range_match.group(1) # DD.MM.YYYY
            end_date_str = date_range_match.group(2)   # DD.MM.YYYY
            week_info["startDate"] = to_iso_date(start_date_str)
            week_info["endDate"] = to_iso_date(end_date_str)
            if week_info.get("startDate"):
                try:
                    # Extract year from the successfully parsed start date
                    current_year = int(week_info["startDate"].split("-")[0])
                    week_info["year"] = current_year
                except (ValueError, IndexError, TypeError):
                    log.warning(f"Could not parse year from ISO startDate: {week_info.get('startDate')}")
            else:
                 log.warning(f"Could not parse start date '{start_date_str}' to ISO format.")
        else:
            log.warning("Could not parse date range (DD.MM.YYYY - DD.MM.YYYY) from HTML.")

        # Fallback: try to get year from current system time if not found or parsed
        if not current_year:
             current_year = datetime.now().year
             week_info["year"] = current_year # Set year in weekInfo even if dates failed
             log.warning(f"Falling back to current system year: {current_year}")

        log.debug(f"Parsed week info: {week_info}")

        # --- Extract Events from Table (search directly) ---
        table = soup.select_one("table.time_8_16") # Select table directly
        if not table:
             log.error("Timetable table (table.time_8_16) not found in HTML.")
             return timetable_data, homework_ids

        log.debug(f"Successfully located timetable table using 'table.time_8_16'.")

        rows = table.select("tr")
        current_day_name_fo: Optional[str] = None
        current_date_part: Optional[str] = None # DD/MM part

        for row_index, row in enumerate(rows):
            cells = row.select("td")
            if not cells:
                continue

            first_cell = cells[0]
            first_cell_text = first_cell.get_text(separator=" ", strip=True)

            # Check if this row is a day header row
            day_match = _RE_DAY_DATE.match(first_cell_text)
            is_day_header = "lektionslinje_1" in first_cell.get(
                "class", []
            ) or "lektionslinje_1_aktuel" in first_cell.get("class", [])

            if is_day_header:
                log.debug(f"Row {row_index}: Identified as day header. Text: '{first_cell_text}'")
                # This row is identified as a day header row.
                if day_match:
                    # Successfully parsed day name and date part
                    current_day_name_fo = day_match.group(1)
                    current_date_part = day_match.group(2) # Store DD/MM
                    log.debug(f"Row {row_index}: Successfully parsed day header: Day='{current_day_name_fo}', Date='{current_date_part}'")
                else:
                    # Header row without a parsable date match (e.g., empty day, weekend)
                    # This case might apply to rows that are *just* spacers between days, like the <td class=mellem_1> rows.
                    # We still want to reset context if the regex fails on a row marked as a header.
                    log.warning(f"Row {row_index}: Identified as day header (class check), but regex failed to parse date: '{first_cell_text}'. Resetting day context.")
                    current_day_name_fo = None # Reset day context
                    current_date_part = None
                # --- REMOVED 'continue' ---
                # Now we proceed to check cells in this row even if it's a header row,
                # because lesson data might be in subsequent cells of the same row.
            elif not day_match: # Explicitly check if it wasn't a day header based on regex match
                # This handles rows that are clearly not day headers (e.g., the pure 'mellem' spacer rows)
                log.debug(f"Row {row_index}: Not identified as day header based on text/regex. First cell text: '{first_cell_text}', Classes: {first_cell.get('class', [])}. Skipping row processing.")
                # If it's not a day header row at all, we can safely skip processing its cells.
                continue

            # --- Process Lesson Cells (Only if not a header row) ---
            # Ensure we have valid day context before processing lesson cells
            if not current_day_name_fo or not current_date_part:
                 # Skip processing cells if we haven't encountered a valid day header yet
                 # or if the last header was malformed.
                 log.debug(f"Skipping row {row_index} cell processing as current day/date context is not validly set.")
                 continue

            # Log row info *before* cell loop
            log.debug(f"Processing row index {row_index} for day: {current_day_name_fo}")
            current_col_index = 1 # Reset column index for each row
            lessons_found_in_row = 0 # Counter for lessons in this row
            day_en = DAY_NAME_MAPPING.get(current_day_name_fo, current_day_name_fo) # Translate day name

            for cell_index, cell in enumerate(cells):
                 # Skip the first cell in any row processed by this inner loop,
                 # as it's either the day header or empty spacing before lessons.
                 # Skip the first cell (index 0) in *any* row being processed by this inner loop.
                 # This cell contains either the day/date info (in header rows) or is an empty spacer.
                 if cell_index == 0:
                      log.debug(f"  Skipping cell 0 (contains day info or is a spacer)")
                      # Need to account for its colspan if skipping, to keep current_col_index accurate
                      try:
                            # Use the actual first cell (cells[0]) to get colspan, not the loop variable 'cell'
                            colspan = int(cells[0].get("colspan", 1))
                      except ValueError:
                            colspan = 1
                      current_col_index += colspan
                      continue

                 log.debug(f"  Processing cell {cell_index} (Col ~{current_col_index}) - Classes: {cell.get('class', 'N/A')}") # ADDED DETAILED LOG
                 colspan = 1
                 # --- Start of indented block ---
                 try:
                     colspan_str = cell.get("colspan")
                     if colspan_str:
                         colspan = int(colspan_str)
                 except (ValueError, TypeError):
                     log.warning(f"Could not parse colspan for cell: {cell.get('colspan', 'None')}")
                     colspan = 1 # Default to 1 if parsing fails

                 # Revert to standard class check but add detailed logging
                 classes = cell.get("class", []) # Get class list
                 class_str = ' '.join(classes) if isinstance(classes, list) else str(classes) # For logging

                 # --- Lesson Identification (Reverted & Refined) ---
                 # Check for class names starting with 'lektionslinje_lesson' followed by a digit,
                 # as observed in the actual HTML (e.g., 'lektionslinje_lesson0').
                 # Also check for cells with 'mellem' class that contain lesson information.
                 is_lesson = False
                 lesson_class_pattern = re.compile(r"lektionslinje_lesson\d+")
                 if isinstance(classes, list):
                     for cls in classes:
                          if lesson_class_pattern.match(cls):
                              is_lesson = True
                              break # Found a match
                 elif isinstance(classes, str): # Fallback if class is a single string
                     if lesson_class_pattern.match(classes):
                         is_lesson = True
                 
                 # Removed the check for 'mellem' class as potential lessons,
                 # as the HTML analysis shows 'mellem' cells are just spacers.
                 # Lesson identification now relies solely on the 'lektionslinje_lesson\d+' class pattern.

                 is_cancelled = any(cls in CANCELLED_CLASS_INDICATORS for cls in classes if isinstance(cls, str))

                 log.debug(f"    Cell {cell_index} check result: is_lesson={is_lesson} (based on class pattern), is_cancelled={is_cancelled}, Classes='{class_str}'")

                 if is_lesson:
                     lessons_found_in_row += 1 # Increment counter
                     a_tags = cell.select("a") # Select links directly from the lesson cell
                     # Expecting at least 3 <a> tags for subject, teacher, room in a valid lesson cell
                     if len(a_tags) >= 3:
                         log.debug(f"      Cell {cell_index}: Identified as lesson AND found {len(a_tags)} links. Proceeding to parse.")
                         class_code_raw = a_tags[0].get_text(strip=True)
                         teacher_short = a_tags[1].get_text(strip=True)
                         room_raw = a_tags[2].get_text(strip=True)

                         # --- Code below is now correctly indented within the if len(a_tags) >= 3 block ---

                         # --- Parse Subject Code ---
                         code_parts = class_code_raw.split("-")
                         subject_code = ""
                         level = ""
                         year_code = "" # Academic year part like '2425'
                         if code_parts:
                             # Handle specific "Várroynd" format
                             if code_parts[0] == "Várroynd" and len(code_parts) > 4:
                                 subject_code = f"{code_parts[0]}-{code_parts[1]}"
                                 level = code_parts[2]
                                 # Assuming team/group is part 3, year is part 4
                                 year_code = code_parts[4]
                             # Handle standard format like SUBJ-LVL-TEAM-YEAR
                             elif len(code_parts) > 3:
                                 subject_code = code_parts[0]
                                 level = code_parts[1]
                                 # Assuming team is part 2, year is part 3
                                 year_code = code_parts[3]
                             else: # Fallback if format is unexpected
                                 subject_code = class_code_raw # Use the raw string
                                 log.warning(f"Unexpected subject code format: {class_code_raw}")


                         # --- Teacher and Location ---
                         teacher_full = teacher_map.get(teacher_short, teacher_short) # Use map or default to short
                         location = room_raw.replace("st.", "").strip() # Clean room string

                         # --- Time and Date ---
                         # Determine time slot based on column index
                         if colspan >= 90: # Heuristics for all-day events based on colspan
                             time_info = {"slot": "All day", "time": "08:10-15:25"} # Approximate
                         else:
                             time_info = get_timeslot_info(current_col_index)
                         # log.debug(f"      Calculated time_info: {time_info}") # Compacted log

                         iso_date = None
                         if current_date_part and current_year:
                             # Combine DD/MM with the year determined earlier
                             iso_date = to_iso_date(current_date_part, current_year)
                         elif current_date_part:
                             log.warning(
                                 f"Cannot determine ISO date for '{current_date_part}' - year is missing or failed parsing."
                             )

                         start_time, end_time = parse_time_range(time_info["time"])

                         # --- Lesson ID ---
                         lesson_id = None
                         # Look for the span containing the lesson ID
                         lesson_span = cell.select_one('span[id^="MyWindow"][id$="Main"]')
                         if lesson_span and lesson_span.get("id"):
                             span_id = lesson_span["id"]
                             # Extract ID: remove prefix "MyWindow" and suffix "Main"
                             if len(span_id) > 12: # "MyWindow" (8) + "Main" (4) = 12
                                 lesson_id = span_id[8:-4]
                             else:
                                 log.warning(
                                     f"Found lesson span with unexpected ID format: {span_id}"
                                 )
                         else:
                             # Log if the span is missing, might indicate HTML structure change
                             log.warning(
                                 f"Could not find lesson ID span in cell for {subject_code} on {iso_date}"
                             )
                         # log.debug(f"      Extracted lesson_id: {lesson_id}") # Compacted log

                         # --- Homework Note Check ---
                         has_homework_note = False
                         # Check for the note image icon using attribute selector
                         note_img = cell.select_one(
                             'input[type="image"][src*="note.gif"]'
                         )
                         if note_img:
                             has_homework_note = True
                             if lesson_id:
                                 # Only add ID if homework note is present AND ID was found
                                 homework_ids.append(lesson_id)
                                 log.debug(f"Homework note found for lesson ID: {lesson_id}")
                             else:
                                 log.warning(f"Homework note found, but no lessonId extracted for cell: {subject_code} on {iso_date}")


                         # --- Assemble Event Dictionary ---
                         try:
                             event = {
                                 "title": subject_code,
                                 "level": level,
                                 "year": format_academic_year(year_code), # Format '2425' -> '2024-2025'
                                 "date": iso_date,
                                 "dayOfWeek": day_en, # Use translated day name
                                 "teacher": (
                                     teacher_full.split(" (")[0] # Clean up name if initials are appended
                                     if " (" in teacher_full
                                     else teacher_full
                                 ),
                                 "teacherShort": teacher_short,
                                 "location": location,
                                 "timeSlot": time_info["slot"],
                                 "startTime": start_time,
                                 "endTime": end_time,
                                 "timeRange": time_info["time"],
                                 "cancelled": is_cancelled,
                                 "lessonId": lesson_id,
                                 "hasHomeworkNote": has_homework_note,
                                 "description": None, # Placeholder for homework text (added later)
                             }
                             log.debug(f"        Assembled event dictionary: {event}") # Log the event before appending
                             timetable_data["events"].append(event)
                             log.debug(f"        Successfully appended event for {subject_code}")
                         except Exception as event_err:
                             log.error(f"      ERROR assembling or appending event for cell {cell_index} ({subject_code} on {iso_date}): {event_err}", exc_info=True)

                     else:
                         # Log if it was identified as a lesson but didn't have enough links
                         log.warning(f"      Cell {cell_index}: Identified as lesson based on class, but found only {len(a_tags)} links. Skipping event creation.")
                         # Ensure we still advance the column index correctly
                         current_col_index += colspan
                         continue # Skip to the next cell
 
                     # The 'else' for 'if len(a_tags) >= 3:' is handled above by logging a warning and continuing

                 # This 'else' corresponds to `if is_lesson:`
                 else:
                     log.debug(f"      Cell {cell_index}: Not identified as a lesson based on class pattern. Skipping.")
                     # Still need to advance column index for non-lesson cells
                     current_col_index += colspan
                     continue # Skip to the next cell

                 # --- This part is now only reached if is_lesson and len(a_tags) >= 3 ---

                 # Move column index forward by the colspan of the current cell
                 # Important: Do this *after* successfully processing a lesson cell or explicitly skipping non-lessons.
                 # to correctly track position across empty/non-lesson cells.
                 current_col_index += colspan
                 # log.debug(f"    Moved col index to ~{current_col_index}") # Compacted log
                 # --- End of indented block ---

            # Log row HTML *after* processing all its cells, to avoid prettify errors blocking cell logs
            try:
                log.debug(f"Finished processing row index {row_index}. Found {lessons_found_in_row} lesson(s). Row HTML: {row.prettify()}")
            except Exception as prettify_err:
                log.warning(f"Finished processing row index {row_index}. Found {lessons_found_in_row} lesson(s). Error logging row HTML: {prettify_err}")

    except Exception as e:
        log.error(f"Critical error during timetable HTML parsing: {e}", exc_info=True)




    log.info(f"Finished parsing timetable. Found {len(timetable_data['events'])} potential events.")
    # Use set to count unique IDs, as duplicates might occur if parsing logic has issues
    unique_homework_ids = set(homework_ids)
    log.info(f"Identified {len(unique_homework_ids)} unique lessons with homework notes.")
    
    # --- Fallback: Extract Events from Class Info if No Events Found ---
    if len(timetable_data["events"]) == 0 and timetable_data.get("studentInfo", {}).get("class"):
        log.warning("No events found through normal parsing. Attempting to extract from class info.")
        class_info = timetable_data["studentInfo"]["class"]
        
        # Look for day headers like "Mánadagur 21/4"
        day_matches = re.finditer(r'([A-ZÁÐÍÓÚÝÆØÅa-záðíóúýæøå]+dagur)\s+(\d{1,2}/\d{1,2})', class_info)
        
        for day_match in day_matches:
            day_name_fo = day_match.group(1)
            date_part = day_match.group(2)
            day_en = DAY_NAME_MAPPING.get(day_name_fo, day_name_fo)
            
            # Find position of this day in string
            day_pos = day_match.start()
            next_day_match = re.search(r'[A-ZÁÐÍÓÚÝÆØÅa-záðíóúýæøå]+dagur', class_info[day_pos + 1:])
            day_end_pos = next_day_match.start() + day_pos + 1 if next_day_match else len(class_info)
            
            # Extract content for this day
            day_content = class_info[day_pos:day_end_pos]
            
            # Find course patterns like "før-A-33-2425-22y TJA st. 516"
            course_matches = re.finditer(r'([a-zæøåA-ZÆØÅ]+-[A-Z]-\d+-\d{4}-\w+)\s+([A-Z]{2,4})\s+st\.\s+(\d+)', day_content)
            
            for i, course_match in enumerate(course_matches):
                course_code = course_match.group(1)
                teacher_short = course_match.group(2)
                location = course_match.group(3)
                
                # Parse course info
                code_parts = course_code.split("-")
                subject_code = code_parts[0] if len(code_parts) > 0 else course_code
                level = code_parts[1] if len(code_parts) > 1 else ""
                year_code = code_parts[3] if len(code_parts) > 3 else ""
                
                # Create ISO date
                iso_date = None
                current_year = timetable_data.get("weekInfo", {}).get("year")
                if current_year:
                    iso_date = to_iso_date(date_part, current_year)
                
                # Use position in day to estimate time slot
                time_info = get_timeslot_info((i + 1) * 10)  # Rough estimate
                start_time, end_time = parse_time_range(time_info["time"])
                
                # Create event
                teacher_full = teacher_map.get(teacher_short, teacher_short)
                event = {
                    "title": subject_code,
                    "level": level,
                    "year": format_academic_year(year_code),
                    "date": iso_date,
                    "dayOfWeek": day_en,
                    "teacher": teacher_full.split(" (")[0] if " (" in teacher_full else teacher_full,
                    "teacherShort": teacher_short,
                    "location": location,
                    "timeSlot": time_info["slot"],
                    "startTime": start_time,
                    "endTime": end_time,
                    "timeRange": time_info["time"],
                    "cancelled": False,
                    "lessonId": None,  # No lesson ID available in this fallback
                    "hasHomeworkNote": False,
                    "description": None,
                }
                timetable_data["events"].append(event)
                log.debug(f"Extracted event from class info: {subject_code} with {teacher_short} in room {location}")
        
        log.info(f"Extracted {len(timetable_data['events'])} events from class info as fallback.")
    
    # --- Add final debug log ---
    log.debug(f"FINAL Events list contains {len(timetable_data['events'])} events.") # Log only the count
    # --- End final debug log ---


    # Return the list of potentially duplicate IDs as the extractor might handle duplicates
    return timetable_data, homework_ids
# --- Homework Merging ---

def merge_homework_into_events(events: List[Dict[str, Any]], homework_map: Dict[str, str]):
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
        lesson_id = event.get("lessonId")
        if lesson_id and lesson_id in homework_map:
            homework_text = homework_map[lesson_id]
            event["description"] = homework_text
            log.debug(f"Merged homework for lesson ID {lesson_id} into event '{event.get('title', 'N/A')}'")
            merged_count += 1
        elif lesson_id:
            # Removed log for missing homework in map - too verbose. The final count is sufficient.
            pass # Explicitly do nothing if homework is not found for a lesson ID

    log.info(f"Merged homework descriptions into {merged_count} events.")
# --- Available Weeks Offset Parser ---
_RE_WEEK_OFFSET = re.compile(r"v=(-?\d+)") # Reverted: Extracts the offset value 'v' from onclick

def parse_available_offsets(html: str) -> List[int]:
    """
    Parses the timetable HTML to find all available week offsets from navigation links.

    Args:
        html: The HTML content string of a timetable page.

    Returns:
        A sorted list of unique integer week offsets found in the navigation.
        Returns an empty list if parsing fails or no offsets are found.
    """
    offsets = set()
    try:
        soup = BeautifulSoup(html, "lxml")
        # Find all anchor tags with an onclick attribute containing 'skemaVis('
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