"""Persistence contracts for session snapshots.

``MemoryStore`` keeps snapshots in process memory. ``PostgresStore`` persists
them through SQLAlchemy; the ``session`` table is created and evolved by the
versioned migrations in ``juliabot/migrations``.
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Protocol

from .types import JSONValue, TriggerType

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

    from .session import Session


@dataclass(frozen=True)
class StoredSession:
    """Serializable session metadata and payload."""

    id: str
    kind: str
    routing_key: str
    trigger: TriggerType
    owner_id: int | None
    guild_id: int | None
    channel_id: int | None
    message_id: int | None
    scope_key: object | None
    payload: dict[str, JSONValue]
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime


class SessionStore(Protocol):
    """Persistence operations required by ``SessionManager``."""

    async def load_keys(self) -> list[StoredSession]:
        """Load records needed to rebuild routing indexes."""

    async def load(self, session_id: str) -> StoredSession | None:
        """Load one session record by id."""

    async def save(self, session: Session) -> None:
        """Persist the current session snapshot."""

    async def delete(self, session_id: str) -> None:
        """Delete one session snapshot."""

    async def purge_expired(self, now: datetime) -> int:
        """Delete expired records and return the number removed."""


class MemoryStore:
    """Store session snapshots in process memory for development and tests."""

    def __init__(self) -> None:
        self._records: dict[str, StoredSession] = {}

    async def load_keys(self) -> list[StoredSession]:
        """Return all stored records without mutating them."""
        return list(self._records.values())

    async def load(self, session_id: str) -> StoredSession | None:
        """Return a defensive copy of one stored record."""
        record = self._records.get(session_id)
        return deepcopy(record) if record else None

    async def save(self, session: Session) -> None:
        """Replace a session snapshot atomically in the in-memory map."""
        self._records[session.id] = StoredSession(
            id=session.id,
            kind=session.registration.name,
            routing_key=session.routing_key,
            trigger=session.registration.trigger,
            owner_id=session.owner_id,
            guild_id=session.guild_id,
            channel_id=session.channel_id,
            message_id=session.message_id,
            scope_key=session.scope_key,
            payload=deepcopy(session.to_payload()),
            created_at=session.created_at,
            last_seen_at=session.last_seen_at,
            expires_at=session.expires_at,
        )

    async def delete(self, session_id: str) -> None:
        """Remove a session snapshot if it exists."""
        self._records.pop(session_id, None)

    async def purge_expired(self, now: datetime) -> int:
        """Remove records whose idle deadline has passed."""
        expired = [
            session_id
            for session_id, record in self._records.items()
            if record.expires_at <= now
        ]
        for session_id in expired:
            del self._records[session_id]
        return len(expired)


class PostgresStore:
    """Persist session snapshots through SQLAlchemy.

    The dialect may be Postgres (production) or SQLite (tests); the store only
    uses portable SQL. It owns its ``sessionmaker`` so it never shares the
    global ``models.session`` instance used by the legacy models.
    """

    def __init__(self, engine: "Engine | None" = None) -> None:
        from sqlalchemy.orm import sessionmaker

        from ..models import SessionRecord
        from ..models import engine as default_engine

        self._record = SessionRecord
        self.engine = engine or default_engine
        self._session_factory = sessionmaker(bind=self.engine)

    async def load_keys(self) -> list[StoredSession]:
        """Return non-expired records without loading their payloads."""
        record = self._record
        now = datetime.now(timezone.utc)
        with self._session_factory() as database:
            rows = database.query(record).filter(record.expires_at > now).all()
            return [_to_stored(row) for row in rows]

    async def load(self, session_id: str) -> StoredSession | None:
        """Return one stored record with its payload."""
        with self._session_factory() as database:
            row = database.get(self._record, session_id)
            return _to_stored(row) if row is not None else None

    async def save(self, session: Session) -> None:
        """Insert or update a session snapshot."""
        record = self._record(
            id=session.id,
            kind=session.registration.name,
            routing_key=str(session.routing_key),
            trigger=session.registration.trigger.value,
            owner_id=session.owner_id,
            guild_id=session.guild_id,
            channel_id=session.channel_id,
            message_id=session.message_id,
            scope_key=None if session.scope_key is None else str(session.scope_key),
            payload=json.dumps(session.to_payload()),
            created_at=_as_utc(session.created_at),
            last_seen_at=_as_utc(session.last_seen_at),
            expires_at=_as_utc(session.expires_at),
        )
        with self._session_factory() as database:
            database.merge(record)
            database.commit()

    async def delete(self, session_id: str) -> None:
        """Delete a session snapshot by id."""
        record = self._record
        with self._session_factory() as database:
            database.query(record).filter(record.id == session_id).delete(
                synchronize_session=False
            )
            database.commit()

    async def purge_expired(self, now: datetime) -> int:
        """Delete expired snapshots and return how many were removed."""
        record = self._record
        with self._session_factory() as database:
            removed = (
                database.query(record)
                .filter(record.expires_at <= _as_utc(now))
                .delete(synchronize_session=False)
            )
            database.commit()
            return int(removed)


def _as_utc(value: datetime) -> datetime:
    """Normalise a timestamp to aware UTC for storage."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _as_aware(value: datetime) -> datetime:
    """Attach UTC to naive timestamps returned by SQLite."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _scope_value(value: str | None) -> object | None:
    """Restore numeric scope keys to integers when possible."""
    if value is None:
        return None
    return int(value) if value.lstrip("-").isdigit() else value


def _to_stored(row) -> StoredSession:
    """Convert an ORM row into the transport-independent record."""
    return StoredSession(
        id=row.id,
        kind=row.kind,
        routing_key=row.routing_key,
        trigger=TriggerType(row.trigger),
        owner_id=row.owner_id,
        guild_id=row.guild_id,
        channel_id=row.channel_id,
        message_id=row.message_id,
        scope_key=_scope_value(row.scope_key),
        payload=json.loads(row.payload or "{}"),
        created_at=_as_aware(row.created_at),
        last_seen_at=_as_aware(row.last_seen_at),
        expires_at=_as_aware(row.expires_at),
    )
