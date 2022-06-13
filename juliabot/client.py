from pathlib import Path

from discord.ext.commands import Bot
from discord import Game, Message
from .models import init_db


class Client(Bot):
    def __init__(self,**options) -> None:
        super().__init__(**options)

        self.color = 0xE6DC56

        init_db()

        cogs = [file.stem for file in Path('juliabot', 'cogs').glob('*.py')]
        for extension in cogs:
            self.load_extension(f'juliabot.cogs.{extension}')


    async def on_ready(self):
        await self.change_presence(
            activity=Game(f"{len(self.guilds)} Servidores!")
        )
        print(f"{self.user} esta logado em {len(self.guilds)} grupos!")
        print("Pronto!")


    async def on_message(self, message: Message):
        print(f"{message.guild} #{message.channel} //{message.author} : {message.content}")
        await self.process_commands(message)



