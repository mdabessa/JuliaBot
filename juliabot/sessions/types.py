"""Value types shared by the session framework.

This module defines the framework vocabulary without importing Discord, so
registrations and lifecycle tests can run independently of the bot runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Union

JSONValue = Union[
    None,
    bool,
    int,
    float,
    str,
    list["JSONValue"],
    dict[str, "JSONValue"],
]


class TriggerType(str, Enum):
    """Event families that can start or continue a session."""

    MESSAGE = "message"
    REACTION = "reaction"
    COMPONENT = "component"


class Scope(str, Enum):
    """The context used to limit registrations and live sessions."""

    NONE = "none"
    USER = "user"
    GUILD = "guild"
    CHANNEL = "channel"


@dataclass(frozen=True)
class Action:
    """An operation exposed by a session.

    ``owner_only=None`` means that the registration's default applies. A
    session pattern can override that default for individual operations, such
    as allowing everyone to turn a pagination page while restricting deletion.
    """

    name: str
    handler: str
    owner_only: bool | None = None
    label: str | None = None
    emoji: str | None = None
    style: str | None = None


@dataclass(frozen=True)
class InteractionEvent:
    """Normalized input passed from a transport to the session manager."""

    transport: TriggerType
    key: str
    user_id: int | None = None
    action: str | None = None
    guild_id: int | None = None
    channel_id: int | None = None
    message_id: int | None = None
    raw: object | None = None
