"""Shared fixtures for the session framework tests.

Everything here is deliberately independent of ``juliabot.sessions`` so the
fixtures can be used while the framework is still being built (phase 1). The
``CountingStore`` double is duck-typed rather than a subclass so it keeps working
as the store protocol evolves, and it records every call so tests can assert the
dispatch efficiency rules (no store traffic for unrelated events).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest


class FakeClock:
    """Deterministic, mutable clock for session expiry tests."""

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(2026, 1, 1, tzinfo=timezone.utc)

    def now(self) -> datetime:
        """Return the current fake time."""
        return self._now

    def advance(self, seconds: float) -> datetime:
        """Move the clock forward and return the new time."""
        self._now += timedelta(seconds=seconds)
        return self._now


class FakeClient:
    """Minimal stand-in for ``juliabot.client.Client``.

    ``add_view`` is included because persistent views must be re-registered at
    boot; tests assert against ``views`` to prove that happens.
    """

    def __init__(self) -> None:
        self.color = 0xE6DC56
        self.user = SimpleNamespace(id=9999, display_name="JuliaBot", bot=True)
        self.views: list[Any] = []

    def add_view(self, view: Any) -> None:
        """Record a view registration."""
        self.views.append(view)


class CountingStore:
    """Duck-typed ``SessionStore`` double that records every call.

    Args:
        records: Initial session records keyed by session id.
    """

    def __init__(self, records: dict[str, Any] | None = None) -> None:
        self.records: dict[str, Any] = dict(records or {})
        self.calls: list[str] = []
        self.purged = 0

    def count(self, name: str) -> int:
        """Return how many times ``name`` was called."""
        return self.calls.count(name)

    async def load_keys(self) -> list[Any]:
        """Return the stored routing keys."""
        self.calls.append("load_keys")
        return list(self.records.values())

    async def load(self, session_id: str) -> Any | None:
        """Return a single stored record."""
        self.calls.append("load")
        return self.records.get(session_id)

    async def save(self, session: Any) -> None:
        """Persist a record, keyed by its id."""
        self.calls.append("save")
        self.records[session.id] = session

    async def delete(self, session_id: str) -> None:
        """Remove a record."""
        self.calls.append("delete")
        self.records.pop(session_id, None)

    async def purge_expired(self, now: datetime) -> int:
        """Pretend to drop expired records and report the count."""
        self.calls.append("purge_expired")
        self.purged = 0
        return self.purged


@pytest.fixture
def fake_clock() -> FakeClock:
    """Return a fresh deterministic clock."""
    return FakeClock()


@pytest.fixture
def fake_client() -> FakeClient:
    """Return a fresh minimal bot client."""
    return FakeClient()


@pytest.fixture
def counting_store() -> CountingStore:
    """Return a fresh call-recording store double."""
    return CountingStore()
