"""Regression tests for the recurring-reminder reschedule loop.

Covers the reported `rml dia8` defect: once a monthly reminder fired, the
background loop rescheduled it one HOUR later on the SAME day instead of the
8th of the next month, so the reminder re-fired every hour forever.
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest
import pytz

from juliabot import converters as converters_module
from juliabot import models
from juliabot.cogs import reminder as reminder_module

GUILD_ID = 10
CHANNEL_ID = 20
MESSAGE_ID = 1000
USER_ID = 30

SAO_PAULO = pytz.timezone("America/Sao_Paulo")

# Frozen instant used as the converter's implicit "now":
# 2025-03-08 12:00 UTC == 2025-03-08 09:00 in America/Sao_Paulo (UTC-3).
# That is the 8th, i.e. exactly the day `dia8` recurs on.
FROZEN_NOW = datetime.datetime(2025, 3, 8, 12, 0, tzinfo=pytz.utc)
# Naive UTC, because `Reminder.time_reminder` is a timezone-naive column.
FROZEN_NOW_NAIVE = datetime.datetime(2025, 3, 8, 12, 0)
EXPECTED_NEXT = datetime.datetime(2025, 4, 8, 12, 0)


class _FrozenDatetime(datetime.datetime):
    """A datetime whose `now()` is pinned so the tests are deterministic."""

    @classmethod
    def now(cls, tz=None):
        return FROZEN_NOW


@pytest.fixture(autouse=True)
def _clean_database():
    models.init_db()
    for table in (models.Reminder, models.Server):
        table.delete_all()
    yield
    models.rollback()
    for table in (models.Reminder, models.Server):
        table.delete_all()
    models.rollback()


@pytest.fixture
def frozen_now(monkeypatch):
    """Pin the clock the converters read for their implicit start value."""
    monkeypatch.setattr(
        converters_module, "datetime", SimpleNamespace(datetime=_FrozenDatetime)
    )
    return FROZEN_NOW


class FakeUser:
    def __init__(self, user_id, bot=False):
        self.id = user_id
        self.bot = bot
        self.mention = f"<@{user_id}>"


class FakeGuild:
    def __init__(self, guild_id):
        self.id = guild_id


class FakeReply:
    def __init__(self, content):
        self.content = content
        self.reactions = []

    async def add_reaction(self, emoji):
        self.reactions.append(emoji)


class FakeReminderMessage:
    """The message a reminder was created from; the loop replies to it."""

    def __init__(self, message_id, channel, guild, mentions=None):
        self.id = message_id
        self.channel = channel
        self.guild = guild
        self.mentions = mentions or []
        self.replies = []

    async def reply(self, content=None, **_kwargs):
        reply = FakeReply(content)
        self.replies.append(reply)
        return reply


class FakeChannel:
    def __init__(self, channel_id, guild):
        self.id = channel_id
        self.guild = guild
        self.messages = {}

    def add_message(self, message):
        self.messages[message.id] = message

    async def fetch_message(self, message_id):
        return self.messages[message_id]


class FakeBot:
    """Deliberately has no `fetch_user`, so the loop's error path cannot be
    mistaken for a successful reschedule."""

    def __init__(self):
        self.channels = {}

    def get_channel(self, channel_id):
        return self.channels.get(channel_id)


def _build_world():
    """Wire up a guild/channel/message that an expired reminder points at."""
    bot = FakeBot()
    guild = FakeGuild(GUILD_ID)
    channel = FakeChannel(CHANNEL_ID, guild)
    message = FakeReminderMessage(MESSAGE_ID, channel, guild)
    channel.add_message(message)
    bot.channels[CHANNEL_ID] = channel
    return bot, message


def _stored_utc(value):
    """Normalise a stored reminder time.

    `Reminder.time_reminder` is a timezone-naive DateTime column, so a value
    read back from the database has to be interpreted as UTC.
    """
    if value.tzinfo is None:
        return value
    return value.astimezone(pytz.utc).replace(tzinfo=None)


def _make_reminder(date_command):
    return models.Reminder(
        str(GUILD_ID),
        str(CHANNEL_ID),
        str(MESSAGE_ID),
        str(USER_ID),
        FROZEN_NOW,
        date_command,
    )


def _expire_only(monkeypatch, reminder):
    monkeypatch.setattr(
        models.Reminder, "get_expired", classmethod(lambda cls: [reminder])
    )


@pytest.mark.asyncio
async def test_monthly_reminder_reschedules_to_the_next_month(
    monkeypatch, frozen_now
):
    """`rml dia8` firing on the 8th must return on the 8th of the next month.

    Regression: it used to be rescheduled one hour later on the SAME 8th, so
    every subsequent loop iteration produced another notification.
    """
    server = models.Server.get_or_create(str(GUILD_ID))
    server.set_timezone(SAO_PAULO)

    reminder = _make_reminder("dia8")
    bot, message = _build_world()
    _expire_only(monkeypatch, reminder)

    cog = reminder_module._ReminderCog(bot)
    await cog.reminder()

    assert (
        models.Reminder.get_all(str(USER_ID)) != []
    ), "the loop took its error path instead of rescheduling the reminder"
    assert _stored_utc(reminder.time_reminder) == EXPECTED_NEXT, (
        "a monthly reminder that fired on its own day must be rescheduled to "
        "the same day of the NEXT month, not to a later hour of the same day"
    )
    assert (
        "Irei te lembrar novamente" in message.replies[0].content
    ), "the reminder should announce the next occurrence"


@pytest.mark.asyncio
async def test_monthly_reminder_does_not_drift_one_hour(monkeypatch, frozen_now):
    """The rescheduled reminder must jump a month, not one hour."""
    server = models.Server.get_or_create(str(GUILD_ID))
    server.set_timezone(SAO_PAULO)

    reminder = _make_reminder("dia8")
    bot, _message = _build_world()
    _expire_only(monkeypatch, reminder)

    cog = reminder_module._ReminderCog(bot)
    await cog.reminder()

    rescheduled = _stored_utc(reminder.time_reminder)

    assert rescheduled > FROZEN_NOW_NAIVE, "the reminder must move forward"
    assert rescheduled != (
        FROZEN_NOW_NAIVE + datetime.timedelta(hours=1)
    ), "the reminder must not drift one hour on the same day"
    assert rescheduled.day == 8, "the reminder must stay on the 8th"
    assert (
        rescheduled.year,
        rescheduled.month,
    ) == (2025, 4), "the reminder must move to the next month"


@pytest.mark.asyncio
async def test_one_shot_reminder_is_deleted_instead_of_rescheduled(
    monkeypatch, frozen_now
):
    """A reminder without a recurrence command is consumed by the loop."""
    reminder = _make_reminder(None)
    bot, _message = _build_world()
    _expire_only(monkeypatch, reminder)

    cog = reminder_module._ReminderCog(bot)
    await cog.reminder()

    assert (
        models.Reminder.get_all(str(USER_ID)) == []
    ), "a one-shot reminder should be deleted once it fires"
