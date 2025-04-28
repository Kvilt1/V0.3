from pydantic import BaseModel, Field
from typing import List, Dict, Any, Union, Literal # Added Union, Literal
from .models import Event

# Import the core TimetableData model
from .models import TimetableData


class InitialSyncRequest(BaseModel):
    """
    Request body for the initial synchronization endpoint.
    """
    student_id: str = Field(..., description="The student's unique identifier (e.g., '12345a').")
    # Keep cookies as List[Dict] for initial sync as it comes directly from Playwright
    cookies: List[Dict[str, Any]] = Field(..., description="The list of Glasir authentication cookies.")


class InitialSyncResponse(BaseModel):
    """
    Response body for a successful initial synchronization.
    """
    access_code: str = Field(..., description="The newly generated access code for the user session.")
    initial_data: List[TimetableData] = Field(..., description="The complete list of fetched timetable data for all available weeks.")
class WeekDiff(BaseModel):
    """
    Represents the differences found for a single week's timetable data
    compared to a previously stored state.
    """
    added: List[Event] = Field(default_factory=list, description="List of events newly added in this week.")
    updated: List[Event] = Field(default_factory=list, description="List of events that have been updated in this week.")
    removed: List[str] = Field(default_factory=list, description="List of lesson IDs for events that have been removed from this week.")


class SyncRequest(BaseModel):
    """
    Request body for the subsequent synchronization endpoint.
    Specifies which weeks to fetch and compare.
    Can accept a list of integers or special string identifiers.
    """
    student_id: str = Field(..., description="The student's unique identifier.") # Added student_id here
    offsets: Union[List[int], Literal["all", "current_forward"]] = Field(
        ...,
        description="List of week offsets (relative to the current week) or a special string ('all', 'current_forward') to synchronize."
    )


class TempSyncResponse(BaseModel):
    """
    Temporary response body for the synchronization endpoint (Phase 3).
    Returns the raw data fetched for the requested weeks.
    """
from datetime import datetime

class SyncResponse(BaseModel):
    """
    Final response body for the synchronization endpoint (Phase 4).
    Returns the per-week diffs for the requested weeks.
    """
    diffs: Dict[str, WeekDiff] = Field(..., description="Mapping of week_key to the WeekDiff object for that week.")
    synced_at: datetime = Field(..., description="Timestamp of when the sync was completed.")

class SessionRefreshRequest(BaseModel):
    """
    Request body for the session refresh endpoint.
    """
    student_id: str = Field(..., description="The student's unique identifier (e.g., '12345a').")
    new_cookies: str = Field(..., description="The new Glasir authentication cookie string to validate and store.")