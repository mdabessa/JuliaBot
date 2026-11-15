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

import asyncio
import base64
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import NamedTuple
from urllib.parse import quote
from xml.etree import ElementTree

import aiohttp

logger = logging.getLogger(__name__)

DAV_NAMESPACE = "{DAV:}"
CALDAV_NAMESPACE = "{urn:ietf:params:xml:ns:caldav}"

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


def _basic_auth(user: str, app_password: str) -> str:
    """Build the ``Authorization`` header value for an app password."""
    token = base64.b64encode(f"{user}:{app_password}".encode("utf-8")).decode("ascii")

    return f"Basic {token}"


class NextcloudError(RuntimeError):
    """Raised when Nextcloud answers a calendar operation unexpectedly."""


class CalendarCollection(NamedTuple):
    """One calendar advertised by a CalDAV ``PROPFIND``."""

    href: str
    name: str


PROPFIND_BODY = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
    "<d:prop><d:displayname/><d:resourcetype/></d:prop>"
    "</d:propfind>"
)


def parse_calendar_list(body: bytes) -> list[CalendarCollection]:
    """Extract the calendars from a CalDAV multistatus document.

    Collections whose ``resourcetype`` is not a CalDAV calendar (address books,
    or the parent collection itself) are ignored.

    Args:
        body (bytes): Raw ``PROPFIND`` response body.

    Returns:
        list[CalendarCollection]: Calendars with their href and display name.
    """
    root = ElementTree.fromstring(body)
    calendars: list[CalendarCollection] = []

    for response in root.iter(f"{DAV_NAMESPACE}response"):
        href = (response.findtext(f"{DAV_NAMESPACE}href") or "").strip()
        if not href:
            continue

        for propstat in response.findall(f"{DAV_NAMESPACE}propstat"):
            prop = propstat.find(f"{DAV_NAMESPACE}prop")
            if prop is None:
                continue
            if (
                prop.find(f"{DAV_NAMESPACE}resourcetype/{CALDAV_NAMESPACE}calendar")
                is None
            ):
                continue

            name = (prop.findtext(f"{DAV_NAMESPACE}displayname") or "").strip()
            calendars.append(CalendarCollection(href, name))

    return calendars


class CalendarClient:
    """Resolve the configured calendar and write reminder events into it.

    The HTTP session is injected (``aiohttp.ClientSession`` or a fake), so no
    test has to touch the network. The resolved href is cached for the process
    lifetime; credentials are never logged.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        config: NextcloudConfig,
        *,
        timeout: float = 5.0,
    ) -> None:
        self._session = session
        self._config = config
        self._timeout = timeout
        self._auth_headers = {
            "Authorization": _basic_auth(config.user, config.app_password)
        }
        self._calendar_url: str | None = None
        self._unresolvable = False

    async def resolve_calendar(self) -> str | None:
        """Return the absolute URL of the configured calendar.

        The href is cached for the process lifetime. A calendar name that is
        missing or matches more than once disables the mirror instead of
        guessing; a transient failure is retried on the next call.

        Returns:
            str | None: The calendar URL, or None when it cannot be resolved.
        """
        if self._calendar_url is not None:
            return self._calendar_url
        if self._unresolvable:
            return None

        try:
            calendars = await self._list_calendars()
        except (
            asyncio.TimeoutError,
            aiohttp.ClientError,
            NextcloudError,
            ElementTree.ParseError,
        ) as error:
            logger.warning("Could not list Nextcloud calendars: %s", error)
            return None

        url = self._select_calendar(calendars)
        if url is None:
            return None

        self._calendar_url = url
        logger.info(
            "Mirroring reminders into Nextcloud calendar %r at %s",
            self._config.calendar,
            self._config.url,
        )
        return url

    async def put_event(self, uid: str, ics: str) -> bool:
        """Store one event, leaving an existing event with the same UID alone.

        Args:
            uid (str): Event identifier; it names the ``.ics`` resource.
            ics (str): The full VCALENDAR document.

        Returns:
            bool: True when the calendar holds the event afterwards, False
            when the calendar could not be resolved.

        Raises:
            NextcloudError: When the server rejects the request.
        """
        calendar_url = await self.resolve_calendar()
        if calendar_url is None:
            return False

        url = f"{calendar_url}{quote(uid, safe='')}.ics"
        status, _body = await self._send(
            "PUT",
            url,
            headers={
                "Content-Type": "text/calendar; charset=utf-8",
                "If-None-Match": "*",
            },
            data=ics.encode("utf-8"),
        )

        if status == 412:
            logger.info("Reminder event %s is already stored; leaving it as is", uid)
            return True
        if status >= 400:
            raise NextcloudError(f"storing event {uid} returned HTTP {status}")

        return True

    async def _list_calendars(self) -> list[CalendarCollection]:
        status, body = await self._send(
            "PROPFIND",
            self._config.calendars_url,
            headers={
                "Depth": "1",
                "Content-Type": "application/xml; charset=utf-8",
            },
            data=PROPFIND_BODY.encode("utf-8"),
        )
        if status != 207:
            raise NextcloudError(f"listing calendars returned HTTP {status}")

        return parse_calendar_list(body)

    async def _send(self, method: str, url: str, **kwargs) -> tuple[int, bytes]:
        headers = {**self._auth_headers, **kwargs.pop("headers", {})}
        timeout = aiohttp.ClientTimeout(total=self._timeout)
        async with self._session.request(
            method, url, headers=headers, timeout=timeout, **kwargs
        ) as response:
            return response.status, await response.read()

    def _select_calendar(self, calendars: list[CalendarCollection]) -> str | None:
        wanted = self._config.calendar
        exact = [calendar for calendar in calendars if calendar.name == wanted]
        matches = exact or [
            calendar
            for calendar in calendars
            if calendar.name.casefold() == wanted.casefold()
        ]

        if len(matches) == 1:
            return self._absolute(matches[0].href)

        self._unresolvable = True
        if matches:
            logger.warning(
                "%d Nextcloud calendars are named %r; refusing to guess. "
                "The reminder mirror is disabled.",
                len(matches),
                wanted,
            )
        else:
            available = ", ".join(sorted(c.name for c in calendars)) or "none"
            logger.warning(
                "No Nextcloud calendar is named %r; available: %s. "
                "The reminder mirror is disabled.",
                wanted,
                available,
            )

        return None

    def _absolute(self, href: str) -> str:
        if href.startswith(("http://", "https://")):
            url = href
        else:
            url = f"{self._config.url}{href}"

        return url if url.endswith("/") else f"{url}/"


def reminder_uid(reminder) -> str:
    """Return the stable calendar UID for a reminder row."""
    return f"juliabot-reminder-{reminder.id}@juliabot"


def reminder_summary(message) -> str:
    """Build the event title from the message the reminder was created from.

    ``Reminder`` stores no text, so the Discord message is the only source of
    the wording (PLAN.md §1 #11). Only the first line is used, so a multiline
    message stays a title.
    """
    content = (getattr(message, "content", "") or "").strip()
    first_line = content.splitlines()[0].strip() if content else ""

    return f"Lembrete: {first_line}"


def reminder_description(message) -> str:
    """Build the event body: where the reminder came from, plus its permalink."""
    channel = getattr(message, "channel", None)
    channel_name = getattr(channel, "name", None) or "desconhecido"
    guild = getattr(message, "guild", None)
    guild_id = getattr(guild, "id", None)
    channel_id = getattr(channel, "id", None)
    message_id = getattr(message, "id", None)

    lines = [f"Criado por !rm em #{channel_name}"]
    if guild_id is not None and channel_id is not None and message_id is not None:
        lines.append(
            f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"
        )

    return "\n".join(lines)


async def publish_reminder(
    client: CalendarClient,
    reminder,
    message,
    *,
    stamp: datetime | None = None,
) -> bool:
    """Mirror one reminder row into the configured calendar.

    Args:
        client (CalendarClient): Transport that owns the calendar href.
        reminder: The persisted ``Reminder``; its id names the UID and its
            ``time_reminder`` is the event's instant.
        message: The Discord message the reminder points at; supplies the
            title and the permalink.
        stamp (datetime, optional): ``DTSTAMP`` value. Defaults to now.

    Returns:
        bool: True when the calendar holds the event, False when the calendar
        could not be resolved.
    """
    uid = reminder_uid(reminder)
    ics = build_event(
        uid=uid,
        start=reminder.time_reminder,
        summary=reminder_summary(message),
        description=reminder_description(message),
        stamp=stamp or datetime.now(timezone.utc),
    )

    return await client.put_event(uid, ics)
