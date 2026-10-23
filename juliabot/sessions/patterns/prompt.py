"""Reusable prompt/confirmation sessions driven by a declarative choice map.

A prompt owns a single message whose buttons are derived from ``choices``.
Concrete sessions provide the prompt text and the outcome handling; there is no
hardcoded emoji or yes/no branching in the pattern itself.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..session import Session
from ..transports.buttons import build_button_view
from ..types import Action, InteractionEvent


@dataclass(frozen=True)
class PromptChoice:
    """Describe one selectable answer in a prompt."""

    label: str
    emoji: str | None = None
    style: str | None = None
    owner_only: bool | None = None


class PromptSession(Session):
    """Ask a question through a fixed, declarative set of buttons."""

    choices: tuple[tuple[str, PromptChoice], ...] = ()

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._message = None

    @property
    def actions(self) -> tuple[Action, ...]:
        """Derive the session actions from the declared choices."""
        return tuple(
            Action(
                name,
                "handle_choice",
                owner_only=choice.owner_only,
                label=choice.label,
                emoji=choice.emoji,
                style=choice.style,
            )
            for name, choice in self.choices
        )

    async def render_prompt(self) -> str:
        """Return the prompt text; concrete sessions must implement it."""
        raise NotImplementedError

    def can_handle(self, choice: str, event: InteractionEvent) -> bool:
        """Return whether the acting user may pick ``choice``.

        The default allows anyone the action's ``owner_only`` policy already
        admitted. Sessions with asymmetric rules (for example "only the
        challenged user may accept") override this instead of encoding the
        rule in the action list.
        """
        return True

    async def on_choice(self, choice: str, event: InteractionEvent) -> None:
        """Handle the accepted choice; the prompt closes afterwards."""

    async def hydrate(self, event: InteractionEvent | None = None) -> None:
        """Reattach the original prompt message after a restore."""
        if self._message is None and event is not None:
            self._message = getattr(getattr(event, "raw", None), "message", None)

    async def start(self, event: InteractionEvent) -> None:
        """Send the prompt message with one persistent button per choice."""
        if not self.choices:
            raise RuntimeError("PromptSession requires at least one choice")
        context = event.raw
        if context is None or self.manager is None:
            raise RuntimeError("PromptSession requires a manager and event context")

        self._message = await context.channel.send(
            content=await self.render_prompt(),
            view=build_button_view(self.manager, self),
        )

    async def handle_choice(self, event: InteractionEvent) -> None:
        """Validate, handle, then close the prompt."""
        choice = event.action
        if choice is None or not self.can_handle(choice, event):
            return
        await self.on_choice(choice, event)
        await self.close()
