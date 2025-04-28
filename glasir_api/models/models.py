# glasir_api/models/models.py
from datetime import datetime
from typing import List, Optional, Union
from pydantic import BaseModel, Field, model_validator, validator

class StudentInfo(BaseModel):
    student_name: str = Field(..., alias="studentName")
    class_: str = Field(..., alias="class")

    class Config:
        populate_by_name = True
        frozen = True
        json_schema_extra = {"example": {"studentName": "John Doe", "class": "22y"}}

class WeekInfo(BaseModel):
    week_number: int = Field(..., alias="weekNumber")
    start_date: str = Field(..., alias="startDate")
    end_date: str = Field(..., alias="endDate")
    year: int
    offset: Optional[int] = None # Added offset field
    week_key: Optional[str] = Field(None, alias="weekKey")

    @validator("start_date", "end_date")
    def validate_date_format(cls, v):
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except ValueError:
            raise ValueError("Date must be in ISO format (YYYY-MM-DD)")

    @validator("week_number")
    def validate_week_number(cls, v):
        if not 1 <= v <= 53:
            raise ValueError("Week number must be between 1 and 53")
        return v

    @model_validator(mode="after")
    def generate_week_key(self):
        if not self.week_key:
            self.week_key = f"{self.year}-W{self.week_number:02d}"
        return self

    class Config:
        populate_by_name = True
        # frozen = True # Removed to allow modification by model_validator
        json_schema_extra = {
            "example": {
                "weekNumber": 13,
                "startDate": "2025-03-24",
                "endDate": "2025-03-30",
                "year": 2025,
                "offset": 0, # Added example for offset
                "weekKey": "2025-W13",
            }
        }

class Event(BaseModel):
    title: str
    level: str
    year: Optional[str] # Made year optional
    date: Optional[str] # Allow date to be optional if parsing fails
    day_of_week: str = Field(..., alias="dayOfWeek") # Renamed from 'day'
    teacher: str
    teacher_short: str = Field(..., alias="teacherShort")
    location: str
    time_slot: Union[int, str] = Field(..., alias="timeSlot")
    start_time: Optional[str] = Field(..., alias="startTime") # Allow optional
    end_time: Optional[str] = Field(..., alias="endTime") # Allow optional
    time_range: str = Field(..., alias="timeRange")
    cancelled: bool = False
    lesson_id: Optional[str] = Field(None, alias="lessonId")
    description: Optional[str] = None
    has_homework_note: bool = Field(False, alias="hasHomeworkNote") # Added from parser logic

    @validator("date")
    def validate_date_format(cls, v):
        # Allow None for date validation if needed, or handle upstream
        if v is None:
            return v
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except ValueError:
            raise ValueError("Date must be in ISO format (YYYY-MM-DD)")

    @validator("start_time", "end_time")
    def validate_time_format(cls, v):
        if not v or not isinstance(v, str):
            return v # Allow None or non-string values if needed
        try:
            datetime.strptime(v, "%H:%M")
            return v
        except ValueError:
            # Consider logging a warning instead of raising an error for flexibility
            # print(f"Warning: Time '{v}' is not in HH:MM format")
            # return v # Or return None, or raise error depending on strictness needed
            raise ValueError("Time must be in HH:MM format")


    class Config:
        populate_by_name = True
        frozen = False # Set to False to allow modification (e.g., adding description)
        json_schema_extra = {
            "example": {
                "title": "evf",
                "level": "A",
                "year": "2024-2025",
                "date": "2025-03-24",
                "dayOfWeek": "Monday",
                "teacher": "Brynjálvur I. Johansen",
                "teacherShort": "BIJ",
                "location": "608",
                "timeSlot": 2,
                "startTime": "10:05",
                "endTime": "11:35",
                "timeRange": "10:05-11:35",
                "cancelled": False,
                "lessonId": "12345678-1234-1234-1234-123456789012",
                "description": "Homework text goes here.",
                "hasHomeworkNote": True,
            }
        }

class TimetableData(BaseModel):
    student_info: StudentInfo = Field(..., alias="studentInfo")
    events: List[Event]
    week_info: WeekInfo = Field(..., alias="weekInfo")
    format_version: int = Field(2, alias="formatVersion") # Keep version consistent

    @validator("format_version")
    def validate_format_version(cls, v):
        # Adjust expected version if needed
        if v != 2:
            raise ValueError("Format version must be 2")
        return v

    class Config:
        populate_by_name = True
        frozen = False # Set to False to allow modification