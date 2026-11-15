"""Tests for the one-shot reminder → Nextcloud calendar mirror.

The publisher is faked at the cog boundary, so no test opens a socket; the
``publish_reminder`` cases assert against the payload a fake client receives.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from types import SimpleNamespace

import pytest
import pytz

import juliabot.models as models
from juliabot import nextcloud
from juliabot.cogs import reminder as reminder_module

GUILD_ID = 10
CHANNEL_ID = 20
MESSAGE_ID = 1000
OWNER_ID = 30

TARGET = datetime.datetime(2026, 3, 14, 12, 0, tzinfo=pytz.utc)

CONFIG = nextcloud.NextcloudConfig(
    url="https://cloud.example.com",
    user="julia",
    app_password="app-password",
    calendar="Lembretes",
    reminder_user_id=str(OWNER_ID),
)


@pytest.fixture(autouse=True)
def clean_database():
    models.init_db()
    models.Reminder.delete_all()
    yield
    models.rollback()
    models.Reminder.delete_all()
    models.rollback()


class FakeChannel:
    def __init__(self, channel_id=CHANNEL_ID, name="geral") -> None:
        self.id = channel_id
        self.name = name
        self.sent: list[str] = []

    async def send(self, content=None, **_kwargs):
        self.sent.append(content)
        return SimpleNamespace(content=content)

    def __str__(self) -> str:
        return self.name


class FakeContext:
    """The subset of ``commands.Context`` that ``remind_me`` touches."""

    def __init__(self, author_id: int = OWNER_ID, content: str = "!rm 1d") -> None:
        self.author = SimpleNamespace(id=author_id)
        self.guild = SimpleNamespace(id=GUILD_ID)
        self.channel = FakeChannel()
        self.replies: list[str] = []
        self.message = SimpleNamespace(
            id=MESSAGE_ID,
            content=content,
            channel=self.channel,
            guild=self.guild,
        )

    async def reply(self, content=None, **_kwargs):
        self.replies.append(content)
        return SimpleNamespace(content=content)


class FakeBot:
    def __init__(self) -> None:
        self.color = 0xE6DC56


class FakeCalendarClient:
    """Records the events it is asked to store."""

    def __init__(self, result: bool = True) -> None:
        self.result = result
        self.events: list[tuple[str, str]] = []

    async def put_event(self, uid: str, ics: str) -> bool:
        self.events.append((uid, ics))
        return self.result


def content_line(ics: str, name: str) -> str:
    """Return the unfolded value of the named property."""
    lines = ics.split("\r\n")

    for index, line in enumerate(lines):
        if not line.startswith(name):
            continue

        parts = [line[len(name) :]]
        for continuation in lines[index + 1 :]:
            if not continuation.startswith(" "):
                break
            parts.append(continuation[1:])

        return "".join(parts)

    raise AssertionError(f"{name} is missing from {ics!r}")


def make_cog(monkeypatch, *, author_id: int = OWNER_ID, config=CONFIG):
    cog = reminder_module._ReminderCog(FakeBot())
    cog.calendar_config = config
    published: list[tuple[int, object]] = []

    async def fake_publish(reminder, message):
        published.append((reminder.id, message))

    monkeypatch.setattr(cog, "_publish_reminder", fake_publish)
    return cog, FakeContext(author_id=author_id), published


async def drain(cog) -> None:
    """Wait for every scheduled mirror task, then let callbacks run."""
    await asyncio.gather(*cog._mirror_tasks)
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_owner_reminder_is_mirrored(monkeypatch):
    cog, ctx, published = make_cog(monkeypatch)

    await reminder_module._ReminderCog.remind_me.callback(cog, ctx, date=TARGET)
    await drain(cog)

    stored = models.Reminder.get_all(OWNER_ID)
    assert len(published) == 1, "the owner's one-shot reminder must be mirrored"
    assert published[0][0] == stored[0].id, "the event must key off the row id"
    assert published[0][1] is ctx.message


@pytest.mark.asyncio
async def test_non_owner_reminder_is_not_mirrored(monkeypatch):
    cog, ctx, published = make_cog(monkeypatch, author_id=OWNER_ID + 1)

    await reminder_module._ReminderCog.remind_me.callback(cog, ctx, date=TARGET)
    await drain(cog)

    assert published == []
    assert (
        len(models.Reminder.get_all(OWNER_ID + 1)) == 1
    ), "the reminder is still stored"


@pytest.mark.asyncio
async def test_mirror_is_off_without_configuration(monkeypatch):
    cog, ctx, published = make_cog(monkeypatch, config=None)

    await reminder_module._ReminderCog.remind_me.callback(cog, ctx, date=TARGET)
    await drain(cog)

    assert published == []


@pytest.mark.asyncio
async def test_remind_me_still_replies_when_the_publisher_raises(monkeypatch, caplog):
    cog, ctx, _published = make_cog(monkeypatch)

    async def boom(_reminder, _message):
        raise nextcloud.NextcloudError("HTTP 500")

    monkeypatch.setattr(cog, "_publish_reminder", boom)

    with caplog.at_level(logging.WARNING, logger="juliabot.cogs.reminder"):
        await reminder_module._ReminderCog.remind_me.callback(cog, ctx, date=TARGET)
        await drain(cog)

    assert "OK, Eu irei te notificar" in ctx.replies[-1]
    assert len(models.Reminder.get_all(OWNER_ID)) == 1
    assert "Could not mirror reminder" in caplog.text


@pytest.mark.asyncio
async def test_a_slow_publisher_is_abandoned(monkeypatch, caplog):
    cog, ctx, _published = make_cog(monkeypatch)
    cog.mirror_timeout = 0.01

    async def slow(_reminder, _message):
        await asyncio.sleep(5)

    monkeypatch.setattr(cog, "_publish_reminder", slow)

    with caplog.at_level(logging.WARNING, logger="juliabot.cogs.reminder"):
        await reminder_module._ReminderCog.remind_me.callback(cog, ctx, date=TARGET)
        await drain(cog)

    assert "OK, Eu irei te notificar" in ctx.replies[-1]
    assert "Could not mirror reminder" in caplog.text


@pytest.mark.asyncio
async def test_recurring_reminders_are_not_mirrored(monkeypatch):
    cog, ctx, published = make_cog(monkeypatch)

    async def fake_convert(_self, _ctx, _argument):
        return TARGET

    monkeypatch.setattr(reminder_module.DeltaToDate, "convert", fake_convert)

    await reminder_module._ReminderCog.remind_me_loop.callback(cog, ctx, arg="2h")
    await drain(cog)

    assert published == [], "rml is out of scope for the mirror"


@pytest.mark.asyncio
async def test_completed_mirror_tasks_are_released(monkeypatch):
    cog, ctx, _published = make_cog(monkeypatch)

    await reminder_module._ReminderCog.remind_me.callback(cog, ctx, date=TARGET)
    await drain(cog)

    assert cog._mirror_tasks == set(), "finished tasks must not be retained"


@pytest.mark.asyncio
async def test_publish_reminder_builds_the_documented_event():
    reminder = models.Reminder(
        str(GUILD_ID), str(CHANNEL_ID), str(MESSAGE_ID), str(OWNER_ID), TARGET
    )
    message = FakeContext().message
    client = FakeCalendarClient()

    stored = await nextcloud.publish_reminder(
        client,
        reminder,
        message,
        stamp=datetime.datetime(2026, 3, 1, 9, 0, tzinfo=pytz.utc),
    )

    assert stored is True
    uid, ics = client.events[0]
    assert uid == f"juliabot-reminder-{reminder.id}@juliabot"
    assert content_line(ics, "UID:") == f"juliabot-reminder-{reminder.id}@juliabot"
    assert content_line(ics, "DTSTART:") == "20260314T120000Z"
    assert content_line(ics, "DTSTAMP:") == "20260301T090000Z"
    assert content_line(ics, "SUMMARY:") == "Lembrete: !rm 1d"
    assert content_line(ics, "DESCRIPTION:") == (
        f"Criado por !rm em #geral\\nhttps://discord.com/channels/{GUILD_ID}/{CHANNEL_ID}/{MESSAGE_ID}"
    )


@pytest.mark.asyncio
async def test_publish_reminder_uses_the_stored_instant_in_utc():
    reminder = models.Reminder(
        str(GUILD_ID), str(CHANNEL_ID), str(MESSAGE_ID), str(OWNER_ID), TARGET
    )
    # Postgres returns aware values, SQLite naive ones; both mean this instant.
    reminder.time_reminder = datetime.datetime(2026, 3, 14, 12, 0)
    client = FakeCalendarClient()

    await nextcloud.publish_reminder(client, reminder, FakeContext().message)

    _uid, ics = client.events[0]
    assert content_line(ics, "DTSTART:") == "20260314T120000Z"


@pytest.mark.asyncio
async def test_publish_reminder_reports_an_unresolved_calendar():
    reminder = models.Reminder(
        str(GUILD_ID), str(CHANNEL_ID), str(MESSAGE_ID), str(OWNER_ID), TARGET
    )

    stored = await nextcloud.publish_reminder(
        FakeCalendarClient(result=False), reminder, FakeContext().message
    )

    assert stored is False


def test_reminder_summary_keeps_only_the_first_line():
    message = SimpleNamespace(content="!rm 1d\nlinha extra")

    assert nextcloud.reminder_summary(message) == "Lembrete: !rm 1d"


def test_reminder_description_omits_the_link_without_ids():
    message = SimpleNamespace(content="!rm 1d", channel=SimpleNamespace(name=None))

    assert nextcloud.reminder_description(message) == "Criado por !rm em #desconhecido"
