from pathlib import Path
from types import SimpleNamespace

import pytest

from juliabot.client import Client


@pytest.mark.asyncio
async def test_client_initialization_loads_cogs(monkeypatch):
    loaded = []

    monkeypatch.setattr("juliabot.client.init_db", lambda: None)

    def fake_bot_init(self, **options):
        return None

    monkeypatch.setattr("juliabot.client.Bot.__init__", fake_bot_init)

    async def fake_load_extension(self, name):
        loaded.append(name)

    monkeypatch.setattr("juliabot.client.Bot.load_extension", fake_load_extension)
    monkeypatch.setattr(
        Path,
        "glob",
        lambda self, pattern: [
            SimpleNamespace(stem="core"),
            SimpleNamespace(stem="help"),
        ],
    )

    client = Client(command_prefix="!")
    await client.setup_hook()

    assert loaded == ["juliabot.cogs.core", "juliabot.cogs.help"]


@pytest.mark.asyncio
async def test_on_message_processes_commands(monkeypatch):
    calls = []

    monkeypatch.setattr("juliabot.client.init_db", lambda: None)
    monkeypatch.setattr("juliabot.client.Bot.__init__", lambda self, **opts: None)
    monkeypatch.setattr("juliabot.client.Path.glob", lambda self, pattern: [])

    client = Client(command_prefix="!")

    async def fake_get_context(message):
        return SimpleNamespace(valid=True)

    async def fake_process_commands(message):
        calls.append(message.content)

    client.get_context = fake_get_context
    client.process_commands = fake_process_commands

    message = SimpleNamespace(author="u", content="!ping")
    await client.on_message(message)

    assert calls == ["!ping"]
