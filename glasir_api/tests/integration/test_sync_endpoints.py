import pytest
import httpx
import databases
import json
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
import sqlalchemy # Needed for count query in one test

# Absolute imports
from glasir_api.models.models import TimetableData, WeekInfo, Event, StudentInfo
from glasir_api.models.api_models import InitialSyncResponse, WeekDiff
from glasir_api.models.db_models import UserSession, WeeklyTimetableState # Import classes
from fastapi import FastAPI, HTTPException # Needed for mocking side_effect

# --- Test Constants ---
TEST_STUDENT_ID = "test_student_123"
VALID_INITIAL_COOKIES = "ASP.NET_SessionId=valid_session; studentid=test_student_123"
INVALID_COOKIES = "ASP.NET_SessionId=invalid_session; studentid=test_student_123"
VALID_REFRESH_COOKIES = "ASP.NET_SessionId=refreshed_session; studentid=test_student_123"

# --- Mock Data ---
# Mock HTML for offset 0 (simplified, just needs the select options)
MOCK_HTML_OFFSET_0 = """
<html><body>
<select name="week">
<option value="-1">Week 16</option>
<option value="0" selected>Week 17</option>
<option value="1">Week 18</option>
<option value="2">Week 19</option>
</select>
</body></html>
"""

# Mock TimetableData
# Week 17 Info (offset 0)
MOCK_WEEK_17_INFO = WeekInfo(week_number=17, year=2025, offset=0, start_date="2025-04-21", end_date="2025-04-27", week_key="2025-W17")

# Event 1 for Week 17 (Initial)
MOCK_EVENT_W17_1 = Event(
    title="Sub1", level="A", year="2024-2025", date="2025-04-21", day_of_week="Monday",
    teacher="Teacher A", teacher_short="TA", location="101", time_slot="1",
    start_time="08:00", end_time="09:30", time_range="08:00-09:30", cancelled=False,
    lesson_id="LESSON_W17_1", description="Initial Desc W17 E1", has_homework_note=False
)

# Event 1 for Week 17 (Updated)
MOCK_EVENT_W17_1_UPDATED = Event(
    title="Sub1 Updated", level="A", year="2024-2025", date="2025-04-21", day_of_week="Monday",
    teacher="Teacher A", teacher_short="TA", location="102", # Changed location
    time_slot="1", start_time="08:05", end_time="09:35", time_range="08:05-09:35", # Changed time
    cancelled=False, lesson_id="LESSON_W17_1", description="Updated Desc W17 E1", has_homework_note=True # Changed desc/homework
)

# Event 2 for Week 17 (New)
MOCK_EVENT_W17_2_NEW = Event(
    title="Sub2 New", level="B", year="2024-2025", date="2025-04-22", day_of_week="Tuesday",
    teacher="Teacher B", teacher_short="TB", location="201", time_slot="3",
    start_time="12:00", end_time="13:30", time_range="12:00-13:30", cancelled=False,
    lesson_id="LESSON_W17_2_NEW", description="New Event W17 E2", has_homework_note=False
)

# Week 18 Info (offset 1)
MOCK_WEEK_18_INFO = WeekInfo(week_number=18, year=2025, offset=1, start_date="2025-04-28", end_date="2025-05-04", week_key="2025-W18")

# Event 1 for Week 18: "søg" (Initial)
MOCK_EVENT_W18_SOG = Event(
    title="søg", level="A", year="2024-2025", date="2025-04-28", day_of_week="Monday",
    teacher="Jón Mikael Degn í Haraldstovu", teacher_short="JOH", location="513", time_slot="1",
    start_time="08:10", end_time="09:40", time_range="08:10-09:40", cancelled=False,
    lesson_id="45CD8E0E-A0F4-4054-BF56-AC7F68425A92", description="https://...", has_homework_note=True
)

# Event 2 for Week 18: "alf" (Will be added in change test)
MOCK_EVENT_W18_ALF = Event(
    title="alf", level="A", year="2024-2025", date="2025-04-28", day_of_week="Monday",
    teacher="Henriette Svenstrup", teacher_short="HSV", location="615", time_slot="2",
    start_time="10:05", end_time="11:35", time_range="10:05-11:35", cancelled=False,
    lesson_id="5E49188C-2870-41AC-BFE6-E7008009679F", description="...", has_homework_note=True
)

# Event 1 for Week 18 Updated: Modified "søg" event for change test
MOCK_EVENT_W18_SOG_UPDATED = Event(
    title="søg", level="A", year="2024-2025", date="2025-04-28", day_of_week="Monday",
    teacher="Jón Mikael Degn í Haraldstovu", teacher_short="JOH", location="514", # Changed location
    time_slot="1", start_time="08:15", end_time="09:45", time_range="08:15-09:45", # Changed time
    cancelled=True, # Changed cancelled status
    lesson_id="45CD8E0E-A0F4-4054-BF56-AC7F68425A92", description="Updated description", has_homework_note=False # Changed desc/homework
)

# --- Combined Mock Timetable Data ---
# Initial Timetable Data (Week 17 with Event 1, Week 18 with Event SOG)
MOCK_STUDENT_INFO = StudentInfo(studentName="Rókur Kvilt Meitilberg", class_="22y")

MOCK_INITIAL_TIMETABLE_DATA_W17 = TimetableData(
    student_info=MOCK_STUDENT_INFO,
    events=[MOCK_EVENT_W17_1],
    week_info=MOCK_WEEK_17_INFO,
    format_version=2
)
MOCK_INITIAL_TIMETABLE_DATA_W18 = TimetableData(
    student_info=MOCK_STUDENT_INFO,
    events=[MOCK_EVENT_W18_SOG],
    week_info=MOCK_WEEK_18_INFO,
    format_version=2
)
MOCK_INITIAL_TIMETABLE_DATA = [MOCK_INITIAL_TIMETABLE_DATA_W17, MOCK_INITIAL_TIMETABLE_DATA_W18]

# Changed Timetable Data for Sync Test (Week 17 updated/added, Week 18 unchanged)
MOCK_CHANGED_TIMETABLE_DATA_W17 = TimetableData(
    student_info=MOCK_STUDENT_INFO,
    events=[MOCK_EVENT_W17_1_UPDATED, MOCK_EVENT_W17_2_NEW], # Updated E1, added E2
    week_info=MOCK_WEEK_17_INFO,
    format_version=2
)
# Week 18 data remains unchanged for this specific sync test scenario
MOCK_CHANGED_TIMETABLE_DATA_SYNC = [MOCK_CHANGED_TIMETABLE_DATA_W17, MOCK_INITIAL_TIMETABLE_DATA_W18]


# Mock teacher map (add new teachers)
MOCK_TEACHER_MAP = {
    "JOH": "Jón Mikael Degn í Haraldstovu",
    "HSV": "Henriette Svenstrup",
    "TA": "Teacher A",
    "TB": "Teacher B"
}

# --- Tests ---

# Test for POST /sync/initial will go here
@pytest.mark.asyncio
async def test_initial_sync_success(async_client: httpx.AsyncClient, app_with_db: FastAPI, mocker): # Use app_with_db
    """
    Test successful initial synchronization via POST /sync/initial.
    - Mocks external calls (_setup_extractor, fetch_week_html, get_multiple_weeks).
    - Verifies 201 status code and response structure.
    - Verifies data persistence in user_sessions and weekly_timetable_state tables.
    """
    # --- Mock External Dependencies ---
    # Mock _setup_extractor to simulate successful cookie validation and setup
    mock_extractor = mocker.AsyncMock()
    mocker.patch(
        "glasir_api.main._setup_extractor", # Absolute path for patching
        return_value=(mock_extractor, MOCK_TEACHER_MAP, "Test Lname") # Return mock extractor, map, dummy lname
    )

    # Mock fetch_week_html (called by initial_sync to get offsets)
    mock_extractor.fetch_week_html.return_value = MOCK_HTML_OFFSET_0

    # Mock get_multiple_weeks to return predefined data for the identified offsets [-1, 0, 1, 2]
    # Note: The actual offsets parsed from MOCK_HTML_OFFSET_0 are [-1, 0, 1, 2]
    # We need mock data corresponding to these offsets if the endpoint uses them all.
    # For simplicity, let's assume the endpoint correctly requests and processes offsets [0, 1] based on MOCK_INITIAL_TIMETABLE_DATA
    # Adjust MOCK_INITIAL_TIMETABLE_DATA if the endpoint logic fetches all parsed offsets.
    mocker.patch(
        "glasir_api.main.get_multiple_weeks", # Absolute path for patching
        return_value=MOCK_INITIAL_TIMETABLE_DATA # Return the predefined list of TimetableData
    )

    # --- Make API Request ---
    request_body = {
        "student_id": TEST_STUDENT_ID,
        "cookies": VALID_INITIAL_COOKIES
    }
    response = await async_client.post("/sync/initial", json=request_body)

    # --- Assert Response ---
    assert response.status_code == 201
    response_data = response.json()
    assert "access_code" in response_data
    assert isinstance(response_data["access_code"], str)
    assert len(response_data["access_code"]) > 10 # Basic check for token format
    assert "initial_data" in response_data
    # Validate the structure of initial_data against TimetableData model (implicitly done by FastAPI response model)
    # Check if the returned data matches the mocked data (adjust based on actual model structure)
    assert len(response_data["initial_data"]) == len(MOCK_INITIAL_TIMETABLE_DATA)
    # Example check on one item (more thorough checks might be needed)
    assert response_data["initial_data"][0]["week_info"]["week_number"] == MOCK_WEEK_17_INFO.week_number
    assert response_data["initial_data"][1]["week_info"]["week_number"] == MOCK_WEEK_18_INFO.week_number

    # --- Assert Database State ---
    access_code = response_data["access_code"]

    # Check user_sessions table
    session_query = UserSession.__table__.select().where(UserSession.__table__.c.student_id == TEST_STUDENT_ID) # Use Class.__table__
    db_session_record = await app_with_db.state.database.fetch_one(session_query) # Use app state db
    assert db_session_record is not None
    assert db_session_record["access_code"] == access_code
    assert db_session_record["cookies_json"] == VALID_INITIAL_COOKIES # Check correct column name
    assert db_session_record["student_id"] == TEST_STUDENT_ID

    # Check weekly_timetable_state table for week 17
    state_query_w17 = WeeklyTimetableState.__table__.select().where( # Use Class.__table__
        (WeeklyTimetableState.__table__.c.student_id == TEST_STUDENT_ID) &
        (WeeklyTimetableState.__table__.c.week_key == MOCK_WEEK_17_INFO.week_key)
    )
    db_state_record_w17 = await app_with_db.state.database.fetch_one(state_query_w17) # Use app state db
    assert db_state_record_w17 is not None
    stored_data_w17 = TimetableData.model_validate_json(db_state_record_w17["week_data_json"]) # Check correct column name
    assert stored_data_w17.week_info.week_number == MOCK_WEEK_17_INFO.week_number
    # Convert list of events to dict keyed by lesson_id for easier lookup
    events_dict_w17 = {event.lesson_id: event for event in stored_data_w17.events}
    assert MOCK_EVENT_W17_1.lesson_id in events_dict_w17

    # Check weekly_timetable_state table for week 18
    state_query_w18 = WeeklyTimetableState.__table__.select().where( # Use Class.__table__
        (WeeklyTimetableState.__table__.c.student_id == TEST_STUDENT_ID) &
        (WeeklyTimetableState.__table__.c.week_key == MOCK_WEEK_18_INFO.week_key)
    )
    db_state_record_w18 = await app_with_db.state.database.fetch_one(state_query_w18) # Use app state db
    assert db_state_record_w18 is not None
    stored_data_w18 = TimetableData.model_validate_json(db_state_record_w18["week_data_json"]) # Check correct column name
    assert stored_data_w18.week_info.week_number == MOCK_WEEK_18_INFO.week_number
    # Convert list of events to dict keyed by lesson_id for easier lookup
    events_dict_w18 = {event.lesson_id: event for event in stored_data_w18.events}
    assert MOCK_EVENT_W18_SOG.lesson_id in events_dict_w18 # Corrected variable name

    # Verify mocks were called (optional but good practice)
    # Get the mock objects using the absolute path
    setup_extractor_mock = mocker.patch("glasir_api.main._setup_extractor")
    get_weeks_mock = mocker.patch("glasir_api.main.get_multiple_weeks")

    setup_extractor_mock.assert_any_call(VALID_INITIAL_COOKIES, mocker.ANY, mocker.ANY) # Check _setup_extractor call
    mock_extractor.fetch_week_html.assert_called_once_with(offset=0, student_id=TEST_STUDENT_ID)
    # Check get_multiple_weeks call - adjust expected offsets based on actual parsing logic if needed
    # Expected offsets from MOCK_HTML_OFFSET_0 are [-1, 0, 1, 2]
    get_weeks_mock.assert_any_call(username="initial_sync",
                                 student_id=TEST_STUDENT_ID,
                                 cookies_str=VALID_INITIAL_COOKIES,
                                 requested_offsets=[-1, 0, 1, 2], # Based on MOCK_HTML_OFFSET_0 parsing
                                 shared_client=mocker.ANY,
                                 db=mocker.ANY)
@pytest.mark.asyncio
async def test_sync_immediately_after_initial(async_client: httpx.AsyncClient, app_with_db: FastAPI, mocker): # Use app_with_db
    """
    Test POST /sync immediately after a successful initial sync.
    Expects empty diffs for the synced weeks.
    """
    # --- 1. Perform Initial Sync (Setup) ---
    # Mock dependencies for initial sync
    mock_extractor = mocker.AsyncMock()
    # Use absolute path patching
    mocker.patch("glasir_api.main._setup_extractor", return_value=(mock_extractor, MOCK_TEACHER_MAP, "Test Lname"))
    mock_extractor.fetch_week_html.return_value = MOCK_HTML_OFFSET_0
    mocker.patch("glasir_api.main.get_multiple_weeks", return_value=MOCK_INITIAL_TIMETABLE_DATA)

    initial_request_body = {"student_id": TEST_STUDENT_ID, "cookies": VALID_INITIAL_COOKIES}
    initial_response = await async_client.post("/sync/initial", json=initial_request_body)
    assert initial_response.status_code == 201
    access_code = initial_response.json()["access_code"]

    # --- 2. Prepare for Sync Request ---
    # Mock get_multiple_weeks again for the /sync call, returning the *same* data
    # Reset the mock or patch again if necessary (pytest-mock usually handles this per-function)
    get_weeks_mock = mocker.patch("glasir_api.main.get_multiple_weeks", return_value=MOCK_INITIAL_TIMETABLE_DATA)

    # Define the offsets to sync (should match what was initially synced)
    # Based on MOCK_INITIAL_TIMETABLE_DATA, we synced weeks with offsets 0 and 1
    sync_offsets = [0, 1]
    sync_request_body = {"offsets": sync_offsets}
    headers = {"X-Access-Code": access_code}

    # --- 3. Make Sync API Request ---
    sync_response = await async_client.post("/sync", json=sync_request_body, headers=headers)

    # --- 4. Assert Sync Response ---
    assert sync_response.status_code == 200
    sync_data = sync_response.json()
    assert "diffs" in sync_data
    assert "synced_at" in sync_data

    diffs = sync_data["diffs"]
    # Check that diffs exist for the requested weeks (keys are "YYYY-WW")
    assert MOCK_WEEK_17_INFO.week_key in diffs
    assert MOCK_WEEK_18_INFO.week_key in diffs

    # Check that diffs are empty
    diff_w17 = WeekDiff(**diffs[MOCK_WEEK_17_INFO.week_key])
    assert not diff_w17.added
    assert not diff_w17.removed
    assert not diff_w17.updated
    assert diff_w17.week_number == MOCK_WEEK_17_INFO.week_number
    assert diff_w17.year == MOCK_WEEK_17_INFO.year

    diff_w18 = WeekDiff(**diffs[MOCK_WEEK_18_INFO.week_key])
    assert not diff_w18.added
    assert not diff_w18.removed
    assert not diff_w18.updated
    assert diff_w18.week_number == MOCK_WEEK_18_INFO.week_number
    assert diff_w18.year == MOCK_WEEK_18_INFO.year

    # --- 5. Assert Database State (Optional: check last_accessed_at update) ---
    session_query = UserSession.__table__.select().where(UserSession.__table__.c.access_code == access_code) # Use Class.__table__
    db_session_record = await app_with_db.state.database.fetch_one(session_query) # Use app state db
    assert db_session_record is not None
    # Check if last_accessed_at was updated (might need to compare with initial sync time)
    assert db_session_record["last_accessed_at"] > db_session_record["created_at"]

    # Verify mocks (optional)
    # get_multiple_weeks should be called twice (once for initial, once for sync)
    assert get_weeks_mock.call_count == 2 # Check call count on the mock object
    # Check the second call specifically
    get_weeks_mock.assert_called_with(username="sync",
                                    student_id=TEST_STUDENT_ID,
                                    cookies_str=VALID_INITIAL_COOKIES, # Cookies from DB session
                                    requested_offsets=sync_offsets,
                                    shared_client=mocker.ANY,
                                    db=mocker.ANY)
@pytest.mark.asyncio
async def test_sync_with_changes(async_client: httpx.AsyncClient, app_with_db: FastAPI, mocker): # Use app_with_db
    """
    Test POST /sync after data has changed since the initial sync.
    Expects correct WeekDiff objects reflecting additions and updates.
    """
    # --- 1. Perform Initial Sync (Setup) ---
    mock_extractor = mocker.AsyncMock()
    # Use absolute path patching
    mocker.patch("glasir_api.main._setup_extractor", return_value=(mock_extractor, MOCK_TEACHER_MAP, "Test Lname"))
    mock_extractor.fetch_week_html.return_value = MOCK_HTML_OFFSET_0
    mocker.patch("glasir_api.main.get_multiple_weeks", return_value=MOCK_INITIAL_TIMETABLE_DATA)

    initial_request_body = {"student_id": TEST_STUDENT_ID, "cookies": VALID_INITIAL_COOKIES}
    initial_response = await async_client.post("/sync/initial", json=initial_request_body)
    assert initial_response.status_code == 201
    access_code = initial_response.json()["access_code"]

    # --- 2. Prepare for Sync Request with Changes ---
    # Mock get_multiple_weeks to return the CHANGED data
    get_weeks_mock = mocker.patch("glasir_api.main.get_multiple_weeks", return_value=MOCK_CHANGED_TIMETABLE_DATA_SYNC)

    sync_offsets = [0, 1] # Syncing week 17 (offset 0) and week 18 (offset 1)
    sync_request_body = {"offsets": sync_offsets}
    headers = {"X-Access-Code": access_code}

    # --- 3. Make Sync API Request ---
    sync_response = await async_client.post("/sync", json=sync_request_body, headers=headers)

    # --- 4. Assert Sync Response ---
    assert sync_response.status_code == 200
    sync_data = sync_response.json()
    assert "diffs" in sync_data
    diffs = sync_data["diffs"]

    # Assert Week 17 Diffs (Changes expected)
    assert MOCK_WEEK_17_INFO.week_key in diffs
    diff_w17 = WeekDiff(**diffs[MOCK_WEEK_17_INFO.week_key])
    assert len(diff_w17.added) == 1
    assert diff_w17.added[0]["lesson_id"] == MOCK_EVENT_W17_2_NEW.lesson_id # Check added event using lesson_id
    assert not diff_w17.removed
    assert len(diff_w17.updated) == 1
    update_w17 = diff_w17.updated[0]
    assert update_w17["event_id"] == MOCK_EVENT_W17_1.lesson_id # Check using lesson_id
    # Check specific changes within the update using correct field names
    assert update_w17["changes"]["start_time"] == [MOCK_EVENT_W17_1.start_time, MOCK_EVENT_W17_1_UPDATED.start_time]
    assert update_w17["changes"]["location"] == [MOCK_EVENT_W17_1.location, MOCK_EVENT_W17_1_UPDATED.location] # Corrected field: location
    assert update_w17["changes"]["title"] == [MOCK_EVENT_W17_1.title, MOCK_EVENT_W17_1_UPDATED.title] # Corrected field: title
    assert update_w17["changes"]["description"] == [MOCK_EVENT_W17_1.description, MOCK_EVENT_W17_1_UPDATED.description] # Corrected field: description
    assert update_w17["changes"]["has_homework_note"] == [MOCK_EVENT_W17_1.has_homework_note, MOCK_EVENT_W17_1_UPDATED.has_homework_note] # Check homework change

    # Assert Week 18 Diffs (No changes expected as per MOCK_CHANGED_TIMETABLE_DATA_SYNC)
    assert MOCK_WEEK_18_INFO.week_key in diffs
    diff_w18 = WeekDiff(**diffs[MOCK_WEEK_18_INFO.week_key])
    assert not diff_w18.added
    assert not diff_w18.removed
    assert not diff_w18.updated

    # --- 5. Assert Database State ---
    # Check that the new state for week 17 is stored correctly
    state_query_w17 = WeeklyTimetableState.__table__.select().where( # Use Class.__table__
        (WeeklyTimetableState.__table__.c.student_id == TEST_STUDENT_ID) &
        (WeeklyTimetableState.__table__.c.week_key == MOCK_WEEK_17_INFO.week_key)
    )
    db_state_record_w17 = await app_with_db.state.database.fetch_one(state_query_w17) # Use app state db
    assert db_state_record_w17 is not None
    stored_data_w17 = TimetableData.model_validate_json(db_state_record_w17["week_data_json"]) # Check correct column name
    # Verify the stored data matches the MOCK_CHANGED_TIMETABLE_DATA_W17
    assert len(stored_data_w17.events) == 2
    # Convert list of events to dict keyed by lesson_id for easier lookup
    events_dict_w17_after_sync = {event.lesson_id: event for event in stored_data_w17.events}
    assert MOCK_EVENT_W17_1_UPDATED.lesson_id in events_dict_w17_after_sync
    assert MOCK_EVENT_W17_2_NEW.lesson_id in events_dict_w17_after_sync
    assert events_dict_w17_after_sync[MOCK_EVENT_W17_1_UPDATED.lesson_id].title == "Sub1 Updated" # Corrected field: title

    # Verify mocks (optional)
    assert get_weeks_mock.call_count == 2 # Check call count on the mock object
    get_weeks_mock.assert_called_with(username="sync",
                                    student_id=TEST_STUDENT_ID,
                                    cookies_str=VALID_INITIAL_COOKIES,
                                    requested_offsets=sync_offsets,
                                    shared_client=mocker.ANY,
                                    db=mocker.ANY)
@pytest.mark.asyncio
async def test_session_refresh_success(async_client: httpx.AsyncClient, app_with_db: FastAPI, mocker): # Use app_with_db
    """
    Test successful session refresh via POST /session/refresh.
    - Performs initial sync to create a session.
    - Mocks cookie validation for the new cookies.
    - Verifies 200 status code and new access code in response.
    - Verifies database update for access code, cookies, and timestamps.
    """
    # --- 1. Perform Initial Sync (Setup) ---
    mock_extractor_initial = mocker.AsyncMock()
    # Use absolute path patching
    mocker.patch("glasir_api.main._setup_extractor", return_value=(mock_extractor_initial, MOCK_TEACHER_MAP, "Test Lname"))
    mock_extractor_initial.fetch_week_html.return_value = MOCK_HTML_OFFSET_0
    mocker.patch("glasir_api.main.get_multiple_weeks", return_value=MOCK_INITIAL_TIMETABLE_DATA)

    initial_request_body = {"student_id": TEST_STUDENT_ID, "cookies": VALID_INITIAL_COOKIES}
    initial_response = await async_client.post("/sync/initial", json=initial_request_body)
    assert initial_response.status_code == 201
    initial_access_code = initial_response.json()["access_code"]

    # --- 2. Prepare for Session Refresh ---
    # Mock _setup_extractor again, this time for the refresh call with NEW cookies
    # It should succeed, indicating the new cookies are valid.
    mock_extractor_refresh = mocker.AsyncMock()
    # We need to patch it again to control the return value for the refresh call specifically
    setup_extractor_mock = mocker.patch("glasir_api.main._setup_extractor", return_value=(mock_extractor_refresh, MOCK_TEACHER_MAP, "Refreshed Lname"))

    refresh_request_body = {
        "student_id": TEST_STUDENT_ID,
        "new_cookies": VALID_REFRESH_COOKIES
    }

    # --- 3. Make Session Refresh API Request ---
    refresh_response = await async_client.post("/session/refresh", json=refresh_request_body)

    # --- 4. Assert Refresh Response ---
    assert refresh_response.status_code == 200
    refresh_data = refresh_response.json()
    assert "access_code" in refresh_data
    new_access_code = refresh_data["access_code"]
    assert isinstance(new_access_code, str)
    assert len(new_access_code) > 10
    assert new_access_code != initial_access_code # Ensure a NEW code was generated

    # --- 5. Assert Database State ---
    session_query = UserSession.__table__.select().where(UserSession.__table__.c.student_id == TEST_STUDENT_ID) # Use Class.__table__
    db_session_record = await app_with_db.state.database.fetch_one(session_query) # Use app state db
    assert db_session_record is not None
    assert db_session_record["access_code"] == new_access_code # Check new access code stored
    assert db_session_record["cookies_json"] == VALID_REFRESH_COOKIES # Check correct column name
    assert db_session_record["student_id"] == TEST_STUDENT_ID
    # Check timestamps were updated
    assert db_session_record["cookies_updated_at"] is not None
    assert db_session_record["access_code_generated_at"] is not None
    assert db_session_record["last_accessed_at"] is not None
    # More specific timestamp checks could compare against 'now' if needed

    # --- 6. Verify Mocks ---
    # _setup_extractor should have been called twice: once for initial, once for refresh
    assert setup_extractor_mock.call_count == 2
    # Check the second call specifically (for the refresh)
    setup_extractor_mock.assert_called_with(VALID_REFRESH_COOKIES, mocker.ANY, mocker.ANY)
@pytest.mark.asyncio
async def test_sync_after_refresh(async_client: httpx.AsyncClient, app_with_db: FastAPI, mocker): # Use app_with_db
    """
    Test POST /sync using the new access code obtained after a session refresh.
    Expects sync to work correctly with the refreshed session details (cookies).
    """
    # --- 1. Perform Initial Sync (Setup) ---
    mock_extractor_initial = mocker.AsyncMock()
    # Use absolute path patching
    mocker.patch("glasir_api.main._setup_extractor", return_value=(mock_extractor_initial, MOCK_TEACHER_MAP, "Test Lname"))
    mock_extractor_initial.fetch_week_html.return_value = MOCK_HTML_OFFSET_0
    mocker.patch("glasir_api.main.get_multiple_weeks", return_value=MOCK_INITIAL_TIMETABLE_DATA)

    initial_request_body = {"student_id": TEST_STUDENT_ID, "cookies": VALID_INITIAL_COOKIES}
    initial_response = await async_client.post("/sync/initial", json=initial_request_body)
    assert initial_response.status_code == 201

    # --- 2. Perform Session Refresh ---
    mock_extractor_refresh = mocker.AsyncMock()
    setup_extractor_mock = mocker.patch("glasir_api.main._setup_extractor", return_value=(mock_extractor_refresh, MOCK_TEACHER_MAP, "Refreshed Lname"))
    refresh_request_body = {"student_id": TEST_STUDENT_ID, "new_cookies": VALID_REFRESH_COOKIES}
    refresh_response = await async_client.post("/session/refresh", json=refresh_request_body)
    assert refresh_response.status_code == 200
    new_access_code = refresh_response.json()["access_code"]

    # --- 3. Prepare for Sync Request using New Access Code ---
    # Mock get_multiple_weeks for the sync call. Let's simulate no changes this time.
    # Use the MOCK_INITIAL_TIMETABLE_DATA as if Glasir returned the same data as initial sync.
    get_weeks_mock = mocker.patch("glasir_api.main.get_multiple_weeks", return_value=MOCK_INITIAL_TIMETABLE_DATA)

    sync_offsets = [0, 1]
    sync_request_body = {"offsets": sync_offsets}
    headers = {"X-Access-Code": new_access_code} # Use the NEW access code

    # --- 4. Make Sync API Request ---
    sync_response = await async_client.post("/sync", json=sync_request_body, headers=headers)

    # --- 5. Assert Sync Response ---
    assert sync_response.status_code == 200
    sync_data = sync_response.json()
    assert "diffs" in sync_data
    diffs = sync_data["diffs"]
    assert MOCK_WEEK_17_INFO.week_key in diffs
    assert MOCK_WEEK_18_INFO.week_key in diffs
    # Expect empty diffs as we mocked get_multiple_weeks to return the original data
    diff_w17 = WeekDiff(**diffs[MOCK_WEEK_17_INFO.week_key])
    assert not diff_w17.added and not diff_w17.removed and not diff_w17.updated
    diff_w18 = WeekDiff(**diffs[MOCK_WEEK_18_INFO.week_key])
    assert not diff_w18.added and not diff_w18.removed and not diff_w18.updated

    # --- 6. Verify Mocks ---
    # get_multiple_weeks called twice (initial, sync)
    assert get_weeks_mock.call_count == 2
    # Check the second call (sync) used the REFRESHED cookies from the DB
    get_weeks_mock.assert_called_with(
        username="sync",
        student_id=TEST_STUDENT_ID,
        cookies_str=VALID_REFRESH_COOKIES, # IMPORTANT: Check it uses the refreshed cookies
        requested_offsets=sync_offsets,
        shared_client=mocker.ANY,
        db=mocker.ANY
    )
    # _setup_extractor called twice (initial, refresh)
    assert setup_extractor_mock.call_count == 2
@pytest.mark.asyncio
async def test_initial_sync_invalid_cookies(async_client: httpx.AsyncClient, mocker):
    """
    Test POST /sync/initial with invalid cookies.
    Expects a 401 Unauthorized response.
    """
    # --- Mock External Dependencies ---
    # Mock _setup_extractor to raise an HTTPException simulating invalid cookies
    setup_extractor_mock = mocker.patch(
        "glasir_api.main._setup_extractor", # Absolute path
        side_effect=HTTPException(status_code=401, detail="Invalid Glasir cookies.")
    )

    # --- Make API Request ---
    request_body = {
        "student_id": TEST_STUDENT_ID,
        "cookies": INVALID_COOKIES # Use invalid cookies
    }
    response = await async_client.post("/sync/initial", json=request_body)

    # --- Assert Response ---
    assert response.status_code == 401
    assert "Invalid Glasir cookies" in response.json()["detail"] # Check detail message if needed

    # Verify mock was called
    setup_extractor_mock.assert_called_once_with(INVALID_COOKIES, mocker.ANY, mocker.ANY)
@pytest.mark.asyncio
async def test_initial_sync_user_already_exists(async_client: httpx.AsyncClient, app_with_db: FastAPI, mocker): # Use app_with_db
    """
    Test POST /sync/initial when a user session already exists for the student_id.
    Expects a 409 Conflict response.
    """
    # --- 1. Perform Initial Sync (Setup) ---
    # Mock dependencies for the first successful initial sync
    mock_extractor = mocker.AsyncMock()
    # Use absolute path patching
    mocker.patch("glasir_api.main._setup_extractor", return_value=(mock_extractor, MOCK_TEACHER_MAP, "Test Lname"))
    mock_extractor.fetch_week_html.return_value = MOCK_HTML_OFFSET_0
    mocker.patch("glasir_api.main.get_multiple_weeks", return_value=MOCK_INITIAL_TIMETABLE_DATA)

    initial_request_body = {"student_id": TEST_STUDENT_ID, "cookies": VALID_INITIAL_COOKIES}
    first_response = await async_client.post("/sync/initial", json=initial_request_body)
    assert first_response.status_code == 201 # Verify the first sync succeeded

    # --- 2. Attempt Second Initial Sync for Same User ---
    # Mocks might need to be reset or re-patched if they were consumed,
    # but for this test, the endpoint should fail before hitting them again.
    # Let's assume the mocks are still in place or re-patch if needed.
    mocker.patch("glasir_api.main._setup_extractor", return_value=(mock_extractor, MOCK_TEACHER_MAP, "Test Lname")) # Re-patch just in case

    second_request_body = {
        "student_id": TEST_STUDENT_ID, # Same student ID
        "cookies": VALID_INITIAL_COOKIES # Doesn't matter if cookies are same or different here
    }
    second_response = await async_client.post("/sync/initial", json=second_request_body)

    # --- 3. Assert Response ---
    assert second_response.status_code == 409
    assert f"A session already exists for student ID {TEST_STUDENT_ID}" in second_response.json()["detail"]

    # --- 4. Assert Database State (Optional: verify no new session created) ---
    # Count sessions for the user, should still be 1
    count_query = sqlalchemy.select(sqlalchemy.func.count()).select_from(UserSession.__table__).where(UserSession.__table__.c.student_id == TEST_STUDENT_ID) # Use Class.__table__
    session_count = await app_with_db.state.database.fetch_val(count_query) # Use app state db
    assert session_count == 1
@pytest.mark.asyncio
async def test_sync_invalid_access_code(async_client: httpx.AsyncClient, app_with_db: FastAPI): # Add app_with_db fixture explicitly
    """
    Test POST /sync with an invalid/non-existent access code.
    Expects a 403 Forbidden response.
    """
    # --- Prepare Request ---
    invalid_access_code = "this-code-does-not-exist"
    sync_offsets = [0] # Offsets don't matter much here
    sync_request_body = {"offsets": sync_offsets}
    headers = {"X-Access-Code": invalid_access_code}

    # --- Make API Request ---
    sync_response = await async_client.post("/sync", json=sync_request_body, headers=headers)

    # --- Assert Response ---
    assert sync_response.status_code == 403
    assert "Invalid access code" in sync_response.json()["detail"]
@pytest.mark.asyncio
async def test_sync_expired_cookies(async_client: httpx.AsyncClient, app_with_db: FastAPI, mocker): # Use app_with_db
    """
    Test POST /sync when the session cookies are older than 24 hours.
    Expects a 401 Unauthorized response with error_code 'COOKIES_EXPIRED'.
    """
    # --- 1. Perform Initial Sync (Setup) ---
    mock_extractor = mocker.AsyncMock()
    mocker.patch("glasir_api.main._setup_extractor", return_value=(mock_extractor, MOCK_TEACHER_MAP, "Test Lname"))
    mock_extractor.fetch_week_html.return_value = MOCK_HTML_OFFSET_0
    mocker.patch("glasir_api.main.get_multiple_weeks", return_value=MOCK_INITIAL_TIMETABLE_DATA)

    initial_request_body = {"student_id": TEST_STUDENT_ID, "cookies": VALID_INITIAL_COOKIES}
    initial_response = await async_client.post("/sync/initial", json=initial_request_body)
    assert initial_response.status_code == 201
    access_code = initial_response.json()["access_code"]

    # --- 2. Manually Update Timestamp in DB to Simulate Expiry ---
    # Set created_at (or cookies_updated_at if implemented) to > 24 hours ago
    expired_time = datetime.now(timezone.utc) - timedelta(hours=25)
    update_query = (
        UserSession.__table__.update() # Use Class.__table__
        .where(UserSession.__table__.c.access_code == access_code)
        .values(
            # Update both just in case, depending on which one the logic checks primarily
            created_at=expired_time,
            cookies_updated_at=expired_time
        )
    )
    await app_with_db.state.database.execute(update_query) # Use app state db
    print(f"Updated session timestamp for {access_code} to {expired_time}")

    # --- 3. Prepare Sync Request ---
    sync_offsets = [0]
    sync_request_body = {"offsets": sync_offsets}
    headers = {"X-Access-Code": access_code}

    # --- 4. Make Sync API Request ---
    sync_response = await async_client.post("/sync", json=sync_request_body, headers=headers)

    # --- 5. Assert Response ---
    assert sync_response.status_code == 401
    response_detail = sync_response.json()["detail"]
    # The detail might be a dict if using the custom structure
    if isinstance(response_detail, dict):
        assert response_detail.get("detail") == "Cookies expired"
        assert response_detail.get("error_code") == "COOKIES_EXPIRED"
    else: # Fallback if detail is just a string
        assert "Cookies expired" in response_detail
@pytest.mark.asyncio
async def test_session_refresh_invalid_cookies(async_client: httpx.AsyncClient, app_with_db: FastAPI, mocker): # Use app_with_db
    """
    Test POST /session/refresh with invalid new_cookies.
    Expects a 401 Unauthorized response.
    """
    # --- 1. Perform Initial Sync (Setup) ---
    # Need a valid session to exist first
    mock_extractor_initial = mocker.AsyncMock()
    mocker.patch("glasir_api.main._setup_extractor", return_value=(mock_extractor_initial, MOCK_TEACHER_MAP, "Test Lname"))
    mock_extractor_initial.fetch_week_html.return_value = MOCK_HTML_OFFSET_0
    mocker.patch("glasir_api.main.get_multiple_weeks", return_value=MOCK_INITIAL_TIMETABLE_DATA)

    initial_request_body = {"student_id": TEST_STUDENT_ID, "cookies": VALID_INITIAL_COOKIES}
    initial_response = await async_client.post("/sync/initial", json=initial_request_body)
    assert initial_response.status_code == 201

    # --- 2. Prepare for Session Refresh with Invalid Cookies ---
    # Mock _setup_extractor to raise an exception when called with INVALID_COOKIES
    setup_extractor_mock = mocker.patch(
        "glasir_api.main._setup_extractor",
        side_effect=HTTPException(status_code=401, detail="Invalid Glasir cookies.")
    )

    refresh_request_body = {
        "student_id": TEST_STUDENT_ID,
        "new_cookies": INVALID_COOKIES # Use invalid cookies for the refresh attempt
    }

    # --- 3. Make Session Refresh API Request ---
    refresh_response = await async_client.post("/session/refresh", json=refresh_request_body)

    # --- 4. Assert Refresh Response ---
    assert refresh_response.status_code == 401
    # Check the detail message (might be generic to avoid leaking info)
    assert "Invalid new_cookies provided" in refresh_response.json()["detail"]

    # --- 5. Verify Mocks ---
    # _setup_extractor should have been called twice (initial, refresh attempt)
    assert setup_extractor_mock.call_count == 2
    # Check the second call specifically (for the refresh attempt)
    setup_extractor_mock.assert_called_with(INVALID_COOKIES, mocker.ANY, mocker.ANY)

    # --- 6. Assert Database State (Optional: verify session wasn't updated) ---
    session_query = UserSession.__table__.select().where(UserSession.__table__.c.student_id == TEST_STUDENT_ID) # Use Class.__table__
    db_session_record = await app_with_db.state.database.fetch_one(session_query) # Use app state db
    assert db_session_record is not None
    # Ensure cookies and access code remain unchanged from initial sync
    assert db_session_record["cookies_json"] == VALID_INITIAL_COOKIES # Check correct column name
    assert db_session_record["access_code"] == initial_response.json()["access_code"]
@pytest.mark.asyncio
async def test_session_refresh_user_not_found(async_client: httpx.AsyncClient, mocker):
    """
    Test POST /session/refresh for a student_id that does not exist.
    Expects a 404 Not Found response.
    """
    # --- Prepare Request ---
    non_existent_student_id = "student_does_not_exist_404"
    # Mock _setup_extractor to succeed, as the check for user existence happens later
    mock_extractor_refresh = mocker.AsyncMock()
    # Use absolute path patching
    setup_extractor_mock = mocker.patch("glasir_api.main._setup_extractor", return_value=(mock_extractor_refresh, MOCK_TEACHER_MAP, "Refreshed Lname"))

    refresh_request_body = {
        "student_id": non_existent_student_id,
        "new_cookies": VALID_REFRESH_COOKIES # Cookies are valid, but user doesn't exist
    }

    # --- Make API Request ---
    refresh_response = await async_client.post("/session/refresh", json=refresh_request_body)

    # --- Assert Response ---
    assert refresh_response.status_code == 404
    assert f"User session not found for student ID {non_existent_student_id}" in refresh_response.json()["detail"]

    # --- Verify Mocks ---
    # _setup_extractor should still be called once to validate cookies before checking DB
    setup_extractor_mock.assert_called_once_with(VALID_REFRESH_COOKIES, mocker.ANY, mocker.ANY)
@pytest.mark.asyncio
async def test_sync_missing_access_code(async_client: httpx.AsyncClient):
    """
    Test POST /sync without providing the X-Access-Code header.
    Expects a 401 Unauthorized response.
    """
    # --- Prepare Request ---
    sync_offsets = [0]
    sync_request_body = {"offsets": sync_offsets}
    # No headers provided

    # --- Make API Request ---
    sync_response = await async_client.post("/sync", json=sync_request_body) # No headers argument

    # --- Assert Response ---
    assert sync_response.status_code == 401
    assert "Missing X-Access-Code header" in sync_response.json()["detail"]
@pytest.mark.asyncio
async def test_initial_sync_invalid_body(async_client: httpx.AsyncClient):
    """
    Test POST /sync/initial with an invalid request body (missing student_id).
    Expects a 422 Unprocessable Entity response.
    """
    # --- Prepare Request ---
    invalid_request_body = {
        # Missing "student_id"
        "cookies": VALID_INITIAL_COOKIES
    }

    # --- Make API Request ---
    response = await async_client.post("/sync/initial", json=invalid_request_body)

    # --- Assert Response ---
    assert response.status_code == 422 # FastAPI's validation error code
    response_data = response.json()
    assert "detail" in response_data
    # Check that the detail indicates the missing field
    assert any("student_id" in error["loc"] and "Field required" in error["msg"] for error in response_data["detail"])
@pytest.mark.asyncio
async def test_sync_glasir_fetch_failure(async_client: httpx.AsyncClient, app_with_db: FastAPI, mocker): # Use app_with_db
    """
    Test POST /sync when the underlying call to fetch data from Glasir fails.
    Expects a 5xx error response (e.g., 502 Bad Gateway or 504 Gateway Timeout).
    """
    # --- 1. Perform Initial Sync (Setup) ---
    mock_extractor_initial = mocker.AsyncMock()
    # Use absolute path patching
    mocker.patch("glasir_api.main._setup_extractor", return_value=(mock_extractor_initial, MOCK_TEACHER_MAP, "Test Lname"))
    mock_extractor_initial.fetch_week_html.return_value = MOCK_HTML_OFFSET_0
    mocker.patch("glasir_api.main.get_multiple_weeks", return_value=MOCK_INITIAL_TIMETABLE_DATA)

    initial_request_body = {"student_id": TEST_STUDENT_ID, "cookies": VALID_INITIAL_COOKIES}
    initial_response = await async_client.post("/sync/initial", json=initial_request_body)
    assert initial_response.status_code == 201
    access_code = initial_response.json()["access_code"]

    # --- 2. Prepare for Sync Request with Fetch Failure ---
    # Mock get_multiple_weeks to raise an httpx error
    mocker.patch(
        "glasir_api.main.get_multiple_weeks", # Absolute path
        side_effect=httpx.RequestError("Simulated network error connecting to Glasir", request=mocker.Mock()) # Provide a mock request object
    )

    sync_offsets = [0, 1]
    sync_request_body = {"offsets": sync_offsets}
    headers = {"X-Access-Code": access_code}

    # --- 3. Make Sync API Request ---
    sync_response = await async_client.post("/sync", json=sync_request_body, headers=headers)

    # --- 4. Assert Sync Response ---
    # The exact status code might depend on the specific error handling in main.py
    # Expecting 502 or 504 based on current error handling for httpx errors
    assert sync_response.status_code in [502, 504]
    assert "Failed to fetch requested weeks from Glasir" in sync_response.json()["detail"] or \
           "Network error fetching requested weeks from Glasir" in sync_response.json()["detail"]

    # --- 5. Assert Database State (Optional: verify state wasn't updated) ---
    # Check that the state for week 17 still matches the initial sync data
    state_query_w17 = WeeklyTimetableState.__table__.select().where( # Use Class.__table__
        (WeeklyTimetableState.__table__.c.student_id == TEST_STUDENT_ID) &
        (WeeklyTimetableState.__table__.c.week_key == MOCK_WEEK_17_INFO.week_key)
    )
    db_state_record_w17 = await app_with_db.state.database.fetch_one(state_query_w17) # Use app state db
    assert db_state_record_w17 is not None
    stored_data_w17 = TimetableData.model_validate_json(db_state_record_w17["week_data_json"]) # Check correct column name
    assert len(stored_data_w17.events) == 1 # Should still be the initial event count
    # Convert list of events to dict keyed by lesson_id for easier lookup
    events_dict_w17_initial = {event.lesson_id: event for event in stored_data_w17.events}
    assert MOCK_EVENT_W17_1.lesson_id in events_dict_w17_initial # Check using lesson_id