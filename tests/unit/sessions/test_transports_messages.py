"""Tests for the message transport."""

from types import SimpleNamespace

import pytest

from juliabot.sessions import Registry, SessionManager
from juliabot.sessions.transports.messages import MessageTransport


@pytest.mark.asyncio
async def test_message_transport_returns_zero_without_rules(counting_store):
    manager = SessionManager(Registry(), counting_store)
    transport = MessageTransport(manager)
    message = SimpleNamespace(
        id=77,
        author=SimpleNamespace(id=3, bot=False),
        guild=SimpleNamespace(id=10),
        channel=SimpleNamespace(id=20),
        content="hello",
    )

    assert await transport.dispatch(message) == 0
    assert counting_store.calls == []


@pytest.mark.asyncio
async def test_message_transport_ignores_bot_messages(counting_store):
    manager = SessionManager(Registry(), counting_store)
    transport = MessageTransport(manager)
    message = SimpleNamespace(
        id=77,
        author=SimpleNamespace(id=999, bot=True),
        guild=SimpleNamespace(id=10),
        channel=SimpleNamespace(id=20),
        content="hello",
    )

    assert await transport.dispatch(message) == 0
    assert counting_store.calls == []


def test_message_transport_normalizes_message_context():
    manager = SessionManager(Registry())
    transport = MessageTransport(manager)
    message = SimpleNamespace(
        id=77,
        author=SimpleNamespace(id=3),
        guild=SimpleNamespace(id=10),
        channel=SimpleNamespace(id=20),
        content="hello",
    )

    event = transport.event(message)

    assert event.key == "77"
    assert event.user_id == 3
    assert event.guild_id == 10
    assert event.channel_id == 20
    assert event.raw is message
