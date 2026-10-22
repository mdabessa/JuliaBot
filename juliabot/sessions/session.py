"""Lifecycle and state for one interactive session.

The base class owns identity, timestamps, ownership metadata, and the
JSON-safe payload boundary. Concrete patterns add behavior without placing
transport or Discord objects in persisted state.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable, Hashable
from uuid import uuid4

from .registration import Registration
from .types import InteractionEvent, JSONValue

Clock = Callable[[], datetime]


class Session:
    """Represent one live instance of a registered interaction."""

    def __init__(
        self,
        registration: Registration,
        event: InteractionEvent,
        *,
        payload: dict[str, JSONValue] | None = None,
        clock: Clock | None = None,
        session_id: str | None = None,
    ) -> None:
        self.registration = registration
        self.id = session_id or uuid4().hex
        self.owner_id = event.user_id
        self.guild_id = event.guild_id
        self.channel_id = event.channel_id
        self.message_id = event.message_id
        self.routing_key = event.key
        self.scope_key: Hashable | None = self._scope_key(event)
        self.created_at = self._now(clock)
        self.last_seen_at = self.created_at
        self.expires_at = self.created_at + timedelta(seconds=registration.timeout)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._payload: dict[str, JSONValue] = dict(payload or {})
        self._closed = False
        self._hydrated = False

    def _scope_key(self, event: InteractionEvent) -> Hashable | None:
        """Select the runtime scope value used for concurrency limits."""
        scope = self.registration.scope.value
        if scope == "user":
            return event.user_id
        if scope == "guild":
            return event.guild_id
        if scope == "channel":
            return event.channel_id
        return None

    @staticmethod
    def _now(clock: Clock | None) -> datetime:
        """Return an aware UTC timestamp from the optional test clock."""
        value = clock() if clock else datetime.now(timezone.utc)
        if value.tzinfo is None:
            raise ValueError("Session clocks must return timezone-aware datetimes")
        return value.astimezone(timezone.utc)

    @property
    def actions(self):
        """Return the actions exposed by this session.

        Patterns override this property when they expose buttons or reactions.
        The base intentionally exposes no actions.
        """
        return ()

    @property
    def closed(self) -> bool:
        """Whether this session has already been closed."""
        return self._closed

    @property
    def hydrated(self) -> bool:
        """Whether restoration hydration has completed."""
        return self._hydrated

    def to_payload(self) -> dict[str, JSONValue]:
        """Return a copy of the JSON-safe state owned by the session."""
        return dict(self._payload)

    def set_payload(self, key: str, value: JSONValue) -> None:
        """Set one JSON-safe payload value."""
        self._payload[key] = value

    async def hydrate(self) -> None:
        """Rebuild transient runtime objects after a persisted restore.

        The base has no transient objects, so hydration is intentionally a
        no-op. The manager marks it complete through ``mark_hydrated``.
        """

    def mark_hydrated(self) -> None:
        """Mark this session as hydrated after restoration."""
        self._hydrated = True

    async def start(self, event: InteractionEvent) -> None:
        """Perform first-render behavior for a newly created session."""

    async def render(self) -> None:
        """Render the current state; concrete patterns provide the UI."""

    async def on_timeout(self) -> None:
        """Close an idle session by default."""
        await self.close()

    async def close(self) -> None:
        """Mark the session closed; repeated calls are harmless."""
        self._closed = True

    def touch(self, now: datetime | None = None) -> None:
        """Refresh the sliding idle timeout after accepted activity."""
        current = now or self._now(self._clock)
        if current.tzinfo is None:
            raise ValueError("Session timestamps must be timezone-aware")
        current = current.astimezone(timezone.utc)
        self.last_seen_at = current
        self.expires_at = current + timedelta(seconds=self.registration.timeout)

    def is_expired(self, now: datetime | None = None) -> bool:
        """Return whether the session's idle deadline has passed."""
        return (now or self._now(self._clock)) >= self.expires_at
