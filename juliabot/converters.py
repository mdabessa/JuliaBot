from discord.ext import commands
import datetime

from .utils import search_anime


class Anime(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> dict | None:
        msg = await ctx.send(f"Procurando anime: `{argument}`...")

        dubbed = "dublado" in argument.lower()
        anime_name = argument.replace("dublado", "")

        search = await search_anime("anime", anime_name)

        if not search["data"]:
            return
        
        anime = search["data"][0]

        anime["dubbed"] = dubbed

        await msg.delete()

        return anime


class Character(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> dict | None:
        msg = await ctx.send(f"Procurando char: `{argument}`...")

        search = await search_anime("character", argument)
        char = search["results"][0]

        await msg.delete()

        return char


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
            raise Exception(
                f"Não é possivel converter {argument} em um objeto datetime.datetime"
            )

        return date


class DeltaToDate(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> datetime.datetime:
        leg = {
            "minute": ["m", "min", "minute", "minutes", "minuto", "minutos"],
            "hour": ["h", "hour", "hours", "hora", "horas", "hr", "hrs"],
            "day": ["d", "day", "days", "dia", "dias"],
            "week": ["w", "week", "weeks", "semana", "semanas"],
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
            elif word in leg["week"]:
                time += num * 604800
            elif word in leg["mounth"]:
                time += num * 2592000
            elif word in leg["year"]:
                time += num * 31536000
            else:
                raise Exception(f"Não é possivel converter {word} em tempo.")

        delta = datetime.timedelta(seconds=time)

        limit = 3153600000  # 100 years
        if (time <= 0) or (time > limit):
            raise Exception(
                f"Delta não pode ser menor que 0 ou maior que {limit} segundos"
            )

        return datetime.datetime.now() + delta
