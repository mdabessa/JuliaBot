"""Translate Jikan call failures into user-facing messages.

The generated commands never surface a traceback: :func:`call_route` converts
the aiohttp exceptions raised by the client into one pt-BR sentence, and records
a 429 so the whole bot backs off instead of hammering a rate-limited API.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import aiohttp

from .jikan_catalog import RouteSpec

logger = logging.getLogger(__name__)

try:  # pydantic ships with jikan4, but the error type stays optional here
    from pydantic import ValidationError as PydanticValidationError
except ImportError:  # pragma: no cover - defensive
    PydanticValidationError = ()  # type: ignore[assignment,misc]

DEFAULT_RETRY_AFTER = 30.0
MAX_RETRY_AFTER = 300.0


class JikanCallError(Exception):
    """A route call failed; ``str(error)`` is safe to show to the user."""


class RateLimitGuard:
    """Track an API-wide 429 window so every user is told the same thing.

    The client's own limiter paces requests, but a 429 means the shared per-IP
    budget is exhausted. Rather than sleeping inside a command (which would
    hold a user for up to a minute), the guard makes calls fail fast with the
    remaining time until the API is expected to accept requests again.
    """

    def __init__(self) -> None:
        self._blocked_until = 0.0

    def block(self, seconds: float) -> None:
        """Remember that the API refused requests for ``seconds``."""
        seconds = max(1.0, min(float(seconds), MAX_RETRY_AFTER))
        self._blocked_until = max(self._blocked_until, time.monotonic() + seconds)

    def remaining(self) -> float:
        """Return the seconds left in the current 429 window."""
        return max(0.0, self._blocked_until - time.monotonic())

    def reset(self) -> None:
        """Forget the current window."""
        self._blocked_until = 0.0


GUARD = RateLimitGuard()


def _retry_after(error: aiohttp.ClientResponseError) -> float:
    """Read ``Retry-After`` from a 429 response, falling back to a default."""
    headers = getattr(error, "headers", None) or {}
    try:
        value = headers.get("Retry-After")
    except Exception:  # pragma: no cover - defensive against odd mappings
        value = None
    if value is None:
        return DEFAULT_RETRY_AFTER
    try:
        return float(value)
    except (TypeError, ValueError):
        return DEFAULT_RETRY_AFTER


def _seconds_text(seconds: float) -> str:
    return f"{max(1, round(seconds))}s"


def _status_message(status: int, retry_after: float) -> str:
    if status == 400:
        return "A API recusou os parâmetros dessa consulta."
    if status in (401, 403):
        return "A API bloqueou essa consulta."
    if status == 404:
        return "Não encontrei nada com esse id ou critério."
    if status == 429:
        return (
            "A API do MyAnimeList está limitando as requisições. "
            f"Tente novamente em {_seconds_text(retry_after)}."
        )
    if status >= 500:
        return "A API do MyAnimeList está instável agora. Tente novamente em instantes."
    return f"A API respondeu com erro {status}."


def translate(error: BaseException, *, retry_remaining: float = 0.0) -> JikanCallError:
    """Convert a client failure into a message the user can act on."""
    # ``ContentTypeError`` subclasses ``ClientResponseError`` with status 0, so
    # it has to be recognised first.
    if isinstance(error, aiohttp.ContentTypeError):
        return JikanCallError("A API respondeu em um formato inesperado.")

    # The client parses the response into a pydantic model inside the route
    # call, so a changed API shape surfaces as a validation error.
    if PydanticValidationError and isinstance(error, PydanticValidationError):
        return JikanCallError("A API respondeu em um formato inesperado.")

    if isinstance(error, aiohttp.ClientResponseError):
        retry_after = _retry_after(error) if error.status == 429 else 0.0
        retry_after = max(retry_after, retry_remaining)
        return JikanCallError(_status_message(error.status, retry_after))

    if isinstance(error, asyncio.TimeoutError):
        return JikanCallError("A consulta demorou demais e foi cancelada.")

    if isinstance(error, aiohttp.ClientError):
        return JikanCallError("Não consegui falar com a API do MyAnimeList.")

    return JikanCallError("Não foi possível concluir a consulta.")


async def call_route(
    client: Any,
    spec: RouteSpec,
    kwargs: dict[str, Any],
    *,
    guard: RateLimitGuard | None = None,
) -> Any:
    """Call one route and return its payload, or raise :class:`JikanCallError`."""
    guard = GUARD if guard is None else guard
    remaining = guard.remaining()
    if remaining > 0:
        raise JikanCallError(_status_message(429, remaining))

    try:
        return await getattr(client, spec.route)(**kwargs)
    except (
        asyncio.TimeoutError,
        aiohttp.ClientError,
        PydanticValidationError,
    ) as error:
        if _is_rate_limited(error):
            retry_after = _retry_after(error)
            guard.block(retry_after)
            logger.warning(
                "Jikan rate limited on %s; backing off %.0fs", spec.route, retry_after
            )
            raise translate(error, retry_remaining=guard.remaining()) from error
        logger.info("Jikan call failed for %s: %r", spec.route, error)
        raise translate(error) from error


def _is_rate_limited(error: BaseException) -> bool:
    """Return whether ``error`` is a 429, ignoring content-type failures."""
    return (
        isinstance(error, aiohttp.ClientResponseError)
        and not isinstance(error, aiohttp.ContentTypeError)
        and error.status == 429
    )
