"""Utility functions for command prefix resolution.

This module provides helpers to fetch the appropriate command prefix
based on server configuration.
"""

from discord import Message
from discord.ext.commands import Bot

from .config import PREFIX
from .models import Server


def get_prefix(bot: Bot, message: Message) -> str:
    """Resolve the command prefix for a message.

    Args:
        bot (discord.ext.commands.Bot): The bot instance.
        message (discord.Message): The message being processed.

    Returns:
        str: Server-specific prefix if in a guild; default PREFIX otherwise.
    """
    if message.guild:
        server = Server.get_or_create(str(message.guild.id))
        server.update()

        return server.prefix
    else:
        return PREFIX
