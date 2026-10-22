"""Persistence contracts and an in-memory session store.

The store is intentionally independent from Discord and SQLAlchemy. Phase 1
uses ``MemoryStore`` while preserving the interface that the Postgres store will
implement later.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from .types import JSONValue, TriggerType

if TYPE_CHECKING:
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
