"""Core bot commands cog.

Provides essential bot commands like ping, prefix display, time, and session
dispatch.
"""

from datetime import datetime
from time import time

import pytz
from discord import Message
from discord.ext import commands, tasks

from ..client import Client
from ..models import BotConfig, Server


class CoreCog(commands.Cog, name="core"):
    """Core bot functionality.

    Provides essential commands: ping, prefix lookup, current time display,
    message repeating, and session event dispatch.
    """

    embed_title = ":brain:Core."

    def __init__(self, bot: Client) -> None:
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
        self.sessions_time_out.start()
        self.update_hearbeat.start()

    @commands.Cog.listener()
    async def on_message(self, message: Message):
        if message.content == self.bot.user.mention:
            await self._prefix(message)

        await self.bot.session_messages.dispatch(message)

    @tasks.loop(seconds=30, reconnect=True)
    async def sessions_time_out(self):
        """Expire idle sessions and purge expired snapshots."""
        await self.bot.sessions.sweep()

    @tasks.loop(seconds=60)
    async def update_hearbeat(self):
        now = datetime.now()

        heartbeat = BotConfig.get("heartbeat")
        if heartbeat is None:
            BotConfig("heartbeat", now.strftime("%d/%m/%Y %H:%M:%S"))
        else:
            heartbeat.value = now.strftime("%d/%m/%Y %H:%M:%S")
            heartbeat.update()


async def setup(bot: Client):
    await bot.add_cog(CoreCog(bot))
