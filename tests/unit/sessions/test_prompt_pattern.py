"""Tests for the declarative PromptSession pattern."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from juliabot.sessions import (
    InteractionEvent,
    Registration,
    Registry,
    Scope,
    SessionManager,
    TriggerType,
)
from juliabot.sessions.patterns import PromptChoice, PromptSession


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


class ConfirmPrompt(PromptSession):
    """Prompt double that records the selected choices."""

    choices = (
        ("yes", PromptChoice("Sim", emoji="👍", style="success")),
        ("no", PromptChoice("Não", emoji="👎", style="danger")),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.handled = []

    async def render_prompt(self):
        return "Confirmar?"

    async def on_choice(self, choice, event):
        self.handled.append((choice, event.user_id))


class RestrictedPrompt(ConfirmPrompt):
    """Prompt double that refuses the ``no`` choice for anyone."""

    def can_handle(self, choice, event):
        return choice != "no"


def make_manager(session_class=ConfirmPrompt):
    registry = Registry()
    registry.register(
        Registration(
            name="prompt",
            session_class=session_class,
            trigger=TriggerType.COMPONENT,
            scope=Scope.USER,
        )
    )
    return SessionManager(registry)


def start_event(context, key="command-1", user_id=1):
    return InteractionEvent(
        transport=TriggerType.COMPONENT,
        key=key,
        user_id=user_id,
        guild_id=10,
        channel_id=20,
        message_id=55,
        raw=context,
    )


def action_event(session, action, user_id=1):
    return InteractionEvent(
        transport=TriggerType.COMPONENT,
        key=session.id,
        user_id=user_id,
        action=action,
    )


@pytest.mark.asyncio
async def test_start_sends_prompt_with_declared_buttons():
    context = FakeContext()
    manager = make_manager()

    session = await manager.start("prompt", start_event(context))

    message = context.channel.sent[0]
    assert message.content == "Confirmar?"
    assert message.view is not None
    assert [button.custom_id for button in message.view.children] == [
        f"sess:{session.id}:yes",
        f"sess:{session.id}:no",
    ]
    assert [button.label for button in message.view.children] == ["Sim", "Não"]


@pytest.mark.asyncio
async def test_choice_is_handled_then_closes_prompt():
    context = FakeContext()
    manager = make_manager()
    session = await manager.start("prompt", start_event(context))

    assert await manager.dispatch(action_event(session, "yes")) is True

    assert session.handled == [("yes", 1)]
    assert session.closed is True
    assert manager.active() == ()


@pytest.mark.asyncio
async def test_unknown_action_is_ignored():
    context = FakeContext()
    manager = make_manager()
    session = await manager.start("prompt", start_event(context))

    assert await manager.dispatch(action_event(session, "maybe")) is False

    assert session.handled == []
    assert session.closed is False


@pytest.mark.asyncio
async def test_refused_choice_keeps_prompt_open():
    context = FakeContext()
    manager = make_manager(RestrictedPrompt)
    session = await manager.start("prompt", start_event(context))

    assert await manager.dispatch(action_event(session, "no")) is True

    assert session.handled == []
    assert session.closed is False
