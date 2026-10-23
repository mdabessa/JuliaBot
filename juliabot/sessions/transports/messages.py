"""Message transport for channel message rules.

Every human message is delivered to the rules indexed for its channel. The
transport performs no store access: rules are either live in RAM or
materialized once from the boot-time key index.
"""

from __future__ import annotations

from discord import Message

from ..manager import SessionManager
from ..types import InteractionEvent, TriggerType


class MessageTransport:
    """Normalize message context and deliver it to channel rules."""

    def __init__(self, manager: SessionManager):
        self.manager = manager

    def event(self, message: Message) -> InteractionEvent:
        """Build the normalized event consumed by message rules."""
        return InteractionEvent(
            transport=TriggerType.MESSAGE,
            key=str(message.id),
            user_id=getattr(message.author, "id", None),
            guild_id=getattr(getattr(message, "guild", None), "id", None),
            channel_id=getattr(getattr(message, "channel", None), "id", None),
            message_id=message.id,
            raw=message,
        )

    async def dispatch(self, message: Message) -> int:
        """Deliver a human message to the rules for its channel.

        Returns how many rules handled it. Bot messages are ignored so a rule
        reacting with its own message cannot loop.
        """
        if getattr(message.author, "bot", False):
            return 0
        return await self.manager.dispatch_message(self.event(message))
