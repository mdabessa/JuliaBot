"""Store reminder trigger times as timezone-aware timestamps.

``reminder.time_reminder`` was created as ``TIMESTAMP WITHOUT TIME ZONE``, so an
aware UTC value written to it was stored with its offset silently dropped. On
PostgreSQL this migration reinterprets the existing naive values as UTC and
switches the column to ``TIMESTAMP WITH TIME ZONE``.

Other dialects cannot ``ALTER COLUMN TYPE`` in place; there the column keeps its
type and the application reads stored values as UTC (see
``juliabot.models.as_utc``).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

VERSION = 2
NAME = "reminder_timestamptz"

TABLE = "reminder"
COLUMN = "time_reminder"


def _can_retype(connection: Connection) -> bool:
    """Return whether the reminder column can be retyped in place."""
    return connection.dialect.name == "postgresql" and connection.dialect.has_table(
        connection, TABLE
    )


def upgrade(connection: Connection) -> None:
    """Make the column timezone-aware, reading existing values as UTC."""
    if not _can_retype(connection):
        return

    connection.execute(
        text(
            f"""
            ALTER TABLE {TABLE}
              ALTER COLUMN {COLUMN} TYPE timestamp with time zone
              USING {COLUMN} AT TIME ZONE 'UTC'
            """
        )
    )


def downgrade(connection: Connection) -> None:
    """Restore the naive column, keeping the UTC wall clock it already holds."""
    if not _can_retype(connection):
        return

    connection.execute(
        text(
            f"""
            ALTER TABLE {TABLE}
              ALTER COLUMN {COLUMN} TYPE timestamp without time zone
              USING {COLUMN} AT TIME ZONE 'UTC'
            """
        )
    )
