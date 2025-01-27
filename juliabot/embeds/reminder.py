from typing import List

import pytz
from discord import Embed

from ..converters import DeltaToDate
from ..models import Reminder


async def reminder_embed(reminder: Reminder, bot) -> Embed:
    embed = Embed(
        title=":alarm_clock: Lembrete :alarm_clock:",
        color=bot.color,
    )

    date = reminder.get_date_str()
    embed.add_field(name="Data:", value=date, inline=False)

    channel = bot.get_channel(int(reminder.channel_id))
    channel = channel.name if channel else "Canal não encontrado!"
    embed.add_field(name="Canal:", value=channel, inline=False)

    created_at = reminder.get_created_str()
    embed.add_field(name="Criado em:", value=created_at, inline=False)

    if reminder.date_command is not None:
        embed.add_field(name="Comando:", value=reminder.date_command, inline=False)
        next_reminder = await DeltaToDate.convert(
            None, None, reminder.date_command, start=reminder.time_reminder
        )

        timezone = pytz.utc
        if reminder.server_id:
            server = reminder.get_server()
            timezone = server.get_timezone()

        next_reminder = next_reminder.astimezone(timezone)
        next_reminder = next_reminder.strftime("%d/%m/%Y %H:%M")
        next_reminder += f" [{timezone.zone}]"

        embed.add_field(
            name="Próximo lembrete (lembrete recorrente):",
            value=next_reminder,
            inline=False,
        )

    return embed
