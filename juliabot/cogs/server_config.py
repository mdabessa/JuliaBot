import datetime

import pytz
from discord.ext import commands

from ..models import Server


class ServerConfig(commands.Cog, name="configuracoes"):
    """Categoria relacionada a comandos de configuração do servidor."""

    embed_title = ":gear:Configurações."

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

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


def setup(bot: commands.Bot):
    bot.add_cog(ServerConfig(bot))
