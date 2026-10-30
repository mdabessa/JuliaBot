"""The ``!jikan`` passthrough for routes that are not worth a command.

Every route is a command already, but this stays as the escape hatch: it can
reach hidden routes (for the bot owner), explain a route's parameters, and list
what the API exposes without loading the help pages.
"""

from __future__ import annotations

import difflib
import logging

from discord import Embed
from discord.ext import commands
from jikan4 import AioJikan

from ..client import Client
from ..config import BOT_JIKAN_RATE_LIMIT
from ..jikan_args import JikanArgumentError, parse_arguments
from ..jikan_catalog import RouteSpec, load_specs
from ..jikan_commands import execute_route
from ..jikan_sessions import register, specs_by_route
from ..sessions import Registry, SessionManager

logger = logging.getLogger(__name__)

GROUPS = ("anime", "manga", "catalog")
GROUP_TITLES = {
    "anime": ":japanese_goblin:Anime",
    "manga": ":books:Manga",
    "catalog": ":mag:Catálogo",
}
MAX_DESCRIPTION = 4096
MAX_EMBEDS = 10
MAX_FIELD_VALUE = 1024
MAX_FIELDS = 25

USAGE = (
    "**`!jikan <rota> [chave=valor ...]`** — chama qualquer rota da API.\n"
    "**`!jikan --list [anime|manga|catálogo]`** — lista as rotas disponíveis.\n"
    "**`!jikan --schema <rota>`** — parâmetros, tipos e padrões de uma rota.\n"
    "\nOs comandos prontos aparecem em `!help !anime_api`, `!help !manga` "
    "e `!help !mal`."
)


def _suggestions(query: str) -> str:
    """Return the closest route names, formatted for an error message."""
    names = [spec.route for spec in load_specs()] + [spec.name for spec in load_specs()]
    matches = difflib.get_close_matches(query, names, n=3, cutoff=0.6)
    if not matches:
        return ""
    return (
        " Talvez você quis dizer: " + ", ".join(f"`{name}`" for name in matches) + "."
    )


def _visible(spec: RouteSpec, is_owner: bool) -> bool:
    return is_owner or not spec.hidden


def _list_embeds(specs: list[RouteSpec], group: str) -> list[Embed]:
    """Pack the route names of one group into description-sized embeds."""
    lines = [f"`{spec.name}` — {spec.brief}" for spec in specs]
    chunks: list[list[str]] = []
    current: list[str] = []
    used = 0
    for line in lines:
        if current and used + len(line) + 1 > MAX_DESCRIPTION:
            chunks.append(current)
            current, used = [], 0
        current.append(line)
        used += len(line) + 1
    if current:
        chunks.append(current)

    total = len(chunks)
    embeds = []
    for position, chunk in enumerate(chunks[:MAX_EMBEDS], start=1):
        title = GROUP_TITLES[group]
        if total > 1:
            title = f"{title} ({position}/{total})"
        embeds.append(Embed(title=title, description="\n".join(chunk)))
    return embeds


def _call_hint(spec: RouteSpec) -> str:
    """Render the Python call that backs this route."""
    arguments = ", ".join(f"{param.name}=..." for param in spec.params)
    return f"`await client.{spec.route}({arguments})`"


def _schema_embed(spec: RouteSpec, prefix: str = "!") -> Embed:
    """Describe one route: usage, what it returns and every parameter."""
    embed = Embed(
        title=f"{prefix}jikan {spec.name}",
        description=spec.description,
    )
    embed.add_field(name="Chamada", value=_call_hint(spec), inline=False)
    embed.add_field(name="Retorno", value=f"`{spec.shape}`", inline=False)
    embed.add_field(name="Rota", value=f"`{spec.route}`", inline=False)

    for param in spec.params[:MAX_FIELDS]:
        parts = [f"tipo: `{param.type_name}`"]
        parts.append("obrigatório" if param.required else "opcional")
        if not param.required and param.default is not None:
            parts.append(f"padrão: `{param.default}`")
        embed.add_field(
            name=param.name,
            value=" • ".join(parts)[:MAX_FIELD_VALUE],
            inline=True,
        )
    embed.set_footer(text=spec.usage)
    return embed


class JikanCog(commands.Cog, name="jikan"):
    """Raw passthrough to the Jikan API."""

    embed_title = ":satellite:Jikan."

    def __init__(self, bot: Client) -> None:
        self.bot = bot
        self.jikan = getattr(bot, "jikan", None) or AioJikan(
            rate_limit=BOT_JIKAN_RATE_LIMIT
        )
        bot.jikan = self.jikan
        if not hasattr(bot, "sessions"):
            bot.sessions = SessionManager(Registry())
        register(bot.sessions)

    async def _is_owner(self, ctx: commands.Context) -> bool:
        is_owner = getattr(self.bot, "is_owner", None)
        if is_owner is None:
            return False
        try:
            return bool(await is_owner(ctx.author))
        except Exception:  # pragma: no cover - owner lookup must not break the command
            logger.debug("Owner lookup failed", exc_info=True)
            return False

    async def _list(self, ctx: commands.Context, argument: str) -> None:
        group = argument.strip().lower()
        if group and group not in GROUPS:
            await ctx.send(
                f"Grupo desconhecido: `{argument}`. Use `anime`, `manga` ou `catalog`."
            )
            return

        owner = await self._is_owner(ctx)
        specs = [
            spec
            for spec in load_specs()
            if _visible(spec, owner) and (not group or spec.group == group)
        ]
        if not specs:
            await ctx.send("Nenhuma rota disponível para esse grupo.")
            return

        groups = [group] if group else list(GROUPS)
        embeds: list[Embed] = []
        for name in groups:
            embeds.extend(
                _list_embeds([spec for spec in specs if spec.group == name], name)
            )
        await ctx.send(embeds=embeds[:MAX_EMBEDS])

    async def _schema(self, ctx: commands.Context, argument: str) -> None:
        name = argument.strip()
        if not name:
            await ctx.send(
                f"Informe uma rota. Exemplo: `!jikan --schema get_anime`.\n\n{USAGE}"
            )
            return

        spec = specs_by_route().get(name) or specs_by_route().get(f"get_{name}")
        if spec is None:
            await ctx.send(f"Rota desconhecida: `{name}`.{_suggestions(name)}")
            return
        if not _visible(spec, await self._is_owner(ctx)):
            await ctx.send(f"Rota desconhecida: `{name}`.")
            return

        await ctx.send(embed=_schema_embed(spec))

    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.command(
        name="jikan",
        brief="Chama qualquer rota da API do MyAnimeList.",
        description=(
            "Passa direto para a API do MyAnimeList. Use `!jikan --list` para "
            "ver as rotas e `!jikan --schema <rota>` para ver os parâmetros."
        ),
        usage="jikan <rota> [chave=valor ...] | jikan --list [grupo] | jikan --schema <rota>",
        aliases=["api"],
    )
    async def jikan_command(self, ctx: commands.Context, *, argument: str = "") -> None:
        text = argument.strip()
        if not text:
            await ctx.send(USAGE)
            return

        head, _, tail = text.partition(" ")
        if head in ("--list", "-l"):
            await self._list(ctx, tail)
            return
        if head in ("--schema", "-s"):
            await self._schema(ctx, tail)
            return

        spec = specs_by_route().get(head) or specs_by_route().get(f"get_{head}")
        if spec is None:
            await ctx.send(f"Rota desconhecida: `{head}`.{_suggestions(head)}")
            return
        if not _visible(spec, await self._is_owner(ctx)):
            await ctx.send(f"Rota desconhecida: `{head}`.")
            return

        try:
            kwargs = parse_arguments(spec, tail)
        except JikanArgumentError as exc:
            await ctx.send(str(exc))
            return

        await execute_route(self, ctx, spec, kwargs)


async def setup(bot: Client):
    await bot.add_cog(JikanCog(bot))
