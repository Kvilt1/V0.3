import datetime
from sqlalchemy import (
    create_engine, MetaData, Table, Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class TeacherCache(Base):
    __tablename__ = "teacher_cache"

    initials = Column(String, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    cached_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False) # Calculated as cached_at + 1 year in service layer

class UserSession(Base):
    __tablename__ = "user_sessions"

    student_id = Column(String, primary_key=True, index=True)
    access_code = Column(String, unique=True, index=True, nullable=False)
    access_code_generated_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    cookies_json = Column(String, nullable=False) # Store as JSON string
    cookies_updated_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    last_accessed_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

class WeeklyTimetableState(Base):
    __tablename__ = "weekly_timetable_states"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(String, ForeignKey("user_sessions.student_id"), index=True, nullable=False)
    week_key = Column(String, index=True, nullable=False) # e.g., "2024-W35"
    week_data_json = Column(String, nullable=False) # Store TimetableData model as JSON string
    last_updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint('student_id', 'week_key', name='uq_student_week'),
    )

# Example of how to create tables (though Alembic is preferred for migrations)
# DATABASE_URL = "sqlite+aiosqlite:///./glasir_data.db" # Get from config
# engine = create_engine(DATABASE_URL)
# Base.metadata.create_all(bind=engine)