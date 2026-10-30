"""Render Jikan route payloads as Discord messages.

The payload shape decides the presentation, so a route added upstream gets a
usable rendering with no change here: lists become titled bullet pages, single
objects become key/value embeds and full entities become a summary embed.
Anything that does not fit becomes inline JSON or a ``.json`` attachment.
"""

from __future__ import annotations

import io
import json
import logging
from dataclasses import dataclass
from typing import Any

from discord import Embed, File

from .jikan_catalog import RENDERER_DEBUG, RouteSpec

logger = logging.getLogger(__name__)

MAX_EMBEDS = 10
MAX_TITLE = 256
MAX_DESCRIPTION = 4096
MAX_FIELD_VALUE = 1024
MAX_FOOTER = 2048
MAX_FIELDS = 25
MAX_INLINE_JSON = 1900
EMPTY_MESSAGE = "Nada encontrado."

_ENTITY_SKIP = frozenset(
    {"title", "name", "url", "images", "synopsis", "description", "moreinfo"}
)

# Fields worth showing first on an entity embed; the remaining keys follow.
_ENTITY_PREFERRED = (
    "type",
    "episodes",
    "chapters",
    "volumes",
    "status",
    "airing",
    "score",
    "scored_by",
    "rank",
    "popularity",
    "members",
    "favorites",
    "year",
    "season",
    "rating",
    "duration",
    "source",
)

_ACRONYMS = frozenset({"mal", "id", "url", "tv", "api", "op", "ed", "sfw"})


@dataclass(frozen=True)
class RenderResult:
    """The Discord message payload produced from one route response."""

    content: str | None = None
    embeds: tuple[Embed, ...] = ()
    file: File | None = None


def _dump(payload: Any) -> Any:
    """Serialize a payload, tolerating pydantic v1 and v2 models."""
    if hasattr(payload, "model_dump"):
        return payload.model_dump()
    if hasattr(payload, "dict"):
        return payload.dict()
    return payload


safe_dump = _dump


def _safe_dump(payload: Any) -> Any:
    """Serialize a payload without ever raising."""
    try:
        return _dump(payload)
    except Exception:
        return repr(payload)


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _is_url(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def _title(spec: RouteSpec) -> str:
    return _clip(spec.brief or spec.name, MAX_TITLE)


def _label(key: str) -> str:
    words = key.split("_")
    label = " ".join(
        word.upper() if word.lower() in _ACRONYMS else word.capitalize()
        for word in words
    )
    return label[:MAX_TITLE]


def _is_empty(value: Any) -> bool:
    """Return whether a payload value carries nothing worth showing."""
    if value is None or value == "":
        return True
    if isinstance(value, dict):
        return all(_is_empty(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return all(_is_empty(item) for item in value)
    return False


def _format_value(value: Any) -> str:
    """Flatten one payload value into an embed field body."""
    if _is_empty(value):
        return ""
    if isinstance(value, dict):
        return "\n".join(
            f"{key}: {_scalar(item)}"
            for key, item in value.items()
            if not _is_empty(item)
        )
    if isinstance(value, (list, tuple)):
        return "\n".join(_scalar(item) for item in value if not _is_empty(item))
    return _scalar(value)


def _scalar(value: Any) -> str:
    if isinstance(value, dict):
        return ", ".join(
            f"{key}: {_scalar(item)}"
            for key, item in value.items()
            if not _is_empty(item)
        )
    if isinstance(value, (list, tuple)):
        return ", ".join(_scalar(item) for item in value if not _is_empty(item))
    return str(value)


def _item_extra(item: dict[str, Any]) -> str:
    extras = []
    for key in ("type", "year", "episodes", "score", "count"):
        value = item.get(key)
        if isinstance(value, (str, int, float)) and value != "":
            extras.append(f"{key}: {value}")
    return " • ".join(extras)


def _item_line(item: Any) -> str:
    """Render one list entry as a single bullet line."""
    if not isinstance(item, dict):
        return f"• {_clip(_scalar(item), MAX_FIELD_VALUE)}"

    label = item.get("title") or item.get("name") or item.get("mal_id")
    if label is None:
        label = ", ".join(
            f"{key}: {_scalar(value)}" for key, value in list(item.items())[:3]
        )

    url = item.get("url")
    line = f"• [{label}]({url})" if _is_url(url) else f"• {label}"
    extra = _item_extra(item)
    if extra:
        line = f"{line} — {extra}"
    return _clip(line, MAX_FIELD_VALUE)


def _image_url(payload: dict[str, Any]) -> str | None:
    images = payload.get("images")
    if not isinstance(images, dict):
        return None
    for kind in ("jpg", "webp"):
        image = images.get(kind)
        if isinstance(image, dict):
            url = image.get("large_image_url") or image.get("image_url")
            if _is_url(url):
                return url
    return None


def _pagination_note(pagination: Any) -> str:
    if not isinstance(pagination, dict) or not pagination:
        return ""
    parts = []
    current = pagination.get("current_page")
    last = pagination.get("last_visible_page")
    if current or last:
        parts.append(f"API página {current or '?'}/{last or '?'}")
    if pagination.get("has_next_page"):
        parts.append("tem próxima")
    return " • ".join(parts)


def _list_result(
    items: list[Any], spec: RouteSpec, color: int, envelope: dict[str, Any] | None
) -> RenderResult:
    if not items:
        return RenderResult(content=EMPTY_MESSAGE)

    lines = [_item_line(item) for item in items]
    budget = MAX_DESCRIPTION - 200
    pages: list[list[str]] = []
    current: list[str] = []
    used = 0
    for line in lines:
        if current and used + len(line) + 1 > budget:
            pages.append(current)
            current, used = [], 0
        current.append(line)
        used += len(line) + 1
    if current:
        pages.append(current)
    pages = pages[:MAX_EMBEDS]

    note = _pagination_note((envelope or {}).get("pagination"))
    embeds = []
    for index, page in enumerate(pages, start=1):
        embed = Embed(
            title=_title(spec),
            description="\n".join(page)[:MAX_DESCRIPTION],
            color=color,
        )
        footer = f"{len(items)} resultado(s) • página {index}/{len(pages)}"
        if note:
            footer = f"{footer} • {note}"
        embed.set_footer(text=_clip(footer, MAX_FOOTER))
        embeds.append(embed)
    return RenderResult(embeds=tuple(embeds))


def _object_result(
    payload: dict[str, Any], spec: RouteSpec, color: int
) -> RenderResult:
    embed = Embed(title=_title(spec), color=color)
    _add_fields(embed, payload, payload.keys())
    if not embed.fields:
        return RenderResult(content=EMPTY_MESSAGE)
    return RenderResult(embeds=(embed,))


def _entity_result(
    payload: dict[str, Any], spec: RouteSpec, color: int
) -> RenderResult:
    title = payload.get("title") or payload.get("name") or _title(spec)
    embed = Embed(title=_clip(str(title), MAX_TITLE), color=color)

    url = payload.get("url")
    if _is_url(url):
        embed.url = url

    image = _image_url(payload)
    if image is not None:
        embed.set_thumbnail(url=image)

    description = (
        payload.get("synopsis") or payload.get("description") or payload.get("moreinfo")
    )
    if isinstance(description, str) and description.strip():
        embed.description = _clip(description.strip(), MAX_DESCRIPTION)

    _add_entity_fields(embed, payload)

    return RenderResult(embeds=(embed,))


def _add_fields(embed: Embed, payload: dict[str, Any], keys: Any) -> None:
    """Add one field per non-empty value, respecting the embed field limit."""
    for key in keys:
        if key in _ENTITY_SKIP or len(embed.fields) >= MAX_FIELDS:
            continue
        text = _format_value(payload.get(key))
        if not text:
            continue
        embed.add_field(
            name=_label(key), value=_clip(text, MAX_FIELD_VALUE), inline=True
        )


def _add_entity_fields(embed: Embed, payload: dict[str, Any]) -> None:
    """Fill an entity embed, showing the interesting fields first."""
    ordered = [key for key in _ENTITY_PREFERRED if key in payload]
    ordered += [key for key in payload if key not in _ENTITY_PREFERRED]
    _add_fields(embed, payload, ordered)


def _json_result(payload: Any, spec: RouteSpec) -> RenderResult:
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    if len(text) <= MAX_INLINE_JSON:
        return RenderResult(content=f"```json\n{text}\n```")
    stream = io.BytesIO(text.encode("utf-8"))
    stream.seek(0)
    return RenderResult(file=File(stream, filename=f"{spec.name}.json"))


def item_embed(
    item: Any, spec: RouteSpec, color: int = 0, position: int = 0, total: int = 1
) -> Embed:
    """Render one list entry as its own embed, used by paginated sessions."""
    data = _safe_dump(item)
    if not isinstance(data, dict):
        embed = Embed(
            title=_title(spec),
            description=_clip(str(data), MAX_DESCRIPTION),
            color=color,
        )
        embed.set_footer(
            text=_clip(f"{spec.name} • {position + 1}/{total}", MAX_FOOTER)
        )
        return embed

    title = data.get("title") or data.get("name") or data.get("mal_id") or _title(spec)
    embed = Embed(title=_clip(str(title), MAX_TITLE), color=color)

    url = data.get("url")
    if _is_url(url):
        embed.url = url

    image = _image_url(data)
    if image is not None:
        embed.set_thumbnail(url=image)

    description = (
        data.get("synopsis") or data.get("description") or data.get("moreinfo")
    )
    if isinstance(description, str) and description.strip():
        embed.description = _clip(description.strip(), MAX_DESCRIPTION)

    _add_entity_fields(embed, data)
    embed.set_footer(text=_clip(f"{spec.name} • {position + 1}/{total}", MAX_FOOTER))
    return embed


def render(payload: Any, spec: RouteSpec, color: int = 0) -> RenderResult:
    """Render a route response for Discord, falling back to raw JSON."""
    data = _safe_dump(payload)
    try:
        if spec.renderer == RENDERER_DEBUG:
            return _json_result(data, spec)

        if isinstance(data, dict):
            inner = data.get("data")
            if isinstance(inner, dict):
                return _object_result(inner, spec, color)
            if isinstance(inner, list):
                return _list_result(inner, spec, color, data)
            if inner is None:
                return _entity_result(data, spec, color)

        if isinstance(data, list):
            return _list_result(data, spec, color, None)

        return _json_result(data, spec)
    except Exception:  # pragma: no cover - a renderer bug must not break a command
        logger.warning("Falling back to raw JSON for %s", spec.route, exc_info=True)
        return _json_result(data, spec)
