"""Discord command argument converters for date and time parsing.

Provides converter classes for parsing various date/time formats used by
reminder and scheduling commands.
"""

import datetime
import logging
import re

import pytz
from dateutil.relativedelta import relativedelta
from discord.ext import commands

from .models import Server

logger = logging.getLogger(__name__)

STEPS = {
    "minute": ["m", "min", "minute", "minutes", "minuto", "minutos"],
    "hour": ["h", "hour", "hours", "hora", "horas", "hr", "hrs"],
    "day": ["d", "day", "days", "dia", "dias"],
    "week": ["w", "week", "weeks", "semana", "semanas"],
    "month": ["month", "months", "mes", "meses", "mês"],
    "year": ["y", "year", "years", "a", "ano", "anos"],
}


def split_word(word, reverse=False):
    """Parse a word into numeric + string pairs using regex.

    Args:
        word (str): Word to parse.
        reverse (bool, optional): If True, matches digits before letters;
            otherwise matches letters before digits. Defaults to False.

    Returns:
        list: List of [number, string] pairs extracted from the word.
    """
    if reverse:
        regex = r"(\d+)([a-zA-Z]*)"
    else:
        regex = r"([a-zA-Z]+)(\d+)"

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
    """Convert date strings in various formats to aware datetime objects.

    Supported formats: DD/MM/YYYY-HH:MM, HH:MM-DD/MM/YYYY, DD/MM/YYYY.
    Respects server timezone when available; otherwise uses UTC.
    """

    async def convert(self, ctx: commands.Context, argument: str) -> datetime.datetime:
        """Convert a date string to a timezone-aware datetime in UTC.

        Args:
            ctx (commands.Context): Command context for guild/server timezone lookup.
            argument (str): Date string in a supported format.

        Returns:
            datetime.datetime: Parsed and timezone-converted datetime in UTC.

        Raises:
            Exception: If the argument cannot be parsed in any supported format.
        """
        formats = [
            "%d/%m/%Y-%H:%M",
            "%H:%M-%d/%m/%Y",
            "%d/%m/%Y",
        ]

        timezone = pytz.utc
        if ctx:
            if ctx.guild:
                server = Server.get(ctx.guild.id)
                timezone = server.get_timezone()

        date = None
        for f in formats:
            try:
                date = datetime.datetime.strptime(argument, f)
                date = timezone.localize(date)
                break
            except:
                continue

        if date is None:
            raise Exception(
                f"Não é possivel converter {argument} em um objeto datetime.datetime"
            )

        date = date.astimezone(pytz.utc)

        now = datetime.datetime.now().astimezone(pytz.utc)
        now = now.strftime("%d/%m/%Y-%H:%M")
        date_ = date.strftime("%d/%m/%Y-%H:%M")
        logger.debug(f"{now} | Date[{argument}] -> {date_}")

        return date


class DeltaToDate(commands.Converter):
    """Convert relative time offsets (e.g., '1d2h30m') to absolute dates.

    Interprets input as a duration relative to a start time (default: now)
    and returns the resulting absolute datetime.
    """

    async def convert(
        self, ctx: commands.Context, argument: str, start: datetime = None
    ) -> datetime.datetime:
        """Convert a relative time offset to an absolute datetime.

        Args:
            ctx (commands.Context): Command context for timezone lookup.
            argument (str): Relative time string (e.g., '1d', '2h30m').
            start (datetime, optional): Reference time to add the offset to.
                Defaults to current UTC time.

        Returns:
            datetime.datetime: Absolute datetime in UTC after adding the offset.

        Raises:
            Exception: If the argument does not start with a digit or contains
            invalid time units.
        """
        if not argument[0].isdigit():
            raise Exception(f"Não é possivel converter {argument} em DeltaToDate.")

        start = start or datetime.datetime.now()
        start = start.astimezone(pytz.utc)

        date = start

        times = {
            "year": False,
            "month": False,
            "week": False,
            "day": False,
            "hour": False,
            "minute": False,
        }

        results = split_word(argument, reverse=True)
        for res in results:
            num = res[0]
            step = None
            for key, value in STEPS.items():
                if res[1] in value:
                    step = key
                    break

            if not step:
                raise Exception(f"Não é possivel converter {res[1]} em tempo.")

            if step not in times:
                raise Exception(f"O tempo {step} não pode ser calculado.")

            times[step] = True
            date += relativedelta(**{step + "s": num})

        now = start.strftime("%d/%m/%Y-%H:%M")
        date_ = date.strftime("%d/%m/%Y-%H:%M")
        logger.debug(f"{now} | DeltaToDate[{argument}] -> {date_}")

        return date


class NextDate(commands.Converter):
    """Convert natural time expressions (e.g., 'monday 14:30') to next occurrence.

    Parses time components without leading digits and schedules for the next
    upcoming occurrence of the specified time.
    """

    async def convert(
        self, ctx: commands.Context, argument: str, start: datetime = None
    ) -> datetime.datetime:
        """Parse a natural time expression and return the next occurrence.

        Args:
            ctx (commands.Context): Command context for timezone lookup.
            argument (str): Time string without leading digits (e.g., 'monday 14:30').
            start (datetime, optional): Start time for offset calculation.
                Defaults to current datetime in the server timezone.

        Returns:
            datetime.datetime: Next absolute datetime matching the expression, in UTC.

        Raises:
            Exception: If the argument starts with a digit or contains invalid
            time units, or if no valid future date can be computed.
        """
        if argument[0].isdigit():
            raise Exception(f"Não é possivel converter {argument} em NextDate.")

        start = start or datetime.datetime.now()

        timezone = pytz.utc
        if ctx:
            if ctx.guild:
                server = Server.get(ctx.guild.id)
                timezone = server.get_timezone()

        start = start.astimezone(timezone)
        date = start

        times = {
            "year": (start.year, True),
            "month": (start.month, True),
            "day": (start.day, True),
            "hour": (start.hour, True),
            "minute": (start.minute, True),
        }

        results = split_word(argument)

        STEPS_ = STEPS.copy()
        del STEPS_["week"]

        for res in results:
            step = None
            for key, value in STEPS_.items():
                if res[1] in value:
                    step = key
                    break

            if not step:
                raise Exception(f"Não é possivel converter {res[1]} em tempo.")

            if step not in times:
                raise Exception(f"O tempo {step} não pode ser calculado.")

            times[step] = (res[0], False)

        for step, (num, _) in times.items():
            date += relativedelta(**{step: num})

            if (date < start) or ((date == start) and (step == "minute")):
                index = list(STEPS_.keys()).index(step)

                while True:
                    index += 1

                    if index == len(STEPS_):
                        raise Exception("Data não pode ser menor que a data atual")

                    if not times[list(STEPS_.keys())[index]][1]:  # if fixed go to next
                        continue

                    next_step = list(STEPS_.keys())[index]
                    date += relativedelta(**{next_step + "s": 1})
                    break

        date = date.astimezone(pytz.utc)

        now = start.strftime("%d/%m/%Y-%H:%M")
        date_ = date.strftime("%d/%m/%Y-%H:%M")
        logger.debug(f"{now} | NextDate[{argument}] -> {date_}")
        return date
