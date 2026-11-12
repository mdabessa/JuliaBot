"""Tests for the versioned migration runner and its CLI."""

from __future__ import annotations

import importlib
import json

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

from juliabot.migrations import (
    MigrationError,
    current_version,
    discover_migrations,
    downgrade,
    status,
    upgrade,
)
from juliabot.migrations.__main__ import main


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    yield engine
    engine.dispose()


def table_names(engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def test_discovery_returns_ordered_reversible_migrations():
    migrations = discover_migrations()

    assert [migration.version for migration in migrations] == [1, 2]
    assert [migration.name for migration in migrations] == [
        "create_session",
        "reminder_timestamptz",
    ]
    for migration in migrations:
        assert callable(migration.upgrade)
        assert callable(migration.downgrade)


def test_upgrade_creates_schema_and_records_version(engine):
    applied = upgrade(engine)

    assert [migration.version for migration in applied] == [1, 2]
    assert current_version(engine) == 2
    assert {"session", "schema_migration"} <= table_names(engine)


def test_upgrade_is_idempotent(engine):
    upgrade(engine)

    assert upgrade(engine) == ()
    assert current_version(engine) == 2


def test_dry_run_reports_pending_without_writing(engine):
    pending = upgrade(engine, dry_run=True)

    assert [migration.version for migration in pending] == [1, 2]
    assert current_version(engine) == 0
    assert "session" not in table_names(engine)


def test_downgrade_reverts_to_zero(engine):
    upgrade(engine)

    reverted = downgrade(engine, 0)

    assert [migration.version for migration in reverted] == [2, 1]
    assert current_version(engine) == 0
    assert "session" not in table_names(engine)


def test_downgrade_rejects_negative_target(engine):
    with pytest.raises(MigrationError):
        downgrade(engine, -1)


def test_status_reports_applied_flags(engine):
    assert status(engine)[0].applied is False

    upgrade(engine)

    assert status(engine)[0].applied is True


def test_cli_upgrade_status_and_downgrade(tmp_path, capsys):
    url = f"sqlite:///{tmp_path / 'bot.sqlite'}"

    assert main(["--database-url", url, "upgrade"]) == 0
    assert "Applied 2 migration(s)." in capsys.readouterr().out

    assert main(["--database-url", url, "status", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "current": 2,
        "migrations": [
            {"version": 1, "name": "create_session", "applied": True},
            {"version": 2, "name": "reminder_timestamptz", "applied": True},
        ],
    }

    assert main(["--database-url", url, "upgrade"]) == 0
    assert "Database is up to date." in capsys.readouterr().out

    assert main(["--database-url", url, "downgrade", "--to", "0"]) == 0
    out = capsys.readouterr().out
    assert "Reverted 2 migration(s)." in out
    assert "Current version: 0" in out


def test_cli_requires_a_database_url(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert main(["status"]) == 2
    assert "No database URL provided" in capsys.readouterr().err


MIGRATION_0002 = importlib.import_module(
    "juliabot.migrations.versions.0002_reminder_timestamptz"
)


class _RecordingDialect:
    def __init__(self, name: str, tables: set[str]) -> None:
        self.name = name
        self._tables = tables

    def has_table(self, connection, table_name, schema=None) -> bool:
        return table_name in self._tables


class _RecordingConnection:
    """Minimal ``Connection`` double that records the SQL it is given."""

    def __init__(self, dialect_name: str, tables: set[str]) -> None:
        self.dialect = _RecordingDialect(dialect_name, tables)
        self.statements: list[str] = []

    def execute(self, statement) -> None:
        self.statements.append(str(statement))


def test_reminder_timestamptz_upgrade_reads_old_values_as_utc():
    connection = _RecordingConnection("postgresql", {"reminder"})

    MIGRATION_0002.upgrade(connection)

    assert len(connection.statements) == 1
    statement = connection.statements[0]
    assert "ALTER COLUMN time_reminder TYPE timestamp with time zone" in statement
    assert "USING time_reminder AT TIME ZONE 'UTC'" in statement


def test_reminder_timestamptz_downgrade_restores_the_naive_column():
    connection = _RecordingConnection("postgresql", {"reminder"})

    MIGRATION_0002.downgrade(connection)

    assert len(connection.statements) == 1
    statement = connection.statements[0]
    assert "ALTER COLUMN time_reminder TYPE timestamp without time zone" in statement
    assert "USING time_reminder AT TIME ZONE 'UTC'" in statement


def test_reminder_timestamptz_is_a_noop_outside_postgres():
    connection = _RecordingConnection("sqlite", {"reminder"})

    MIGRATION_0002.upgrade(connection)
    MIGRATION_0002.downgrade(connection)

    assert connection.statements == []


def test_reminder_timestamptz_is_a_noop_without_the_legacy_table():
    connection = _RecordingConnection("postgresql", set())

    MIGRATION_0002.upgrade(connection)
    MIGRATION_0002.downgrade(connection)

    assert connection.statements == []


def test_reminder_timestamptz_is_recorded_on_a_real_database(engine):
    upgrade(engine, target=1)
    assert current_version(engine) == 1

    assert [migration.version for migration in upgrade(engine)] == [2]
    assert current_version(engine) == 2
