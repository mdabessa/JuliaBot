"""Legacy Discord reaction transport for existing sessions."""

from __future__ import annotations

from discord import Reaction, User

from ..manager import SessionManager
from ..types import InteractionEvent, TriggerType


class ReactionTransport:
    """Translate reaction events into session actions without database reads."""

    def __init__(self, manager: SessionManager):
        self.manager = manager

    async def dispatch(self, reaction: Reaction, user: User) -> bool:
        """Dispatch a reaction to the session attached to its message."""
        if getattr(user, "bot", False):
            return False

        message = reaction.message
        session = self.manager.get(str(message.id))
        if session is None:
            return False

        emoji = str(reaction.emoji)
        action = next(
            (candidate for candidate in session.actions if candidate.emoji == emoji),
            None,
        )
        if action is None:
            return False

        event = InteractionEvent(
            transport=TriggerType.REACTION,
            key=str(message.id),
            user_id=user.id,
            action=action.name,
            guild_id=getattr(getattr(message, "guild", None), "id", None),
            channel_id=getattr(getattr(message, "channel", None), "id", None),
            message_id=message.id,
            raw=reaction,
        )
        return await self.manager.dispatch(event)
