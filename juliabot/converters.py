from discord.ext import commands
import datetime
from dateutil.relativedelta import relativedelta
import re


def split_word(word, reverse=False):
    if reverse:
        regex = r'(\d+)([a-zA-Z]*)'
    else:
        regex = r'([a-zA-Z]+)(\d+)'
        
    matches = re.findall(regex, word)
    result = []
    for match in matches:
        if reverse:
            num, chars = match
        else:
            chars, num = match

        if num:
            num = int(num)
        else:
            num = 1

        result.append([num, chars])
    return result


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
        if not argument[0].isdigit():
            raise Exception(f"Não é possivel converter {argument} em DeltaToDate.")

        print(argument)
        start = start or datetime.datetime.now()
        steps = {
            "minute": ["min", "minute", "minutes", "minuto", "minutos"],
            "hour": ["h", "hour", "hours", "hora", "horas", "hr", "hrs"],
            "day": ["d", "day", "days", "dia", "dias"],
            "week": ["w", "week", "weeks", "semana", "semanas"],
            "month": ["month", "months", "mes", "meses", "mês"],
            "year": ["y", "year", "years", "a", "ano", "anos"],
        }

        time = 0
        results = split_word(argument, reverse=True)
        for res in results:
            num = res[0]
            step = None
            for key, value in steps.items():
                if res[1] in value:
                    step = key
                    break
            
            if not step:
                continue

            if step in steps["minute"]:
                time += num * 60
            elif step in steps["hour"]:
                time += num * 3600
            elif step in steps["day"]:
                time += num * 86400
            elif step in steps["week"]:
                time += num * 604800
            elif step in steps["month"]:
                time += num * 2592000
            elif step in steps["year"]:
                time += num * 31536000
            else:
                raise Exception(f"Não é possivel converter {step} em tempo.")

        delta = datetime.timedelta(seconds=time)

        limit = 3153600000  # 100 years
        if (time <= 0) or (time > limit):
            raise Exception(
                f"Delta não pode ser menor que 0 ou maior que {limit} segundos"
            )

        return start + delta


class NextDate(commands.Converter):
    async def convert(
        self, ctx: commands.Context, argument: str, start: datetime = None
    ) -> datetime.datetime:
        if argument[0].isdigit():
            raise Exception(f"Não é possivel converter {argument} em NextDate.")

        date = start or datetime.datetime.now()
        steps = {
            "minute": ["min", "minute", "minutes", "minuto", "minutos"],
            "hour": ["h", "hour", "hours", "hora", "horas", "hr", "hrs"],
            "day": ["d", "day", "days", "dia", "dias"],
            "month": ["month", "months", "mes", "meses", "mês"],
            "year": ["y", "year", "years", "a", "ano", "anos"],
        }
    
        results = split_word(argument)
        hour_append = False
        for res in results:
            step = None
            for key, value in steps.items():
                if res[1] in value:
                    step = key
                    break
            
            if not step:
                continue
            
            if step == 'hour': 
                hour_append = True

            num = res[0]
            date += relativedelta(**{step:num})

            if date < (datetime.datetime.now()  + datetime.timedelta(hours=3)): # FIXME: UTC+3 Hardcoded
                index = list(steps.keys()).index(step)
                if index + 1 == len(steps):
                    raise Exception("O ano não pode ser menor que o ano atual.")

                next_step = list(steps.keys())[index + 1]
                date += relativedelta(**{next_step+'s':1})

        if hour_append:
            date = date + datetime.timedelta(hours=3) # FIXME: UTC+3 Hardcoded

        return date
