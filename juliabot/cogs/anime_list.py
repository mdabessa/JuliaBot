from asyncio import sleep
from typing import Optional

from discord import Embed, TextChannel, User
from discord.ext import commands, tasks

from ..converters import Anime
from ..models import AnimesNotifier, Server, AnimesList
from ..scripts import Script
from ..utils import get_anime


class AnimeList(commands.Cog, name="animelist"):
    """Categoria relacionada a notificação e lista de animes."""

    embed_title = ":japanese_ogre:AnimeList."

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @staticmethod
    @Script.function(name="anime_list", events=["on_reaction_add"])
    async def _anime_list(cache: dict, **kwargs):
        if cache["status"] == "created":
            ctx = kwargs["ctx"]
            animes_db = kwargs["animes"]
            animes_jk = []
            message = await ctx.send("Buscando animes...")

            cache["index"] = 0
            cache["status"] = "searching"
            cache["animes_db"] = animes_db
            cache["animes_jk"] = animes_jk
            cache["message"] = message
            cache["ctx"] = ctx

            await message.add_reaction("⬅️")
            await message.add_reaction("➡️")
            await message.add_reaction("❌")

            for i, _anime in enumerate(animes_db):
                anime = await get_anime(_anime.mal_id)
                animes_jk.append(anime)

                if len(animes_jk) > 0:
                    index = cache["index"]
                    anime = animes_jk[index]

                    dubbed = " [Dublado]" if _anime.dubbed else ""

                    desc = (
                        f'Nome: {anime["title"]}{dubbed}\n'
                        + f'Episódios: {anime["episodes"]}\n'
                        + f'Tipo: {anime["type"]}\n'
                        + f'Lançando: {"Sim" if anime["airing"] else "Não"}\n'
                        + f'Link: [MyAnimeList]({anime["url"]})'
                    )

                    embed = Embed(title="Anime:", description=desc, color=ctx.bot.color)
                    embed.set_thumbnail(url=anime["image_url"])

                    if i != len(animes_db) - 1:
                        embed.set_footer(
                            text=f"{index+1}/{len(animes_jk)} animes  -  Pesquisando: {len(animes_jk)}/{len(animes_db)} animes."
                        )
                        await sleep(4)
                    else:
                        embed.set_footer(text=f"{index+1}/{len(animes_jk)} animes.")

                    await message.edit(embed=embed, content="")
                else:
                    await message.edit(embed=None, content="Sua lista esta vazia!")

            cache["status"] = "started"

        elif cache["status"] == "searching":
            user = kwargs["user"]
            emoji = kwargs["emoji"]

            index = cache["index"]
            animes_jk = cache["animes_jk"]
            animes_db = cache["animes_db"]
            message = cache["message"]
            ctx = cache["ctx"]

            if emoji == "➡️":
                index += 1
                if index >= len(animes_jk):
                    index = 0

            if emoji == "⬅️":
                index -= 1
                if index < 0:
                    index = len(animes_jk) - 1

            if emoji == "❌" and animes_db[index].user_id == str(user.id):
                if index < len(animes_jk):
                    anime = animes_jk[index]
                    _anime = animes_db[index]

                    _anime.delete()

                    animes_jk.remove(anime)
                    animes_db.remove(_anime)

                    if index >= len(animes_jk):
                        index = len(animes_jk) - 1

                    dubbed = " [Dublado]" if _anime.dubbed else ""
                    await ctx.send(
                        f'`{anime["title"]}{dubbed}` removido da sua lista com sucesso!'
                    )

            cache["index"] = index

        elif cache["status"] == "started":
            user = kwargs["user"]
            emoji = kwargs["emoji"]

            ctx = cache["ctx"]
            message = cache["message"]
            animes_jk = cache["animes_jk"]
            animes_db = cache["animes_db"]
            index = cache["index"]

            if emoji == "➡️":
                index += 1
                if index >= len(animes_jk):
                    index = 0

            if emoji == "⬅️":
                index -= 1
                if index < 0:
                    index = len(animes_jk) - 1

            if emoji == "❌" and animes_db[index].user_id == str(user.id):
                if index < len(animes_jk):
                    anime = animes_jk[index]
                    _anime = animes_db[index]

                    _anime.delete()

                    animes_jk.remove(anime)
                    animes_db.remove(_anime)

                    if index >= len(animes_jk):
                        index = len(animes_jk) - 1

                    dubbed = " [Dublado]" if _anime.dubbed else ""
                    await ctx.send(
                        f'`{anime["title"]}{dubbed}` removido da sua lista com sucesso!'
                    )

            cache["index"] = index

            if len(animes_jk) > 0:
                anime = animes_jk[index]
                _anime = animes_db[index]

                dubbed = " [Dublado]" if _anime.dubbed else ""

                desc = (
                    f'Nome: {anime["title"]}{dubbed}\n'
                    + f'Episódios: {anime["episodes"]}\n'
                    + f'Tipo: {anime["type"]}\n'
                    + f'Lançando: {"Sim" if anime["airing"] else "Não"}\n'
                    + f'Link: [MyAnimeList]({anime["url"]})'
                )

                emb = Embed(title="Anime:", description=desc, color=ctx.bot.color)
                emb.set_thumbnail(url=anime["image_url"])
                emb.set_footer(text=f"{index+1}/{len(animes_jk)} animes.")

                await message.edit(embed=emb, content="")
            else:
                await message.edit(embed=None, content="Sua lista esta vazia!")

    @staticmethod
    @Script.function(events=["on_reaction_add"])
    async def add_anime_confirm(cache: dict, **kwargs):
        if cache["status"] == "created":
            ctx = kwargs["ctx"]
            anime = kwargs["anime"]

            dub = " [Dublado]" if anime["dubbed"] else ""
            desc = (
                f'Nome: {anime["title"]}{dub}\n'
                + f'Episódios: {anime["episodes"]}\n'
                + f'Tipo: {anime["type"]}\n'
                + f'Lançando?: {"Sim" if anime["airing"] else "Não"}\n'
                + f'Link: [MyAnimeList]({anime["url"]})'
            )

            embed = Embed(
                title="Confirmar anime para adicionar:",
                description=desc,
                color=ctx.bot.color,
            )

            embed.set_thumbnail(url=anime["image_url"])

            message = await ctx.send(embed=embed)
            await message.add_reaction("👍")
            await message.add_reaction("👎")

            cache["message"] = message
            cache["author"] = ctx.author
            cache["anime"] = anime
            cache["status"] = "started"

        else:
            user = kwargs["user"]
            emoji = kwargs["emoji"]
            message = cache["message"]

            author = cache["author"]
            anime = cache["anime"]

            if emoji == "👍" and author == user:
                if (
                    AnimesList.get(
                        user_id=user.id, mal_id=anime["mal_id"], dubbed=anime["dubbed"]
                    )
                    is None
                ):
                    AnimesList(
                        user_id=user.id, mal_id=anime["mal_id"], dubbed=anime["dubbed"]
                    )
                    await message.add_reaction("✅")

                else:
                    await message.channel.send(
                        "Esse anime ja esta na sua lista de notificações."
                    )
                    await message.add_reaction("❌")

                cache["status"] = 0

            elif emoji == "👎" and author == user:
                await message.add_reaction("❌")
                cache["status"] = 0

    @staticmethod
    @Script.function(events=["on_reaction_add"])
    async def del_anime_confirm(cache: dict, **kwargs):
        if cache["status"] == "created":
            ctx = kwargs["ctx"]
            anime = kwargs["anime"]

            dub = " [Dublado]" if anime["dubbed"] else ""
            desc = (
                f'Nome: {anime["title"]}{dub}\n'
                + f'Episódios: {anime["episodes"]}\n'
                + f'Tipo: {anime["type"]}\n'
                + f'Lançando?: {"Sim" if anime["airing"] else "Não"}\n'
                + f'Link: [MyAnimeList]({anime["url"]})'
            )

            embed = Embed(
                title="Confirmar anime para remover:",
                description=desc,
                color=ctx.bot.color,
            )

            embed.set_thumbnail(url=anime["image_url"])

            message = await ctx.send(embed=embed)
            await message.add_reaction("👍")
            await message.add_reaction("👎")

            cache["message"] = message
            cache["author"] = ctx.author
            cache["anime"] = anime
            cache["status"] = "started"

        else:
            user = kwargs["user"]
            emoji = kwargs["emoji"]
            message = cache["message"]

            author = cache["author"]
            anime = cache["anime"]

            if emoji == "👍" and author == user:
                al = AnimesList.get(
                    user_id=user.id, mal_id=anime["mal_id"], dubbed=anime["dubbed"]
                )
                if al is not None:
                    al.delete()
                    await message.add_reaction("✅")

                else:
                    await message.channel.send(
                        "Esse anime não esta na sua lista de notificações."
                    )
                    await message.add_reaction("❌")

                cache["status"] = 0

            elif emoji == "👎" and author == user:
                await message.add_reaction("❌")
                cache["status"] = 0

    @commands.Cog.listener()
    async def on_ready(self):
        self.anime_notifier.start()

    @commands.guild_only()
    @commands.command(
        brief="Canal de notificações de animes.",
        help="Retorna o canal de notificações de animes do servidor.",
        aliases=["ac"],
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
        brief="Configure o canal de notificações de animes.",
        aliases=["sac"],
        help="Define o canal de notificações de novos episódios de animes.",
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

    @commands.command(
        brief="Adicione um anime a sua lista.",
        help="Adicione um anime a sua lista, para você ser notificado quando lançar episódio novo.",
        aliases=["aa"],
    )
    async def add_anime(self, ctx: commands.Context, *, anime: Anime):
        scr = Script(f"add_anime_confirm_{ctx.guild.id}", "add_anime_confirm")
        await scr.execute(ctx=ctx, anime=anime)

    @commands.command(brief="Remova um anime da sua lista.", aliases=["da"])
    async def del_anime(self, ctx: commands.Context, *, anime: Anime):
        scr = Script(f"del_anime_confirm_{ctx.guild.id}", "del_anime_confirm")
        await scr.execute(ctx=ctx, anime=anime)

    @commands.command(
        brief="Liste todos os animes da sua lista, ou da pessoa mensionada.",
        aliases=["al"],
    )
    async def anime_list(self, ctx: commands.Context, user: Optional[User] = None):
        if user is None:
            user = ctx.author

        animes = AnimesList.get_user(str(user.id))

        if animes:
            scr = Script(f"anime_list_{ctx.author.id}", "anime_list", time_out=600)
            await scr.execute(ctx=ctx, animes=animes)

        else:
            if user == ctx.author:
                await ctx.send("Sua lista esta vazia!")
            else:
                await ctx.send(f"A lista de {user.mention} esta vazia!")

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

            except Exception:
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

            users = AnimesList.get_anime(anime.mal_id, anime.dubbed)

            for user in users:
                try:
                    _user = await self.bot.fetch_user(int(user.user_id))

                    message = await _user.send(embed=embed)
                    await message.add_reaction("👍")
                except:
                    user.delete()

        for anime in animes:
            anime.set_notified(True)


def setup(bot: commands.Bot):
    bot.add_cog(AnimeList(bot))
