from discord.ext import commands
import datetime
import re


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
    async def convert(
        self, ctx: commands.Context, argument: str, start: datetime = None
    ) -> datetime.datetime:
        start = start or datetime.datetime.now()
        regex = r"(\d+)([a-zA-Z]+)"

        steps = {
            "minute": ["m", "min", "minute", "milegnutes", "minuto", "minutos"],
            "hour": ["h", "hour", "hours", "hora", "horas", "hr", "hrs"],
            "day": ["d", "day", "days", "dia", "dias"],
            "week": ["w", "week", "weeks", "semana", "semanas"],
            "month": ["month", "months", "mes", "meses", "mês"],
            "year": ["y", "year", "years", "a", "ano", "anos"],
        }

        results = re.findall(regex, argument)

        time = 0
        for delta in results:
            if delta[0] == "" or delta[1] == "":
                continue

            num = int(delta[0])
            word = delta[1]

            if word in steps["minute"]:
                time += num * 60
            elif word in steps["hour"]:
                time += num * 3600
            elif word in steps["day"]:
                time += num * 86400
            elif word in steps["week"]:
                time += num * 604800
            elif word in steps["mounth"]:
                time += num * 2592000
            elif word in steps["year"]:
                time += num * 31536000
            else:
                raise Exception(f"Não é possivel converter {word} em tempo.")

        delta = datetime.timedelta(seconds=time)

        limit = 3153600000  # 100 years
        if (time <= 0) or (time > limit):
            raise Exception(
                f"Delta não pode ser menor que 0 ou maior que {limit} segundos"
            )

        return start + delta
