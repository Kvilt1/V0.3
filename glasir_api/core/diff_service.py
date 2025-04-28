from typing import List, Optional, Dict, Set
from glasir_api.models.models import TimetableData, Event
from glasir_api.models.api_models import WeekDiff

def calculate_week_diff(old_week_data: Optional[TimetableData], new_week_data: TimetableData) -> WeekDiff:
    """
    Calculates the difference between an old and new version of timetable data for a specific week.

    Compares events based on their `lessonId`.

    Args:
        old_week_data: The previously stored TimetableData for the week, or None if it's the first time seeing this week.
        new_week_data: The newly fetched TimetableData for the week.

    Returns:
        A WeekDiff object detailing the added, updated, and removed events.
    """
    added: List[Event] = []
    updated: List[Event] = []
    removed: List[str] = []

    old_events_dict: Dict[str, Event] = {}
    if old_week_data and old_week_data.events:
        # Use the correct attribute name 'lesson_id'
        old_events_dict = {event.lesson_id: event for event in old_week_data.events if event.lesson_id}

    new_events_dict: Dict[str, Event] = {}
    if new_week_data.events:
        # Use the correct attribute name 'lesson_id'
        new_events_dict = {event.lesson_id: event for event in new_week_data.events if event.lesson_id}

    old_lesson_ids: Set[str] = set(old_events_dict.keys())
    new_lesson_ids: Set[str] = set(new_events_dict.keys())

    # Find added events (in new but not in old)
    added_ids = new_lesson_ids - old_lesson_ids
    for lesson_id in added_ids:
        added.append(new_events_dict[lesson_id])

    # Find removed events (in old but not in new)
    removed_ids = old_lesson_ids - new_lesson_ids
    removed.extend(list(removed_ids)) # Store only the IDs

    # Find potentially updated events (in both old and new)
    potential_update_ids = old_lesson_ids.intersection(new_lesson_ids)
    for lesson_id in potential_update_ids:
        old_event = old_events_dict[lesson_id]
        new_event = new_events_dict[lesson_id]

        # Simple comparison: if the event objects are not identical, consider it updated.
        # A more granular comparison could be implemented here if needed,
        # checking specific fields like time, room, teacher, etc.
        if old_event != new_event:
            updated.append(new_event) # Add the new version of the event

    return WeekDiff(added=added, updated=updated, removed=removed)