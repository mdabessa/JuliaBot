from pathlib import Path

from discord import Game, Intents, Message
from discord.ext.commands import Bot

from .models import init_db


class Client(Bot):
    def __init__(self, **options) -> None:
        intents = Intents.default()
        intents.message_content = True
        super().__init__(intents=intents, **options)

        self.color = 0xE6DC56

        init_db()

    async def setup_hook(self) -> None:
        cogs = [file.stem for file in Path("juliabot", "cogs").glob("*.py")]
        for extension in cogs:
            await self.load_extension(f"juliabot.cogs.{extension}")

    async def on_ready(self):
        await self.change_presence(activity=Game(f"{len(self.guilds)} Servidores!"))
        print(f"{self.user} esta logado em {len(self.guilds)} grupos!")
        print("Pronto!")

    async def on_message(self, message: Message):
        ctx = await self.get_context(message)
        if ctx.valid:
            print(f"Autor: {message.author} - Comando: {message.content}")

        await self.process_commands(message)
