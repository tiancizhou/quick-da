"""add opencode sessions and events

Revision ID: 0004_opencode_sessions
Revises: 0003_llm_settings
Create Date: 2026-06-26 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite import DATETIME as SQLiteDateTime

revision: str = "0004_opencode_sessions"
down_revision: Union[str, Sequence[str], None] = "0003_llm_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DB_DATETIME = sa.DateTime().with_variant(
    SQLiteDateTime(storage_format="%(year)04d-%(month)02d-%(day)02d %(hour)02d:%(minute)02d:%(second)02d"),
    "sqlite",
)


def upgrade() -> None:
    op.add_column("apps", sa.Column("opencode_session_id", sa.String(length=100), nullable=True))
    op.add_column("apps", sa.Column("opencode_workspace", sa.String(length=500), nullable=True))
    op.create_table(
        "opencode_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("app_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", DB_DATETIME, nullable=False),
        sa.ForeignKeyConstraint(["app_id"], ["apps.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_opencode_events_app_sequence", "opencode_events", ["app_id", "sequence"])
    op.create_index("ix_opencode_events_app_created", "opencode_events", ["app_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_opencode_events_app_created", table_name="opencode_events")
    op.drop_index("ix_opencode_events_app_sequence", table_name="opencode_events")
    op.drop_table("opencode_events")
    op.drop_column("apps", "opencode_workspace")
    op.drop_column("apps", "opencode_session_id")
