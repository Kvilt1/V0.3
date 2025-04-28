import pytest
from datetime import time

# Correct imports based on models.py and api_models.py
from glasir_api.core.diff_service import calculate_week_diff
from glasir_api.models.models import Event, TimetableData, WeekInfo, StudentInfo
from glasir_api.models.api_models import WeekDiff # EventChange is not used/defined here

# --- Mock Data based on Event model and api_response.json structure ---

# Use lessonId as the unique identifier for events in the diff service context
# Event 1: "søg" from api_response.json
EVENT_SOG = Event(
    lessonId="45CD8E0E-A0F4-4054-BF56-AC7F68425A92", title="søg", level="A", year="2024-2025", date="2025-04-28", dayOfWeek="Monday",
    teacher="Jón Mikael Degn í Haraldstovu", teacherShort="JOH", location="513", timeSlot="1",
    startTime="08:10", endTime="09:40", timeRange="08:10-09:40", cancelled=False,
    description="https://...", hasHomeworkNote=True
)

# Event 2: "alf" from api_response.json
EVENT_ALF = Event(
    lessonId="5E49188C-2870-41AC-BFE6-E7008009679F", title="alf", level="A", year="2024-2025", date="2025-04-28", dayOfWeek="Monday",
    teacher="Henriette Svenstrup", teacherShort="HSV", location="615", timeSlot="2",
    startTime="10:05", endTime="11:35", timeRange="10:05-11:35", cancelled=False,
    description="...", hasHomeworkNote=True
)

# Event 3: "evf" from api_response.json (cancelled)
EVENT_EVF = Event(
    lessonId="AAE89253-DF48-42E8-984C-367CE9953C18", title="evf", level="A", year="2024-2025", date="2025-04-28", dayOfWeek="Monday",
    teacher="Brynjálvur I. Johansen", teacherShort="BIJ", location="606", timeSlot="3",
    startTime="12:10", endTime="13:40", timeRange="12:10-13:40", cancelled=True,
    description=None, hasHomeworkNote=False
)

# Event 1 Updated: Modified "søg" event
EVENT_SOG_UPDATED = Event(
    lessonId="45CD8E0E-A0F4-4054-BF56-AC7F68425A92", title="søg", level="A", year="2024-2025", date="2025-04-28", dayOfWeek="Monday",
    teacher="Jón Mikael Degn í Haraldstovu", teacherShort="JOH", location="514", # Changed location
    timeSlot="1", startTime="08:15", endTime="09:45", timeRange="08:15-09:45", # Changed time
    cancelled=True, # Changed cancelled status
    description="Updated description", hasHomeworkNote=False # Changed desc/homework
)

# Common Student and Week Info
STUDENT_INFO = StudentInfo(studentName="Test Student", class_="22x")
WEEK_INFO = WeekInfo(week_number=18, year=2025, start_date="2025-04-28", end_date="2025-05-04")

# --- TimetableData Instances for Tests ---

# Base state with SOG and ALF events
TIMETABLE_BASE = TimetableData(
    studentInfo=STUDENT_INFO,
    weekInfo=WEEK_INFO,
    events=[EVENT_SOG, EVENT_ALF],
    formatVersion=2
)

# Identical state
TIMETABLE_IDENTICAL = TimetableData(
    studentInfo=STUDENT_INFO,
    weekInfo=WEEK_INFO,
    events=[EVENT_SOG, EVENT_ALF],
    formatVersion=2
)

# State with added EVF event
TIMETABLE_ADDED = TimetableData(
    studentInfo=STUDENT_INFO,
    weekInfo=WEEK_INFO,
    events=[EVENT_SOG, EVENT_ALF, EVENT_EVF], # Added EVF
    formatVersion=2
)

# State with removed ALF event
TIMETABLE_REMOVED = TimetableData(
    studentInfo=STUDENT_INFO,
    weekInfo=WEEK_INFO,
    events=[EVENT_SOG], # Removed ALF
    formatVersion=2
)

# State with updated SOG event
TIMETABLE_UPDATED = TimetableData(
    studentInfo=STUDENT_INFO,
    weekInfo=WEEK_INFO,
    events=[EVENT_SOG_UPDATED, EVENT_ALF], # Updated SOG
    formatVersion=2
)

# State for combination test (Old: SOG, ALF; New: SOG_UPDATED, EVF)
TIMETABLE_COMBO_OLD = TimetableData(
    studentInfo=STUDENT_INFO,
    weekInfo=WEEK_INFO,
    events=[EVENT_SOG, EVENT_ALF],
    formatVersion=2
)
TIMETABLE_COMBO_NEW = TimetableData(
    studentInfo=STUDENT_INFO,
    weekInfo=WEEK_INFO,
    events=[EVENT_SOG_UPDATED, EVENT_EVF], # Updated SOG, Removed ALF, Added EVF
    formatVersion=2
)

# State with empty events list
TIMETABLE_EMPTY = TimetableData(
    studentInfo=STUDENT_INFO,
    weekInfo=WEEK_INFO,
    events=[], # Empty list
    formatVersion=2
)


# --- Unit Tests for calculate_week_diff ---

def test_calculate_week_diff_no_changes():
    """Test calculate_week_diff when old and new data are identical."""
    diff = calculate_week_diff(TIMETABLE_BASE, TIMETABLE_IDENTICAL)
    assert isinstance(diff, WeekDiff)
    # Removed assertions for week_number and year as they are not part of WeekDiff model
    assert not diff.added
    assert not diff.removed
    assert not diff.updated

def test_calculate_week_diff_events_added():
    """Test calculate_week_diff when events are added."""
    diff = calculate_week_diff(TIMETABLE_BASE, TIMETABLE_ADDED)
    assert isinstance(diff, WeekDiff)
    assert len(diff.added) == 1
    assert diff.added[0] == EVENT_EVF # Check the correct event was added
    assert not diff.removed
    assert not diff.updated

def test_calculate_week_diff_events_removed():
    """Test calculate_week_diff when events are removed."""
    diff = calculate_week_diff(TIMETABLE_BASE, TIMETABLE_REMOVED)
    assert isinstance(diff, WeekDiff)
    assert not diff.added
    assert len(diff.removed) == 1
    assert diff.removed[0] == EVENT_ALF.lesson_id # Check the correct lesson_id was removed
    assert not diff.updated

def test_calculate_week_diff_events_updated():
    """Test calculate_week_diff when events are updated."""
    diff = calculate_week_diff(TIMETABLE_BASE, TIMETABLE_UPDATED)
    assert isinstance(diff, WeekDiff)
    assert not diff.added
    assert not diff.removed
    assert len(diff.updated) == 1
    # The updated list contains the *new* event object directly
    updated_event = diff.updated[0]
    assert isinstance(updated_event, Event)
    assert updated_event == EVENT_SOG_UPDATED # Check if the updated event is the new version

def test_calculate_week_diff_combination():
    """Test calculate_week_diff with added, removed, and updated events."""
    diff = calculate_week_diff(TIMETABLE_COMBO_OLD, TIMETABLE_COMBO_NEW)
    assert isinstance(diff, WeekDiff)
    # Added EVF
    assert len(diff.added) == 1
    assert diff.added[0] == EVENT_EVF
    # Removed ALF
    assert len(diff.removed) == 1
    assert diff.removed[0] == EVENT_ALF.lesson_id # Check lesson_id
    # Updated SOG
    assert len(diff.updated) == 1
    updated_event = diff.updated[0]
    assert isinstance(updated_event, Event)
    assert updated_event == EVENT_SOG_UPDATED # Check if the updated event is the new version

def test_calculate_week_diff_old_data_none():
    """Test calculate_week_diff when old_data is None (first sync)."""
    diff = calculate_week_diff(None, TIMETABLE_BASE)
    assert isinstance(diff, WeekDiff)
    assert len(diff.added) == 2 # Both SOG and ALF should be added
    assert EVENT_SOG in diff.added
    assert EVENT_ALF in diff.added
    assert not diff.removed
    assert not diff.updated

def test_calculate_week_diff_new_data_empty():
    """Test calculate_week_diff when new_data has empty events."""
    diff = calculate_week_diff(TIMETABLE_BASE, TIMETABLE_EMPTY)
    assert isinstance(diff, WeekDiff)
    assert not diff.added
    assert len(diff.removed) == 2 # Both SOG and ALF should be removed
    # Check for lesson IDs in the removed list
    assert EVENT_SOG.lesson_id in diff.removed
    assert EVENT_ALF.lesson_id in diff.removed
    assert not diff.updated