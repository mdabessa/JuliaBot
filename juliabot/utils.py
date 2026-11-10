"""Utility functions for command prefix resolution and the run heartbeat.

This module provides helpers to fetch the appropriate command prefix based on
server configuration, and to store/read the heartbeat a running instance leaves
in the database.
"""

from __future__ import annotations

import datetime

import pytz
from discord import Message
from discord.ext.commands import Bot

from .config import PREFIX
from .models import BotConfig, Server, as_utc

HEARTBEAT_KEY = "heartbeat"
# Legacy heartbeat format: a local wall clock without an offset.
LEGACY_HEARTBEAT_FORMAT = "%d/%m/%Y %H:%M:%S"


def get_prefix(bot: Bot, message: Message) -> str:
    """Resolve the command prefix for a message.

    Args:
        bot (discord.ext.commands.Bot): The bot instance.
        message (discord.Message): The message being processed.

    Returns:
        str: Server-specific prefix if in a guild; default PREFIX otherwise.
    """
    if message.guild:
        server = Server.get_or_create(str(message.guild.id))
        server.update()

        return server.prefix
    else:
        return PREFIX


def parse_heartbeat(value: str) -> datetime.datetime | None:
    """Parse a stored heartbeat into an aware UTC timestamp.

    ISO-8601 values carry their own offset. The legacy format is a local wall
    clock, so it is read as UTC — the same assumption the rest of the database
    makes during the transition.

    Args:
        value (str): Stored heartbeat value.

    Returns:
        datetime.datetime | None: The instant, or None when unreadable.
    """
    text = (value or "").strip()
    if not text:
        return None

    try:
        stamp = datetime.datetime.fromisoformat(text)
    except ValueError:
        try:
            stamp = datetime.datetime.strptime(text, LEGACY_HEARTBEAT_FORMAT)
        except ValueError:
            return None

    return as_utc(stamp)


def get_heartbeat_age(now: datetime.datetime | None = None) -> float | None:
    """Return how long ago the heartbeat was written, in seconds.

    Args:
        now (datetime.datetime, optional): Reference instant. Defaults to the
            current UTC time.

    Returns:
        float | None: Age in seconds, or None when there is no readable
        heartbeat.
    """
    entry = BotConfig.get(HEARTBEAT_KEY)
    if entry is None:
        return None

    stamp = parse_heartbeat(entry.value)
    if stamp is None:
        return None

    reference = as_utc(now) if now is not None else datetime.datetime.now(pytz.utc)

    return (reference - stamp).total_seconds()


def write_heartbeat(now: datetime.datetime | None = None) -> None:
    """Store the current instant as an ISO-8601 UTC heartbeat.

    Args:
        now (datetime.datetime, optional): Instant to store. Defaults to the
            current UTC time.
    """
    stamp = as_utc(now) if now is not None else datetime.datetime.now(pytz.utc)
    value = stamp.isoformat()

    entry = BotConfig.get(HEARTBEAT_KEY)
    if entry is None:
        BotConfig(HEARTBEAT_KEY, value)
        return

    entry.value = value
    entry.update()
