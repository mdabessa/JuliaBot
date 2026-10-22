"""Discord button transport for interactive sessions.

Buttons carry the session id in their custom id, so they remain routable
without a database lookup for unrelated component interactions. Views use
``timeout=None`` so they can be re-registered at boot in a later phase.
"""

from __future__ import annotations

from discord import ButtonStyle, Interaction
from discord.ui import Button, View

from ..manager import SessionManager
from ..session import Session
from ..types import Action, InteractionEvent, TriggerType

_CUSTOM_ID_PREFIX = "sess"


class SessionButton(Button):
    """One dynamic button that dispatches an action to a session manager."""

    def __init__(self, manager: SessionManager, session: Session, action: Action):
        self.manager = manager
        self.session_id = session.id
        self.action_name = action.name
        super().__init__(
            style=_button_style(action.style),
            label=action.label or action.name,
            emoji=action.emoji,
            custom_id=build_custom_id(session.id, action.name),
        )

    async def callback(self, interaction: Interaction) -> None:
        """Normalize and dispatch the Discord component interaction."""
        event = InteractionEvent(
            transport=TriggerType.COMPONENT,
            key=self.session_id,
            user_id=interaction.user.id,
            action=self.action_name,
            guild_id=getattr(interaction.guild, "id", None),
            channel_id=getattr(interaction.channel, "id", None),
            message_id=getattr(getattr(interaction, "message", None), "id", None),
            raw=interaction,
        )
        dispatched = await self.manager.dispatch(event)
        if _response_done(interaction):
            return

        if not dispatched and _is_owner_denied(self.manager, event):
            await interaction.response.send_message(
                "Você não pode usar esta ação.", ephemeral=True
            )
        else:
            await interaction.response.defer()


class SessionButtonView(View):
    """Persistent view containing all actions exposed by a session."""

    def __init__(self, manager: SessionManager, session: Session):
        super().__init__(timeout=None)
        for action in session.actions:
            self.add_item(SessionButton(manager, session, action))


def build_button_view(manager: SessionManager, session: Session) -> SessionButtonView:
    """Build a persistent button view for a live session."""
    return SessionButtonView(manager, session)


def build_custom_id(session_id: str, action_name: str) -> str:
    """Create the stable custom id used to route a button interaction."""
    custom_id = f"{_CUSTOM_ID_PREFIX}:{session_id}:{action_name}"
    if len(custom_id) > 100:
        raise ValueError("Button custom_id cannot exceed Discord's 100-character limit")
    return custom_id


def parse_custom_id(custom_id: str) -> tuple[str, str]:
    """Parse a session button id into session id and action name."""
    prefix, session_id, action_name = custom_id.split(":", 2)
    if prefix != _CUSTOM_ID_PREFIX or not session_id or not action_name:
        raise ValueError(f"Invalid session custom_id: {custom_id}")
    return session_id, action_name


def _button_style(style: str | None) -> ButtonStyle:
    """Map framework styles to Discord button styles."""
    return {
        "success": ButtonStyle.success,
        "danger": ButtonStyle.danger,
        "primary": ButtonStyle.primary,
        "secondary": ButtonStyle.secondary,
    }.get(style or "secondary", ButtonStyle.secondary)


def _response_done(interaction: Interaction) -> bool:
    """Return whether a component interaction has already been acknowledged."""
    return interaction.response.is_done()


def _is_owner_denied(manager: SessionManager, event: InteractionEvent) -> bool:
    """Distinguish authorization failures from unknown or invalid components."""
    session = manager.get(event.key)
    if session is None:
        return False
    action = next(
        (candidate for candidate in session.actions if candidate.name == event.action),
        None,
    )
    if action is None:
        return False
    owner_only = (
        session.registration.owner_only
        if action.owner_only is None
        else action.owner_only
    )
    return owner_only and event.user_id != session.owner_id
