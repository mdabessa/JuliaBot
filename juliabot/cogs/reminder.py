from typing import Union

from discord import Embed
from discord.ext import commands, tasks

from ..converters import Date, DeltaToDate, NextDate
from ..embeds.reminder import reminder_embed
from ..models import Reminder
from ..scripts import Script


class _Reminder(commands.Cog, name="reminder"):
    """Categoria relacionada a comandos de lembrete."""

    embed_title = ":alarm_clock:Reminder."

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        self.reminder.start()

    @staticmethod
    @Script.function(name="list_reminders", events=["on_reaction_add"])
    async def _list_reminders(cache: dict, **kwargs):
        if cache["status"] == "created":
            cache["status"] = "started"
            cache["bot"] = kwargs["bot"]
            cache["reminders"] = kwargs["reminders"]
            cache["index"] = 0

            reminder = cache["reminders"][cache["index"]]
            embed = await reminder_embed(reminder, cache["bot"])
            embed.set_footer(text=f"1/{len(cache['reminders'])} Lembrete(s)")

            cache["message"] = await kwargs["ctx"].reply(embed=embed)

            await cache["message"].add_reaction("⬅️")
            await cache["message"].add_reaction("➡️")
            await cache["message"].add_reaction("❌")

        elif cache["status"] == "started":
            index = cache["index"]
            reminder = cache["reminders"][cache["index"]]
            if kwargs["emoji"] == "⬅️":
                index -= 1
            elif kwargs["emoji"] == "➡️":
                index += 1
            elif kwargs["emoji"] == "❌" and kwargs["user"].id == int(reminder.user_id):
                cache["reminders"].remove(reminder)
                reminder.delete()
                await cache["message"].channel.send(
                    f'Lembrete de `{reminder.time_reminder.strftime("%d/%m/%Y %H:%M")}` deletado com sucesso!'
                )

            if index < 0:
                index = len(cache["reminders"]) - 1
            elif index >= len(cache["reminders"]):
                index = 0

            if cache["reminders"]:
                cache["index"] = index
                reminder = cache["reminders"][cache["index"]]
                embed = await reminder_embed(reminder, cache["bot"])
                embed.set_footer(
                    text=f"{index + 1}/{len(cache['reminders'])} Lembrete(s)"
                )
                await cache["message"].edit(embed=embed)
            else:
                await cache["message"].edit(
                    content="Você não tem nenhum lembrete!", embed=None
                )
                cache["status"] = 0

    @commands.command(
        brief="Mostra todos os seus lembretes!",
        aliases=["rms", "lembretes", "reminders"],
    )
    async def list_reminders(self, ctx: commands.Context):
        reminders = Reminder.get_all(user_id=ctx.author.id)
        if not reminders:
            return await ctx.reply("Você não tem nenhum lembrete!")

        scr = Script(
            name=f"{ctx.author.id}_list_reminders",
            function_name="list_reminders",
            time_out=180,
        )

        await scr.execute(bot=self.bot, ctx=ctx, reminders=reminders)

    @commands.command(
        brief="Irei te notificar no dia desejado, relembrando sua mensagem!",
        aliases=["rm", "lembrete", "remind"],
    )
    async def remind_me(
        self, ctx: commands.Context, date: Union[Date, DeltaToDate, NextDate]
    ):
        Reminder(ctx.channel.id, ctx.message.id, ctx.author.id, date)
        await ctx.reply(
            f'OK, Eu irei te notificar no dia `{date.strftime("%d/%m/%Y %H:%M")}`!'
        )

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

        Reminder(ctx.channel.id, ctx.message.id, ctx.author.id, date, arg)
        await ctx.reply(
            f'OK, Eu irei te notificar dia `{date.strftime("%d/%m/%Y %H:%M")}`'
        )

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
                    text += f" (Irei te lembrar novamente dia `{new_date.strftime('%d/%m/%Y %H:%M')}`)"
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


def setup(bot: commands.Bot):
    bot.add_cog(_Reminder(bot))
