"""Reusable state and actions for paginated Discord interactions.

The pattern keeps the current index in the session payload while treating the
items, message, and client objects as transient runtime state. Concrete
sessions provide item loading, rendering, and mutation hooks.
"""

from __future__ import annotations

from typing import Generic, Sequence, TypeVar

from ..session import Session
from ..transports.buttons import build_button_view
from ..types import Action, InteractionEvent, JSONValue

Item = TypeVar("Item")


class PaginationSession(Session, Generic[Item]):
    """Manage navigation through a mutable sequence of items."""

    extra_actions: tuple[Action, ...] = ()
    empty_message = "Não há itens para exibir."

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._items: list[Item] = []
        self._message = None

    @property
    def actions(self) -> tuple[Action, ...]:
        """Return open navigation actions followed by pattern extensions."""
        return (
            Action("previous", "previous_page", owner_only=False, label="Anterior"),
            Action("next", "next_page", owner_only=False, label="Próximo"),
            *self.extra_actions,
        )

    @property
    def index(self) -> int:
        """Return the current page index from the typed payload boundary."""
        value = self._payload.get("index", 0)
        return int(value) if isinstance(value, (int, float)) else 0

    @property
    def items(self) -> tuple[Item, ...]:
        """Return a read-only view of currently loaded items."""
        return tuple(self._items)

    async def load_items(self) -> Sequence[Item]:
        """Load the current item sequence; concrete sessions must implement it."""
        raise NotImplementedError

    async def render_item(self, item: Item, index: int, total: int):
        """Build the Discord content for one page."""
        raise NotImplementedError

    async def delete_item(self, item: Item, event: InteractionEvent) -> None:
        """Delete an item from its backing store; optional for read-only pages."""
        raise NotImplementedError

    async def start(self, event: InteractionEvent) -> None:
        """Load items and send the first page with a persistent button view."""
        self._items = list(await self.load_items())
        if not self._items:
            await self.close()
            return

        self.set_payload("index", self._normalise_index(self.index))
        context = event.raw
        if context is None or self.manager is None:
            raise RuntimeError("PaginationSession requires a manager and event context")
        embed = await self.render_item(
            self._items[self.index], self.index, len(self._items)
        )
        self._message = await context.reply(
            embed=embed,
            view=build_button_view(self.manager, self),
        )

    async def hydrate(self) -> None:
        """Reload transient items after a future persisted restore."""
        self._items = list(await self.load_items())
        self.set_payload("index", self._normalise_index(self.index))

    async def previous_page(self, event: InteractionEvent) -> None:
        """Move to the previous page and render it."""
        if not self._items:
            await self.close()
            return
        self.set_payload("index", self._normalise_index(self.index - 1))
        await self.render()

    async def next_page(self, event: InteractionEvent) -> None:
        """Move to the next page and render it."""
        if not self._items:
            await self.close()
            return
        self.set_payload("index", self._normalise_index(self.index + 1))
        await self.render()

    async def delete_current(self, event: InteractionEvent) -> None:
        """Delete the current item and render the remaining list."""
        if not self._items:
            await self.close()
            return
        item = self._items[self.index]
        await self.delete_item(item, event)
        self._items.pop(self.index)
        if not self._items:
            if self._message is not None:
                await self._message.edit(content=self.empty_message, embed=None)
            await self.close()
            return
        self.set_payload("index", self._normalise_index(self.index))
        await self.render()

    async def render(self) -> None:
        """Render the current item when a live Discord message exists."""
        if self._message is None or not self._items:
            return
        embed = await self.render_item(
            self._items[self.index], self.index, len(self._items)
        )
        await self._message.edit(embed=embed)

    async def refresh_items(self) -> None:
        """Reload items and render the current page when possible."""
        self._items = list(await self.load_items())
        if not self._items:
            await self.close()
            return
        self.set_payload("index", self._normalise_index(self.index))
        await self.render()

    async def append_item(self, item: Item) -> None:
        """Append an item and render it if the session was previously empty."""
        was_empty = not self._items
        self._items.append(item)
        if was_empty:
            self.set_payload("index", 0)
        await self.render()

    def _normalise_index(self, index: int) -> int:
        """Wrap an index around the currently loaded sequence."""
        if not self._items:
            return 0
        return index % len(self._items)

    def to_payload(self) -> dict[str, JSONValue]:
        """Return only serializable pagination state."""
        return {"index": self.index}
