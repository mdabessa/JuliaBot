from typing import Union
from discord.ext import commands, tasks


from ..models import Reminder
from ..converters import Date, DeltaToDate


class _Reminder(commands.Cog, name="Reminder"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        self.reminder.start()

    @commands.command(
        brief="Irei te notificar no dia desejado, relembrando sua mensagem!",
        aliases=["rm", "lembrete", "remind"],
    )
    async def remember_me(self, ctx: commands.Context, date: Union[Date, DeltaToDate]):
        Reminder(ctx.channel.id, ctx.message.id, ctx.author.id, date)
        await ctx.reply(
            f'OK, Eu irei te notificar no dia `{date.strftime("%d/%m/%Y %H:%M")}`!'
        )

    @tasks.loop(seconds=60)
    async def reminder(self):
        expired = Reminder.get_expired()

        for _reminder in expired:
            try:
                channel = self.bot.get_channel(int(_reminder.channel_id))
                message = await channel.fetch_message(
                    int(_reminder.message_id)
                )  # Raise if not found

                text = ""
                for user in message.mentions:
                    text += f" {user.mention}"

                await message.reply(
                    "Aqui esta a mensagem que você me pediu para te lembrar!" + text
                )
                _reminder.delete()

            except:
                user = await self.bot.get_user(int(_reminder.user_id))
                if user:
                    user.send(
                        "Você criou um lembrete para hoje, mas não consegui recuperar a mensagem do lembrete para te marcar. :worried:"
                    )

                _reminder.delete()


def setup(bot: commands.Bot):
    bot.add_cog(_Reminder(bot))
