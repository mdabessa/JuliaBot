"""Tests for CoreCog routing into session transports."""

from types import SimpleNamespace

import pytest

from juliabot.cogs import core as core_module


class RecordingTransport:
    def __init__(self, result=False):
        self.events = []
        self.result = result

    async def dispatch(self, value, user=None):
        self.events.append((value, user))
        return self.result


@pytest.mark.asyncio
async def test_core_routes_messages_to_session_transport(monkeypatch):
    message_transport = RecordingTransport()
    bot = SimpleNamespace(
        user=SimpleNamespace(id=999, mention="<@999>"),
        session_messages=message_transport,
    )
    cog = core_module.CoreCog(bot)
    message = SimpleNamespace(content="hello")
    monkeypatch.setattr(core_module.Script, "fetch_script", lambda *args, **kwargs: [])

    await cog.on_message(message)

    assert message_transport.events == [(message, None)]


@pytest.mark.asyncio
async def test_core_routes_reactions_to_session_transport(monkeypatch):
    reaction_transport = RecordingTransport()
    bot_user = SimpleNamespace(id=999)
    bot = SimpleNamespace(
        user=bot_user,
        session_reactions=reaction_transport,
    )
    cog = core_module.CoreCog(bot)
    reaction = SimpleNamespace(message=SimpleNamespace(id=55))
    user = SimpleNamespace(id=7)
    monkeypatch.setattr(core_module.Script, "fetch_script", lambda *args, **kwargs: [])

    await cog.on_reaction_add(reaction, user)

    assert reaction_transport.events == [(reaction, user)]
