"""Behavior tests for channel message rules."""

from __future__ import annotations

import pytest

from juliabot.sessions import (
    InteractionEvent,
    Registration,
    Registry,
    Scope,
    SessionManager,
    TriggerType,
)
from juliabot.sessions.patterns import MessageRuleSession


class RecordingRule(MessageRuleSession):
    """Rule double that counts handled messages in its payload."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.seen = []

    async def handle(self, event: InteractionEvent) -> bool:
        self.seen.append(event.message_id)
        self.set_payload("count", int(self._payload.get("count", 0)) + 1)
        return True


class RaisingRule(MessageRuleSession):
    """Rule double that always fails."""

    async def handle(self, event: InteractionEvent) -> bool:
        raise RuntimeError("rule boom")


def make_registration(
    name: str = "rule", session_class=RecordingRule, **kwargs
) -> Registration:
    return Registration(
        name=name,
        session_class=session_class,
        trigger=TriggerType.MESSAGE,
        scope=Scope.CHANNEL,
        persistent=True,
        max_per_scope=1,
        resumable=True,
        **kwargs,
    )


def start_event(channel_id=20, key="rule-command", user_id=1):
    return InteractionEvent(
        transport=TriggerType.MESSAGE,
        key=key,
        user_id=user_id,
        guild_id=10,
        channel_id=channel_id,
        message_id=55,
    )


def message_event(channel_id=20, message_id=100, user_id=7):
    return InteractionEvent(
        transport=TriggerType.MESSAGE,
        key=str(message_id),
        user_id=user_id,
        channel_id=channel_id,
        message_id=message_id,
    )


@pytest.mark.asyncio
async def test_rule_receives_only_its_channel_messages():
    registry = Registry()
    registry.register(make_registration())
    manager = SessionManager(registry)
    session = await manager.start("rule", start_event(channel_id=20))

    assert (
        await manager.dispatch_message(message_event(channel_id=20, message_id=100))
        == 1
    )
    assert session.seen == [100]

    assert (
        await manager.dispatch_message(message_event(channel_id=21, message_id=101))
        == 0
    )
    assert session.seen == [100]


@pytest.mark.asyncio
async def test_rules_are_indexed_in_registration_order():
    registry = Registry()
    registry.register(make_registration("first"))
    registry.register(make_registration("second"))
    manager = SessionManager(registry)
    first = await manager.start(
        "first", start_event(channel_id=20, key="first-command")
    )
    second = await manager.start(
        "second", start_event(channel_id=20, key="second-command")
    )

    assert manager.message_rules(20) == (first, second)
    assert await manager.dispatch_message(message_event(channel_id=20)) == 2
    assert first.seen == [100]
    assert second.seen == [100]


@pytest.mark.asyncio
async def test_global_rule_receives_every_channel():
    registry = Registry()
    registry.register(make_registration())
    manager = SessionManager(registry)
    session = await manager.start("rule", start_event(channel_id=None, key="global"))

    assert await manager.dispatch_message(message_event(channel_id=20)) == 1
    assert await manager.dispatch_message(message_event(channel_id=21)) == 1
    assert session.seen == [100, 100]


@pytest.mark.asyncio
async def test_no_rules_means_no_store_traffic(counting_store):
    manager = SessionManager(Registry(), counting_store)

    assert await manager.dispatch_message(message_event(channel_id=20)) == 0
    assert counting_store.calls == []


@pytest.mark.asyncio
async def test_restored_rule_materializes_on_first_message_only(
    counting_store, fake_clock
):
    registry = Registry()
    registry.register(make_registration())
    first = SessionManager(registry, counting_store, clock=fake_clock.now)
    await first.start("rule", start_event(channel_id=20))
    counting_store.calls.clear()

    restarted = SessionManager(registry, counting_store, clock=fake_clock.now)
    await restarted.restore()
    assert counting_store.calls == ["load_keys"]

    counting_store.calls.clear()
    assert await restarted.dispatch_message(message_event(message_id=200)) == 1
    assert counting_store.calls == ["load"]

    counting_store.calls.clear()
    assert await restarted.dispatch_message(message_event(message_id=201)) == 1
    assert counting_store.calls == []

    (restored,) = restarted.message_rules(20)
    assert restored.to_payload()["count"] == 2


@pytest.mark.asyncio
async def test_closed_rule_stops_receiving_messages():
    registry = Registry()
    registry.register(make_registration())
    manager = SessionManager(registry)
    session = await manager.start("rule", start_event(channel_id=20))

    await manager.close(session)

    assert manager.message_rules(20) == ()
    assert await manager.dispatch_message(message_event(channel_id=20)) == 0


@pytest.mark.asyncio
async def test_rule_failure_does_not_break_other_rules():
    registry = Registry()
    registry.register(make_registration("broken", RaisingRule))
    registry.register(make_registration("healthy"))
    manager = SessionManager(registry)
    await manager.start("broken", start_event(channel_id=20, key="broken-command"))
    healthy = await manager.start(
        "healthy", start_event(channel_id=20, key="healthy-command")
    )

    assert await manager.dispatch_message(message_event(channel_id=20)) == 1
    assert healthy.seen == [100]
