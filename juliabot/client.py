from pathlib import Path

from discord.ext.commands import Bot
from discord import Game, Message
from .models import init_db


class Client(Bot):
    def __init__(self,**options) -> None:
        super().__init__(**options)

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


    async def on_message(self, ctx: Message):
        print(f"{ctx.guild} #{ctx.channel} //{ctx.author} : {ctx.content}")
        await self.process_commands(ctx)



