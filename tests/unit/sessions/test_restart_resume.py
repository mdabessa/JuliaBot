"""Tests for restart restoration and lazy hydration."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from juliabot.sessions import (
    Action,
    InteractionEvent,
    MemoryStore,
    Registration,
    Registry,
    Scope,
    Session,
    SessionManager,
    TriggerType,
)
from juliabot.sessions.transports.buttons import restore_button_views


class ResumableSession(Session):
    """Session double that records hydration and a reversible state change."""

    actions = (Action("bump", "bump", owner_only=False),)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.hydrations = 0
        self.bound_message = None

    async def hydrate(self, event: InteractionEvent | None = None) -> None:
        self.hydrations += 1
        self.bound_message = getattr(getattr(event, "raw", None), "message", None)

    async def bump(self, event: InteractionEvent) -> None:
        self.set_payload("count", int(self._payload.get("count", 0)) + 1)

    def to_payload(self) -> dict:
        return {"count": int(self._payload.get("count", 0))}


class CountingStore(MemoryStore):
    """Memory store that records read traffic."""

    def __init__(self):
        super().__init__()
        self.calls = []

    async def load_keys(self):
        self.calls.append("load_keys")
        return await super().load_keys()

    async def load(self, session_id):
        self.calls.append("load")
        return await super().load(session_id)


def make_registry() -> Registry:
    registry = Registry()
    registry.register(
        Registration(
            name="resumable",
            session_class=ResumableSession,
            trigger=TriggerType.COMPONENT,
            scope=Scope.USER,
            timeout=60,
            resumable=True,
        )
    )
    return registry


def start_event(key="command-1", user_id=1):
    return InteractionEvent(
        transport=TriggerType.COMPONENT,
        key=key,
        user_id=user_id,
        guild_id=10,
        channel_id=20,
        message_id=55,
    )


def action_event(key, action="bump", user_id=1):
    return InteractionEvent(
        transport=TriggerType.COMPONENT,
        key=key,
        user_id=user_id,
        action=action,
    )


@pytest.mark.asyncio
async def test_restart_resumes_session_with_payload(fake_clock):
    store = MemoryStore()
    first = SessionManager(make_registry(), store, clock=fake_clock.now)
    original = await first.start("resumable", start_event(), payload={"count": 1})

    restarted = SessionManager(make_registry(), store, clock=fake_clock.now)
    records = await restarted.restore()
    assert [record.id for record in records] == [original.id]

    assert await restarted.dispatch(action_event(original.id)) is True

    resumed = restarted.get(original.id)
    assert resumed is not None
    assert resumed.hydrations == 1
    assert resumed.to_payload() == {"count": 2}


@pytest.mark.asyncio
async def test_sweeper_drops_expired_restore_keys(fake_clock):
    store = MemoryStore()
    first = SessionManager(make_registry(), store, clock=fake_clock.now)
    await first.start("resumable", start_event(), payload={"count": 1})

    fake_clock.advance(120)
    restarted = SessionManager(make_registry(), store, clock=fake_clock.now)

    assert await restarted.restore() == ()
    assert await restarted.dispatch(action_event("unknown")) is False


@pytest.mark.asyncio
async def test_restore_and_dispatch_respect_the_query_budget(fake_clock):
    store = CountingStore()
    first = SessionManager(make_registry(), store, clock=fake_clock.now)
    original = await first.start("resumable", start_event(), payload={"count": 1})
    store.calls.clear()

    restarted = SessionManager(make_registry(), store, clock=fake_clock.now)
    await restarted.restore()
    assert store.calls == ["load_keys"]

    store.calls.clear()
    assert await restarted.dispatch(action_event("not-a-session")) is False
    assert store.calls == []

    assert await restarted.dispatch(action_event(original.id)) is True
    assert store.calls == ["load"]

    store.calls.clear()
    assert await restarted.dispatch(action_event(original.id)) is True
    assert store.calls == []


@pytest.mark.asyncio
async def test_restore_rebuilds_persistent_views(fake_client, fake_clock):
    store = MemoryStore()
    first = SessionManager(make_registry(), store, clock=fake_clock.now)
    original = await first.start("resumable", start_event(), payload={"count": 1})

    restarted = SessionManager(make_registry(), store, clock=fake_clock.now)
    records = await restarted.restore()

    assert restore_button_views(restarted, fake_client, records) == 1
    assert len(fake_client.views) == 1
    assert [button.custom_id for button in fake_client.views[0].children] == [
        f"sess:{original.id}:bump"
    ]


@pytest.mark.asyncio
async def test_hydration_binds_the_original_message(fake_clock):
    store = MemoryStore()
    first = SessionManager(make_registry(), store, clock=fake_clock.now)
    original = await first.start("resumable", start_event(), payload={"count": 1})

    restarted = SessionManager(make_registry(), store, clock=fake_clock.now)
    await restarted.restore()

    message = SimpleNamespace(id=55)
    interaction = SimpleNamespace(message=message)
    event = InteractionEvent(
        transport=TriggerType.COMPONENT,
        key=original.id,
        user_id=1,
        action="bump",
        raw=interaction,
    )

    assert await restarted.dispatch(event) is True
    assert restarted.get(original.id).bound_message is message
