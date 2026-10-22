"""Tests for SessionManager lifecycle and dispatch policy."""

from datetime import timedelta

import pytest

from juliabot.sessions import (
    Action,
    InteractionEvent,
    Registration,
    Registry,
    Scope,
    Session,
    SessionManager,
    TriggerType,
)


class ManagedSession(Session):
    actions = (
        Action("open", "open_session"),
        Action("next", "next_page", owner_only=False),
        Action("close", "close_session"),
    )

    async def start(self, event: InteractionEvent) -> None:
        self.set_payload("started", True)

    async def open_session(self, event: InteractionEvent) -> None:
        self.set_payload("opened_by", event.user_id)

    async def next_page(self, event: InteractionEvent) -> None:
        self.set_payload("next_by", event.user_id)

    async def close_session(self, event: InteractionEvent) -> None:
        await self.close()


class RaisingSession(ManagedSession):
    actions = (Action("explode", "explode"),)

    async def explode(self, event: InteractionEvent) -> None:
        self.set_payload("before_error", True)
        raise RuntimeError("expected test failure")


def registration(
    name: str = "managed", *, session_class=ManagedSession, **kwargs
) -> Registration:
    values = {
        "name": name,
        "session_class": session_class,
        "trigger": TriggerType.COMPONENT,
        "scope": Scope.USER,
        "timeout": 60,
    }
    values.update(kwargs)
    return Registration(**values)


def event(key: str, *, user_id: int = 1, action: str | None = None):
    return InteractionEvent(
        transport=TriggerType.COMPONENT,
        key=key,
        user_id=user_id,
        action=action,
        channel_id=10,
        message_id=20,
    )


def manager_for(registration_value, store=None, fake_clock=None):
    registry = Registry()
    registry.register(registration_value)
    return SessionManager(registry, store, clock=fake_clock.now if fake_clock else None)


@pytest.mark.asyncio
async def test_start_dispatch_and_close():
    manager = manager_for(registration())
    session = await manager.start("managed", event("session-1"))

    assert session.to_payload() == {"started": True}
    assert await manager.dispatch(event("session-1", action="open")) is True
    assert session.to_payload()["opened_by"] == 1

    assert await manager.dispatch(event("session-1", action="close")) is True
    assert manager.active() == ()


@pytest.mark.asyncio
async def test_session_id_alias_dispatches_the_same_live_session():
    manager = manager_for(registration())
    session = await manager.start("managed", event("message-1"))

    assert manager.get(session.id) is session
    assert await manager.dispatch(event(session.id, action="open")) is True
    assert session.to_payload()["opened_by"] == 1


@pytest.mark.asyncio
async def test_unknown_key_returns_without_store_calls(counting_store):
    manager = manager_for(registration(), counting_store)

    assert await manager.dispatch(event("missing", action="next")) is False
    assert counting_store.calls == []


@pytest.mark.asyncio
async def test_action_ownership_can_be_overridden():
    manager = manager_for(registration())
    session = await manager.start("managed", event("session-1", user_id=1))

    assert await manager.dispatch(event("session-1", user_id=2, action="open")) is False
    assert await manager.dispatch(event("session-1", user_id=2, action="next")) is True
    assert session.to_payload()["next_by"] == 2


@pytest.mark.asyncio
async def test_max_per_scope_closes_oldest(fake_clock):
    manager = manager_for(registration(max_per_scope=2), fake_clock=fake_clock)
    first = await manager.start("managed", event("first"))
    fake_clock.advance(1)
    second = await manager.start("managed", event("second"))
    fake_clock.advance(1)
    third = await manager.start("managed", event("third"))

    assert first.closed is True
    assert [session.routing_key for session in manager.active()] == [
        "second",
        "third",
    ]


@pytest.mark.asyncio
async def test_sweep_closes_only_expired_sessions(fake_clock):
    manager = manager_for(
        registration(timeout=10, max_per_scope=2), fake_clock=fake_clock
    )
    expired = await manager.start("managed", event("expired"))
    fake_clock.advance(5)
    active = await manager.start("managed", event("active"))
    fake_clock.advance(6)

    assert await manager.sweep() == 1
    assert expired.closed is True
    assert active.closed is False
    assert manager.active() == (active,)


@pytest.mark.asyncio
async def test_action_error_is_isolated_and_does_not_corrupt_session():
    manager = manager_for(registration(session_class=RaisingSession))
    session = await manager.start("managed", event("session-1"))
    before = session.last_seen_at

    assert await manager.dispatch(event("session-1", action="explode")) is False
    assert session.closed is False
    assert session.to_payload() == {"started": True, "before_error": True}
    assert session.last_seen_at == before


@pytest.mark.asyncio
async def test_dispatch_refreshes_sliding_expiry(fake_clock):
    manager = manager_for(registration(timeout=10), fake_clock=fake_clock)
    session = await manager.start("managed", event("session-1"))
    original_expiry = session.expires_at
    fake_clock.advance(5)

    assert await manager.dispatch(event("session-1", action="next")) is True
    assert session.expires_at > original_expiry
    assert session.expires_at == fake_clock.now() + timedelta(seconds=10)
