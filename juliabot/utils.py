from discord.ext.commands import Bot
from discord import Message

from .models import Server


def get_prefix(bot: Bot, message: Message) -> str:
    if message.guild:
        server = Server.get_or_create(str(message.guild.id))
        return server.prefix
    else:
        return "j!"
