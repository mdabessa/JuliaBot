from datetime import datetime
from time import time

import pytz
from discord import Message, Reaction, User
from discord.ext import commands, tasks

from ..models import BotConfig, Server
from ..scripts import Script


class Core(commands.Cog, name="core"):
    """Categoria relacionada a comandos e funções cores do bot."""

    embed_title = ":brain:Core."

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _prefix(self, message: Message):
        prefix = await self.bot.get_prefix(message)
        await message.channel.send(f"O prefixo do servidor é: `{prefix}`")

    @commands.command(
        name="ping",
        brief="Pong!",
        description="Um comando para calcular a latencia das mensagens.",
        aliases=["latency", "latencia"],
    )
    async def ping(self, ctx: commands.Context):
        t = time()
        msg = await ctx.send("Ping!")
        t = int((time() - t) * 1000)
        await msg.edit(content=f"`{t}ms` Pong!")

    @commands.command(
        name="prefix", brief="Retorna o prefix do bot no servidor.", aliases=["prefixo"]
    )
    async def prefix(self, ctx: commands.Context):
        await self._prefix(ctx.message)

    @commands.command(
        brief="Mostra a hora atual do servidor!",
        aliases=["time", "hora"],
    )
    async def current_time(self, ctx: commands.Context):
        timezone = pytz.utc
        if ctx.guild:
            server = Server.get(ctx.guild.id)
            timezone = server.get_timezone()

        now = datetime.now().astimezone(timezone)
        now = now.strftime("%d/%m/%Y %H:%M")

        await ctx.reply(f"A hora atual do servidor é: `{now} [{timezone.zone}]`")

    @commands.cooldown(1, 10, commands.BucketType.member)
    @commands.command(name="say", brief="Fazer o bot dizer algo.", aliases=["diga"])
    async def say(self, ctx: commands.Context, *, content: str):
        await ctx.send(content)

    @commands.has_permissions(administrator=True)
    @commands.command(
        name="upchat", brief="Suba o chat do canal.", aliases=["subirchat", "uc"]
    )
    async def up_chat(self, ctx: commands.Context):
        await ctx.send("** **\n" * 50)

    @commands.Cog.listener()
    async def on_ready(self):
        self.scripts_time_out.start()
        self.update_hearbeat.start()

    @commands.Cog.listener()
    async def on_message(self, message: Message):
        if message.content == self.bot.user.mention:
            await self._prefix(message)

        for scr in Script.fetch_script("on_message", by="events", _in="function"):
            await scr.execute(message=message)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: Reaction, user: User):
        if self.bot.user == user:
            return

        scr = Script.fetch_script(reaction.message, by="message", _in="cache")
        if scr and "on_reaction_add" in scr[0].func["events"]:
            await scr[0].execute(user=user, emoji=reaction.emoji)

    @tasks.loop(seconds=30, reconnect=True)
    async def scripts_time_out(self):
        now = datetime.now()
        for script in Script.get_scripts().copy():
            diff = now - script.last_execute
            if diff.total_seconds() >= script.time_out:
                script.close()

    @tasks.loop(seconds=60)
    async def update_hearbeat(self):
        now = datetime.now()

        heartbeat = BotConfig.get("heartbeat")
        if heartbeat is None:
            BotConfig("heartbeat", now.strftime("%d/%m/%Y %H:%M:%S"))
        else:
            heartbeat.value = now.strftime("%d/%m/%Y %H:%M:%S")
            heartbeat.update()


def setup(bot: commands.Bot):
    bot.add_cog(Core(bot))
