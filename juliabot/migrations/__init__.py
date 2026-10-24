"""Versioned, reversible schema migrations for JuliaBot.

Each module in ``versions`` exposes ``VERSION``, ``NAME``, ``upgrade`` and
``downgrade``. The applied version is tracked in the ``schema_migration`` table,
so upgrades and rollbacks are idempotent and can be automated by CI.
"""

from .runner import (
    Migration,
    MigrationError,
    MigrationStatus,
    current_version,
    discover_migrations,
    downgrade,
    status,
    upgrade,
)

__all__ = [
    "Migration",
    "MigrationError",
    "MigrationStatus",
    "current_version",
    "discover_migrations",
    "downgrade",
    "status",
    "upgrade",
]
