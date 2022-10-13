from discord import User as DUser, TextChannel
from discord.errors import NotFound, Forbidden
from discord.ext import commands, tasks

from jikan4 import AioJikan
from typing import Optional

from ..config import BOT_JIKAN_RATE_LIMIT
from ..embeds.anime import anime_embed, episode_embed
from ..models import AnimesList, User, Server, AnimesNotifier
from ..scripts import Script


class Animes(commands.Cog, name="animes"):
    """Categoria relacionado a comandos e de animes em geral."""

    embed_title = ":japanese_goblin:Animes."

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.jikan = AioJikan(rate_limit=BOT_JIKAN_RATE_LIMIT)

    @staticmethod
    @Script.function(name="search_anime", events=["on_reaction_add"])
    async def search_anime(cache: dict, **kwargs) -> None:
        if cache["status"] == "created":
            cache["status"] = "started"
            cache["color"] = kwargs["color"]
            cache["dubbed"] = kwargs["dubbed"]
            cache["anime_search"] = kwargs["anime_search"]
            cache["index"] = 0

            embed = anime_embed(
                cache["anime_search"].data[cache["index"]], cache["color"]
            )
            embed.set_footer(
                text=f"Anime {cache['index'] + 1} de {len(cache['anime_search'].data)}"
            )

            message = await kwargs["ctx"].send(embed=embed)
            await message.add_reaction("⬅️")
            await message.add_reaction("➡️")
            await message.add_reaction("📝")
            cache["message"] = message

        else:
            if kwargs["emoji"] == "⬅️":
                cache["index"] -= 1
            elif kwargs["emoji"] == "➡️":
                cache["index"] += 1

            if kwargs["emoji"] == "📝":
                if AnimesList.get(
                    user_id=kwargs["user"].id,
                    mal_id=cache["anime_search"].data[cache["index"]].mal_id,
                    dubbed=cache["dubbed"],
                ):
                    await cache["message"].channel.send("Anime ja esta na lista!")
                else:
                    AnimesList(
                        user_id=kwargs["user"].id,
                        mal_id=cache["anime_search"].data[cache["index"]].mal_id,
                        dubbed=cache["dubbed"],
                    )

                    anime_title = cache["anime_search"].data[cache["index"]].title
                    anime_title = (
                        anime_title
                        if not cache["dubbed"]
                        else f"{anime_title} (Dublado)"
                    )

                    await cache["message"].channel.send(
                        f"`{anime_title}` adicionado a lista!"
                    )

            if cache["index"] < 0:
                cache["index"] = len(cache["anime_search"].data) - 1
            elif cache["index"] > len(cache["anime_search"].data) - 1:
                cache["index"] = 0

            embed = anime_embed(
                cache["anime_search"].data[cache["index"]], cache["color"]
            )
            embed.set_footer(
                text=f"Anime {cache['index'] + 1} de {len(cache['anime_search'].data)}"
            )
            await cache["message"].edit(embed=embed)

    @staticmethod
    @Script.function(name="anime_list", events=["on_reaction_add"])
    async def _anime_list(cache: dict, **kwargs) -> None:
        if cache["status"] == "created":
            cache["status"] = "searching"
            cache["color"] = kwargs["color"]
            cache["jikan"] = kwargs["jikan"]
            cache["anime_list"] = kwargs["animes"]
            cache["author"] = kwargs["ctx"].author
            cache["animes"] = []
            cache["index"] = 0

            message = await kwargs["ctx"].send("Buscando animes...")
            await message.add_reaction("⬅️")
            await message.add_reaction("➡️")
            await message.add_reaction("❌")
            cache["message"] = message

            for i in cache["anime_list"]:
                anime = await cache["jikan"].get_anime(i.mal_id)

                if i.dubbed:
                    anime.title = f"{anime.title} (Dublado)"

                cache["animes"].append(anime)

                # The list and the index can be modified while the bot is searching for the animes
                if len(cache["animes"]):
                    if cache["index"] < 0:
                        cache["index"] = len(cache["animes"]) - 1
                    elif cache["index"] > len(cache["animes"]) - 1:
                        cache["index"] = 0

                    embed = anime_embed(cache["animes"][cache["index"]], cache["color"])
                    embed.set_footer(
                        text=f"Animes: {cache['index'] + 1}/{len(cache['animes'])} - Pesquisando: {len(cache['animes'])}/{len(cache['anime_list'])}"
                    )
                    await message.edit(embed=embed, content=None)

                else:
                    await message.edit(
                        embed=None, content="A lista de animes está vazia."
                    )

            cache["status"] = "started"

        elif cache["status"] == "searching":  # Will be updated in the for loop above
            index = cache["index"]
            if (
                kwargs["emoji"] == "❌" and cache["author"] == kwargs["user"]
            ):  # Delete the anime from the list
                cache["anime_list"][index].delete()
                await cache["message"].channel.send(
                    f'`{cache["animes"][index].title}` removido da lista!'
                )
                cache["animes"].pop(index)
                index -= 1

            if kwargs["emoji"] == "⬅️":
                index -= 1
            elif kwargs["emoji"] == "➡️":
                index += 1

            cache["index"] = index

        else:
            index = cache["index"]
            if kwargs["emoji"] == "❌" and cache["author"] == kwargs["user"]:  #
                cache["anime_list"][index].delete()
                await cache["message"].channel.send(
                    f'`{cache["animes"][index].title}` removido da lista!'
                )
                cache["animes"].pop(index)
                index -= 1

            if kwargs["emoji"] == "⬅️":
                index -= 1
            elif kwargs["emoji"] == "➡️":
                index += 1

            if index < 0:
                index = len(cache["animes"]) - 1
            elif index > len(cache["animes"]) - 1:
                index = 0

            cache["index"] = index

            if len(cache["animes"]):
                embed = anime_embed(cache["animes"][index], cache["color"])
                embed.set_footer(text=f"Animes: {index + 1}/{len(cache['animes'])}")
                await cache["message"].edit(embed=embed, content=None)

            else:
                await cache["message"].edit(
                    embed=None, content="A lista de animes está vazia."
                )

    @commands.cooldown(1, 4, commands.BucketType.user)
    @commands.command(
        name="search_anime",
        brief="Pesquisa um anime.",
        description="Pesquisa um anime no MyAnimeList.",
        aliases=["anime", "ai"],
    )
    async def search_anime(self, ctx: commands.Context, *, anime: str) -> None:
        dubbed = False
        if anime.lower().endswith("dublado"):
            dubbed = True
            anime = anime[:-8]

        animes = await self.jikan.search_anime(search_type="tv", query=anime)
        if animes.data:
            scr = Script(
                name=f"{ctx.author.id}_search_anime",
                function_name="search_anime",
                time_out=300,
            )
            await scr.execute(
                ctx=ctx, anime_search=animes, color=self.bot.color, dubbed=dubbed
            )

        else:
            await ctx.send(f"Não foi encontrado nenhum anime com o nome `{anime}`.")

    @commands.cooldown(1, 4, commands.BucketType.user)
    @commands.command(
        name="anime_list",
        brief="Mostra a lista de animes.",
        description="Mostra a lista de animes que você adicionou para serem notificados.",
        aliases=["al"],
    )
    async def anime_list(
        self, ctx: commands.Context, user: Optional[DUser] = None
    ) -> None:
        if not user:
            user = ctx.author

        animes = AnimesList.get_user(user_id=user.id)
        if animes:
            scr = Script(
                name=f"{ctx.author.id}_anime_list",
                function_name="anime_list",
                time_out=300,
            )
            await scr.execute(
                ctx=ctx, animes=animes, color=self.bot.color, jikan=self.jikan
            )

        else:
            await ctx.send(f"{user.mention} não tem nenhum anime na lista.")

    @commands.command(
        brief="Configure a linguagem dos animes que você quer ser notificado.",
        description="Configure a linguagem dos animes que você quer ser notificado. Possíveis linguagens: `pt-br`, `en-us` e `pt-br/en-us`.",
        aliases=["sal", "lang"],
    )
    async def set_anime_lang(self, ctx: commands.Context, *, lang: str):
        if lang.lower() not in ["pt-br", "en-us", "pt-br/en-us"]:
            await ctx.send(
                "Lingua inválida!\nPossíveis linguagens: `pt-br`, `en-us` e `pt-br/en-us`."
            )
            return

        user = User.get_or_create(str(ctx.author.id))
        user.set_anime_lang(lang)
        await ctx.send(f"Linguagem de animes configurada para: `{lang}`")

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

        await ctx.send(f"Canal de notificação de animes: `{channel}`")

    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    @commands.command(
        brief="Configure o canal de notificações de animes.",
        description="Configure o canal de notificações de animes. Se não for passado nenhum canal, será desativado as notificações de animes neste servidor.",
        aliases=["sac"],
        help="Define o canal de notificações de novos episódios de animes.",
    )
    async def set_anime_channel(
        self, ctx: commands.Context, channel: Optional[TextChannel] = None
    ):
        server = Server.get(str(ctx.guild.id))

        if channel is None:
            server.set_anime_channel(None)
            await ctx.send("Notificações de animes desabilitadas neste servidor.")
            return

        server.set_anime_channel(str(channel.id))
        await ctx.send(f"Canal de notificações de anime configurado para: `{channel}`")

    @commands.Cog.listener()
    async def on_ready(self):
        self.anime_notifier.start()

    @tasks.loop(minutes=1)
    async def anime_notifier(self):
        animes = AnimesNotifier.get_not_notified()

        animes.reverse()  # To notify the last added anime first
        for anime in animes:
            embed = episode_embed(anime, self.bot.color)

            users = AnimesList.get_anime(mal_id=anime.mal_id, dubbed=anime.dubbed)
            for user in users:
                try:
                    user = await self.bot.fetch_user(user.user_id)

                    await user.send(embed=embed)

                except Forbidden:
                    user.delete()
                    print(f"User {user.user_id} has blocked the bot.")
                except NotFound:
                    pass

            for guild in self.bot.guilds:
                server = Server.get(str(guild.id))
                if server.anime_channel is not None:
                    try:
                        channel = self.bot.fetch_channel(int(server.anime_channel))
                        await channel.send(embed=embed)

                    except Forbidden:
                        server.set_anime_channel(None)
                        print(f"Bot has no permission to send messages in {channel}")

                    except NotFound:
                        pass

            anime.set_notified(True)


def setup(bot: commands.Bot):
    bot.add_cog(Animes(bot))
