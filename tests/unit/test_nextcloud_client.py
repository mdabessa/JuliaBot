"""Tests for the CalDAV transport.

Every case injects a fake ``aiohttp`` session: no test opens a socket, reads
the host timezone or waits on a real timeout.
"""

from __future__ import annotations

import base64
import logging
from types import SimpleNamespace

import aiohttp
import pytest

from juliabot import nextcloud

CONFIG = nextcloud.NextcloudConfig(
    url="https://cloud.example.com",
    user="julia",
    app_password="app-password",
    calendar="Lembretes",
    reminder_user_id="1234",
)

CALENDAR_COLLECTION = "<d:collection/><c:calendar/>"
PLAIN_COLLECTION = "<d:collection/>"
ICS = "BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"


class FakeResponse:
    """Minimal stand-in for an ``aiohttp.ClientResponse``."""

    def __init__(self, status: int, body: bytes = b"") -> None:
        self.status = status
        self._body = body

    async def read(self) -> bytes:
        return self._body

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class FakeSession:
    """Replays queued responses (or exceptions) and records the requests."""

    def __init__(self, *actions) -> None:
        self.actions = list(actions)
        self.requests: list[SimpleNamespace] = []

    def request(self, method: str, url: str, **kwargs):
        self.requests.append(SimpleNamespace(method=method, url=url, kwargs=kwargs))
        if not self.actions:
            raise AssertionError(f"unexpected request: {method} {url}")

        action = self.actions.pop(0)
        if isinstance(action, Exception):
            raise action
        return action


def multistatus(*entries) -> bytes:
    """Render a CalDAV multistatus body from ``(href, name, resourcetype)``."""
    responses = "".join(
        "<d:response>"
        f"<d:href>{href}</d:href>"
        "<d:propstat><d:prop>"
        f"<d:displayname>{name}</d:displayname>"
        f"<d:resourcetype>{resource}</d:resourcetype>"
        "</d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat>"
        "</d:response>"
        for href, name, resource in entries
    )
    body = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
        f"{responses}</d:multistatus>"
    )
    return body.encode("utf-8")


def client_for(session: FakeSession, config: nextcloud.NextcloudConfig = CONFIG):
    return nextcloud.CalendarClient(session, config)


def test_parse_calendar_list_extracts_calendars_only():
    body = multistatus(
        ("/remote.php/dav/calendars/julia/", "", PLAIN_COLLECTION),
        ("/remote.php/dav/calendars/julia/personal/", "Pessoal", CALENDAR_COLLECTION),
        (
            "/remote.php/dav/calendars/julia/lembretes/",
            "Lembretes",
            CALENDAR_COLLECTION,
        ),
    )

    calendars = nextcloud.parse_calendar_list(body)

    assert calendars == [
        nextcloud.CalendarCollection(
            "/remote.php/dav/calendars/julia/personal/", "Pessoal"
        ),
        nextcloud.CalendarCollection(
            "/remote.php/dav/calendars/julia/lembretes/", "Lembretes"
        ),
    ]


@pytest.mark.asyncio
async def test_resolve_calendar_returns_the_matching_calendar_url():
    session = FakeSession(
        FakeResponse(
            207,
            multistatus(
                (
                    "/remote.php/dav/calendars/julia/personal/",
                    "Pessoal",
                    CALENDAR_COLLECTION,
                ),
                (
                    "/remote.php/dav/calendars/julia/lembretes/",
                    "Lembretes",
                    CALENDAR_COLLECTION,
                ),
            ),
        )
    )

    url = await client_for(session).resolve_calendar()

    assert url == "https://cloud.example.com/remote.php/dav/calendars/julia/lembretes/"


@pytest.mark.asyncio
async def test_resolve_calendar_asks_for_display_names_with_depth_one():
    session = FakeSession(FakeResponse(207, multistatus()))

    await client_for(session).resolve_calendar()

    (request,) = session.requests
    assert request.method == "PROPFIND"
    assert request.url == "https://cloud.example.com/remote.php/dav/calendars/julia/"
    assert request.kwargs["headers"]["Depth"] == "1"
    body = request.kwargs["data"].decode("utf-8")
    assert "displayname" in body
    assert "resourcetype" in body


@pytest.mark.asyncio
async def test_resolve_calendar_caches_the_href():
    session = FakeSession(
        FakeResponse(
            207,
            multistatus(
                (
                    "/remote.php/dav/calendars/julia/lembretes/",
                    "Lembretes",
                    CALENDAR_COLLECTION,
                )
            ),
        )
    )
    client = client_for(session)

    first = await client.resolve_calendar()
    second = await client.resolve_calendar()

    assert first == second
    assert len(session.requests) == 1


@pytest.mark.asyncio
async def test_resolve_calendar_prefers_an_exact_name_match():
    session = FakeSession(
        FakeResponse(
            207,
            multistatus(
                (
                    "/remote.php/dav/calendars/julia/upper/",
                    "LEMBRETES",
                    CALENDAR_COLLECTION,
                ),
                (
                    "/remote.php/dav/calendars/julia/exact/",
                    "Lembretes",
                    CALENDAR_COLLECTION,
                ),
            ),
        )
    )

    url = await client_for(session).resolve_calendar()

    assert url == "https://cloud.example.com/remote.php/dav/calendars/julia/exact/"


@pytest.mark.asyncio
async def test_resolve_calendar_falls_back_to_a_case_insensitive_match():
    session = FakeSession(
        FakeResponse(
            207,
            multistatus(
                (
                    "/remote.php/dav/calendars/julia/shouty/",
                    "LEMBRETES",
                    CALENDAR_COLLECTION,
                )
            ),
        )
    )

    url = await client_for(session).resolve_calendar()

    assert url == "https://cloud.example.com/remote.php/dav/calendars/julia/shouty/"


@pytest.mark.asyncio
async def test_resolve_calendar_ignores_collections_that_are_not_calendars():
    session = FakeSession(
        FakeResponse(
            207,
            multistatus(
                (
                    "/remote.php/dav/calendars/julia/lembretes/",
                    "Lembretes",
                    PLAIN_COLLECTION,
                )
            ),
        )
    )

    assert await client_for(session).resolve_calendar() is None


@pytest.mark.asyncio
async def test_resolve_calendar_gives_up_and_lists_the_available_names(caplog):
    session = FakeSession(
        FakeResponse(
            207,
            multistatus(
                (
                    "/remote.php/dav/calendars/julia/personal/",
                    "Pessoal",
                    CALENDAR_COLLECTION,
                )
            ),
        )
    )

    with caplog.at_level(logging.WARNING, logger="juliabot.nextcloud"):
        assert await client_for(session).resolve_calendar() is None

    assert "Pessoal" in caplog.text


@pytest.mark.asyncio
async def test_resolve_calendar_refuses_to_guess_between_ambiguous_names(caplog):
    session = FakeSession(
        FakeResponse(
            207,
            multistatus(
                (
                    "/remote.php/dav/calendars/julia/one/",
                    "lembretes",
                    CALENDAR_COLLECTION,
                ),
                (
                    "/remote.php/dav/calendars/julia/two/",
                    "LEMBRETES",
                    CALENDAR_COLLECTION,
                ),
            ),
        )
    )
    client = client_for(session)

    with caplog.at_level(logging.WARNING, logger="juliabot.nextcloud"):
        assert await client.resolve_calendar() is None

    assert "refusing to guess" in caplog.text
    assert await client.resolve_calendar() is None
    assert len(session.requests) == 1, "an ambiguous calendar must not be relisted"


@pytest.mark.asyncio
async def test_resolve_calendar_retries_after_a_transient_failure():
    session = FakeSession(
        aiohttp.ClientError("connection reset"),
        FakeResponse(
            207,
            multistatus(
                (
                    "/remote.php/dav/calendars/julia/lembretes/",
                    "Lembretes",
                    CALENDAR_COLLECTION,
                )
            ),
        ),
    )
    client = client_for(session)

    assert await client.resolve_calendar() is None
    assert (
        await client.resolve_calendar()
        == "https://cloud.example.com/remote.php/dav/calendars/julia/lembretes/"
    )


@pytest.mark.asyncio
async def test_resolve_calendar_returns_none_on_an_unexpected_status():
    session = FakeSession(FakeResponse(500))

    assert await client_for(session).resolve_calendar() is None


@pytest.mark.asyncio
async def test_put_event_uploads_with_if_none_match():
    session = FakeSession(
        FakeResponse(
            207,
            multistatus(
                (
                    "/remote.php/dav/calendars/julia/lembretes/",
                    "Lembretes",
                    CALENDAR_COLLECTION,
                )
            ),
        ),
        FakeResponse(201),
    )
    client = client_for(session)

    stored = await client.put_event("juliabot-reminder-42@juliabot", ICS)

    assert stored is True
    put = session.requests[-1]
    assert put.method == "PUT"
    assert put.url == (
        "https://cloud.example.com/remote.php/dav/calendars/julia/lembretes/"
        "juliabot-reminder-42%40juliabot.ics"
    )
    assert put.kwargs["headers"]["If-None-Match"] == "*"
    assert put.kwargs["headers"]["Content-Type"].startswith("text/calendar")
    assert put.kwargs["data"] == ICS.encode("utf-8")


@pytest.mark.asyncio
async def test_put_event_treats_a_412_as_success():
    session = FakeSession(
        FakeResponse(
            207,
            multistatus(
                (
                    "/remote.php/dav/calendars/julia/lembretes/",
                    "Lembretes",
                    CALENDAR_COLLECTION,
                )
            ),
        ),
        FakeResponse(412),
    )

    assert await client_for(session).put_event("uid", ICS) is True


@pytest.mark.asyncio
async def test_put_event_raises_when_the_server_rejects_the_event():
    session = FakeSession(
        FakeResponse(
            207,
            multistatus(
                (
                    "/remote.php/dav/calendars/julia/lembretes/",
                    "Lembretes",
                    CALENDAR_COLLECTION,
                )
            ),
        ),
        FakeResponse(500),
    )

    with pytest.raises(nextcloud.NextcloudError):
        await client_for(session).put_event("uid", ICS)


@pytest.mark.asyncio
async def test_requests_authenticate_with_the_app_password():
    session = FakeSession(FakeResponse(207, multistatus()))

    await client_for(session).resolve_calendar()

    expected = base64.b64encode(b"julia:app-password").decode("ascii")
    assert session.requests[0].kwargs["headers"]["Authorization"] == f"Basic {expected}"


@pytest.mark.asyncio
async def test_the_password_never_reaches_the_logs(caplog):
    session = FakeSession(
        FakeResponse(
            207,
            multistatus(
                (
                    "/remote.php/dav/calendars/julia/lembretes/",
                    "Lembretes",
                    CALENDAR_COLLECTION,
                )
            ),
        ),
        FakeResponse(500),
    )
    client = client_for(session)

    with caplog.at_level(logging.DEBUG, logger="juliabot.nextcloud"):
        await client.resolve_calendar()
        with pytest.raises(nextcloud.NextcloudError):
            await client.put_event("uid", ICS)

    assert "app-password" not in caplog.text


@pytest.mark.asyncio
async def test_put_event_does_nothing_when_the_calendar_is_unknown():
    session = FakeSession(FakeResponse(207, multistatus()))

    assert await client_for(session).put_event("uid", ICS) is False
    assert [request.method for request in session.requests] == ["PROPFIND"]
