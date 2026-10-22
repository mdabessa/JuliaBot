"""Tests for indexed registration lookup."""

import pytest

from juliabot.sessions import Registration, Registry, Scope, Session, TriggerType


class DummySession(Session):
    pass


def registration(
    name: str,
    *,
    trigger: TriggerType = TriggerType.MESSAGE,
    scope_key=None,
) -> Registration:
    return Registration(
        name=name,
        session_class=DummySession,
        trigger=trigger,
        scope=Scope.CHANNEL,
        scope_key=scope_key,
    )


def test_registry_matches_global_and_requested_scope_only():
    registry = Registry()
    global_registration = registration("global", scope_key=None)
    channel_registration = registration("channel-7", scope_key=7)
    other_registration = registration("channel-8", scope_key=8)
    registry.register(global_registration)
    registry.register(channel_registration)
    registry.register(other_registration)

    assert registry.match(TriggerType.MESSAGE, 7) == (
        global_registration,
        channel_registration,
    )
    assert registry.match(TriggerType.MESSAGE, 9) == (global_registration,)
    assert registry.match(TriggerType.REACTION, 7) == ()


def test_registry_does_not_scan_unrelated_scope_buckets():
    registry = Registry()
    registrations = [
        registration(f"channel-{index}", scope_key=index) for index in range(100)
    ]
    for item in registrations:
        registry.register(item)

    matches = registry.match(TriggerType.MESSAGE, 42)

    assert matches == (registrations[42],)


def test_registry_rejects_duplicate_names():
    registry = Registry()
    registry.register(registration("duplicate"))

    with pytest.raises(ValueError, match="already exists"):
        registry.register(registration("duplicate", trigger=TriggerType.REACTION))


def test_registration_rejects_invalid_limits():
    with pytest.raises(ValueError, match="timeout"):
        Registration("bad-timeout", DummySession, TriggerType.MESSAGE, timeout=0)

    with pytest.raises(ValueError, match="max_per_scope"):
        Registration("bad-limit", DummySession, TriggerType.MESSAGE, max_per_scope=0)
