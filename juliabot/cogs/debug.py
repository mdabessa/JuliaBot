from discord.ext import commands

from ..scripts import Script


class Debug(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
    
    
    async def cog_check(self, ctx: commands.Context):
        return await ctx.bot.is_owner(ctx.author)


    @commands.command(
        name='reload',
        brief='Recarregar commandos.',
        description='Recarrega todos os cogs do bot.',
        )
    async def reload_cogs(self, ctx: commands.Context):
        msg = await ctx.send('Recarregando cogs...')
        exts = self.bot.extensions.copy()
        for ext in exts:
            await msg.edit(content=f'Recarregando {ext}...')
            self.bot.reload_extension(ext)

        await msg.edit(content='Cogs regarregados com sucesso!')


    @commands.command(
        name='scripts',
        brief='Listar todos os scripts rodando.',
        aliases=["get_scripts"]
    )
    async def get_all_scripts(self, ctx: commands.Context):
        scripts = Script.get_scripts()
        if scripts:
            for script in scripts:
                await ctx.send(f'```Nome: {script.name}\nCache:{script.cache}```')
        else:
            await ctx.send('Nenhum script rodando no momento.')

def setup(bot: commands.Bot):
    bot.add_cog(Debug(bot))
