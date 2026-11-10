"""Build iCalendar events for one-shot Discord reminders.

The builder is pure: every value it needs is an argument, so the output is
deterministic and testable without a clock, a network or a database. Only the
CalDAV transport uses it.

Event shape (RFC 5545)::

    BEGIN:VCALENDAR
    VERSION:2.0
    PRODID:-//JuliaBot//reminder//EN
    BEGIN:VEVENT
    UID:juliabot-reminder-42@juliabot
    DTSTAMP:20261109T120000Z
    DTSTART:20261109T150000Z
    SUMMARY:Lembrete: pagar aluguel
    DESCRIPTION:Criado por !rm em #geral\\nhttps://discord.com/channels/10/20/1000
    END:VEVENT
    END:VCALENDAR

There is no ``DTEND`` (the event marks a moment, not a busy block), no
``VALARM`` (each calendar applies its own default reminder) and no attendee.
"""

from __future__ import annotations

from datetime import datetime, timezone

PRODID = "-//JuliaBot//reminder//EN"

#: RFC 5545 §3.1 recommends keeping content lines within 75 octets.
MAX_LINE_OCTETS = 75

#: Long Discord messages are clipped so summaries stay recognisable.
MAX_SUMMARY_LENGTH = 120

CRLF = "\r\n"


def escape_text(value: str) -> str:
    """Escape a TEXT value as required by RFC 5545 §3.3.11.

    Args:
        value (str): Raw text, e.g. a Discord message.

    Returns:
        str: The text with ``\\``, ``;``, ``,`` and line breaks escaped.
    """
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def fold_line(line: str) -> str:
    """Fold one content line into 75-octet chunks (RFC 5545 §3.1).

    Continuation lines start with a single space, which counts towards the
    limit, and multi-byte UTF-8 characters are never split.

    Args:
        line (str): A single unfolded content line.

    Returns:
        str: The line, folded with ``CRLF`` + space where necessary.
    """
    if len(line.encode("utf-8")) <= MAX_LINE_OCTETS:
        return line

    chunks: list[str] = []
    remaining = line
    limit = MAX_LINE_OCTETS

    while len(remaining.encode("utf-8")) > limit:
        size = 0
        cut = 0
        for index, char in enumerate(remaining):
            size += len(char.encode("utf-8"))
            if size > limit:
                break
            cut = index + 1
        chunks.append(remaining[:cut])
        remaining = remaining[cut:]
        limit = MAX_LINE_OCTETS - 1

    chunks.append(remaining)
    return f"{CRLF} ".join(chunks)


def _clip_summary(value: str) -> str:
    """Clip already-escaped text, never ending on a half-cut escape sequence."""
    clipped = value[:MAX_SUMMARY_LENGTH]

    trailing_backslashes = len(clipped) - len(clipped.rstrip("\\"))
    if trailing_backslashes % 2:
        clipped = clipped[:-1]

    return clipped


def build_event(
    uid: str,
    start: datetime,
    summary: str,
    description: str,
    stamp: datetime,
) -> str:
    """Render a zero-length VEVENT for a reminder.

    Args:
        uid (str): Stable event identifier, e.g. ``juliabot-reminder-42@juliabot``.
        start (datetime): The instant the reminder fires. A naive value is UTC.
        summary (str): Event title; escaped, then clipped to
            ``MAX_SUMMARY_LENGTH`` characters.
        description (str): Event body, escaped before folding.
        stamp (datetime): Creation time (``DTSTAMP``). Passed in so the output
            is deterministic.

    Returns:
        str: A complete VCALENDAR document with CRLF line endings.
    """
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{_format_utc(stamp)}",
        f"DTSTART:{_format_utc(start)}",
        f"SUMMARY:{_clip_summary(escape_text(summary))}",
        f"DESCRIPTION:{escape_text(description)}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]

    return "".join(f"{fold_line(line)}{CRLF}" for line in lines)


def _format_utc(value: datetime) -> str:
    """Format an instant as an RFC 5545 UTC timestamp.

    A naive value is read as UTC, never as the host's local time.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
