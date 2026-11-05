"""Discovery, ordering, and execution of versioned schema migrations.

The runner is deliberately small and dialect-agnostic: migrations are plain
Python callables receiving an open SQLAlchemy connection, and the applied
version lives in a single ``schema_migration`` table.
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, cast

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

if TYPE_CHECKING:
    from sqlalchemy.engine import CursorResult
from . import versions as versions_package

SCHEMA_TABLE = "schema_migration"
_ADVISORY_LOCK_KEY = 0x4A554C49  # "JULI" — serialises concurrent migrations.

MigrationCallable = Callable[[Connection], None]


class MigrationError(RuntimeError):
    """Raised when migration discovery or execution is invalid."""


@dataclass(frozen=True)
class Migration:
    """One versioned schema change with both directions."""

    version: int
    name: str
    upgrade: MigrationCallable
    downgrade: MigrationCallable


@dataclass(frozen=True)
class MigrationStatus:
    """The applied state of one discovered migration."""

    version: int
    name: str
    applied: bool


def discover_migrations() -> tuple[Migration, ...]:
    """Import every module in ``versions`` and return them sorted by version."""
    found: list[Migration] = []

    for module_info in pkgutil.iter_modules(versions_package.__path__):
        module = importlib.import_module(
            f"{versions_package.__name__}.{module_info.name}"
        )
        version = getattr(module, "VERSION", None)
        name = getattr(module, "NAME", None)
        upgrade_fn = getattr(module, "upgrade", None)
        downgrade_fn = getattr(module, "downgrade", None)

        if not isinstance(version, int) or version < 1:
            raise MigrationError(
                f"{module.__name__} must define a positive integer VERSION"
            )
        if not isinstance(name, str) or not name:
            raise MigrationError(f"{module.__name__} must define a non-empty NAME")
        if not callable(upgrade_fn) or not callable(downgrade_fn):
            raise MigrationError(
                f"{module.__name__} must define upgrade() and downgrade()"
            )

        found.append(
            Migration(
                version,
                name,
                cast(MigrationCallable, upgrade_fn),
                cast(MigrationCallable, downgrade_fn),
            )
        )

    versions_seen: set[int] = set()
    for migration in found:
        if migration.version in versions_seen:
            raise MigrationError(f"Duplicate migration version: {migration.version}")
        versions_seen.add(migration.version)

    return tuple(sorted(found, key=lambda migration: migration.version))


def _has_schema_table(connection: Connection) -> bool:
    """Return whether the version table exists without creating it."""
    return connection.dialect.has_table(connection, SCHEMA_TABLE)


def _ensure_schema_table(connection: Connection) -> None:
    """Create the version table if it does not exist."""
    connection.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {SCHEMA_TABLE} (
                version INTEGER NOT NULL PRIMARY KEY,
                name VARCHAR(128) NOT NULL,
                applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )


def _applied_versions(connection: Connection) -> set[int]:
    """Return the versions already recorded in the database."""
    if not _has_schema_table(connection):
        return set()
    result = cast(
        "CursorResult", connection.execute(text(f"SELECT version FROM {SCHEMA_TABLE}"))
    )
    return {int(row[0]) for row in result}


def _lock(connection: Connection, engine: Engine) -> None:
    """Serialise concurrent migrations on Postgres."""
    if engine.dialect.name == "postgresql":
        connection.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": _ADVISORY_LOCK_KEY}
        )


def current_version(engine: Engine) -> int:
    """Return the highest applied version, or ``0`` when none is applied."""
    with engine.begin() as connection:
        applied = _applied_versions(connection)
    return max(applied, default=0)


def status(engine: Engine) -> tuple[MigrationStatus, ...]:
    """Return every discovered migration with its applied flag."""
    migrations = discover_migrations()
    with engine.begin() as connection:
        applied = _applied_versions(connection)
    return tuple(
        MigrationStatus(migration.version, migration.name, migration.version in applied)
        for migration in migrations
    )


def upgrade(
    engine: Engine,
    target: int | None = None,
    *,
    dry_run: bool = False,
) -> tuple[Migration, ...]:
    """Apply pending migrations up to ``target`` (default: the latest)."""
    migrations = discover_migrations()
    target_version = migrations[-1].version if target is None and migrations else target
    if target_version is None:
        target_version = 0
    if target_version < 0:
        raise MigrationError("Target version cannot be negative")

    with engine.begin() as connection:
        _lock(connection, engine)
        if dry_run:
            applied = _applied_versions(connection)
        else:
            _ensure_schema_table(connection)
            applied = _applied_versions(connection)

        pending = tuple(
            migration
            for migration in migrations
            if migration.version not in applied and migration.version <= target_version
        )
        if dry_run:
            return pending

        for migration in pending:
            migration.upgrade(connection)
            connection.execute(
                text(
                    f"INSERT INTO {SCHEMA_TABLE} (version, name) VALUES (:version, :name)"
                ),
                {"version": migration.version, "name": migration.name},
            )

    return pending


def downgrade(engine: Engine, target: int = 0) -> tuple[Migration, ...]:
    """Revert applied migrations down to ``target`` (exclusive)."""
    if target < 0:
        raise MigrationError("Target version cannot be negative")

    migrations = discover_migrations()
    reverted: list[Migration] = []

    with engine.begin() as connection:
        _lock(connection, engine)
        _ensure_schema_table(connection)
        applied = _applied_versions(connection)

        for migration in reversed(migrations):
            if migration.version in applied and migration.version > target:
                migration.downgrade(connection)
                connection.execute(
                    text(f"DELETE FROM {SCHEMA_TABLE} WHERE version = :version"),
                    {"version": migration.version},
                )
                reverted.append(migration)

    return tuple(reverted)
