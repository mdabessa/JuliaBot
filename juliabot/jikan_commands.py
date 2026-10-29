"""Build Discord commands from the Jikan route catalog.

One :class:`~discord.ext.commands.Command` is generated per route so the bot
follows the installed ``jikan4`` package instead of a hand-written command list.
The callback takes the whole argument tail as a single string and hands it to
:func:`~juliabot.jikan_args.parse_arguments`, so argument handling stays in one
tested place.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Iterable

from discord.ext import commands

from .jikan_args import JikanArgumentError, parse_arguments
from .jikan_catalog import RouteSpec

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 2000


def _dump_payload(payload: Any) -> str:
    """Serialize a route payload as JSON, tolerating pydantic v1 and v2."""
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump()
    elif hasattr(payload, "dict"):
        payload = payload.dict()
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def _split_message(text: str, limit: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Split a long text into messages without cutting lines needlessly."""
    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) > limit:
            chunks.append(current)
            current = line
        else:
            current += line
    if current:
        chunks.append(current)
    return chunks


async def send_raw_payload(ctx: commands.Context, payload: Any) -> None:
    """Send the payload as a fenced JSON block.

    This is the debug rendering path; the generic renderers replace it for the
    routes that have a nicer presentation.
    """
    body = f"```json\n{_dump_payload(payload)}\n```"
    for chunk in _split_message(body):
        await ctx.send(chunk)


def resolve_client(cog: commands.Cog):
    """Return the Jikan client shared through the bot, if one exists."""
    bot = getattr(cog, "bot", None)
    return getattr(bot, "jikan", None) or getattr(cog, "jikan", None)


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

        payload = await getattr(client, spec.route)(**kwargs)
        await send_raw_payload(ctx, payload)

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
