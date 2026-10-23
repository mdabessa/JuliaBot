"""Session patterns driven by channel messages instead of component clicks.

Message rules are long-lived sessions indexed per channel. They are evaluated in
constant time per message: the manager keeps one bucket per channel plus a
global bucket, so a busy channel never scans unrelated rules.
"""

from __future__ import annotations

from ..session import Session
from ..transports.buttons import build_button_view
from ..types import Action, InteractionEvent


class MessageRuleSession(Session):
    """Long-lived session that reacts to messages matching its filter."""

    def matches(self, event: InteractionEvent) -> bool:
        """Return whether this rule applies to the message."""
        return True

    async def on_message(self, event: InteractionEvent) -> bool:
        """Match the message and delegate to ``handle``."""
        if not self.matches(event):
            return False
        return await self.handle(event)

    async def handle(self, event: InteractionEvent) -> bool:
        """Handle a matching message; concrete rules must implement it."""
        raise NotImplementedError


class ChannelEntryPointRule(MessageRuleSession):
    """Durable per-channel interaction with an anchor message.

    The rule stays alive across restarts and receives every human message in its
    channel. Concrete products override :meth:`on_channel_message`; the base
    implementation only owns the anchor message and the disable action.
    """

    anchor_text = "Este canal possui uma interação permanente."
    disabled_text = "Interação desativada."
    actions = (
        Action(
            "disable",
            "disable",
            owner_only=True,
            label="Desativar",
            style="danger",
        ),
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._anchor = None

    async def start(self, event: InteractionEvent) -> None:
        """Send the anchor message and remember it for later updates."""
        context = event.raw
        channel = getattr(context, "channel", None)
        if channel is None or self.manager is None:
            raise RuntimeError(
                "ChannelEntryPointRule requires a channel context and manager"
            )

        self._anchor = await channel.send(
            content=self.anchor_text,
            view=build_button_view(self.manager, self),
        )
        anchor_id = getattr(self._anchor, "id", None)
        if anchor_id is not None:
            self.set_payload("anchor_message_id", anchor_id)

    async def handle(self, event: InteractionEvent) -> bool:
        """Forward the message to the product hook."""
        return await self.on_channel_message(event)

    async def on_channel_message(self, event: InteractionEvent) -> bool:
        """Product hook for a channel message; the base performs no action."""
        return False

    async def disable(self, event: InteractionEvent) -> None:
        """Remove the anchor controls and close the rule."""
        if self._anchor is not None:
            await self._anchor.edit(content=self.disabled_text, view=None)
        await self.close()
