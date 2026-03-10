"""Discord bot client with cog management and event handlers.

This module provides the main bot client class that inherits from discord.ext.commands.Bot
and adds custom initialization, cog loading, and event handling logic.
"""

import logging
from pathlib import Path

from discord import Game, Intents, Message
from discord.ext.commands import Bot

from .models import init_db

logger = logging.getLogger(__name__)


class Client(Bot):
    """Main bot client with Discord integration and dynamic cog loading.

    Extends discord.ext.commands.Bot with custom initialization of intents,
    embed color, and database setup, plus auto-loading of cogs from the cogs folder.
    """

    def __init__(self, test_mode: bool = False, **options) -> None:
        """Initialize the bot client with default intents and configuration.

        Args:
            test_mode (bool): Whether to run in test mode.
            **options: Additional keyword arguments passed to discord.ext.commands.Bot.
        """
        intents = Intents.default()
        intents.message_content = True
        super().__init__(intents=intents, **options)

        self.color = 0xE6DC56
        self.test_mode = test_mode

        init_db()

    async def setup_hook(self) -> None:
        """Load all cog extensions from the cogs directory.

        Called during bot initialization to dynamically discover and load
        all modules in juliabot/cogs/.
        """
        cogs = [file.stem for file in Path("juliabot", "cogs").glob("*.py")]
        for extension in cogs:
            await self.load_extension(f"juliabot.cogs.{extension}")

    async def on_ready(self):
        """Handle bot ready event.

        Updates the bot's presence with the guild count and logs the connection status.
        """
        await self.change_presence(activity=Game(f"{len(self.guilds)} Servidores!"))
        logger.info(f"{self.user} esta logado em {len(self.guilds)} grupos!")
        logger.info("Pronto!")

    async def on_message(self, message: Message):
        """Handle incoming messages and process commands.

        Args:
            message (discord.Message): The received message.
        """
        ctx = await self.get_context(message)
        if ctx.valid:
            logger.debug(f"Autor: {message.author} - Comando: {message.content}")

        if not message.author.bot:
            await self.process_commands(message)
            return

        if self.test_mode:
            ctx = await self.get_context(message)
            if ctx.valid:
                await self.invoke(ctx)
