"""Behavior tests for the migrated reminder pagination session."""

from types import SimpleNamespace

import pytest
from discord import Embed

from juliabot.cogs import reminder as reminder_module
from juliabot.sessions import InteractionEvent, Registry, SessionManager, TriggerType


class FakeReminder:
    def __init__(self, user_id="7"):
        self.user_id = user_id
        self.deleted = False

    def delete(self):
        self.deleted = True

    def get_date_str(self):
        return "01/01/2027 12:00 [UTC]"


class FakeMessage:
    def __init__(self):
        self.channel = SimpleNamespace(sent=[])
        self.edits = []

        async def send(content):
            self.channel.sent.append(content)

        self.channel.send = send

    async def edit(self, **kwargs):
        self.edits.append(kwargs)


class FakeContext:
    def __init__(self, bot):
        self.bot = bot
        self.author = SimpleNamespace(id=7)
        self.guild = SimpleNamespace(id=10)
        self.channel = SimpleNamespace(id=20)
        self.message = SimpleNamespace(id=55)
        self.replies = []

    async def reply(self, **kwargs):
        message = FakeMessage()
        message.view = kwargs["view"]
        message.embed = kwargs["embed"]
        self.replies.append(message)
        return message


@pytest.mark.asyncio
async def test_reminder_pagination_deletes_only_for_owner(monkeypatch):
    reminders = [FakeReminder()]
    monkeypatch.setattr(
        reminder_module.Reminder,
        "get_all",
        lambda user_id: reminders,
    )

    async def fake_embed(reminder, bot):
        return Embed(title="Reminder")

    monkeypatch.setattr(reminder_module, "reminder_embed", fake_embed)
    bot = SimpleNamespace(sessions=SessionManager(Registry()), color=0xE6DC56)
    cog = reminder_module._ReminderCog(bot)
    context = FakeContext(bot)
    event = InteractionEvent(
        transport=TriggerType.COMPONENT,
        key="command-55",
        user_id=7,
        guild_id=10,
        channel_id=20,
        message_id=55,
        raw=context,
    )

    session = await bot.sessions.start(reminder_module.LIST_REMINDERS, event)

    assert session.to_payload() == {"index": 0}
    assert (
        await bot.sessions.dispatch(
            InteractionEvent(
                transport=TriggerType.COMPONENT,
                key=session.id,
                user_id=8,
                action="delete",
            )
        )
        is False
    )
    assert reminders[0].deleted is False

    assert (
        await bot.sessions.dispatch(
            InteractionEvent(
                transport=TriggerType.COMPONENT,
                key=session.id,
                user_id=7,
                action="delete",
            )
        )
        is True
    )
    assert reminders[0].deleted is True
    assert session.closed is True
    assert context.replies[0].edits[-2] == {
        "content": "Você não tem nenhum lembrete!",
        "embed": None,
    }
    assert context.replies[0].edits[-1] == {"view": None}
