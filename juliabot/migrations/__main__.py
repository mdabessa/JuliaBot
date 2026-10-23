"""Command-line entry point for schema migrations.

Usage::

    python -m juliabot.migrations status [--json]
    python -m juliabot.migrations upgrade [--to VERSION] [--dry-run]
    python -m juliabot.migrations downgrade --to VERSION

The database URL is read from ``--database-url`` or ``DATABASE_URL``. This makes
the command usable both locally and from CI without importing the bot config.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from .runner import MigrationError, current_version, downgrade, status, upgrade


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the migration CLI."""
    parser = argparse.ArgumentParser(
        prog="python -m juliabot.migrations",
        description="Inspect and apply JuliaBot schema migrations.",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="SQLAlchemy database URL (defaults to DATABASE_URL).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="Show migration state.")
    status_parser.add_argument(
        "--json", action="store_true", help="Machine-readable output."
    )

    upgrade_parser = subparsers.add_parser("upgrade", help="Apply pending migrations.")
    upgrade_parser.add_argument("--to", type=int, default=None, help="Target version.")
    upgrade_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List pending migrations without applying.",
    )

    downgrade_parser = subparsers.add_parser(
        "downgrade", help="Revert migrations down to a version."
    )
    downgrade_parser.add_argument(
        "--to", type=int, required=True, help="Version to stop at (0 reverts all)."
    )

    return parser


def _resolve_url(explicit: str | None) -> str:
    """Resolve and normalise the database URL."""
    url = explicit or os.environ.get("DATABASE_URL")
    if not url:
        raise MigrationError(
            "No database URL provided. Pass --database-url or set DATABASE_URL."
        )
    return url.replace("postgres://", "postgresql://")


def main(argv: list[str] | None = None) -> int:
    """Run the requested migration command and return an exit code."""
    args = _build_parser().parse_args(argv)

    try:
        engine = create_engine(_resolve_url(args.database_url))
    except (MigrationError, SQLAlchemyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    try:
        if args.command == "status":
            states = status(engine)
            current = current_version(engine)
            if args.json:
                print(
                    json.dumps(
                        {
                            "current": current,
                            "migrations": [
                                {
                                    "version": state.version,
                                    "name": state.name,
                                    "applied": state.applied,
                                }
                                for state in states
                            ],
                        }
                    )
                )
            else:
                print(f"Current version: {current}")
                for state in states:
                    marker = "applied" if state.applied else "pending"
                    print(f"  {state.version:04d}  {marker:8s} {state.name}")
            return 0

        if args.command == "upgrade":
            pending = upgrade(engine, args.to, dry_run=args.dry_run)

            if args.dry_run:
                print(f"Pending migrations: {len(pending)}")
            elif pending:
                print(f"Applied {len(pending)} migration(s).")
            else:
                print("Database is up to date.")

            for migration in pending:
                print(f"  {migration.version:04d}  {migration.name}")
            return 0

        reverted = downgrade(engine, args.to)
        print(f"Reverted {len(reverted)} migration(s).")
        for migration in reverted:
            print(f"  {migration.version:04d}  {migration.name}")
        print(f"Current version: {current_version(engine)}")
        return 0

    except (MigrationError, SQLAlchemyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
