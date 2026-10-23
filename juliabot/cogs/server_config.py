"""Server configuration cog.

Provides administrative commands to customize bot behavior per guild,
including prefix, timezone, and durable channel interactions.
"""

import datetime
from types import SimpleNamespace

import pytz
from discord import TextChannel
from discord.ext import commands

from ..client import Client
from ..models import Server
from ..sessions import (
    InteractionEvent,
    Registration,
    Registry,
    Scope,
    SessionManager,
    TriggerType,
)
from ..sessions.patterns import ChannelEntryPointRule

ENTRY_POINT = "channel.entry_point"


class ServerConfigCog(commands.Cog, name="configuracoes"):
    """Server configuration management.

    Provides administrative commands for configuring guild-specific settings
    like command prefix and timezone.
    """

    embed_title = ":gear:Configurações."

    def __init__(self, bot: Client) -> None:
        self.bot = bot
        if not hasattr(bot, "sessions"):
            bot.sessions = SessionManager(Registry())
        if bot.sessions.registry.get(ENTRY_POINT) is None:
            bot.sessions.registry.register(
                Registration(
                    name=ENTRY_POINT,
                    session_class=ChannelEntryPointRule,
                    trigger=TriggerType.MESSAGE,
                    scope=Scope.CHANNEL,
                    persistent=True,
                    resumable=True,
                    max_per_scope=1,
                )
            )

    async def cog_check(self, ctx: commands.Context):
        if ctx.guild == None:
            return False

        perms = ctx.channel.permissions_for(ctx.author)
        return perms.administrator

    @commands.command(
        brief="Mude o prefixo do bot.", help="Mude o prefixo do bot no servidor."
    )
    async def set_prefix(self, ctx: commands.Context, prefix: str):
        server = Server.get_or_create(str(ctx.guild.id))
        server.set_prefix(prefix)
        await ctx.send(f"Prefixo de comandos mudado para `{prefix}`")

    @commands.command(
        brief="Mude o fuso horário do bot.",
        help="Mude o fuso horário do bot no servidor.",
        aliases=["stz", "set_tz"],
    )
    async def set_timezone(self, ctx: commands.Context, timezone: str):
        now = datetime.datetime.now()
        try:
            timezone = pytz.timezone(timezone)
            now.astimezone(timezone)
        except:
            raise Exception(f"Fuso horário `{timezone}` não é válido.")

        server = Server.get_or_create(str(ctx.guild.id))
        server.set_timezone(timezone)

        await ctx.send(
            f"Fuso horário mudado para `{timezone.zone}` | Hora atual: `{now.strftime('%d/%m/%Y %H:%M')} [{timezone.zone}]`"
        )

    @commands.command(
        name="entrypoint",
        brief="Cria uma interação permanente no canal.",
        description=(
            "Cria uma mensagem permanente neste canal. Toda mensagem enviada "
            "nele passará pela interação até ser desativada."
        ),
        aliases=["ponto_entrada"],
    )
    async def entrypoint(
        self, ctx: commands.Context, channel: TextChannel = None
    ) -> None:
        channel = channel or ctx.channel
        if self._entry_point(channel.id) is not None:
            await ctx.send("Este canal já possui uma interação permanente.")
            return

        await self.bot.sessions.start(
            ENTRY_POINT, self._entry_point_event(ctx, channel)
        )
        await ctx.send(f"Interação permanente criada em {channel.mention}.")

    @commands.command(
        name="entrypoint_disable",
        brief="Remove a interação permanente do canal.",
        description="Remove a interação permanente e os botões do canal.",
        aliases=["entrypoint_off", "desativar_ponto_entrada"],
    )
    async def entrypoint_disable(
        self, ctx: commands.Context, channel: TextChannel = None
    ) -> None:
        channel = channel or ctx.channel
        rule = self._entry_point(channel.id)
        if rule is None:
            await ctx.send("Este canal não possui uma interação permanente.")
            return

        await rule.shutdown(channel)
        await ctx.send("Interação permanente desativada.")

    def _entry_point(self, channel_id: int):
        """Return the entry point rule active in a channel, if any."""
        return next(
            (
                rule
                for rule in self.bot.sessions.message_rules(channel_id)
                if rule.registration.name == ENTRY_POINT
            ),
            None,
        )

    @staticmethod
    def _entry_point_event(ctx: commands.Context, channel) -> InteractionEvent:
        """Build the event that starts an entry point rule for a channel."""
        return InteractionEvent(
            transport=TriggerType.MESSAGE,
            key=f"{ENTRY_POINT}:{channel.id}",
            user_id=ctx.author.id,
            guild_id=getattr(ctx.guild, "id", None),
            channel_id=channel.id,
            message_id=ctx.message.id,
            raw=SimpleNamespace(channel=channel),
        )


async def setup(bot: Client):
    await bot.add_cog(ServerConfigCog(bot))
