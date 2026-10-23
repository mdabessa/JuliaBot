"""Lifecycle orchestration for registered sessions.

``SessionManager`` owns live instances and is the only layer that applies
registration limits, ownership checks, expiry, and persistence decisions.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable

from .registry import Registry
from .session import Session
from .store import MemoryStore, SessionStore
from .types import InteractionEvent, JSONValue

logger = logging.getLogger(__name__)
Clock = Callable[[], datetime]


class SessionManager:
    """Create, dispatch, expire, and close live sessions."""

    def __init__(
        self,
        registry: Registry,
        store: SessionStore | None = None,
        *,
        clock: Clock | None = None,
    ) -> None:
        self.registry = registry
        self.store = store or MemoryStore()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._sessions_by_key: dict[str, Session] = {}
        self._sessions_by_id: dict[str, Session] = {}

    def _now(self) -> datetime:
        """Return an aware UTC timestamp from the manager clock."""
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("Session clocks must return timezone-aware datetimes")
        return value.astimezone(timezone.utc)

    async def start(
        self,
        name: str,
        event: InteractionEvent,
        *,
        payload: dict[str, JSONValue] | None = None,
    ) -> Session:
        """Create and start a session for a registered interaction.

        Existing sessions over the registration's scope limit are closed from
        oldest to newest before the new session starts.
        """
        registration = self.registry.get(name)
        if registration is None:
            raise KeyError(f"Unknown session registration: {name}")
        if event.key in self._sessions_by_key:
            raise ValueError(f"Session routing key already exists: {event.key}")

        candidates = [
            session
            for session in self._sessions_by_id.values()
            if session.registration.name == name
            and session.scope_key == self._runtime_scope_key(registration, event)
        ]
        if registration.max_per_scope is not None:
            excess = len(candidates) - registration.max_per_scope + 1
            for session in sorted(candidates, key=lambda item: item.created_at)[
                : max(0, excess)
            ]:
                await self.close(session)

        session = registration.session_class(
            registration,
            event,
            payload=payload,
            clock=self._clock,
        )
        session.manager = self
        self._sessions_by_key[event.key] = session
        self._sessions_by_id[session.id] = session
        self._sessions_by_key[session.id] = session
        session.mark_hydrated()

        try:
            await session.start(event)
            if session.closed:
                await self.close(session)
            elif registration.resumable:
                await self.store.save(session)
        except Exception:
            await self.close(session)
            raise

        return session

    @staticmethod
    def _runtime_scope_key(registration, event: InteractionEvent):
        """Return the value used to enforce a registration's live limit."""
        scope = registration.scope.value
        if scope == "user":
            return event.user_id
        if scope == "guild":
            return event.guild_id
        if scope == "channel":
            return event.channel_id
        return None

    async def dispatch(self, event: InteractionEvent) -> bool:
        """Dispatch an event to a known live session.

        Unknown keys return before touching the store. Handler exceptions are
        logged and isolated so one broken interaction cannot abort dispatch for
        other events.
        """
        session = self._sessions_by_key.get(event.key)
        if session is None or session.closed:
            return False
        if session.is_expired(self._now()):
            await self.close(session)
            return False
        if event.action is None:
            return False

        action = next(
            (
                candidate
                for candidate in session.actions
                if candidate.name == event.action
            ),
            None,
        )
        if action is None:
            return False

        owner_only = (
            session.registration.owner_only
            if action.owner_only is None
            else action.owner_only
        )
        if owner_only and event.user_id != session.owner_id:
            return False

        try:
            if not session.hydrated:
                await session.hydrate()
                session.mark_hydrated()
            handler = getattr(session, action.handler)
            await handler(event)
        except Exception:
            logger.exception(
                "Session action failed: session=%s action=%s",
                session.id,
                event.action,
            )
            return False

        session.touch(self._now())
        if session.closed:
            await self.close(session)
        elif session.registration.resumable:
            await self.store.save(session)
        return True

    def get(self, key: str) -> Session | None:
        """Return a live session by routing key or session id."""
        return self._sessions_by_key.get(key)

    async def close(self, session: Session) -> None:
        """Close a live session and remove its persisted snapshot."""
        await session.close()
        self._sessions_by_id.pop(session.id, None)
        for key, candidate in tuple(self._sessions_by_key.items()):
            if candidate is session:
                del self._sessions_by_key[key]
        if session.registration.resumable:
            await self.store.delete(session.id)

    async def sweep(self) -> int:
        """Close expired live sessions and purge expired store records."""
        now = self._now()
        expired = [
            session
            for session in self._sessions_by_id.values()
            if session.is_expired(now)
        ]
        for session in expired:
            await self.close(session)
        await self.store.purge_expired(now)
        return len(expired)

    def active(self) -> tuple[Session, ...]:
        """Return a stable snapshot of live sessions for diagnostics."""
        return tuple(self._sessions_by_id.values())
