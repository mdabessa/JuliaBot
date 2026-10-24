"""Behavior tests for the durable channel entry point rule."""

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
from juliabot.sessions.patterns import ChannelEntryPointRule


class RecordingEntryPoint(ChannelEntryPointRule):
    """Entry point double that records channel messages."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.seen = []

    async def on_channel_message(self, event: InteractionEvent) -> bool:
        self.seen.append(event.message_id)
        return True


class FakeAnchor:
    def __init__(self, content):
        self.id = 900
        self.content = content
        self.view = None
        self.edits = []

    async def edit(self, **kwargs):
        self.edits.append(kwargs)
        if "content" in kwargs:
            self.content = kwargs["content"]
        self.view = kwargs.get("view", self.view)


class FakeChannel:
    def __init__(self):
        self.sent = []
        self.messages = []

    async def send(self, content=None, view=None):
        anchor = FakeAnchor(content)
        anchor.view = view
        self.sent.append(anchor)
        return anchor

    async def fetch_message(self, message_id):
        return self.sent[0]


class FakeContext:
    def __init__(self, channel):
        self.channel = channel


def make_registration(session_class=RecordingEntryPoint):
    return Registration(
        name="channel.entry",
        session_class=session_class,
        trigger=TriggerType.MESSAGE,
        scope=Scope.CHANNEL,
        persistent=True,
        max_per_scope=1,
        resumable=True,
    )


def start_event(channel_id=20, user_id=1, raw=None):
    return InteractionEvent(
        transport=TriggerType.MESSAGE,
        key=f"channel.entry:{channel_id}",
        user_id=user_id,
        guild_id=10,
        channel_id=channel_id,
        message_id=55,
        raw=raw,
    )


def message_event(channel_id=20, message_id=100):
    return InteractionEvent(
        transport=TriggerType.MESSAGE,
        key=str(message_id),
        user_id=7,
        channel_id=channel_id,
        message_id=message_id,
    )


def action_event(session, action="disable", user_id=1):
    return InteractionEvent(
        transport=TriggerType.COMPONENT,
        key=session.id,
        user_id=user_id,
        action=action,
    )


@pytest.mark.asyncio
async def test_start_sends_anchor_and_persists_its_id():
    registry = Registry()
    registry.register(make_registration())
    manager = SessionManager(registry)
    channel = FakeChannel()

    session = await manager.start(
        "channel.entry", start_event(raw=FakeContext(channel))
    )

    assert channel.sent[0].content == ChannelEntryPointRule.anchor_text
    assert channel.sent[0].view is not None
    assert session.to_payload() == {"anchor_message_id": 900}


@pytest.mark.asyncio
async def test_every_channel_message_reaches_the_entry_point():
    registry = Registry()
    registry.register(make_registration())
    manager = SessionManager(registry)
    session = await manager.start(
        "channel.entry",
        start_event(raw=FakeContext(FakeChannel())),
    )

    assert await manager.dispatch_message(message_event(message_id=100)) == 1
    assert await manager.dispatch_message(message_event(message_id=101)) == 1
    assert session.seen == [100, 101]


@pytest.mark.asyncio
async def test_owner_can_disable_and_controls_are_removed():
    registry = Registry()
    registry.register(make_registration())
    manager = SessionManager(registry)
    channel = FakeChannel()
    session = await manager.start(
        "channel.entry", start_event(user_id=1, raw=FakeContext(channel))
    )

    assert await manager.dispatch(action_event(session, user_id=1)) is True

    assert session.closed is True
    assert channel.sent[0].edits == [
        {"content": ChannelEntryPointRule.disabled_text, "view": None}
    ]
    assert manager.message_rules(20) == ()


@pytest.mark.asyncio
async def test_non_owner_cannot_disable():
    registry = Registry()
    registry.register(make_registration())
    manager = SessionManager(registry)
    channel = FakeChannel()
    session = await manager.start(
        "channel.entry", start_event(user_id=1, raw=FakeContext(channel))
    )

    assert await manager.dispatch(action_event(session, user_id=9)) is False

    assert session.closed is False
    assert channel.sent[0].edits == []
    assert manager.message_rules(20) == (session,)
