"""Tests for the versioned migration runner and its CLI."""

from __future__ import annotations

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

    assert [migration.version for migration in migrations] == [1]
    assert migrations[0].name == "create_session"
    assert callable(migrations[0].upgrade)
    assert callable(migrations[0].downgrade)


def test_upgrade_creates_schema_and_records_version(engine):
    applied = upgrade(engine)

    assert [migration.version for migration in applied] == [1]
    assert current_version(engine) == 1
    assert {"session", "schema_migration"} <= table_names(engine)


def test_upgrade_is_idempotent(engine):
    upgrade(engine)

    assert upgrade(engine) == ()
    assert current_version(engine) == 1


def test_dry_run_reports_pending_without_writing(engine):
    pending = upgrade(engine, dry_run=True)

    assert [migration.version for migration in pending] == [1]
    assert current_version(engine) == 0
    assert "session" not in table_names(engine)


def test_downgrade_reverts_to_zero(engine):
    upgrade(engine)

    reverted = downgrade(engine, 0)

    assert [migration.version for migration in reverted] == [1]
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
    assert "Applied 1 migration(s)." in capsys.readouterr().out

    assert main(["--database-url", url, "status", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "current": 1,
        "migrations": [{"version": 1, "name": "create_session", "applied": True}],
    }

    assert main(["--database-url", url, "upgrade"]) == 0
    assert "Database is up to date." in capsys.readouterr().out

    assert main(["--database-url", url, "downgrade", "--to", "0"]) == 0
    out = capsys.readouterr().out
    assert "Reverted 1 migration(s)." in out
    assert "Current version: 0" in out


def test_cli_requires_a_database_url(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert main(["status"]) == 2
    assert "No database URL provided" in capsys.readouterr().err
