from types import SimpleNamespace

from sqlalchemy import Column, Integer, MetaData, String, Table

import juliabot.models as models


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
        lambda eng: called.setdefault("engine", eng),
    )
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
    assert info_logs[-1] == "Database auto migration applied 1 column(s): servers.changelog_channel"


def test_init_db_logs_when_no_auto_migration_needed(monkeypatch):
    info_logs = []

    monkeypatch.setattr(models.Model.metadata, "create_all", lambda eng: None)
    monkeypatch.setattr(models, "_auto_add_missing_simple_columns", lambda: [])
    monkeypatch.setattr(
        models.logger,
        "info",
        lambda message, *args: info_logs.append(message % args if args else message),
    )

    models.init_db()

    assert info_logs[-1] == "Database schema is up to date (no auto migration needed)"
