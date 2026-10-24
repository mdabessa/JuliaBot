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
async def test_core_routes_messages_to_session_transport():
    message_transport = RecordingTransport()
    bot = SimpleNamespace(
        user=SimpleNamespace(id=999, mention="<@999>"),
        session_messages=message_transport,
    )
    cog = core_module.CoreCog(bot)
    message = SimpleNamespace(content="hello")

    await cog.on_message(message)

    assert message_transport.events == [(message, None)]
