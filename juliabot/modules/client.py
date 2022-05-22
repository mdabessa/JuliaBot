import discord


class Client(discord.Client):
    def __init__(self,**options) -> None:
        super().__init__(**options)
    

    async def on_message(self, ctx: discord.Message):
        print(f"{ctx.guild} #{ctx.channel} //{ctx.author} : {ctx.content}")

