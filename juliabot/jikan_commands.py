"""Build Discord commands from the Jikan route catalog.

One :class:`~discord.ext.commands.Command` is generated per route so the bot
follows the installed ``jikan4`` package instead of a hand-written command list.
The callback takes the whole argument tail as a single string and hands it to
:func:`~juliabot.jikan_args.parse_arguments`, so argument handling stays in one
tested place.
"""

from __future__ import annotations

import logging
from typing import Iterable

from discord.ext import commands

from .jikan_args import JikanArgumentError, parse_arguments
from .jikan_catalog import RouteSpec
from .jikan_errors import JikanCallError, call_route
from .jikan_render import RenderResult, render

logger = logging.getLogger(__name__)


async def send_rendered(ctx: commands.Context, result: RenderResult) -> None:
    """Send one rendered result as a single Discord message."""
    if result.file is not None:
        await ctx.send(content=result.content, file=result.file)
        return
    if result.embeds:
        await ctx.send(content=result.content, embeds=list(result.embeds))
        return
    if result.content is not None:
        await ctx.send(content=result.content)


def resolve_client(cog: commands.Cog):
    """Return the Jikan client shared through the bot, if one exists."""
    bot = getattr(cog, "bot", None)
    return getattr(bot, "jikan", None) or getattr(cog, "jikan", None)


def _color_of(cog: commands.Cog) -> int:
    return getattr(getattr(cog, "bot", None), "color", 0)


def build_command(cog: commands.Cog, spec: RouteSpec) -> commands.Command:
    """Build the command that exposes one route."""

    async def _dispatch(command_cog, ctx: commands.Context, *, raw: str = "") -> None:
        try:
            kwargs = parse_arguments(spec, raw)
        except JikanArgumentError as exc:
            await ctx.send(str(exc))
            return

        client = resolve_client(command_cog)
        if client is None:
            await ctx.send("O cliente da API de animes não está disponível.")
            return

        try:
            payload = await call_route(client, spec, kwargs)
        except JikanCallError as exc:
            await ctx.send(str(exc))
            return

        await send_rendered(ctx, render(payload, spec, _color_of(command_cog)))

    _dispatch.__name__ = spec.name
    # A cog command is invoked as ``callback(cog, ctx, ...)``; the qualified
    # name tells discord.py to skip both leading parameters when it inspects
    # the signature, leaving only ``raw``.
    _dispatch.__qualname__ = f"{type(cog).__name__}.{spec.name}"
    _dispatch.__doc__ = spec.description

    callback = commands.cooldown(*spec.cooldown, commands.BucketType.user)(_dispatch)
    return commands.Command(
        callback,
        name=spec.name,
        aliases=list(spec.aliases),
        brief=spec.brief,
        description=spec.description,
        usage=spec.usage,
        hidden=spec.hidden,
        extras={"route": spec.route},
    )


def _conflict(command: commands.Command, cog: commands.Cog, taken: set[str]):
    """Return the label that blocks this command, if any."""
    for label in (command.name, *command.aliases):
        if label in taken:
            return f"`{label}` was already generated"
        get_command = getattr(getattr(cog, "bot", None), "get_command", None)
        if get_command is not None and get_command(label) is not None:
            return f"`{label}` is already used by another command"
    return None


def build_commands(
    cog: commands.Cog,
    specs: Iterable[RouteSpec],
    allowlist: Iterable[str] | None = None,
) -> tuple[commands.Command, ...]:
    """Build the commands of ``specs``, skipping curated and colliding routes.

    A name clash is logged and skipped instead of raised: ``Cog._inject`` rolls
    back the whole cog when a registration fails, so one bad alias must never
    take the other commands down with it.
    """
    allowed = None if allowlist is None else set(allowlist)
    taken: set[str] = set()
    built: list[commands.Command] = []

    for spec in specs:
        if spec.curated:
            continue
        if allowed is not None and spec.route not in allowed:
            continue

        command = build_command(cog, spec)
        conflict = _conflict(command, cog, taken)
        if conflict is not None:
            logger.warning("Skipping generated command %s: %s", spec.name, conflict)
            continue

        taken.update((command.name, *command.aliases))
        built.append(command)

    return tuple(built)
