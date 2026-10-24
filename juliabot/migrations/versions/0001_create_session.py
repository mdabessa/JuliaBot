"""Create the persisted interactive-session table.

This is the first migration owned by the new schema-migration system. The
``session`` table is intentionally excluded from ``Base.metadata.create_all`` so
this script stays the single source of truth for its shape.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

VERSION = 1
NAME = "create_session"


def _timestamp_type(connection: Connection) -> str:
    """Return a timezone-aware timestamp type for the active dialect."""
    if connection.dialect.name == "postgresql":
        return "TIMESTAMP WITH TIME ZONE"
    return "DATETIME"


def upgrade(connection: Connection) -> None:
    """Create the session table and its lookup indexes."""
    timestamp = _timestamp_type(connection)
    connection.execute(
        text(
            f"""
            CREATE TABLE session (
                id VARCHAR(32) NOT NULL PRIMARY KEY,
                kind VARCHAR(128) NOT NULL,
                routing_key VARCHAR(128) NOT NULL UNIQUE,
                trigger VARCHAR(16) NOT NULL,
                owner_id BIGINT NULL,
                guild_id BIGINT NULL,
                channel_id BIGINT NULL,
                message_id BIGINT NULL,
                scope_key VARCHAR(64) NULL,
                payload TEXT NOT NULL,
                created_at {timestamp} NOT NULL,
                last_seen_at {timestamp} NOT NULL,
                expires_at {timestamp} NOT NULL
            )
            """
        )
    )
    connection.execute(text("CREATE INDEX ix_session_kind ON session (kind)"))
    connection.execute(
        text("CREATE INDEX ix_session_expires_at ON session (expires_at)")
    )


def downgrade(connection: Connection) -> None:
    """Drop the session table and everything it stores."""
    connection.execute(text("DROP TABLE session"))
