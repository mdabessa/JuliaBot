import datetime
from types import SimpleNamespace

import pytest
import pytz
from sqlalchemy import Column, Integer, MetaData, String, Table

import juliabot.models as models

GUILD_ID = "10"
CHANNEL_ID = "20"
MESSAGE_ID = "1000"
USER_ID = "30"
SAO_PAULO = pytz.timezone("America/Sao_Paulo")


@pytest.fixture
def reminder_tables():
    models.init_db()
    for table in (models.Reminder, models.Server):
        table.delete_all()
    yield
    models.rollback()
    for table in (models.Reminder, models.Server):
        table.delete_all()
    models.rollback()


def _make_reminder(time_reminder, date_command=None):
    return models.Reminder(
        GUILD_ID, CHANNEL_ID, MESSAGE_ID, USER_ID, time_reminder, date_command
    )


def test_as_utc_treats_naive_values_as_utc():
    naive = datetime.datetime(2025, 3, 8, 12, 0)

    assert models.as_utc(naive) == datetime.datetime(2025, 3, 8, 12, 0, tzinfo=pytz.utc)


def test_as_utc_converts_aware_values_to_the_same_instant():
    local = SAO_PAULO.localize(datetime.datetime(2025, 3, 8, 9, 0))

    assert models.as_utc(local) == datetime.datetime(2025, 3, 8, 12, 0, tzinfo=pytz.utc)


def test_as_utc_keeps_utc_values_unchanged():
    aware = datetime.datetime(2025, 3, 8, 12, 0, tzinfo=pytz.utc)

    converted = models.as_utc(aware)

    assert converted == aware
    assert converted.utcoffset() == datetime.timedelta(0)


def test_get_date_str_reads_stored_naive_times_as_utc(reminder_tables):
    server = models.Server.get_or_create(GUILD_ID)
    server.set_timezone(SAO_PAULO)

    reminder = _make_reminder(datetime.datetime(2025, 3, 8, 12, 0, tzinfo=pytz.utc))
    # SQLite drops the offset, so read-back values are naive UTC.
    reminder.time_reminder = datetime.datetime(2025, 3, 8, 12, 0)

    assert reminder.get_date_str() == "08/03/2025 09:00 [America/Sao_Paulo]"


def test_get_created_str_reads_stored_naive_times_as_utc(reminder_tables):
    server = models.Server.get_or_create(GUILD_ID)
    server.set_timezone(SAO_PAULO)

    reminder = _make_reminder(datetime.datetime(2025, 3, 8, 12, 0, tzinfo=pytz.utc))
    reminder.time_created = datetime.datetime(2025, 3, 8, 12, 0)

    assert reminder.get_created_str() == "08/03/2025 09:00 [America/Sao_Paulo]"


def test_reminder_time_round_trips_as_the_same_instant(reminder_tables):
    expected = datetime.datetime(2025, 3, 8, 12, 0, tzinfo=pytz.utc)
    reminder = _make_reminder(expected)

    fresh = models.Session()
    try:
        stored = fresh.query(models.Reminder).filter_by(id=reminder.id).one()
        stored_value = stored.time_reminder
    finally:
        fresh.close()

    assert models.as_utc(stored_value) == expected


def test_reminder_time_columns_are_timezone_aware():
    table = models.Reminder.__table__

    assert table.c.time_reminder.type.timezone is True
    assert table.c.time_created.type.timezone is True


def test_is_simple_auto_add_column_allows_basic_nullable_column():
    column = Column("extra", String, nullable=True)

    assert models._is_simple_auto_add_column(column) is True


def test_is_simple_auto_add_column_blocks_non_null_without_server_default():
    column = Column("required", String, nullable=False)

    assert models._is_simple_auto_add_column(column) is False


def test_auto_add_missing_simple_columns_adds_only_supported_columns(monkeypatch):
    test_table = Table(
        "servers",
        MetaData(),
        Column("id", Integer, primary_key=True),
        Column("changelog_channel", String, nullable=True),
        Column("must_have_value", String, nullable=False),
    )

    class FakeInspector:
        def get_table_names(self):
            return ["servers"]

        def get_columns(self, table_name):
            assert table_name == "servers"
            return [{"name": "id"}]

    executed = []

    class FakeConnection:
        def execute(self, statement):
            executed.append(str(statement))

    class FakeBegin:
        def __enter__(self):
            return FakeConnection()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(models, "inspect", lambda _engine: FakeInspector())
    monkeypatch.setattr(models.engine, "begin", lambda: FakeBegin())
    monkeypatch.setattr(
        models,
        "Base",
        SimpleNamespace(metadata=SimpleNamespace(sorted_tables=[test_table])),
    )

    applied = models._auto_add_missing_simple_columns()

    assert applied == [("servers", "changelog_channel")]
    assert len(executed) == 1
    assert "ALTER TABLE" in executed[0]
    assert "ADD COLUMN" in executed[0]
    assert "changelog_channel" in executed[0]


def test_init_db_logs_summary_when_auto_migration_runs(monkeypatch):
    called = {}
    info_logs = []

    monkeypatch.setattr(
        models.Model.metadata,
        "create_all",
        lambda eng, tables=None: called.setdefault("engine", eng),
    )
    monkeypatch.setattr("juliabot.migrations.upgrade", lambda engine: ())
    monkeypatch.setattr(
        models,
        "_auto_add_missing_simple_columns",
        lambda: [("servers", "changelog_channel")],
    )
    monkeypatch.setattr(
        models.logger,
        "info",
        lambda message, *args: info_logs.append(message % args if args else message),
    )

    models.init_db()

    assert called["engine"] is models.engine
    assert (
        info_logs[-1]
        == "Database auto migration applied 1 column(s): servers.changelog_channel"
    )


def test_init_db_logs_when_no_auto_migration_needed(monkeypatch):
    info_logs = []

    monkeypatch.setattr(
        models.Model.metadata, "create_all", lambda eng, tables=None: None
    )
    monkeypatch.setattr("juliabot.migrations.upgrade", lambda engine: ())
    monkeypatch.setattr(models, "_auto_add_missing_simple_columns", lambda: [])
    monkeypatch.setattr(
        models.logger,
        "info",
        lambda message, *args: info_logs.append(message % args if args else message),
    )

    models.init_db()

    assert info_logs[-1] == "Database schema is up to date (no auto migration needed)"
