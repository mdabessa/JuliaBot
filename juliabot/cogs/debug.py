from time import time

from discord.ext import commands


class Debug(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot


    @commands.is_owner()
    @commands.command(
        name='reload',
        brief='Recarregar commandos.',
        description='Recarrega todos os cogs do bot.',
        hidden=True,
        )
    async def reload_cogs(self, ctx: commands.Context):
        exts = self.bot.extensions.copy()
        for ext in exts:
            await ctx.send(f'Recarregando {ext}...')
            self.bot.reload_extension(ext)
            await ctx.send(f'{ext} recarregada com sucesso!')



def setup(bot: commands.Bot):
    bot.add_cog(Debug(bot))
