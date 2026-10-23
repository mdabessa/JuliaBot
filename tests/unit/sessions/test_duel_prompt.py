"""Behavior tests for the migrated duel prompt session."""

from __future__ import annotations

import pytest

from juliabot.cogs import fun as fun_module
from juliabot.sessions import (
    InteractionEvent,
    Registration,
    Registry,
    Scope,
    SessionManager,
    TriggerType,
)


class FakeMessage:
    def __init__(self, channel, content, view):
        self.channel = channel
        self.content = content
        self.view = view


class FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, content=None, view=None):
        message = FakeMessage(self, content, view)
        self.sent.append(message)
        return message


class FakeContext:
    def __init__(self):
        self.channel = FakeChannel()


AUTHOR_ID = 30
RIVAL_ID = 808
OUTSIDER_ID = 999


def make_manager():
    registry = Registry()
    registry.register(
        Registration(
            name=fun_module.DUEL,
            session_class=fun_module.DuelPrompt,
            trigger=TriggerType.COMPONENT,
            scope=Scope.GUILD,
            timeout=60,
            max_per_scope=2,
        )
    )
    return SessionManager(registry)


def start_event(context, key="command-1", guild_id=10):
    return InteractionEvent(
        transport=TriggerType.COMPONENT,
        key=key,
        user_id=AUTHOR_ID,
        guild_id=guild_id,
        channel_id=20,
        message_id=55,
        raw=context,
    )


def action_event(session, action, user_id):
    return InteractionEvent(
        transport=TriggerType.COMPONENT,
        key=session.id,
        user_id=user_id,
        action=action,
    )


async def start_duel(context, manager, key="command-1"):
    return await manager.start(
        fun_module.DUEL,
        start_event(context, key),
        payload={"author_id": AUTHOR_ID, "vs_id": RIVAL_ID},
    )


@pytest.mark.asyncio
async def test_duel_prompt_announces_challenge_with_buttons():
    context = FakeContext()
    manager = make_manager()

    session = await start_duel(context, manager)

    message = context.channel.sent[0]
    assert message.content == f"<@{AUTHOR_ID}> desafia <@{RIVAL_ID}> para um duelo!"
    assert message.view is not None
    assert session.to_payload() == {"author_id": AUTHOR_ID, "vs_id": RIVAL_ID}


@pytest.mark.asyncio
async def test_only_the_challenged_user_can_accept():
    context = FakeContext()
    manager = make_manager()
    session = await start_duel(context, manager)

    await manager.dispatch(action_event(session, "accept", OUTSIDER_ID))

    assert session.closed is False
    assert len(context.channel.sent) == 1

    await manager.dispatch(action_event(session, "accept", AUTHOR_ID))

    assert session.closed is False
    assert len(context.channel.sent) == 1


@pytest.mark.asyncio
async def test_either_participant_can_decline():
    context = FakeContext()
    manager = make_manager()
    session = await start_duel(context, manager)

    await manager.dispatch(action_event(session, "decline", AUTHOR_ID))

    assert session.closed is True
    assert context.channel.sent[-1].content == f"<@{AUTHOR_ID}> recusou o duelo!"


@pytest.mark.asyncio
async def test_outsider_cannot_decline():
    context = FakeContext()
    manager = make_manager()
    session = await start_duel(context, manager)

    await manager.dispatch(action_event(session, "decline", OUTSIDER_ID))

    assert session.closed is False
    assert len(context.channel.sent) == 1


@pytest.mark.asyncio
async def test_accept_random_outcome_when_rival_wins(monkeypatch):
    monkeypatch.setattr(fun_module, "randint", lambda _a, _b: 1)
    context = FakeContext()
    manager = make_manager()
    session = await start_duel(context, manager)

    await manager.dispatch(action_event(session, "accept", RIVAL_ID))

    assert session.closed is True
    assert context.channel.sent[-1].content == (
        f"<@{RIVAL_ID}> aceitou o duelo e venceu! \n"
        f"<@{AUTHOR_ID}> perdeu o duelo! :sob:"
    )


@pytest.mark.asyncio
async def test_accept_random_outcome_when_rival_loses(monkeypatch):
    monkeypatch.setattr(fun_module, "randint", lambda _a, _b: 0)
    context = FakeContext()
    manager = make_manager()
    session = await start_duel(context, manager)

    await manager.dispatch(action_event(session, "accept", RIVAL_ID))

    assert session.closed is True
    assert context.channel.sent[-1].content == (
        f"<@{RIVAL_ID}> aceitou o duelo e perdeu! \n"
        f"<@{AUTHOR_ID}> ganhou o duelo! :sunglasses:"
    )


@pytest.mark.asyncio
async def test_duel_limit_is_two_per_guild():
    context = FakeContext()
    manager = make_manager()
    first = await start_duel(context, manager, key="first")
    second = await start_duel(context, manager, key="second")
    third = await start_duel(context, manager, key="third")

    assert first.closed is True
    assert second.closed is False
    assert third.closed is False
    assert len(manager.active()) == 2


@pytest.mark.asyncio
async def test_duel_limit_is_scoped_per_guild():
    context = FakeContext()
    manager = make_manager()
    first = await start_duel(context, manager, key="first")
    second = await manager.start(
        fun_module.DUEL,
        start_event(context, "second", guild_id=11),
        payload={"author_id": AUTHOR_ID, "vs_id": RIVAL_ID},
    )

    assert first.closed is False
    assert second.closed is False
