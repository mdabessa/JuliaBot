"""Mirror one-shot Discord reminders into an existing Nextcloud calendar.

The module has three layers:

* a pure iCalendar builder (``build_event``, ``escape_text``, ``fold_line``)
  that needs no clock, network or database;
* ``NextcloudConfig``, which is only built when every ``NEXTCLOUD_*`` setting
  is present, and therefore doubles as the feature flag;
* ``CalendarClient``, a thin CalDAV transport that resolves a calendar by
  display name and writes events into it.

The calendar is never read back: Discord remains the only place a reminder is
created, delivered and removed.

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

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote

PRODID = "-//JuliaBot//reminder//EN"

#: RFC 5545 §3.1 recommends keeping content lines within 75 octets.
MAX_LINE_OCTETS = 75

#: Long Discord messages are clipped so summaries stay recognisable.
MAX_SUMMARY_LENGTH = 120

CRLF = "\r\n"

#: Every one of these must be set for the mirror to be enabled.
ENV_URL = "NEXTCLOUD_URL"
ENV_USER = "NEXTCLOUD_USER"
ENV_APP_PASSWORD = "NEXTCLOUD_APP_PASSWORD"
ENV_CALENDAR = "NEXTCLOUD_CALENDAR"
ENV_REMINDER_USER_ID = "REMINDER_CALENDAR_USER_ID"

SETTING_NAMES = (
    ENV_URL,
    ENV_USER,
    ENV_APP_PASSWORD,
    ENV_CALENDAR,
    ENV_REMINDER_USER_ID,
)


@dataclass(frozen=True)
class NextcloudConfig:
    """Settings for mirroring reminders into an existing Nextcloud calendar.

    The configuration exists only when every setting is present, so its
    presence is the feature flag: ``None`` from :meth:`from_env` means the
    mirror is off and no reminder touches the network.
    """

    url: str
    user: str
    app_password: str
    calendar: str
    reminder_user_id: str

    @classmethod
    def from_env(cls) -> NextcloudConfig | None:
        """Read the settings from the environment.

        Returns:
            NextcloudConfig | None: The configuration, or None when any
            setting is missing or blank.
        """
        values = {name: (os.environ.get(name) or "").strip() for name in SETTING_NAMES}
        if not all(values.values()):
            return None

        return cls(
            url=values[ENV_URL].rstrip("/"),
            user=values[ENV_USER],
            app_password=values[ENV_APP_PASSWORD],
            calendar=values[ENV_CALENDAR],
            reminder_user_id=values[ENV_REMINDER_USER_ID],
        )

    @property
    def calendars_url(self) -> str:
        """Return the CalDAV collection that holds the user's calendars."""
        return f"{self.url}/remote.php/dav/calendars/{quote(self.user, safe='')}/"


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
