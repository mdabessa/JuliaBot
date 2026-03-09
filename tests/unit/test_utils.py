from types import SimpleNamespace

from juliabot import utils


def test_get_prefix_for_guild_message(monkeypatch):
    called = {}

    def fake_get_or_create(server_id):
        called["server_id"] = server_id
        return SimpleNamespace(prefix="?", update=lambda: None)

    monkeypatch.setattr(utils.Server, "get_or_create", fake_get_or_create)

    message = SimpleNamespace(guild=SimpleNamespace(id=123))
    prefix = utils.get_prefix(bot=None, message=message)

    assert prefix == "?"
    assert called["server_id"] == "123"


def test_get_prefix_for_dm_message():
    message = SimpleNamespace(guild=None)
    prefix = utils.get_prefix(bot=None, message=message)

    assert prefix == utils.PREFIX
