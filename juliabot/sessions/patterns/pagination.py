"""Reusable state and actions for paginated Discord interactions.

The pattern keeps the current index in the session payload while treating the
items, message, and client objects as transient runtime state. Concrete
sessions provide item loading, rendering, and mutation hooks.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Generic, Sequence, TypeVar

from discord.errors import HTTPException

from ..session import Session
from ..transports.buttons import build_button_view
from ..types import Action, InteractionEvent, JSONValue

Item = TypeVar("Item")


class PaginationSession(Session, Generic[Item]):
    """Manage navigation through a mutable sequence of items."""

    extra_actions: tuple[Action, ...] = ()
    empty_message = "Não há itens para exibir."
    loading_message = "Carregando..."
    progressive = False

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._items: list[Item] = []
        self._message = None
        self._loading_task: asyncio.Task | None = None

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

    async def delete_item(self, item: Item, event: InteractionEvent) -> bool:
        """Delete an item from its backing store, optionally refusing.

        Return ``True`` when the item was removed so the pattern can drop it
        from the current page. Return ``False`` to keep it, for example when
        the acting user does not own the entry.
        """
        raise NotImplementedError

    async def iter_items(self) -> AsyncIterator[Item]:
        """Yield items to load; override to load progressively."""
        for item in await self.load_items():
            yield item

    async def load_more(self, direction: int) -> bool:
        """Load an adjacent remote page when navigation hits a boundary.

        Return ``True`` when the page was replaced; the pattern then stops
        handling that navigation. The default keeps local wrap-around.
        """
        return False

    async def on_loading_finished(self) -> None:
        """Hook called after progressive loading fills the page."""

    async def start(self, event: InteractionEvent) -> None:
        """Send the first page and start progressive loading when configured."""
        if not self.progressive:
            self._items = list(await self.load_items())
            if not self._items:
                await self.close()
                return

        self.set_payload("index", self._normalise_index(self.index))
        context = event.raw
        if context is None or self.manager is None:
            raise RuntimeError("PaginationSession requires a manager and event context")

        view = build_button_view(self.manager, self)
        if self._items:
            embed = await self.render_item(
                self._items[self.index], self.index, len(self._items)
            )
            self._message = await context.reply(embed=embed, view=view)
        else:
            self._message = await context.reply(content=self.loading_message, view=view)

        if self.progressive:
            self._loading_task = asyncio.create_task(self._consume_progressive())

    async def hydrate(self, event: InteractionEvent | None = None) -> None:
        """Reload transient items and reattach the original Discord message."""
        self._items = list(await self.load_items())
        self.set_payload("index", self._normalise_index(self.index))
        if self._message is None and event is not None:
            self._message = getattr(getattr(event, "raw", None), "message", None)

    async def previous_page(self, event: InteractionEvent) -> None:
        """Move to the previous page, loading the previous remote page first."""
        if not self._items:
            await self.close()
            return
        if self.index == 0 and await self.load_more(-1):
            return
        self.set_payload("index", self._normalise_index(self.index - 1))
        await self.render()

    async def next_page(self, event: InteractionEvent) -> None:
        """Move to the next page, loading the next remote page first."""
        if not self._items:
            await self.close()
            return
        if self.index + 1 >= len(self._items) and await self.load_more(1):
            return
        self.set_payload("index", self._normalise_index(self.index + 1))
        await self.render()

    async def delete_current(self, event: InteractionEvent) -> None:
        """Delete the current item and render the remaining list."""
        if not self._items:
            await self.close()
            return
        item = self._items[self.index]
        if not await self.delete_item(item, event):
            return
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
        await self._message.edit(content=None, embed=embed)

    async def wait_for_loading(self) -> None:
        """Wait for progressive loading to finish, if it is running."""
        task = self._loading_task
        if task is not None and not task.done():
            await asyncio.shield(task)

    async def _consume_progressive(self) -> None:
        """Append progressively loaded items and finalize the page."""
        try:
            async for item in self.iter_items():
                if self.closed:
                    return
                await self.append_item(item)
            if not self._items:
                await self._show_empty()
                await self.close()
                return
            await self.on_loading_finished()
        finally:
            self._loading_task = None

    async def _show_empty(self) -> None:
        """Replace the loading placeholder with the empty-state message."""
        if self._message is not None:
            await self._message.edit(content=self.empty_message, embed=None)

    async def close(self) -> None:
        """Close the session, stop the loader, and drop the message's view."""
        if self.closed:
            return
        task = self._loading_task
        if task is not None and task is not asyncio.current_task() and not task.done():
            task.cancel()
        await self._detach_view()
        await super().close()

    async def _detach_view(self) -> None:
        """Best-effort removal of the buttons from the original message.

        Closed sessions are no longer routable, so leaving the view in place
        makes the buttons look alive while every click silently no-ops. Only
        the view is cleared: content and embeds stay readable.
        """
        message = self._message
        if message is None:
            return
        try:
            await message.edit(view=None)
        except (HTTPException, AttributeError):
            pass

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
