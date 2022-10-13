from asyncio import sleep
from typing import Optional

from discord import Embed, TextChannel, User
from discord.ext import commands, tasks
from discord.errors import NotFound

from ..models import AnimesNotifier, Server, AnimesList, User
from ..scripts import Script


def get_anime(*a, **k):
    pass


class AnimeList(commands.Cog, name="animelist"):
    """Categoria relacionada a notificação e lista de animes."""

    embed_title = ":japanese_ogre:AnimeList."

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot


    @commands.Cog.listener()
    async def on_ready(self):
        self.anime_notifier.start()

    @tasks.loop(minutes=1)
    async def anime_notifier(self):
        animes = AnimesNotifier.get_not_notified()

        if not animes:
            return

        animes.reverse()
        for guild in self.bot.guilds:
            try:
                server = Server.get_or_create(guild.id)
                channel_id = server.anime_channel

                if channel_id is None:
                    continue

                channel = await self.bot.fetch_channel(int(channel_id))

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

            except Exception as e:
                print(e)

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

            users = AnimesList.get_anime(anime.mal_id, anime.dubbed)

            for user in users:
                try:
                    disc_user = await self.bot.fetch_user(int(user.user_id))

                    _user = User.get_or_create(user.user_id)

                    if anime.lang.lower() not in _user.anime_lang.lower():
                        continue

                    message = await disc_user.send(embed=embed)
                    await message.add_reaction("👍")
                except NotFound:
                    user.delete()

        for anime in animes:
            anime.set_notified(True)


def setup(bot: commands.Bot):
    bot.add_cog(AnimeList(bot))
