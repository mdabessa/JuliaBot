from typing import List
from discord import Embed
from datetime import timedelta

from ..models import Reminder
from ..converters import DeltaToDate


async def reminder_embed(reminder: Reminder, bot) -> Embed:
    embed = Embed(
        title=":alarm_clock: Lembrete :alarm_clock:",
        color=bot.color,
    )

    time_reminder = reminder.time_reminder
    time_created = reminder.time_created

    # apply GMT-3 timezone
    time_reminder = time_reminder - timedelta(hours=3)
    time_created = time_created - timedelta(hours=3)

    date = time_reminder.strftime("%d/%m/%Y %H:%M")
    embed.add_field(name="Data:", value=date, inline=False)

    channel = bot.get_channel(int(reminder.channel_id))
    channel = channel.name if channel else "Canal não encontrado!"
    embed.add_field(name="Canal:", value=channel, inline=False)

    created_at = time_created.strftime("%d/%m/%Y %H:%M")
    embed.add_field(name="Criado em:", value=created_at, inline=False)

    if reminder.date_command is not None:
        embed.add_field(name="Comando:", value=reminder.date_command, inline=False)
        next_reminder = await DeltaToDate.convert(
            None, None, reminder.date_command, start=time_reminder
        )
        next_reminder = next_reminder.strftime("%d/%m/%Y %H:%M")
        embed.add_field(
            name="Próximo lembrete (lembrete recorrente):",
            value=next_reminder,
            inline=False,
        )

    return embed
