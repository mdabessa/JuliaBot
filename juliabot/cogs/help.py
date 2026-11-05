"""Help command cog with a paginated command listing.

``!help`` opens a one-embed category index: one line per cog, with a count and
the ``!help <cog>`` that opens it. Choosing a category renders that cog's
compact command grid (dense command names, grouped by cog) across as many pages
as its embed budget needs. Pages are computed once against the invoking context
and the session only navigates them. ``!help <command>`` keeps the one-shot
detail embed.
"""

import difflib
import logging
from dataclasses import dataclass
from typing import Iterable, Optional

from discord import Embed
from discord.ext import commands

from ..client import Client
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

logger = logging.getLogger(__name__)

HELP_PAGES = "help.pages"

PAGE_TITLE = "Lista de Comandos"
MAX_FIELDS_PER_PAGE = 25
MAX_FIELD_VALUE = 1024
MAX_DESCRIPTION = 4096
MAX_EMBED_LENGTH = 6000
# Title, description, and footer are reserved up front so a cog's fields can be
# packed against one value budget without re-measuring the whole embed.
EMBED_OVERHEAD = 256

# Page kinds: the index lists categories, a commands page lists one cog's grid.
PAGE_KIND_INDEX = "index"
PAGE_KIND_COMMANDS = "commands"
# Cogs without a ``help_section`` land in the main "Comandos" block, which is
# rendered first so hand-written commands stay one glance away.
MAIN_SECTION = ""
MAIN_SECTION_TITLE = "Comandos"


@dataclass(frozen=True)
class HelpPage:
    """One pre-built page of the compact command listing."""

    title: str
    description: str
    fields: tuple[tuple[str, str], ...]
    cogs: tuple[str, ...] = ()
    kind: str = PAGE_KIND_COMMANDS


@dataclass(frozen=True)
class CogEntry:
    """One cog as the category index needs to describe it."""

    name: str
    title: str
    section: str
    command_count: int


def _command_label(command: commands.Command) -> str:
    """Render one command as `` `name` (alias1, alias2) ``."""
    if not command.aliases:
        return f"`{command.name}`"
    aliases = ", ".join(command.aliases)
    return f"`{command.name}` ({aliases})"


def _cog_title(cog: commands.Cog, cog_name: str) -> str:
    """Return the display title for a cog, falling back to its registered name."""
    return getattr(cog, "embed_title", None) or cog_name


def _clip(token: str) -> str:
    """Keep a single command token inside Discord's per-value limit."""
    if len(token) <= MAX_FIELD_VALUE:
        return token
    logger.warning("Help entry exceeds %d characters; truncating", MAX_FIELD_VALUE)
    return token[: MAX_FIELD_VALUE - 1] + "…"


def _cog_fields(title: str, tokens: list[str]) -> list[tuple[str, str]]:
    """Turn one cog's command tokens into fields that fit the value limit.

    A cog that outgrows a single value spills into continuation fields instead
    of being cut off, so the listing stays complete no matter how many
    commands a cog grows.
    """
    chunks: list[str] = []
    current = ""
    for token in (_clip(token) for token in tokens):
        candidate = f"{current} {token}" if current else token
        if len(candidate) > MAX_FIELD_VALUE:
            chunks.append(current)
            current = token
        else:
            current = candidate
    if current:
        chunks.append(current)

    if len(chunks) <= 1:
        return [(title, chunks[0] if chunks else "")]
    return [
        (f"{title} ({position}/{len(chunks)})", chunk)
        for position, chunk in enumerate(chunks, start=1)
    ]


async def _visible_commands(
    cog: commands.Cog, ctx: commands.Context
) -> list[commands.Command]:
    """Return the commands of a cog the invoking user may run.

    ``Command.can_run`` already evaluates the owning cog's ``cog_check``, so
    owner-only cogs stay hidden for everyone else. Check failures are logged
    instead of silently dropping the command.
    """
    visible: list[commands.Command] = []
    for command in cog.walk_commands():
        if getattr(command, "hidden", False):
            continue
        try:
            if not await command.can_run(ctx):
                continue
        except Exception:
            logger.warning(
                "Skipping %s in the help listing",
                command.qualified_name,
                exc_info=True,
            )
            continue
        visible.append(command)
    return visible


def _section_of(cog: commands.Cog) -> str:
    """Return the index section a cog belongs to, defaulting to the main one.

    Read through ``getattr`` so the help cog never imports the Jikan subsystem
    just to learn which cogs are generated; a cog opts in by declaring a
    ``help_section`` class attribute, like it already declares ``embed_title``.
    """
    section = getattr(cog, "help_section", "")
    return section if isinstance(section, str) else ""


def _count_label(amount: int) -> str:
    """Render a command count with the right plural."""
    return f"{amount} comando" if amount == 1 else f"{amount} comandos"


def _chunk_fields(
    fields: list[tuple[str, str]], max_fields: int
) -> list[tuple[tuple[str, str], ...]]:
    """Pack one cog's fields into pages sized by Discord's embed budgets.

    A category page holds a single cog, so only the per-value and total embed
    budgets bound it: the page never splits because of how many other cogs
    exist.
    """
    char_budget = MAX_EMBED_LENGTH - EMBED_OVERHEAD
    pages: list[tuple[tuple[str, str], ...]] = []
    current: list[tuple[str, str]] = []
    used = 0

    for field in fields:
        cost = len(field[0]) + len(field[1])
        if current and (len(current) >= max_fields or used + cost > char_budget):
            pages.append(tuple(current))
            current, used = [], 0
        current.append(field)
        used += cost

    if current:
        pages.append(tuple(current))
    return pages


async def collect_cogs(ctx: commands.Context) -> list[CogEntry]:
    """Describe every cog the invoking user can see, in registration order.

    Counts come from :func:`_visible_commands` rather than ``get_commands`` so
    an owner-only cog reports nothing to everyone else and disappears from the
    index entirely.
    """
    bot = getattr(ctx, "bot", None)
    cogs = getattr(bot, "cogs", {}) or {}

    entries: list[CogEntry] = []
    for cog_name, cog in cogs.items():
        visible = await _visible_commands(cog, ctx)
        if not visible:
            continue
        entries.append(
            CogEntry(
                name=cog_name,
                title=_cog_title(cog, cog_name),
                section=_section_of(cog),
                command_count=len(visible),
            )
        )
    return entries


def _index_lines(entries: list[CogEntry], prefix: str) -> list[tuple[str, str]]:
    """Render the index as ``(line, cog name)`` pairs, grouped by section.

    Block headers and the blank separator between blocks carry no cog name, so
    callers can collect the cogs of one page without re-parsing the text.
    """
    sections: dict[str, list[CogEntry]] = {}
    for entry in entries:
        sections.setdefault(entry.section, []).append(entry)

    order = [MAIN_SECTION] if MAIN_SECTION in sections else []
    order.extend(section for section in sections if section != MAIN_SECTION)

    lines: list[tuple[str, str]] = []
    for position, section in enumerate(order):
        if position:
            lines.append(("", ""))
        header = MAIN_SECTION_TITLE if section == MAIN_SECTION else section
        lines.append((f"**{header}**", ""))
        for entry in sections[section]:
            line = (
                f"{entry.title} — {_count_label(entry.command_count)} · "
                f"`{prefix}help {entry.name}`"
            )
            lines.append((line, entry.name))
    return lines


def _chunk_index(
    lines: list[tuple[str, str]], budget: int
) -> list[list[tuple[str, str]]]:
    """Pack index lines into description-sized pages."""
    chunks: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    used = 0

    for line, cog_name in lines:
        cost = len(line) + 1
        if current and used + cost > budget:
            chunks.append(current)
            current, used = [], 0
        current.append((line, cog_name))
        used += cost

    if current:
        chunks.append(current)
    return chunks


async def build_help_index(ctx: commands.Context, prefix: str = "!") -> list[HelpPage]:
    """Build the category index: one line per cog, grouped by section.

    The index is a description list rather than a field grid so its size tracks
    the number of cogs, not the number of commands behind them.
    """
    entries = await collect_cogs(ctx)
    if not entries:
        return []

    hint = (
        f"`{prefix}help comando` para detalhes · "
        f"`{prefix}help categoria` para abrir."
    )
    lines = _index_lines(entries, prefix)
    chunks = _chunk_index(lines, MAX_DESCRIPTION - len(hint) - 1)

    pages: list[HelpPage] = []
    for position, chunk in enumerate(chunks):
        description = "\n".join(line for line, _ in chunk).strip("\n")
        if position == len(chunks) - 1:
            description = f"{description}\n{hint}"
        pages.append(
            HelpPage(
                title=(
                    PAGE_TITLE
                    if len(chunks) == 1
                    else f"{PAGE_TITLE} ({position + 1}/{len(chunks)})"
                ),
                description=description,
                fields=(),
                cogs=tuple(name for _, name in chunk if name),
                kind=PAGE_KIND_INDEX,
            )
        )
    return pages


async def build_cog_pages(
    ctx: commands.Context, prefix: str = "!", cog_name: str = ""
) -> list[HelpPage]:
    """Build the command pages of a single cog, with no cog-count cap."""
    bot = getattr(ctx, "bot", None)
    cogs = getattr(bot, "cogs", {}) or {}
    cog = cogs.get(cog_name)
    if cog is None:
        return []

    visible = await _visible_commands(cog, ctx)
    if not visible:
        return []

    title = _cog_title(cog, cog_name)
    fields = _cog_fields(title, [_command_label(command) for command in visible])
    description = f"{prefix}help comando para detalhes"

    return [
        HelpPage(
            title=title,
            description=description,
            fields=chunk,
            cogs=(cog_name,),
            kind=PAGE_KIND_COMMANDS,
        )
        for chunk in _chunk_fields(fields, MAX_FIELDS_PER_PAGE)
    ]


async def _candidate_labels(ctx: commands.Context) -> list[str]:
    """Collect the labels a suggestion may point at; never raises.

    Suggestions are best effort: an unknown argument must still get its plain
    "not found" answer when the cog tree cannot be walked, so a structural
    failure degrades to an empty pool instead of failing the command.
    """
    bot = getattr(ctx, "bot", None)
    cogs = getattr(bot, "cogs", {}) or {}

    labels: list[str] = []
    try:
        for cog_name, cog in cogs.items():
            labels.append(cog_name)
            labels.append(_cog_title(cog, cog_name))
            for command in await _visible_commands(cog, ctx):
                labels.append(command.name)
                labels.extend(command.aliases)
    except Exception:
        logger.warning("Could not build help suggestions", exc_info=True)
        return []

    # A cog without an ``embed_title`` contributes its name twice.
    return list(dict.fromkeys(labels))


def _suggestions(labels: Iterable[str], query: str) -> str:
    """Return a "did you mean" suffix for an unknown help argument."""
    if not query:
        return ""
    matches = difflib.get_close_matches(query, list(labels), n=3, cutoff=0.6)
    if not matches:
        return ""
    rendered = ", ".join(f"`{name}`" for name in matches)
    return f" Talvez você quis dizer: {rendered}."


async def resolve_prefix(context) -> str:
    """Return the command prefix for a command context or an interaction."""
    prefix = getattr(context, "prefix", None)
    if isinstance(prefix, str) and prefix:
        return prefix

    bot = getattr(context, "bot", None) or getattr(context, "client", None)
    get_prefix = getattr(bot, "get_prefix", None)
    if get_prefix is None:
        return "!"
    value = await get_prefix(getattr(context, "message", None))
    if isinstance(value, (list, tuple)):
        value = value[0] if value else "!"
    return value if isinstance(value, str) and value else "!"


class HelpPagination(PaginationSession[HelpPage]):
    """Navigate the help levels of one channel: the index, or one cog's grid."""

    extra_actions = (
        Action("index", "show_index", owner_only=False, label="Categorias"),
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._context = None
        self._color = 0

    @property
    def requested_cog(self) -> str:
        """Return the cog a ``!help !<cog>`` invocation asked to jump to."""
        value = self._payload.get("cog", "")
        return value if isinstance(value, str) else ""

    async def start(self, event: InteractionEvent) -> None:
        """Capture the invoking context before the first page renders."""
        context = event.raw
        if context is None:
            raise RuntimeError("Help sessions require an invoking context")
        self._bind_runtime(context)
        await super().start(event)

    async def hydrate(self, event: InteractionEvent | None = None) -> None:
        """Recover the invoking context on a restored interaction."""
        if event is not None and self._context is None:
            self._bind_runtime(event.raw)
        await super().hydrate(event)

    def _bind_runtime(self, context) -> None:
        """Store the context and the embed color used to render pages."""
        self._context = context
        bot = getattr(context, "bot", None) or getattr(context, "client", None)
        self._color = getattr(bot, "color", 0)

    async def load_items(self) -> list[HelpPage]:
        """Build the pages of the current level: the index or one cog's grid.

        The ``cog`` payload key doubles as the level selector: empty renders the
        category index, a cog name renders that cog's command pages.
        """
        prefix = await resolve_prefix(self._context)
        cog_name = self.requested_cog
        if not cog_name:
            return await build_help_index(self._context, prefix)
        return await build_cog_pages(self._context, prefix, cog_name)

    async def show_index(self, event: InteractionEvent) -> None:
        """Return to the category index without leaving the session.

        Switching level in place is what keeps the index reachable: starting a
        second session would trip ``max_per_scope=1`` and drop the one on
        screen, leaving only a dead message behind.
        """
        if not self.requested_cog:
            await self.render()
            return
        self.set_payload("cog", "")
        self.set_payload("index", 0)
        await self._reload()

    async def _reload(self) -> None:
        """Rebuild the items after a level switch and redraw the page."""
        self._items = list(await self.load_items())
        if not self._items:
            await self.close()
            return
        self.set_payload("index", self._normalise_index(self.index))
        await self.render()

    async def render_item(self, item: HelpPage, index: int, total: int):
        """Render one page: a category menu, or a numbered command listing."""
        embed = Embed(title=item.title, description=item.description, color=self._color)
        for name, value in item.fields:
            embed.add_field(name=name, value=value, inline=True)
        if item.kind != PAGE_KIND_INDEX:
            embed.set_footer(text=f"Página {index + 1}/{total}")
        return embed


class HelpCog(commands.Cog, name="help"):
    """Help and command documentation.

        Provides help information for commands and cog categories with
    declarative formatting.
    """

    embed_title = ":question:Help."

    def __init__(self, bot: Client) -> None:
        self.bot = bot
        if not hasattr(bot, "sessions"):
            bot.sessions = SessionManager(Registry())
        if bot.sessions.registry.get(HELP_PAGES) is None:
            bot.sessions.registry.register(
                Registration(
                    name=HELP_PAGES,
                    session_class=HelpPagination,
                    trigger=TriggerType.COMPONENT,
                    scope=Scope.CHANNEL,
                    timeout=120,
                    max_per_scope=1,
                    resumable=False,
                )
            )

    @staticmethod
    def _session_event(ctx: commands.Context) -> InteractionEvent:
        """Build a normalized interaction event from a command invocation."""
        return InteractionEvent(
            transport=TriggerType.COMPONENT,
            key=str(ctx.message.id),
            user_id=ctx.author.id,
            guild_id=getattr(ctx.guild, "id", None),
            channel_id=getattr(ctx.channel, "id", None),
            message_id=ctx.message.id,
            raw=ctx,
        )

    def _command_embed(self, prefix: str, command: commands.Command) -> Embed:
        """Build the one-shot detail embed for a single command."""
        desc = command.help if command.help is not None else command.brief
        embed = Embed(title=f"{prefix}{command.name}", color=self.bot.color)
        embed.add_field(name="Descrição:", value=desc, inline=False)
        if command.aliases:
            embed.add_field(
                name="Aliases:",
                value=" ".join([f"`{x}`" for x in command.aliases]),
                inline=False,
            )
        embed.add_field(
            name="Exemplo:",
            value=f"{prefix}{command.name} {command.signature}",
            inline=False,
        )
        return embed

    async def _start_pages(
        self, ctx: commands.Context, cog_name: Optional[str] = None
    ) -> None:
        """Start the session, on the index or on one cog's level."""
        payload = {"index": 0}
        if cog_name:
            payload["cog"] = cog_name
        session = await self.bot.sessions.start(
            HELP_PAGES, self._session_event(ctx), payload=payload
        )
        if session.closed:
            # A category can close on start when every command in it is
            # hidden or fails ``can_run``; say which one, not just "nothing".
            reason = (
                f"Nenhum comando disponível em `{cog_name}`."
                if cog_name
                else "Nenhum comando disponível."
            )
            await ctx.send(reason)

    @commands.command(brief="Ajuda", aliases=["ajuda"])
    async def help(self, ctx: commands.Context, argument: Optional[str] = None):
        prefix = await resolve_prefix(ctx)

        if argument is None:
            await self._start_pages(ctx)
            return

        # ``!help !<cog>`` jumps to a cog page without shadowing command names.
        jump = argument.startswith("!")
        name = argument[1:] if jump else argument

        command = None if jump else self.bot.get_command(name)
        if command is not None:
            await ctx.send(embed=self._command_embed(prefix, command))
            return

        if name and self.bot.get_cog(name) is not None:
            await self._start_pages(ctx, cog_name=name)
            return

        suggestions = _suggestions(await _candidate_labels(ctx), name)
        await ctx.send(
            f"Nenhum comando/categoria encontrado com o nome de `{argument}`!"
            f"{suggestions}"
        )


async def setup(bot: Client):
    await bot.add_cog(HelpCog(bot))
