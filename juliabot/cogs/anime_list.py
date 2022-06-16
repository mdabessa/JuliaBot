from typing import Optional

from discord import Embed, TextChannel
from discord.ext import commands, tasks

from ..models import AnimesNotifier, Server
from ..converters import Anime


class AnimeList(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        self.anime_notifier.start()

    @commands.guild_only()
    @commands.command(
        brief="Retorna o canal de notificações de animes do servidor", aliases=["ac"]
    )
    async def anime_channel(self, ctx: commands.Context):
        server = Server.get(str(ctx.guild.id))

        if server.anime_channel is None:
            await ctx.send(
                f"O servidor `{ctx.guild}` não possui nenhum canal de notificações de animes configurado!"
            )
            return

        channel = self.bot.get_channel(server.anime_channel)

        if channel is None:
            await ctx.send(
                f"O servidor `{ctx.guild}` não possui nenhum canal de notificações de animes configurado!"
            )
            server.set_anime_channel(None)
            return

        await ctx.send(f"Canal de notificação de animes: {channel}")

    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    @commands.command(
        brief="Configure o canal de notificações de animes", aliases=["sac"]
    )
    async def set_anime_channel(
        self, ctx: commands.Context, channel: Optional[TextChannel] = None
    ):
        server = Server.get(str(ctx.guild.id))

        if channel is None:
            server.set_anime_channel(None)
            await ctx.send("Notificações de animes desabilitadas!")
            return

        server.set_anime_channel(str(channel.id))
        await ctx.send(f"Canal de notificações de anime configurado para: `{channel}`")

    @tasks.loop(minutes=1)
    async def anime_notifier(self):
        animes = AnimesNotifier.get_not_notified()

        if not animes:
            return

        animes.reverse()
        for guild in self.bot.guilds:
            server = Server.get_or_create(guild.id)
            channel_id = server.anime_channel

            if channel_id is None:
                continue

            channel = self.bot.get_channel(int(channel_id))

            if channel is None:
                continue

            for anime in animes:
                dub = " [Dublado]" if anime.dubbed else ""
                embed = Embed(
                    title=anime.name,
                    url=anime.url,
                    description=f"Episódio {anime.episode}" + dub,
                    color=self.bot.color,
                )
                embed.set_image(url=anime.image)
                embed.set_footer(text=anime.site)

                await channel.send(embed=embed)

        for anime in animes:
            anime.set_notified(True)


def setup(bot: commands.Bot):
    bot.add_cog(AnimeList(bot))
