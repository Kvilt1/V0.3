"""Initial migration with UserSession, WeeklyTimetableState, TeacherCache

Revision ID: aaec88858733
Revises: 
Create Date: 2025-04-28 08:05:55.056149

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aaec88858733'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('teacher_cache',
    sa.Column('initials', sa.String(), nullable=False),
    sa.Column('full_name', sa.String(), nullable=False),
    sa.Column('cached_at', sa.DateTime(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('initials')
    )
    op.create_index(op.f('ix_teacher_cache_initials'), 'teacher_cache', ['initials'], unique=False)
    op.create_table('user_sessions',
    sa.Column('student_id', sa.String(), nullable=False),
    sa.Column('access_code', sa.String(), nullable=False),
    sa.Column('access_code_generated_at', sa.DateTime(), nullable=False),
    sa.Column('cookies_json', sa.String(), nullable=False),
    sa.Column('cookies_updated_at', sa.DateTime(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('last_accessed_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('student_id')
    )
    op.create_index(op.f('ix_user_sessions_access_code'), 'user_sessions', ['access_code'], unique=True)
    op.create_index(op.f('ix_user_sessions_student_id'), 'user_sessions', ['student_id'], unique=False)
    op.create_table('weekly_timetable_states',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('student_id', sa.String(), nullable=False),
    sa.Column('week_key', sa.String(), nullable=False),
    sa.Column('week_data_json', sa.String(), nullable=False),
    sa.Column('last_updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['student_id'], ['user_sessions.student_id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('student_id', 'week_key', name='uq_student_week')
    )
    op.create_index(op.f('ix_weekly_timetable_states_student_id'), 'weekly_timetable_states', ['student_id'], unique=False)
    op.create_index(op.f('ix_weekly_timetable_states_week_key'), 'weekly_timetable_states', ['week_key'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_weekly_timetable_states_week_key'), table_name='weekly_timetable_states')
    op.drop_index(op.f('ix_weekly_timetable_states_student_id'), table_name='weekly_timetable_states')
    op.drop_table('weekly_timetable_states')
    op.drop_index(op.f('ix_user_sessions_student_id'), table_name='user_sessions')
    op.drop_index(op.f('ix_user_sessions_access_code'), table_name='user_sessions')
    op.drop_table('user_sessions')
    op.drop_index(op.f('ix_teacher_cache_initials'), table_name='teacher_cache')
    op.drop_table('teacher_cache')
    # ### end Alembic commands ###
