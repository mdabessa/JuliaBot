"""Reminder and scheduling cog.

Provides commands to create, list, and manage reminders with recurrence
support using Discord reactions.
"""

from typing import Union

from discord.ext import commands, tasks

from ..client import Client
from ..converters import Date, DeltaToDate, NextDate
from ..embeds.reminder import reminder_embed
from ..models import Reminder
from ..sessions import (
    Action,
    InteractionEvent,
    Registration,
    Registry,
    Scope,
    SessionManager,
    TriggerType,
)
from ..sessions.patterns import PaginationSession

LIST_REMINDERS = "reminder.list"


class ReminderPagination(PaginationSession[Reminder]):
    """Paginate one user's reminders with owner-only deletion."""

    extra_actions = (
        Action(
            "delete",
            "delete_current",
            label="Excluir",
            emoji="❌",
            style="danger",
        ),
    )
    empty_message = "Você não tem nenhum lembrete!"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._bot = None

    async def start(self, event: InteractionEvent) -> None:
        """Capture the runtime bot reference before the first render."""
        self._bot = getattr(event.raw, "bot", None)
        await super().start(event)

    async def hydrate(self, event: InteractionEvent | None = None) -> None:
        """Recover the bot reference from the interaction before rendering."""
        if event is not None and self._bot is None:
            self._bot = getattr(event.raw, "client", None)
        await super().hydrate(event)

    async def load_items(self):
        """Load the owner's current reminders from the existing model API."""
        return Reminder.get_all(user_id=self.owner_id)

    async def render_item(self, item: Reminder, index: int, total: int):
        """Render one reminder with the current position in the list."""
        embed = await reminder_embed(item, self._bot)
        embed.set_footer(text=f"{index + 1}/{total} Lembrete(s)")
        return embed

    async def delete_item(self, item: Reminder, event: InteractionEvent) -> bool:
        """Delete the selected reminder and announce the deletion."""
        item.delete()
        if self._message is not None:
            await self._message.channel.send(
                f"Lembrete de `{item.get_date_str()}` deletado com sucesso!"
            )
        return True


class _ReminderCog(commands.Cog, name="reminder"):
    """Reminder management and scheduling.

    Provides commands to create recurring and one-time reminders, with
    background task handling for notifications.
    """

    embed_title = ":alarm_clock:Reminder."

    def __init__(self, bot: Client) -> None:
        self.bot = bot
        if not hasattr(bot, "sessions"):
            bot.sessions = SessionManager(Registry())
        if bot.sessions.registry.get(LIST_REMINDERS) is None:
            bot.sessions.registry.register(
                Registration(
                    name=LIST_REMINDERS,
                    session_class=ReminderPagination,
                    trigger=TriggerType.COMPONENT,
                    scope=Scope.USER,
                    timeout=180,
                    max_per_scope=1,
                    resumable=True,
                )
            )

    @commands.Cog.listener()
    async def on_ready(self):
        self.reminder.start()

    @commands.command(
        brief="Mostra todos os seus lembretes!",
        aliases=["rms", "lembretes", "reminders"],
    )
    async def list_reminders(self, ctx: commands.Context):
        reminders = Reminder.get_all(user_id=ctx.author.id)
        if not reminders:
            return await ctx.reply("Você não tem nenhum lembrete!")

        event = InteractionEvent(
            transport=TriggerType.COMPONENT,
            key=str(ctx.message.id),
            user_id=ctx.author.id,
            guild_id=getattr(ctx.guild, "id", None),
            channel_id=ctx.channel.id,
            message_id=ctx.message.id,
            raw=ctx,
        )
        await self.bot.sessions.start(LIST_REMINDERS, event)

    @commands.command(
        brief="Irei te notificar no dia desejado, relembrando sua mensagem!",
        aliases=["rm", "lembrete", "remind"],
    )
    async def remind_me(
        self, ctx: commands.Context, date: Union[Date, DeltaToDate, NextDate]
    ):
        reminder = Reminder(
            ctx.guild.id, ctx.channel.id, ctx.message.id, ctx.author.id, date
        )
        await ctx.reply(f"OK, Eu irei te notificar no dia `{reminder.get_date_str()}`!")

    @commands.command(
        brief="Irei te notificar todos os tempos do padrão, relembrando sua mensagem!",
        aliases=["rml", "lembretel", "remindloop"],
    )
    async def remind_me_loop(self, ctx: commands.Context, arg: str):
        converters = [DeltaToDate, NextDate]
        for converter in converters:
            try:
                date = await converter.convert(None, ctx, arg)
                break
            except Exception:
                if converter == converters[-1]:
                    return await ctx.reply("Por favor, use um formato de data válido!")

        reminder = Reminder(
            ctx.guild.id, ctx.channel.id, ctx.message.id, ctx.author.id, date, arg
        )
        await ctx.reply(f"OK, Eu irei te notificar dia `{reminder.get_date_str()}`")

    @tasks.loop(seconds=20, reconnect=True)
    async def reminder(self):
        converters = [DeltaToDate, NextDate]
        expired = Reminder.get_expired()

        for _reminder in expired:
            try:
                channel = self.bot.get_channel(int(_reminder.channel_id))
                message = await channel.fetch_message(int(_reminder.message_id))

                text = ""

                if _reminder.date_command:
                    for converter in converters:
                        try:
                            new_date = await converter.convert(
                                None, message, _reminder.date_command
                            )
                            break
                        except Exception:
                            if converter == converters[-1]:
                                _reminder.delete()
                                raise Exception("Date command cannot be converted!")

                    _reminder.time_reminder = new_date
                    _reminder.update()
                    text += f" (Irei te lembrar novamente dia `{_reminder.get_date_str()}`!)"
                else:
                    _reminder.delete()

                for user in message.mentions:
                    text += f" {user.mention}"

                m = await message.reply(
                    "Aqui esta a mensagem que você me pediu para te lembrar!" + text
                )

                await m.add_reaction("👍")

            except:
                user = await self.bot.fetch_user(int(_reminder.user_id))
                if user:
                    await user.send(
                        "Você criou um lembrete para hoje, mas não consegui recuperar a mensagem do lembrete para te marcar. :worried:"
                    )

                _reminder.delete()


async def setup(bot: Client):
    await bot.add_cog(_ReminderCog(bot))
