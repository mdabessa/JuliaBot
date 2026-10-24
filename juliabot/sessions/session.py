"""Lifecycle and state for one interactive session.

The base class owns identity, timestamps, ownership metadata, and the
JSON-safe payload boundary. Concrete patterns add behavior without placing
transport or Discord objects in persisted state.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable, Hashable, Mapping
from uuid import uuid4

from .registration import Registration
from .types import InteractionEvent, JSONValue

Clock = Callable[[], datetime]


def _as_aware_utc(value: datetime) -> datetime:
    """Return an aware UTC timestamp, assuming UTC for naive values."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


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
        self.expires_at = self._initial_expiry(registration, self.created_at)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._payload: dict[str, JSONValue] = dict(payload or {})
        self._closed = False
        self._hydrated = False
        self.manager = None

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

    @staticmethod
    def _initial_expiry(registration: Registration, created_at: datetime) -> datetime:
        """Return the idle deadline, or the far future for persistent sessions."""
        if registration.persistent:
            return datetime.max.replace(tzinfo=timezone.utc)
        return created_at + timedelta(seconds=registration.timeout)

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

    async def hydrate(self, event: InteractionEvent | None = None) -> None:
        """Rebuild transient runtime objects after a persisted restore.

        The base has no transient objects, so hydration is intentionally a
        no-op. Patterns that hold messages or items accept the triggering event
        so they can reattach to the original Discord message. The manager marks
        hydration complete through ``mark_hydrated``.
        """

    def restore_state(
        self,
        payload: Mapping[str, JSONValue],
        *,
        created_at: datetime,
        last_seen_at: datetime,
        expires_at: datetime,
        scope_key: Hashable | None = None,
    ) -> None:
        """Apply a persisted snapshot to a freshly constructed session shell.

        The session is left un-hydrated so the first interaction can rebuild
        transient objects with access to the triggering event.
        """
        self._payload = dict(payload)
        self.created_at = _as_aware_utc(created_at)
        self.last_seen_at = _as_aware_utc(last_seen_at)
        self.expires_at = _as_aware_utc(expires_at)
        self.scope_key = scope_key
        self._closed = False
        self._hydrated = False

    def mark_hydrated(self) -> None:
        """Mark this session as hydrated after restoration."""
        self._hydrated = True

    async def start(self, event: InteractionEvent) -> None:
        """Perform first-render behavior for a newly created session."""

    async def on_message(self, event: InteractionEvent) -> bool:
        """Handle a message event; message rules override this hook.

        Return ``True`` when the message was handled, which lets the manager
        count deliveries and refresh sliding expiry.
        """
        return False

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
        if not self.registration.persistent:
            self.expires_at = current + timedelta(seconds=self.registration.timeout)

    def is_expired(self, now: datetime | None = None) -> bool:
        """Return whether the session's idle deadline has passed."""
        return (now or self._now(self._clock)) >= self.expires_at
