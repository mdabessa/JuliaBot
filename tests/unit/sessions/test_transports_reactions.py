"""Tests for the legacy reaction transport."""

from types import SimpleNamespace

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
from juliabot.sessions.transports.reactions import ReactionTransport


class ReactionSession(Session):
    actions = (Action("next", "next_page", owner_only=False, emoji="➡️"),)

    async def next_page(self, event: InteractionEvent) -> None:
        self.set_payload("reacted_by", event.user_id)


def make_reaction(message_id=55, emoji="➡️"):
    message = SimpleNamespace(
        id=message_id,
        guild=SimpleNamespace(id=10),
        channel=SimpleNamespace(id=20),
    )
    return SimpleNamespace(message=message, emoji=emoji)


@pytest.mark.asyncio
async def test_reaction_routes_by_message_id(counting_store):
    registry = Registry()
    registry.register(
        Registration(
            name="reactions",
            session_class=ReactionSession,
            trigger=TriggerType.REACTION,
            scope=Scope.CHANNEL,
        )
    )
    manager = SessionManager(registry, counting_store)
    session = await manager.start(
        "reactions",
        InteractionEvent(
            transport=TriggerType.REACTION,
            key="55",
            user_id=1,
            channel_id=20,
            message_id=55,
        ),
    )
    transport = ReactionTransport(manager)
    user = SimpleNamespace(id=2, bot=False)

    assert await transport.dispatch(make_reaction(), user) is True
    assert session.to_payload()["reacted_by"] == 2
    assert counting_store.calls == []


@pytest.mark.asyncio
async def test_unknown_reaction_is_silent_and_does_not_read_store(counting_store):
    manager = SessionManager(Registry(), counting_store)
    transport = ReactionTransport(manager)

    assert (
        await transport.dispatch(make_reaction(message_id=999), SimpleNamespace(id=2))
        is False
    )
    assert counting_store.calls == []


@pytest.mark.asyncio
async def test_bot_reaction_is_ignored(counting_store):
    manager = SessionManager(Registry(), counting_store)
    transport = ReactionTransport(manager)

    assert (
        await transport.dispatch(make_reaction(), SimpleNamespace(id=999, bot=True))
        is False
    )
    assert counting_store.calls == []
