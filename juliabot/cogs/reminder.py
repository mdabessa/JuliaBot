from typing import Union
from discord.ext import commands, tasks
import datetime


from ..models import Reminder


class Date(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> datetime.datetime:
        formats = [
            "%d/%m/%Y-%H:%M",
            "%H:%M-%d/%m/%Y",
            "%d/%m/%Y",
        ]

        date = None
        for f in formats:
            try:
                date = datetime.datetime.strptime(argument, f)
                break
            except:
                continue
        
        if date is None:
            raise Exception(f'Não é possivel converter {argument} em um objeto datetime.datetime')

        return date


class DeltaToDate(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> datetime.datetime:
        leg = {
            "minute": ["m", "min", "minute", "minutes", "minuto", "minutos"],
            "hour": ["h", "hour", "hours", "hora", "horas", "hr", "hrs"],
            "day": ["d", "day", "days", "dia", "dias"],
            "mounth": ["mounth", "mounths", "mes", "meses", "mês"],
            "year": ["y", "year", "years", "a", "ano", "anos"],
        }

        deltas = []
        l = 0
        num = ""
        word = ""
        for i in argument:
            try:
                _num = str(int(i))
                if l == 1:
                    deltas.append([num, word])
                    l = 0
                    num = _num
                    word = ""
                else:
                    num += _num

            except:
                l = 1
                word += i

        deltas.append([num, word])
        
        time = 0
        for delta in deltas:
            if delta[0] == "" or delta[1] == "":
                continue

            num = int(delta[0])
            word = delta[1]

            if word in leg["minute"]:
                time += num * 60
            elif word in leg["hour"]:
                time += num * 3600
            elif word in leg["day"]:
                time += num * 86400
            elif word in leg["mounth"]:
                time += num * 2592000
            elif word in leg["year"]:
                time += num * 31536000
            else:
                return None

        delta = datetime.timedelta(seconds=time)

        limit = 3153600000  # 100 years
        if (time <= 0) or (time > limit):
            raise Exception(f'Delta não pode ser menor que 0 ou maior que {limit} segundos')

        return  datetime.datetime.now() + delta
    
  

class _Reminder(commands.Cog, name='Reminder'):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
    

    @commands.Cog.listener()
    async def on_ready(self):
        self.reminder.start()


    @commands.command(
        brief = 'Irei te notificar no dia desejado, relembrando sua mensagem!',
        aliases=['rm', 'lembrete', 'remind']
    )
    async def remember_me(self, ctx: commands.Context, date: Union[Date, DeltaToDate]):
        Reminder(ctx.channel.id, ctx.message.id, ctx.author.id, date)
        await ctx.reply(f'OK, Eu irei te notificar no dia `{date.strftime("%d/%m/%Y %H:%M")}`!')


    @tasks.loop(seconds=60)
    async def reminder(self):
        expired = Reminder.get_expired()
        
        for _reminder in expired:
            try:
                channel = self.bot.get_channel(int(_reminder.channel_id))
                message = await channel.fetch_message(int(_reminder.message_id)) # Raise if not found

                text = ''
                for user in message.mentions:
                    text += f" {user.mention}"

                await message.reply('Aqui esta a mensagem que você me pediu para te lembrar!' + text)
                _reminder.delete()
            
            except:
                user = await self.bot.get_user(int(_reminder.user_id))
                if user:
                    user.send("Você criou um lembrete para hoje, mas não consegui recuperar a mensagem do lembrete para te marcar. :worried:")

                _reminder.delete()


def setup(bot: commands.Bot):
    bot.add_cog(_Reminder(bot))

