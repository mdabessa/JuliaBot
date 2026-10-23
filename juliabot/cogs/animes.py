"""Anime search and watchlist management cog.

Provides commands to search for animes, view details, and manage a personal
watchlist with Jikan API integration.
"""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from discord import TextChannel
from discord import User as DUser
from discord.errors import Forbidden, NotFound
from discord.ext import commands, tasks
from jikan4 import AioJikan

from ..client import Client
from ..config import BOT_JIKAN_RATE_LIMIT
from ..embeds.anime import anime_embed, episode_embed
from ..models import AnimesList, AnimesNotifier, Server, User
from ..sessions import (
    Action,
    InteractionEvent,
    Registration,
    Registry,
    Scope,
    SessionManager,
    TriggerType,
)
from ..sessions.patterns import PaginationSession

if TYPE_CHECKING:
    from jikan4.models import Anime

logger = logging.getLogger(__name__)

ANIME_SEARCH = "animes.search"
ANIME_LIST = "animes.list"


@dataclass(frozen=True)
class AnimeEntry:
    """Runtime pair of a Jikan anime and the user's watchlist row."""

    anime: "Anime"
    entry: AnimesList


class AnimeSearchPagination(PaginationSession["Anime"]):
    """Paginate a Jikan search, fetching adjacent Jikan pages on demand."""

    extra_actions = (
        Action("add", "add_current", owner_only=False, label="Adicionar", emoji="📝"),
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._jikan = None
        self._color = 0
        self._pagination = None

    @property
    def query(self) -> str:
        """Return the search query stored in the payload."""
        value = self._payload.get("query", "")
        return value if isinstance(value, str) else ""

    @property
    def jikan_page(self) -> int:
        """Return the Jikan result page currently loaded."""
        value = self._payload.get("jikan_page", 1)
        return int(value) if isinstance(value, (int, float)) else 1

    @property
    def dubbed(self) -> bool:
        """Return whether results are treated as dubbed."""
        return bool(self._payload.get("dubbed", False))

    async def start(self, event: InteractionEvent) -> None:
        """Capture runtime dependencies, then load the first Jikan page."""
        context = event.raw
        if context is None or getattr(context, "cog", None) is None:
            raise RuntimeError("Anime sessions require an invoking cog context")
        self._jikan = context.cog.jikan
        self._color = context.bot.color
        await super().start(event)

    async def load_items(self) -> list["Anime"]:
        """Fetch one Jikan page and keep its pagination metadata."""
        result = await self._jikan.search_anime(
            search_type="tv", query=self.query, page=self.jikan_page
        )
        self._pagination = result.pagination
        return list(result.data)

    async def load_more(self, direction: int) -> bool:
        """Fetch the adjacent Jikan page when navigation hits a boundary."""
        page = self.jikan_page + direction
        if page < 1:
            return False
        if direction > 0 and not getattr(self._pagination, "has_next_page", False):
            return False
        if direction < 0 and self.jikan_page <= 1:
            return False

        self.set_payload("jikan_page", page)
        items = list(await self.load_items())
        if not items:
            self.set_payload("jikan_page", page - direction)
            return False

        self._items = items
        self.set_payload("index", 0 if direction > 0 else len(items) - 1)
        await self.render()
        return True

    async def render_item(self, item: "Anime", index: int, total: int):
        """Render one search result with its position in the Jikan page."""
        embed = anime_embed(item, self._color)
        embed.set_footer(text=f"Anime {index + 1} de {total}")
        return embed

    async def add_current(self, event: InteractionEvent) -> None:
        """Add the current result to the acting user's watchlist."""
        item = self._items[self.index]
        if AnimesList.get(
            user_id=event.user_id, mal_id=item.mal_id, dubbed=self.dubbed
        ):
            await self._message.channel.send(f"`{item.title}` já está na sua lista!")
            return

        AnimesList(user_id=event.user_id, mal_id=item.mal_id, dubbed=self.dubbed)
        title = item.title if not self.dubbed else f"{item.title} (Dublado)"
        await self._message.channel.send(f"`{title}` adicionado a lista!")

    def to_payload(self) -> dict:
        """Persist only the search coordinates and current index."""
        return {
            "index": self.index,
            "query": self.query,
            "jikan_page": self.jikan_page,
            "dubbed": self.dubbed,
        }


class AnimeListPagination(PaginationSession[AnimeEntry]):
    """Progressively load and paginate one user's anime watchlist."""

    progressive = True
    loading_message = "Buscando animes..."
    empty_message = "A lista de animes está vazia."
    extra_actions = (
        Action(
            "delete",
            "delete_current",
            owner_only=False,
            label="Remover",
            emoji="❌",
            style="danger",
        ),
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._jikan = None
        self._color = 0
        self._expected = 0
        self._searching = False

    @property
    def target_user_id(self) -> int:
        """Return the watchlist owner's id from the payload."""
        value = self._payload.get("target_user_id", 0)
        return int(value) if isinstance(value, (int, float)) else 0

    async def start(self, event: InteractionEvent) -> None:
        """Capture runtime dependencies and begin progressive loading."""
        context = event.raw
        if context is None or getattr(context, "cog", None) is None:
            raise RuntimeError("Anime sessions require an invoking cog context")
        self._jikan = context.cog.jikan
        self._color = context.bot.color
        self._searching = True
        await super().start(event)

    async def load_rows(self) -> list[AnimesList]:
        """Load the watchlist rows backing this session."""
        rows = AnimesList.get_user(user_id=self.target_user_id)
        self._expected = len(rows)
        return rows

    async def iter_items(self):
        """Yield anime details one at a time while the list loads."""
        for row in await self.load_rows():
            anime = await self._jikan.get_anime(row.mal_id)
            if row.dubbed:
                anime.title = f"{anime.title} (Dublado)"
            yield AnimeEntry(anime=anime, entry=row)

    async def load_items(self):
        """Load the whole list eagerly for hydration and refresh paths."""
        return [item async for item in self.iter_items()]

    async def on_loading_finished(self) -> None:
        """Drop the search-progress footer once loading completes."""
        self._searching = False
        await self.render()

    async def render_item(self, item: AnimeEntry, index: int, total: int):
        """Render one watchlist entry, including search progress."""
        embed = anime_embed(item.anime, self._color)
        if self._searching:
            embed.set_footer(
                text=(
                    f"Animes: {index + 1}/{total} - "
                    f"Pesquisando: {total}/{self._expected}"
                )
            )
        else:
            embed.set_footer(text=f"Animes: {index + 1}/{total}")
        return embed

    async def delete_item(self, item: AnimeEntry, event: InteractionEvent) -> bool:
        """Remove an entry only when the acting user owns it."""
        if str(item.entry.user_id) != str(event.user_id):
            return False
        item.entry.delete()
        if self._message is not None:
            await self._message.channel.send(f"`{item.anime.title}` removido da lista!")
        return True

    def to_payload(self) -> dict:
        """Persist only the index and the watchlist owner id."""
        return {"index": self.index, "target_user_id": self.target_user_id}


class AnimesCog(commands.Cog, name="animes"):
    """Anime search and watchlist management.

    Provides interactive anime search with pagination and watchlist operations
    using the Jikan MyAnimeList API.
    """

    embed_title = ":japanese_goblin:Animes."

    def __init__(self, bot: Client) -> None:
        self.bot = bot
        self.jikan = AioJikan(rate_limit=BOT_JIKAN_RATE_LIMIT)
        if not hasattr(bot, "sessions"):
            bot.sessions = SessionManager(Registry())
        self._register_sessions()

    def _register_sessions(self) -> None:
        """Register the anime sessions once per bot instance."""
        registrations = (
            Registration(
                name=ANIME_SEARCH,
                session_class=AnimeSearchPagination,
                trigger=TriggerType.COMPONENT,
                scope=Scope.USER,
                timeout=300,
                max_per_scope=1,
            ),
            Registration(
                name=ANIME_LIST,
                session_class=AnimeListPagination,
                trigger=TriggerType.COMPONENT,
                scope=Scope.USER,
                timeout=300,
                max_per_scope=1,
            ),
        )
        for registration in registrations:
            if self.bot.sessions.registry.get(registration.name) is None:
                self.bot.sessions.registry.register(registration)

    @staticmethod
    def _session_event(ctx: commands.Context) -> InteractionEvent:
        """Build a normalized interaction event from a command invocation."""
        return InteractionEvent(
            transport=TriggerType.COMPONENT,
            key=str(ctx.message.id),
            user_id=ctx.author.id,
            guild_id=getattr(ctx.guild, "id", None),
            channel_id=ctx.channel.id,
            message_id=ctx.message.id,
            raw=ctx,
        )

    @commands.cooldown(1, 4, commands.BucketType.user)
    @commands.command(
        name="search_anime",
        brief="Pesquisa um anime.",
        description="Pesquisa um anime no MyAnimeList.",
        aliases=["anime", "ai", "sa"],
    )
    async def search_anime(self, ctx: commands.Context, *, anime: str) -> None:
        dubbed = False
        if anime.lower().endswith("dublado"):
            dubbed = True
            anime = anime[:-8]

        session = await self.bot.sessions.start(
            ANIME_SEARCH,
            self._session_event(ctx),
            payload={"query": anime, "jikan_page": 1, "dubbed": dubbed},
        )
        if session.closed:
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
        if not animes:
            await ctx.send(f"{user.mention} não tem nenhum anime na lista.")
            return

        await self.bot.sessions.start(
            ANIME_LIST,
            self._session_event(ctx),
            payload={"target_user_id": user.id},
        )

    @commands.cooldown(1, 4, commands.BucketType.user)
    @commands.command(
        name="add_anime",
        brief="Adiciona um anime na lista.",
        description="Adiciona um anime na lista utilizando o mal_id para ser notificado quando sair um novo episódio.",
        aliases=["aa"],
    )
    async def add_anime(
        self, ctx: commands.Context, mal_id: int, dubbed: bool = False
    ) -> None:
        anime = await self.jikan.get_anime(mal_id)
        if anime:
            if anime.type == "TV":
                if (
                    AnimesList.get(user_id=ctx.author.id, mal_id=mal_id, dubbed=dubbed)
                    is None
                ):
                    AnimesList(
                        mal_id=mal_id,
                        dubbed=dubbed,
                        user_id=ctx.author.id,
                    )
                    await ctx.send(f"`{anime.title}` adicionado na lista!")

                else:
                    await ctx.send(f"`{anime.title}` já está na lista.")

            else:
                await ctx.send(f"`{anime.title}` não é um anime.")

        else:
            await ctx.send("Não foi encontrado nenhum anime com esse ID.")

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

        channel = self.bot.get_channel(int(server.anime_channel))

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
        try:
            animes = AnimesNotifier.get_not_notified()

            animes.reverse()  # To notify the last added anime first
            for anime in animes:
                embed = episode_embed(anime, self.bot.color)

                users = AnimesList.get_anime(mal_id=anime.mal_id, dubbed=anime.dubbed)
                for user in users:
                    _user = User.get_or_create(str(user.user_id))
                    if anime.lang.lower() not in _user.anime_lang.lower():
                        continue

                    try:
                        discord_user = await self.bot.fetch_user(int(user.user_id))
                        msg = await discord_user.send(embed=embed)
                        await msg.add_reaction(
                            "👍"
                        )  # Help the user mark the episode as watched

                    except Forbidden:
                        user.delete()
                        logger.warning(f"User {user.user_id} has blocked the bot.")

                    except NotFound:
                        logger.warning(f"User {user.user_id} not found.")

                    except Exception as e:
                        logger.error(
                            f"Error sending anime notification to user {user.user_id}: {e}"
                        )

                for guild in self.bot.guilds:
                    server = Server.get(str(guild.id))
                    if (server is None) or (server.anime_channel is None):
                        continue

                    try:
                        channel = await self.bot.fetch_channel(
                            int(server.anime_channel)
                        )
                        await channel.send(embed=embed)

                    except Forbidden:
                        server.set_anime_channel(None)
                        logger.warning(
                            f"Bot has no permission to send messages in {channel}"
                        )

                    except NotFound:
                        logger.warning(f"Channel {server.anime_channel} not found.")

                    except Exception as e:
                        logger.error(
                            f"Error sending anime notification to channel {server.anime_channel}: {e}"
                        )

                anime.set_notified(True)

        except Exception as e:
            logger.error(f"Error in anime notification task: {e}")


async def setup(bot: Client):
    await bot.add_cog(AnimesCog(bot))
