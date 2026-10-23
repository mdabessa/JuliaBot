"""Behavior tests for the AI channel conversation rule.

The rule is a :class:`ChannelEntryPointRule` subclass, so these tests focus on
what the AI cog adds: filtering commands and empty messages, feeding channel
history into the prompt, and staying quiet when generation fails.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from juliabot.cogs import ai as ai_module
from juliabot.sessions import (
    InteractionEvent,
    Registration,
    Registry,
    Scope,
    SessionManager,
    TriggerType,
)

AI_CHANNEL = ai_module.AI_CHANNEL


class AsyncHistory:
    """Async iterator over a fixed list of messages."""

    def __init__(self, messages):
        self._messages = list(messages)

    def __aiter__(self):
        self._iterator = iter(self._messages)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration:
            raise StopAsyncIteration


class FakeAuthor:
    """Stand-in for a Discord user with a distinct identity."""

    def __init__(self, display_name="Alice", user_id=7):
        self.display_name = display_name
        self.id = user_id


class FakeMessage:
    """Channel message that records replies."""

    def __init__(
        self,
        content,
        *,
        author=None,
        message_id=100,
        channel=None,
        client=None,
    ):
        self.id = message_id
        self.content = content
        self.author = author if author is not None else FakeAuthor()
        self.channel = channel
        self.client = client
        self.replies: list[str] = []

    async def reply(self, content):
        """Record a reply instead of calling Discord."""
        self.replies.append(content)
        return content


class FakeAnchor:
    """Anchor message returned by ``FakeChannel.send``."""

    def __init__(self, content):
        self.id = 900
        self.content = content
        self.view = None
        self.edits: list[dict[str, object]] = []

    async def edit(self, **kwargs):
        """Record an edit and apply it to the fake message."""
        self.edits.append(kwargs)
        if "content" in kwargs:
            self.content = kwargs["content"]
        if "view" in kwargs:
            self.view = kwargs["view"]


class FakeChannel:
    """Channel double providing history, sending, and fetching."""

    def __init__(self, history=()):
        self.history_messages = list(history)
        self.history_limits: list[int | None] = []
        self.sent: list[FakeAnchor] = []

    def history(self, limit=None):
        """Return the configured history as an async iterator."""
        self.history_limits.append(limit)
        return AsyncHistory(self.history_messages)

    async def send(self, content=None, view=None):
        """Record the anchor message."""
        anchor = FakeAnchor(content)
        anchor.view = view
        self.sent.append(anchor)
        return anchor

    async def fetch_message(self, message_id):
        """Return the previously sent anchor message."""
        return self.sent[0]


class FakeBotClient:
    """Minimal bot client exposing the attributes the rule reads."""

    def __init__(self, prefix="!"):
        self.user = SimpleNamespace(id=9999, display_name="JuliaBot", bot=True)
        self.prefix = prefix

    async def get_prefix(self, message):
        """Return the configured prefix, mirroring discord.py."""
        return self.prefix


def make_manager():
    """Build a manager with the AI rule registered."""
    registry = Registry()
    registry.register(
        Registration(
            name=AI_CHANNEL,
            session_class=ai_module.AIConversationRule,
            trigger=TriggerType.MESSAGE,
            scope=Scope.CHANNEL,
            persistent=True,
            resumable=True,
            max_per_scope=1,
        )
    )
    return SessionManager(registry)


async def start_rule(manager, channel, channel_id=20):
    """Start the AI rule for a channel and return the session."""
    event = InteractionEvent(
        transport=TriggerType.MESSAGE,
        key=f"{AI_CHANNEL}:{channel_id}",
        user_id=1,
        guild_id=10,
        channel_id=channel_id,
        message_id=55,
        raw=SimpleNamespace(channel=channel),
    )
    return await manager.start(AI_CHANNEL, event)


def message_event(message, channel_id=20):
    """Build the message event a transport would dispatch."""
    return InteractionEvent(
        transport=TriggerType.MESSAGE,
        key=str(message.id),
        user_id=message.author.id,
        channel_id=channel_id,
        message_id=message.id,
        raw=message,
    )


@pytest.mark.asyncio
async def test_ai_rule_replies_to_channel_messages(monkeypatch):
    """A plain message is answered with channel history in the prompt."""
    prompts: list[list[dict[str, str]]] = []

    def fake_generate(messages):
        prompts.append(messages)
        return SimpleNamespace(response="Olá, humano!")

    monkeypatch.setattr(ai_module, "generate_response", fake_generate)

    bot = FakeBotClient()
    channel = FakeChannel(
        [
            FakeMessage(
                "mensagem antiga",
                author=FakeAuthor("Bob", 8),
                message_id=1,
                client=bot,
            ),
            FakeMessage(
                "resposta anterior",
                author=bot.user,
                message_id=2,
                client=bot,
            ),
        ]
    )
    manager = make_manager()
    await start_rule(manager, channel)

    message = FakeMessage("oi", channel=channel, client=bot)
    handled = await manager.dispatch_message(message_event(message))

    assert handled == 1
    assert message.replies == ["Olá, humano!"]
    assert channel.history_limits == [ai_module.MESSAGE_HISTORY_LIMIT]

    contents = [entry["content"] for entry in prompts[0]]
    assert contents[0] == ai_module.SYSTEM_PROMPT
    assert "Bob: mensagem antiga" in contents
    assert "resposta anterior" in contents
    assert contents[-1] == "Alice: oi"


@pytest.mark.asyncio
async def test_ai_rule_ignores_command_messages(monkeypatch):
    """Command-prefixed messages are left to the command framework."""
    called = False

    def fake_generate(messages):
        nonlocal called
        called = True
        return SimpleNamespace(response="nunca")

    monkeypatch.setattr(ai_module, "generate_response", fake_generate)

    bot = FakeBotClient()
    channel = FakeChannel()
    manager = make_manager()
    await start_rule(manager, channel)

    message = FakeMessage("!ping", channel=channel, client=bot)
    handled = await manager.dispatch_message(message_event(message))

    assert handled == 0
    assert message.replies == []
    assert called is False


@pytest.mark.asyncio
async def test_ai_rule_ignores_empty_messages(monkeypatch):
    """Whitespace-only messages never reach the model."""
    monkeypatch.setattr(
        ai_module,
        "generate_response",
        lambda messages: pytest.fail("generate_response must not be called"),
    )

    bot = FakeBotClient()
    channel = FakeChannel()
    manager = make_manager()
    await start_rule(manager, channel)

    message = FakeMessage("   ", channel=channel, client=bot)
    handled = await manager.dispatch_message(message_event(message))

    assert handled == 0
    assert message.replies == []


@pytest.mark.asyncio
async def test_ai_rule_reports_generation_failure(monkeypatch, caplog):
    """A failing model call logs the error and sends nothing."""

    def fake_generate(messages):
        raise RuntimeError("boom")

    monkeypatch.setattr(ai_module, "generate_response", fake_generate)

    bot = FakeBotClient()
    channel = FakeChannel()
    manager = make_manager()
    await start_rule(manager, channel)

    message = FakeMessage("oi", channel=channel, client=bot)
    with caplog.at_level(logging.ERROR, logger=ai_module.__name__):
        handled = await manager.dispatch_message(message_event(message))

    assert handled == 0
    assert message.replies == []
    assert any(
        "AI channel response failed" in record.message for record in caplog.records
    )


@pytest.mark.asyncio
async def test_build_message_history_stops_at_breakpoint():
    """History collection halts at a breakpoint command."""
    messages: list[dict[str, str]] = [{"role": "system", "content": "sys"}]
    channel = FakeChannel(
        [
            FakeMessage("!breakpoint", message_id=1),
            FakeMessage("depois do breakpoint", message_id=2),
        ]
    )

    await ai_module.build_message_history(
        channel=channel,
        question="",
        messages=messages,
        bot_user=None,
        breakpoint_prefixes=("!breakpoint", "!bp"),
    )

    assert messages == [{"role": "system", "content": "sys"}]


@pytest.mark.asyncio
async def test_build_message_history_respects_character_budget():
    """History stops once the character budget would be exceeded."""
    messages: list[dict[str, str]] = [{"role": "system", "content": "sys"}]
    channel = FakeChannel(
        [
            FakeMessage("recente", author=FakeAuthor("Bob", 8), message_id=1),
            FakeMessage("x" * ai_module.CHARACTER_LIMIT, message_id=2),
        ]
    )

    await ai_module.build_message_history(
        channel=channel,
        question="",
        messages=messages,
        bot_user=None,
        exclude_message_id=None,
    )

    contents = [entry["content"] for entry in messages]
    assert contents == ["sys", "Bob: recente"]
