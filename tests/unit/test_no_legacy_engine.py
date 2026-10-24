"""Guards that the legacy Script engine stays removed."""

from __future__ import annotations

from pathlib import Path

LEGACY_REFERENCES = ("juliabot.scripts", "from ..scripts")


def test_legacy_engine_module_is_gone():
    assert not Path("juliabot/scripts.py").exists()


def test_no_source_module_references_the_legacy_engine():
    offenders = []
    for path in Path("juliabot").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if any(reference in source for reference in LEGACY_REFERENCES):
            offenders.append(str(path))

    assert offenders == [], f"Legacy engine references remain: {offenders}"
