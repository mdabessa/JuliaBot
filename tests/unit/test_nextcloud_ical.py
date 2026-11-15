"""Tests for the pure iCalendar event builder.

Every case runs without a clock, a network, a database or the host timezone:
``build_event`` receives its values as arguments, so the output is exact.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest
import pytz

from juliabot import nextcloud

GOLDEN = Path(__file__).resolve().parent.parent / "golden" / "nextcloud_reminder.ics"

UID = "juliabot-reminder-42@juliabot"
START = datetime.datetime(2026, 11, 9, 15, 0, tzinfo=datetime.timezone.utc)
STAMP = datetime.datetime(2026, 11, 9, 12, 0, tzinfo=datetime.timezone.utc)
SUMMARY = "Lembrete: pagar aluguel"
DESCRIPTION = "Criado por !rm em #geral\nhttps://discord.com/channels/1/2/3"


def build(**overrides) -> str:
    """Render the reference event, overriding individual arguments."""
    values = {
        "uid": UID,
        "start": START,
        "summary": SUMMARY,
        "description": DESCRIPTION,
        "stamp": STAMP,
    }
    values.update(overrides)
    return nextcloud.build_event(**values)


def content_line(event: str, name: str) -> str:
    """Return the unfolded value of the named property."""
    lines = event.split("\r\n")

    for index, line in enumerate(lines):
        if not line.startswith(name):
            continue

        parts = [line[len(name) :]]
        for continuation in lines[index + 1 :]:
            if not continuation.startswith(" "):
                break
            parts.append(continuation[1:])

        return "".join(parts)

    raise AssertionError(f"{name} is missing from {event!r}")


def test_build_event_matches_the_golden_file():
    with GOLDEN.open(encoding="utf-8", newline="") as handle:
        expected = handle.read()

    assert build() == expected


def test_event_is_a_calendar_with_crlf_line_endings():
    event = build()

    assert event.startswith("BEGIN:VCALENDAR\r\n")
    assert event.endswith("END:VCALENDAR\r\n")
    assert "\n" not in event.replace("\r\n", ""), "every line must end with CRLF"


def test_event_has_no_dtend_alarm_attendee_or_rule():
    event = build()

    for forbidden in ("DTEND", "VALARM", "ATTENDEE", "RRULE"):
        assert forbidden not in event


def test_event_carries_the_documented_properties():
    event = build()

    assert content_line(event, "UID:") == UID
    assert content_line(event, "PRODID:") == nextcloud.PRODID
    assert content_line(event, "VERSION:") == "2.0"
    assert content_line(event, "SUMMARY:") == SUMMARY


def test_dtstart_is_utc_for_an_aware_value_in_another_timezone():
    sao_paulo = pytz.timezone("America/Sao_Paulo")
    event = build(start=sao_paulo.localize(datetime.datetime(2026, 11, 9, 12, 0)))

    assert content_line(event, "DTSTART:") == "20261109T150000Z"


def test_dtstart_treats_a_naive_value_as_utc():
    event = build(start=datetime.datetime(2026, 11, 9, 15, 0))

    assert content_line(event, "DTSTART:") == "20261109T150000Z"


def test_dtstamp_comes_from_the_stamp_argument():
    event = build(
        stamp=datetime.datetime(2026, 11, 9, 12, 30, tzinfo=datetime.timezone.utc)
    )

    assert content_line(event, "DTSTAMP:") == "20261109T123000Z"


@pytest.mark.parametrize(
    ("raw", "escaped"),
    [
        ("plain text", "plain text"),
        ("back\\slash", "back\\\\slash"),
        ("semi;colon", "semi\\;colon"),
        ("comma,separated", "comma\\,separated"),
        ("line\nbreak", "line\\nbreak"),
        ("windows\r\nbreak", "windows\\nbreak"),
        ("all; of, it\\\n", "all\\; of\\, it\\\\\\n"),
    ],
)
def test_escape_text_follows_rfc_5545(raw, escaped):
    assert nextcloud.escape_text(raw) == escaped


def test_build_event_escapes_summary_and_description():
    event = build(summary="a;b,c\\d", description="e;f,g\\h\ni")

    assert content_line(event, "SUMMARY:") == "a\\;b\\,c\\\\d"
    assert content_line(event, "DESCRIPTION:") == "e\\;f\\,g\\\\h\\ni"


def test_fold_line_leaves_a_line_of_exactly_75_octets_alone():
    line = "SUMMARY:" + "a" * (nextcloud.MAX_LINE_OCTETS - len("SUMMARY:"))

    assert len(line.encode("utf-8")) == nextcloud.MAX_LINE_OCTETS
    assert nextcloud.fold_line(line) == line


def test_fold_line_splits_a_longer_line_at_75_octets():
    line = "SUMMARY:" + "a" * 80

    folded = nextcloud.fold_line(line)

    assert folded == f"{line[:75]}\r\n {line[75:]}"


def test_fold_line_keeps_every_chunk_within_the_limit():
    line = "DESCRIPTION:" + "x" * 200

    for chunk in nextcloud.fold_line(line).split("\r\n"):
        assert len(chunk.encode("utf-8")) <= nextcloud.MAX_LINE_OCTETS


def test_fold_line_never_splits_a_multibyte_character():
    line = "SUMMARY:" + "é" * 60

    folded = nextcloud.fold_line(line)
    chunks = folded.split("\r\n")

    # 8 + 33 * 2 = 74 octets: a 34th two-octet character would overflow.
    assert chunks[0] == "SUMMARY:" + "é" * 33
    assert folded.replace("\r\n ", "") == line
    for chunk in chunks:
        assert len(chunk.encode("utf-8")) <= nextcloud.MAX_LINE_OCTETS


def test_build_event_folds_long_values():
    event = build(description="x" * 200)

    assert "\r\n " in event
    for line in event.split("\r\n"):
        assert len(line.encode("utf-8")) <= nextcloud.MAX_LINE_OCTETS


def test_summary_is_clipped_to_the_maximum_length():
    event = build(summary="a" * 300)

    assert content_line(event, "SUMMARY:") == "a" * nextcloud.MAX_SUMMARY_LENGTH


def test_summary_is_escaped_before_being_clipped():
    event = build(summary=";" * 100)

    value = content_line(event, "SUMMARY:")

    assert value == "\\;" * (nextcloud.MAX_SUMMARY_LENGTH // 2)


def test_clipping_never_leaves_a_dangling_escape():
    event = build(summary="a" + ";" * 100)

    value = content_line(event, "SUMMARY:")

    assert value == "a" + "\\;" * 59
    assert not value.endswith("\\")
