from discord.ext import commands

from ..client import Client
from ..collect_updates import UpdateCollector
from ..embeds.changelog import changelog_embed



class ChangelogCog(commands.Cog):
    """Changelog"""

    embed_title = ":newspaper: Changelog"

    def __init__(self, bot: Client) -> None:
        self.bot = bot
    

    @commands.command(
        name="changelog",
        brief="Mostra as últimas atualizações do Bot.",
        description="Mostra as últimas atualizações do Bot, incluindo novas funcionalidades, correções de bugs e melhorias.",
        aliases=["updates", "novidades", "upd"]
    )
    async def changelog(self, ctx: commands.Context):
        updates = UpdateCollector.get_last_n_commits(10)
        if not updates:
            await ctx.send("Nenhuma atualização encontrada.")
            return
        
        embed = changelog_embed(updates, self.bot.color)
        await ctx.send(embed=embed)




async def setup(bot: Client) -> None:
    await bot.add_cog(ChangelogCog(bot))
