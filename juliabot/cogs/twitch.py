from discord.ext import commands
import requests


class Twitch(commands.Cog):
    """Twitch"""

    embed_title = ":tv: Twitch"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(
        name="stream",
        brief="Verifica se um streamer está online.",
        description="Verifica se dado streamer está online na Twitch.",
        aliases=["str", "streamer"],
    )
    async def stream(self, ctx: commands.Context, streamer: str):
        url = f'https://www.twitch.tv/{streamer}'
        response = requests.get(url)

        if response.status_code != 200:
            await ctx.send(f"Não foi possível acessar o canal de {streamer}.")
            return
        
        online = 'isLiveBroadcast' in response.text

        if online:
            await ctx.send(f"`{streamer}` está online!")
        else:
            await ctx.send(f"`{streamer}` está offline.")


def setup(bot: commands.Bot):
    bot.add_cog(Twitch(bot))
