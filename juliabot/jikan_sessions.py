"""Button pagination for the generated Jikan commands.

Paginated routes get one embed per result with previous/next buttons that walk
the results and fetch the adjacent API page at the boundaries. The session
payload holds only JSON-safe values, so a session survives a restart.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from .jikan_catalog import RouteSpec, load_specs
from .jikan_errors import JikanCallError, call_route
from .jikan_render import item_embed, safe_dump
from .sessions import InteractionEvent, Registration, Scope, SessionManager, TriggerType
from .sessions.patterns import PaginationSession

logger = logging.getLogger(__name__)

JIKAN_PAGE = "jikan.page"


@lru_cache(maxsize=1)
def specs_by_route() -> dict[str, RouteSpec]:
    """Index the route catalog by client method name."""
    return {spec.route: spec for spec in load_specs()}


def route_spec(route: str) -> RouteSpec | None:
    """Return the catalog entry of one route."""
    return specs_by_route().get(route)


def register(manager: SessionManager) -> None:
    """Register the shared pagination session once per bot instance."""
    if manager.registry.get(JIKAN_PAGE) is not None:
        return
    manager.registry.register(
        Registration(
            name=JIKAN_PAGE,
            session_class=JikanRoutePagination,
            trigger=TriggerType.COMPONENT,
            scope=Scope.USER,
            timeout=300,
            max_per_scope=1,
            resumable=True,
        )
    )


def _bind_runtime(session: Any, context: Any) -> None:
    """Bind the shared Jikan client and embed color from a context."""
    bot = getattr(context, "bot", None) or getattr(context, "client", None)
    if bot is None:
        return
    session._jikan = getattr(bot, "jikan", None)
    session._color = getattr(bot, "color", 0)


class JikanRoutePagination(PaginationSession[Any]):
    """Paginate the results of one generated route."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._jikan = None
        self._color = 0

    @property
    def route(self) -> str:
        """Return the client method this session paginates."""
        value = self._payload.get("route", "")
        return value if isinstance(value, str) else ""

    @property
    def kwargs(self) -> dict[str, Any]:
        """Return the route arguments frozen when the command ran."""
        value = self._payload.get("kwargs")
        return dict(value) if isinstance(value, dict) else {}

    @property
    def api_page(self) -> int:
        """Return the API page currently loaded."""
        value = self._payload.get("api_page", 1)
        return int(value) if isinstance(value, (int, float)) else 1

    @property
    def has_next(self) -> bool:
        """Return whether the API reported another page."""
        return bool(self._payload.get("has_next", False))

    @property
    def spec(self) -> RouteSpec | None:
        """Return the catalog entry of this session's route."""
        return route_spec(self.route)

    def to_payload(self) -> dict:
        """Persist only the routing state needed to resume."""
        return {
            "route": self.route,
            "kwargs": self.kwargs,
            "api_page": self.api_page,
            "index": self.index,
            "has_next": self.has_next,
        }

    async def start(self, event: InteractionEvent) -> None:
        """Capture runtime dependencies, then load the first API page."""
        context = event.raw
        if context is None:
            raise RuntimeError("Jikan pagination requires an invoking context")
        _bind_runtime(self, context)
        await super().start(event)

    async def hydrate(self, event: InteractionEvent | None = None) -> None:
        """Rebind the shared client before reloading a restored session."""
        if event is not None:
            _bind_runtime(self, event.raw)
        await super().hydrate(event)

    async def load_items(self) -> list[Any]:
        """Fetch the current API page and keep its pagination metadata."""
        spec = self.spec
        if spec is None or self._jikan is None:
            return []

        payload = await call_route(
            self._jikan, spec, {**self.kwargs, "page": self.api_page}
        )
        pagination = getattr(payload, "pagination", None)
        self.set_payload("has_next", bool(getattr(pagination, "has_next_page", False)))
        return [safe_dump(item) for item in (getattr(payload, "data", None) or [])]

    async def load_more(self, direction: int) -> bool:
        """Fetch the adjacent API page when navigation hits a boundary."""
        page = self.api_page + direction
        if page < 1:
            return False
        if direction > 0 and not self.has_next:
            return False

        self.set_payload("api_page", page)
        try:
            items = list(await self.load_items())
        except JikanCallError as exc:
            logger.info("Jikan page %s of %s failed: %s", page, self.route, exc)
            self.set_payload("api_page", page - direction)
            return False

        if not items:
            self.set_payload("api_page", page - direction)
            return False

        self._items = items
        self.set_payload("index", 0 if direction > 0 else len(items) - 1)
        await self.render()
        return True

    async def render_item(self, item: Any, index: int, total: int):
        """Render one result as its own embed."""
        spec = self.spec
        if spec is None:
            return None
        return item_embed(item, spec, self._color, index, total)
