"""Tests for the transport-independent Session lifecycle."""

import json
from datetime import timedelta

import pytest

from juliabot.sessions import (
    InteractionEvent,
    Registration,
    Registry,
    Scope,
    Session,
    SessionManager,
    TriggerType,
)


class LifecycleSession(Session):
    async def hydrate(self) -> None:
        self.set_payload("hydrated", True)


def make_registration(**kwargs) -> Registration:
    values = {
        "name": "lifecycle",
        "session_class": LifecycleSession,
        "trigger": TriggerType.COMPONENT,
        "scope": Scope.USER,
        "timeout": 60,
        **kwargs,
    }
    return Registration(**values)


def event(key: str = "message-1", user_id: int = 1) -> InteractionEvent:
    return InteractionEvent(
        transport=TriggerType.COMPONENT,
        key=key,
        user_id=user_id,
        channel_id=10,
        message_id=20,
    )


def test_payload_is_json_serializable_and_defensive():
    registration = make_registration()
    session = LifecycleSession(registration, event(), payload={"index": 2})

    payload = session.to_payload()
    payload["index"] = 99

    assert session.to_payload() == {"index": 2}
    assert json.dumps(session.to_payload()) == '{"index": 2}'


@pytest.mark.asyncio
async def test_hydrate_is_noop_for_base_session_until_manager_marks_it():
    registration = make_registration()
    session = Session(registration, event())

    assert session.hydrated is False

    await session.hydrate()
    session.mark_hydrated()

    assert session.hydrated is True
    assert session.to_payload() == {}


@pytest.mark.asyncio
async def test_close_is_idempotent():
    session = LifecycleSession(make_registration(), event())

    await session.close()
    await session.close()

    assert session.closed is True


def test_touch_refreshes_sliding_expiry(fake_clock):
    session = LifecycleSession(
        make_registration(timeout=60), event(), clock=fake_clock.now
    )
    original_expiry = session.expires_at

    fake_clock.advance(30)
    session.touch()

    assert session.last_seen_at == fake_clock.now()
    assert session.expires_at > original_expiry
    assert session.expires_at == fake_clock.now() + timedelta(seconds=60)


def test_expiry_uses_aware_utc_timestamps(fake_clock):
    session = LifecycleSession(make_registration(), event(), clock=fake_clock.now)

    assert session.created_at.tzinfo is not None
    assert session.created_at.utcoffset().total_seconds() == 0
    assert session.is_expired(fake_clock.now()) is False


@pytest.mark.asyncio
async def test_session_ids_are_unique_across_managers(fake_clock):
    registration = make_registration()
    registry = Registry()
    registry.register(registration)
    first_manager = SessionManager(registry, clock=fake_clock.now)
    second_manager = SessionManager(registry, clock=fake_clock.now)

    first = await first_manager.start("lifecycle", event("one"))
    second = await second_manager.start("lifecycle", event("two"))

    assert first.id != second.id
