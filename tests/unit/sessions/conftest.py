"""Shared fixtures for the session framework tests.

``CountingStore`` is a ``MemoryStore`` that records every call, so tests can
assert the dispatch efficiency rules (no store traffic for unrelated events)
while still exercising real snapshot semantics.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from juliabot.sessions import MemoryStore


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


class CountingStore(MemoryStore):
    """In-memory store that records every call for efficiency assertions."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []
        self.purged = 0

    def count(self, name: str) -> int:
        """Return how many times ``name`` was called."""
        return self.calls.count(name)

    async def load_keys(self):
        """Return stored records, recording the call."""
        self.calls.append("load_keys")
        return await super().load_keys()

    async def load(self, session_id: str):
        """Return one stored record, recording the call."""
        self.calls.append("load")
        return await super().load(session_id)

    async def save(self, session) -> None:
        """Persist a session snapshot, recording the call."""
        self.calls.append("save")
        await super().save(session)

    async def delete(self, session_id: str) -> None:
        """Delete a record, recording the call."""
        self.calls.append("delete")
        await super().delete(session_id)

    async def purge_expired(self, now: datetime) -> int:
        """Purge expired records, recording the call and count."""
        self.calls.append("purge_expired")
        self.purged = await super().purge_expired(now)
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
