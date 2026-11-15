import datetime
from types import SimpleNamespace

import pytest
import pytz

from juliabot import models, utils


@pytest.fixture
def heartbeat_rows():
    models.init_db()
    models.BotConfig.delete_all()
    yield
    models.rollback()
    models.BotConfig.delete_all()
    models.rollback()


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


def test_parse_heartbeat_reads_iso_8601_offsets():
    parsed = utils.parse_heartbeat("2025-03-08T09:00:00-03:00")

    assert parsed == datetime.datetime(2025, 3, 8, 12, 0, tzinfo=pytz.utc)


def test_parse_heartbeat_reads_the_legacy_wall_clock_as_utc():
    parsed = utils.parse_heartbeat("08/03/2025 12:00:00")

    assert parsed == datetime.datetime(2025, 3, 8, 12, 0, tzinfo=pytz.utc)


@pytest.mark.parametrize("value", ["", None, "not a timestamp"])
def test_parse_heartbeat_rejects_unreadable_values(value):
    assert utils.parse_heartbeat(value) is None


def test_write_heartbeat_stores_an_iso_8601_utc_value(heartbeat_rows):
    utils.write_heartbeat(datetime.datetime(2025, 3, 8, 15, 0, tzinfo=pytz.utc))

    stored = models.BotConfig.get(utils.HEARTBEAT_KEY)

    assert stored.value == "2025-03-08T15:00:00+00:00"


def test_write_heartbeat_updates_a_single_row(heartbeat_rows):
    utils.write_heartbeat(datetime.datetime(2025, 3, 8, 15, 0, tzinfo=pytz.utc))
    utils.write_heartbeat(datetime.datetime(2025, 3, 8, 15, 1, tzinfo=pytz.utc))

    stored = models.BotConfig.get(utils.HEARTBEAT_KEY)

    assert stored.value == "2025-03-08T15:01:00+00:00"
    assert len(models.BotConfig.select_all()) == 1


def test_get_heartbeat_age_is_none_without_a_heartbeat(heartbeat_rows):
    assert utils.get_heartbeat_age() is None


def test_get_heartbeat_age_measures_an_iso_8601_heartbeat(heartbeat_rows):
    utils.write_heartbeat(datetime.datetime(2025, 3, 8, 15, 0, tzinfo=pytz.utc))

    age = utils.get_heartbeat_age(
        datetime.datetime(2025, 3, 8, 15, 2, 30, tzinfo=pytz.utc)
    )

    assert age == pytest.approx(150.0)


def test_get_heartbeat_age_measures_a_legacy_heartbeat(heartbeat_rows):
    models.BotConfig(utils.HEARTBEAT_KEY, "08/03/2025 15:00:00")

    age = utils.get_heartbeat_age(datetime.datetime(2025, 3, 8, 15, 5, tzinfo=pytz.utc))

    assert age == pytest.approx(300.0)
