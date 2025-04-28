import pytest
from bs4 import BeautifulSoup

from glasir_api.core.parsers import parse_week_html, GlasirParserError
from glasir_api.models.models import Event  # Assuming this is the model

# --- Test Data ---
# Added minimal table structure required by the parser
HTML_WITH_EVENTS = """
<html><body>
<table class="time_8_16">
    <tr><td class="lektionslinje_1">Mánadagur 01/01</td>
        <td colspan="24" class="lektionslinje_lesson0">
            <a href="#">SUBJ-A-TEAM-2425</a><br>
            <a href="#">TEA</a><br>
            <a href="#">R101</a>
            <span id="MyWindowLESSONID1Main"></span>
        </td>
        <td colspan="24" class="lektionslinje_lesson0">
            <a href="#">PHYS-B-TEAM-2425</a><br>
            <a href="#">PHY</a><br>
            <a href="#">R202</a>
            <span id="MyWindowLESSONID2Main"></span>
        </td>
    </tr>
</table>
</body></html>
"""

HTML_NO_EVENTS_MESSAGE = """
<html><body>
<p>Engar tímar hesa vikuna</p> {# Explicit message, table might be missing or empty #}
{# Option 1: Table missing (parser should handle this) #}
{# Option 2: Table present but empty #}
<table class="time_8_16">
    <tr><td class="lektionslinje_1">Mánadagur 01/01</td></tr>
</table>
</body></html>
"""

HTML_VALID_STRUCTURE_NO_EVENTS = """
<html><body>
<table class="time_8_16">
    <tr><td class="lektionslinje_1">Mánadagur 01/01</td></tr>
    <tr><td class="lektionslinje_1">Týsdagur 02/01</td></tr>
</table>
</body></html>
"""

HTML_INVALID_STRUCTURE = """
<html><body><div>Missing schedule table</div></body></html>
""" # This HTML intentionally lacks the table.time_8_16

HTML_PARTIAL_EVENT = """
<html><body>
<table class="time_8_16">
    <tr><td class="lektionslinje_1">Mánadagur 01/01</td>
        <td colspan="24" class="lektionslinje_lesson0">
             {# Missing links, potentially missing ID span #}
             Incomplete Data
        </td>
         <td colspan="24" class="lektionslinje_lesson0">
             <a href="#">GOOD-A-TEAM-2425</a><br>
             <a href="#">OKT</a><br>
             {# Missing room link #}
             <span id="MyWindowLESSONID3Main"></span>
        </td>
    </tr>
</table>
</body></html>
"""

# --- Tests ---

# TDD Anchor: Test parse success with events
def test_parse_week_html_success_with_events():
    """Tests parsing HTML with multiple valid events."""
    events = parse_week_html(HTML_WITH_EVENTS)
    assert len(events) == 2
    assert isinstance(events[0], Event)
    assert events[0].title == "SUBJ" # Based on updated HTML
    assert events[0].level == "A"
    assert events[0].teacher_short == "TEA"
    assert events[0].location == "R101"
    assert events[0].lesson_id == "LESSONID1"
    # Add checks for the second event
    assert isinstance(events[1], Event)
    assert events[1].title == "PHYS"
    assert events[1].teacher_short == "PHY"
    assert events[1].location == "R202"
    assert events[1].lesson_id == "LESSONID2"
    # Add more assertions for the second event if needed

# TDD Anchor: Test parse success with explicit 'no events' message
def test_parse_week_html_success_explicit_no_events():
    """Tests parsing HTML containing a specific 'no events' message."""
    events = parse_week_html(HTML_NO_EVENTS_MESSAGE)
    assert events == []

# TDD Anchor: Test parse success with valid structure but no event elements
def test_parse_week_html_success_valid_structure_no_events():
    """Tests parsing valid HTML structure that simply lacks event elements."""
    events = parse_week_html(HTML_VALID_STRUCTURE_NO_EVENTS)
    assert events == []

# TDD Anchor: Test parse failure with empty/None input
@pytest.mark.parametrize("invalid_input", [None, "", " "])
def test_parse_week_html_failure_empty_input(invalid_input):
    """Tests that parsing fails gracefully with empty or None input."""
    with pytest.raises(GlasirParserError, match="Input HTML content is empty or invalid"):
        parse_week_html(invalid_input)

# TDD Anchor: Test parse failure with invalid HTML (missing main structure)
def test_parse_week_html_failure_invalid_html_structure():
    """Tests parsing HTML that lacks the expected main structure."""
    # This might depend on how robust the parser is.
    # Expect error because the main table is missing
    with pytest.raises(GlasirParserError, match="Could not find main schedule container"):
         parse_week_html(HTML_INVALID_STRUCTURE)


# TDD Anchor: Test parse with partial data warnings (or failure)
def test_parse_week_html_partial_data():
    """
    Tests parsing HTML where event data is incomplete.
    Depending on implementation, this might raise an error or skip the partial event.
    Assuming it should raise an error for missing critical data like end_time.
    """
    # Expect an empty list because the parser skips events with insufficient links/data
    events = parse_week_html(HTML_PARTIAL_EVENT)
    assert events == []