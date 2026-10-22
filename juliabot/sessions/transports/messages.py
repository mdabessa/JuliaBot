"""Message transport boundary for future message-triggered sessions.

Phase 2 deliberately does not start sessions from messages. Phase 7 adds
message-rule registrations; keeping this adapter now gives the bot one stable
transport boundary without adding a per-message store query.
"""

from __future__ import annotations

from discord import Message

from ..manager import SessionManager
from ..types import InteractionEvent, TriggerType


class MessageTransport:
    """Normalize message context while message rules are not yet enabled."""

    def __init__(self, manager: SessionManager):
        self.manager = manager

    def event(self, message: Message) -> InteractionEvent:
        """Build the normalized event that Phase 7 rules will consume."""
        return InteractionEvent(
            transport=TriggerType.MESSAGE,
            key=str(message.id),
            user_id=getattr(message.author, "id", None),
            guild_id=getattr(getattr(message, "guild", None), "id", None),
            channel_id=getattr(getattr(message, "channel", None), "id", None),
            message_id=message.id,
            raw=message,
        )

    async def dispatch(self, message: Message) -> bool:
        """Ignore messages until message-rule registrations are implemented."""
        self.event(message)
        return False
