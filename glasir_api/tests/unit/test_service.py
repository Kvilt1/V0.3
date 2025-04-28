import pytest
import httpx
from pytest_mock import MockerFixture

from glasir_api.core.service import fetch_and_parse_single_week
from glasir_api.core.client import GlasirClientError
from glasir_api.core.parsers import GlasirParserError
from glasir_api.models.models import Event  # Assuming this is the correct model

# --- Mock Data ---
MOCK_HTML_WITH_DATA = "<html><body>...event data...</body></html>"
MOCK_HTML_NO_DATA = "<html><body>Engar tímar</body></html>"
MOCK_PARSED_EVENTS = [
    Event(
        title="Test Subject",
        level="A",
        year="2024-2025", # Example academic year
        date="2024-04-15", # Example date
        dayOfWeek="Monday",
        teacher="Test Teacher",
        teacherShort="TST",
        location="R001",
        timeSlot=1,
        startTime="08:00",
        endTime="09:00",
        timeRange="08:00-09:00",
        cancelled=False,
        lessonId="mock-lesson-id-123",
        hasHomeworkNote=False,
        description=None
    )
]
MOCK_PARSED_NO_EVENTS = []

# --- Tests ---

# TDD Anchor: Test service success path (fetch ok, parse ok with data)
@pytest.mark.asyncio
async def test_service_success_with_data(mocker: MockerFixture):
    """Tests the happy path where fetch and parse succeed, returning events."""
    mock_fetch = mocker.patch(
        "glasir_api.core.service.fetch_glasir_week_html",
        return_value=MOCK_HTML_WITH_DATA
    )
    mock_parse = mocker.patch(
        "glasir_api.core.service.parse_week_html",
        return_value=MOCK_PARSED_EVENTS
    )
    mock_client = mocker.Mock(spec=httpx.AsyncClient)
    week = 15
    year = 2024

    # Pass teacher_map=None explicitly as it's now part of the signature
    events = await fetch_and_parse_single_week(mock_client, week, year, teacher_map=None)

    mock_fetch.assert_called_once_with(mock_client, week, year)
    # Assert mock_parse was called with HTML and the teacher_map (which is None here)
    mock_parse.assert_called_once_with(MOCK_HTML_WITH_DATA, None)
    assert events == MOCK_PARSED_EVENTS

# TDD Anchor: Test service success path (fetch ok, parse ok with no data)
@pytest.mark.asyncio
async def test_service_success_no_data(mocker: MockerFixture):
    """Tests the happy path where fetch succeeds and parse correctly returns no events."""
    mock_fetch = mocker.patch(
        "glasir_api.core.service.fetch_glasir_week_html",
        return_value=MOCK_HTML_NO_DATA
    )
    mock_parse = mocker.patch(
        "glasir_api.core.service.parse_week_html",
        return_value=MOCK_PARSED_NO_EVENTS
    )
    mock_client = mocker.Mock(spec=httpx.AsyncClient)
    week = 16
    year = 2024

    # Pass teacher_map=None explicitly
    events = await fetch_and_parse_single_week(mock_client, week, year, teacher_map=None)

    mock_fetch.assert_called_once_with(mock_client, week, year)
    # Assert mock_parse was called with HTML and the teacher_map (None)
    mock_parse.assert_called_once_with(MOCK_HTML_NO_DATA, None)
    assert events == MOCK_PARSED_NO_EVENTS

# TDD Anchor: Test service failure path (fetch fails)
@pytest.mark.asyncio
async def test_service_failure_fetch_fails(mocker: MockerFixture):
    """Tests that the service propagates client errors when fetching fails."""
    fetch_exception = GlasirClientError("Fetch failed", original_exception=httpx.TimeoutException("timeout", request=mocker.Mock()))
    mock_fetch = mocker.patch(
        "glasir_api.core.service.fetch_glasir_week_html",
        side_effect=fetch_exception
    )
    mock_parse = mocker.patch("glasir_api.core.service.parse_week_html") # Should not be called
    mock_client = mocker.Mock(spec=httpx.AsyncClient)
    week = 17
    year = 2024

    with pytest.raises(GlasirClientError) as excinfo:
        await fetch_and_parse_single_week(mock_client, week, year)

    mock_fetch.assert_called_once_with(mock_client, week, year)
    mock_parse.assert_not_called()
    assert excinfo.value == fetch_exception # Check if the original exception is re-raised

# TDD Anchor: Test service failure path (fetch ok, parse fails)
@pytest.mark.asyncio
async def test_service_failure_parse_fails(mocker: MockerFixture):
    """Tests that the service propagates parser errors when parsing fails."""
    parse_exception = GlasirParserError("Parse failed", html_content=MOCK_HTML_WITH_DATA)
    mock_fetch = mocker.patch(
        "glasir_api.core.service.fetch_glasir_week_html",
        return_value=MOCK_HTML_WITH_DATA
    )
    mock_parse = mocker.patch(
        "glasir_api.core.service.parse_week_html",
        side_effect=parse_exception
    )
    mock_client = mocker.Mock(spec=httpx.AsyncClient)
    week = 18
    year = 2024

    with pytest.raises(GlasirParserError) as excinfo:
        await fetch_and_parse_single_week(mock_client, week, year)

    mock_fetch.assert_called_once_with(mock_client, week, year)
    # Assert mock_parse was called with HTML and the teacher_map (None)
    mock_parse.assert_called_once_with(MOCK_HTML_WITH_DATA, None)
    assert excinfo.value == parse_exception # Check if the original exception is re-raised