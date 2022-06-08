from discord.ext import commands

from ..models import Server


class ServerConfig(commands.Cog, name='Configurações do Servidor'):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
    
    async def cog_check(self, ctx: commands.Context):
        if ctx.guild == None:
            return False
        
        perms = ctx.channel.permissions_for(ctx.author)
        return perms.administrator
    
    @commands.command()
    async def set_prefix(self, ctx: commands.Context, prefix: str):
        server = Server.get_or_create(str(ctx.guild.id))
        server.set_prefix(prefix)
        await ctx.send(f"Prefixo de comandos mudado para `{prefix}`")


def setup(bot: commands.Bot):
    bot.add_cog(ServerConfig(bot))
