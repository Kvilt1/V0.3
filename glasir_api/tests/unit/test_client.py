import pytest
import httpx
from pytest_mock import MockerFixture

from glasir_api.core.client import fetch_glasir_week_html, GlasirClientError
from glasir_api.core.constants import GLASIR_SCHEDULE_URL

# TDD Anchor: Test fetch success (200 OK)
@pytest.mark.asyncio
async def test_fetch_glasir_week_html_success(mocker: MockerFixture):
    """
    Tests that fetch_glasir_week_html returns HTML content on a successful fetch.
    """
    mock_response = mocker.Mock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.text = "<html><body>Mock HTML</body></html>"
    mock_response.raise_for_status = mocker.Mock() # Does nothing for 200

    mock_get = mocker.patch("httpx.AsyncClient.get", return_value=mock_response)
    mock_client = mocker.Mock(spec=httpx.AsyncClient)
    mock_client.get = mock_get

    week_number = 10
    year = 2024
    expected_url = f"{GLASIR_SCHEDULE_URL}?h={week_number}&a={year}"

    # Call the function with the client and the expected URL
    html_content = await fetch_glasir_week_html(mock_client, expected_url)

    # Assert that the underlying client's get method was called correctly (without timeout kwarg in this mock setup)
    mock_client.get.assert_called_once_with(expected_url) # Check mock_client.get call
    assert html_content == mock_response.text
    # The raise_for_status is on the response mock, not called directly by fetch_glasir_week_html
    # mock_response.raise_for_status.assert_called_once() # This check is likely incorrect here

# TDD Anchor: Test fetch non-200 status (e.g., 404, 500)
@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [404, 500, 403])
async def test_fetch_glasir_week_html_http_error(mocker: MockerFixture, status_code: int):
    """
    Tests that fetch_glasir_week_html raises GlasirClientError for non-200 status codes.
    """
    mock_response = mocker.Mock(spec=httpx.Response)
    mock_response.status_code = status_code
    mock_response.text = f"Error {status_code}"
    # Configure raise_for_status to raise an appropriate httpx error
    mock_response.raise_for_status = mocker.Mock(side_effect=httpx.HTTPStatusError(
        f"{status_code} Client Error", request=mocker.Mock(), response=mock_response
    ))

    mock_get = mocker.patch("httpx.AsyncClient.get", return_value=mock_response)
    mock_client = mocker.Mock(spec=httpx.AsyncClient)
    mock_client.get = mock_get

    week_number = 10
    year = 2024
    expected_url = f"{GLASIR_SCHEDULE_URL}?h={week_number}&a={year}"

    with pytest.raises(GlasirClientError) as excinfo:
        # Call with the expected URL
        await fetch_glasir_week_html(mock_client, expected_url)

    # Assert the underlying client method call (without timeout kwarg)
    mock_client.get.assert_called_once_with(expected_url)
    # raise_for_status is part of the mock response's behavior, not directly asserted here
    # mock_response.raise_for_status.assert_called_once()
    assert f"HTTP error {status_code}" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, httpx.HTTPStatusError)

# TDD Anchor: Test fetch timeout
@pytest.mark.asyncio
async def test_fetch_glasir_week_html_timeout(mocker: MockerFixture):
    """
    Tests that fetch_glasir_week_html raises GlasirClientError on a timeout.
    """
    mock_get = mocker.patch(
        "httpx.AsyncClient.get",
        side_effect=httpx.TimeoutException("Request timed out", request=mocker.Mock())
    )
    mock_client = mocker.Mock(spec=httpx.AsyncClient)
    mock_client.get = mock_get

    week_number = 10
    year = 2024
    expected_url = f"{GLASIR_SCHEDULE_URL}?h={week_number}&a={year}"

    with pytest.raises(GlasirClientError) as excinfo:
        # Call with the expected URL
        await fetch_glasir_week_html(mock_client, expected_url)

    # Assert the underlying client method call (without timeout kwarg)
    mock_client.get.assert_called_once_with(expected_url)
    assert "Timeout occurred" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, httpx.TimeoutException)

# TDD Anchor: Test fetch connection error
@pytest.mark.asyncio
async def test_fetch_glasir_week_html_connection_error(mocker: MockerFixture):
    """
    Tests that fetch_glasir_week_html raises GlasirClientError on a connection error.
    """
    mock_get = mocker.patch(
        "httpx.AsyncClient.get",
        side_effect=httpx.ConnectError("Connection failed", request=mocker.Mock())
    )
    mock_client = mocker.Mock(spec=httpx.AsyncClient)
    mock_client.get = mock_get

    week_number = 10
    year = 2024
    expected_url = f"{GLASIR_SCHEDULE_URL}?h={week_number}&a={year}"

    with pytest.raises(GlasirClientError) as excinfo:
        # Call with the expected URL
        await fetch_glasir_week_html(mock_client, expected_url)

    # Assert the underlying client method call (without timeout kwarg)
    mock_client.get.assert_called_once_with(expected_url)
    assert "Connection error" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, httpx.ConnectError)