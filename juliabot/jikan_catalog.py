"""Catalog of the Jikan API surface exposed as Discord commands.

One :class:`RouteSpec` is derived per public ``AioJikan`` coroutine by
introspection, so a route added to the ``jikan4`` package becomes a command
without any change here. ``POLICY`` carries only the decisions that cannot be
derived: command naming, aliases, visibility, renderer hints and parameter
defaults.
"""

from __future__ import annotations

import inspect
import logging
import types
import typing
from dataclasses import dataclass, replace
from typing import Any, Iterable

from jikan4 import AioJikan

logger = logging.getLogger(__name__)

SUPPORTED_PARAM_TYPES = (int, float, str, bool)
_CLIENT_LIFECYCLE = frozenset({"close"})
_NONE_TYPE = type(None)

GROUP_ANIME = "anime"
GROUP_MANGA = "manga"
GROUP_CATALOG = "catalog"

RENDERER_AUTO = "auto"
RENDERER_EMBED = "embed"
RENDERER_DEBUG = "debug"
RENDERERS = frozenset({RENDERER_AUTO, RENDERER_EMBED, RENDERER_DEBUG})

_SECTION_HEADERS = frozenset(
    {
        "Args:",
        "Arguments:",
        "Returns:",
        "Raises:",
        "Examples:",
        "Yields:",
        "Note:",
        "Notes:",
    }
)


@dataclass(frozen=True)
class ParamSpec:
    """One argument accepted by a route, normalized for Discord."""

    name: str
    annotation: type
    required: bool
    default: Any = None

    @property
    def type_name(self) -> str:
        """Return the annotation name shown in the command usage."""
        return getattr(self.annotation, "__name__", str(self.annotation))


@dataclass(frozen=True)
class RouteSpec:
    """Everything the command generator needs to expose one Jikan route."""

    route: str
    name: str
    group: str
    brief: str
    description: str
    params: tuple[ParamSpec, ...] = ()
    positional: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    hidden: bool = False
    curated: bool = False
    renderer: str = RENDERER_AUTO
    cooldown: tuple[int, int] = (1, 5)

    @property
    def required_params(self) -> tuple[ParamSpec, ...]:
        """Return the parameters the user must supply."""
        return tuple(param for param in self.params if param.required)

    @property
    def positional_names(self) -> tuple[str, ...]:
        """Return the parameters that may be filled by position, in order.

        Required parameters always qualify; a route's natural search term
        (``q``/``query``) joins them in declaration order, so
        ``!search_manga naruto`` works without naming the key.
        """
        extra = set(self.positional)
        return tuple(
            param.name for param in self.params if param.required or param.name in extra
        )

    @property
    def usage(self) -> str:
        """Render the command signature shown by ``!help``."""
        positional = set(self.positional_names)
        tokens = [self.name]
        for param in self.params:
            if param.name in positional:
                tokens.append(f"<{param.name}>")
            else:
                tokens.append(f"[{param.name}={param.type_name}]")
        return " ".join(tokens)


@dataclass(frozen=True)
class RoutePolicy:
    """Overrides for a route that introspection cannot decide on its own."""

    name: str | None = None
    aliases: tuple[str, ...] = ()
    hidden: bool = False
    curated: bool = False
    renderer: str | None = None
    cooldown: tuple[int, int] | None = None

    def apply(self, spec: RouteSpec) -> RouteSpec:
        """Return the spec with this policy applied."""
        changes: dict[str, Any] = {}
        if self.name is not None:
            changes["name"] = self.name
        if self.aliases:
            changes["aliases"] = self.aliases
        if self.hidden:
            changes["hidden"] = True
        if self.curated:
            changes["curated"] = True
        if self.renderer is not None:
            changes["renderer"] = self.renderer
        if self.cooldown is not None:
            changes["cooldown"] = self.cooldown
        return replace(spec, **changes)


# Routes that expose crawlable data: reachable through ``!jikan`` but kept out
# of the help listing.
_HIDDEN_ROUTES = (
    "get_anime_deleted",
    "get_anime_unapproved",
    "get_anime_denied",
    "get_manga_deleted",
    "get_manga_unapproved",
    "get_manga_denied",
)

# Routes that answer with thousands of ids, rendered as a JSON attachment.
_BULK_DUMPS = (
    "get_anime_ids",
    "get_manga_ids",
    "get_character_ids",
    "get_person_ids",
    "get_producer_ids",
)

_EXPLICIT_POLICY: dict[str, RoutePolicy] = {
    # ``anime`` and ``manga`` are curatorial aliases of the hand-written search
    # commands, so the detail routes are named ``*_info``.
    "get_anime": RoutePolicy(name="anime_info", aliases=("ani",)),
    "get_manga": RoutePolicy(name="manga_info"),
    # Covered by the hand-written ``search_anime`` command in the animes cog.
    "search_anime": RoutePolicy(curated=True),
    "get_seasons_now": RoutePolicy(aliases=("now",)),
    "get_schedules": RoutePolicy(aliases=("sched",)),
    "get_top_anime": RoutePolicy(aliases=("ta",)),
    "get_characters": RoutePolicy(aliases=("chars",)),
    "get_random_anime": RoutePolicy(renderer=RENDERER_EMBED, aliases=("ra",)),
    **{
        route: RoutePolicy(renderer=RENDERER_EMBED)
        for route in (
            "get_random_manga",
            "get_random_character",
            "get_random_person",
            "get_anime_themes",
            "get_anime_videos",
            "get_anime_statistics",
            "get_anime_moreinfo",
            "get_manga_moreinfo",
            "get_manga_statistics",
        )
    },
}

POLICY: dict[str, RoutePolicy] = {
    **_EXPLICIT_POLICY,
    **{route: RoutePolicy(hidden=True) for route in _HIDDEN_ROUTES},
    **{
        route: RoutePolicy(hidden=True, renderer=RENDERER_DEBUG)
        for route in _BULK_DUMPS
    },
}


def _split_docstring(doc: str | None) -> tuple[str, str]:
    """Split a docstring into a one-line brief and the summary paragraph."""
    text = (doc or "").strip()
    if not text:
        return "", ""

    summary: list[str] = []
    for line in text.splitlines():
        if line.strip() in _SECTION_HEADERS:
            break
        summary.append(line)

    summary_text = "\n".join(summary).strip()
    brief = next((line.strip() for line in summary if line.strip()), "")
    return brief, summary_text or brief


def _unwrap_optional(annotation: Any) -> Any:
    """Collapse ``X | None`` to ``X``; other unions stay untouched."""
    origin = typing.get_origin(annotation)
    if origin is typing.Union or origin is types.UnionType:
        args = [arg for arg in typing.get_args(annotation) if arg is not _NONE_TYPE]
        if len(args) == 1:
            return args[0]
    return annotation


def _hints_from_globals(func: Any) -> dict[str, Any]:
    """Evaluate the string annotations of a method one parameter at a time.

    ``jikan4`` uses ``from __future__ import annotations``, so annotations stay
    strings until resolved. This mirrors ``typing.get_type_hints`` while
    tolerating a single unresolvable annotation instead of losing the whole
    signature.
    """
    globalns = getattr(func, "__globals__", {})
    hints: dict[str, Any] = {}
    for name, param in inspect.signature(func).parameters.items():
        annotation = param.annotation
        if not isinstance(annotation, str):
            if annotation is not inspect.Parameter.empty:
                hints[name] = annotation
            continue
        try:
            hints[name] = eval(annotation, globalns)  # noqa: S307
        except Exception:  # pragma: no cover - defensive
            logger.debug("Unresolvable annotation %r on %r", annotation, func)
    return hints


def _type_hints(func: Any) -> dict[str, Any]:
    """Resolve the annotations of a client method."""
    try:
        return typing.get_type_hints(func)
    except Exception:  # pragma: no cover - defensive against odd annotations
        logger.debug("Resolving annotations of %r individually", func, exc_info=True)
        return _hints_from_globals(func)


def _param_spec(
    route: str, param: inspect.Parameter, hints: dict[str, Any]
) -> ParamSpec:
    """Build a :class:`ParamSpec` from one inspected parameter."""
    annotation = _unwrap_optional(hints.get(param.name, param.annotation))
    if annotation not in SUPPORTED_PARAM_TYPES:
        logger.warning(
            "%s: parameter %r has unsupported annotation %r; treating it as str",
            route,
            param.name,
            annotation,
        )
        annotation = str

    required = param.default is inspect.Parameter.empty
    return ParamSpec(
        name=param.name,
        annotation=annotation,
        required=required,
        default=None if required else param.default,
    )


def _command_name(route: str) -> str:
    """Derive a command name from a client method name."""
    return route[len("get_") :] if route.startswith("get_") else route


def _group_of(route: str) -> str:
    """Assign a route to the cog family that will expose it."""
    if route == "search_anime" or route.startswith("get_anime"):
        return GROUP_ANIME
    if route == "search_manga" or route.startswith("get_manga"):
        return GROUP_MANGA
    return GROUP_CATALOG


# The natural search term of a route: positional so `!search_manga naruto`
# works without spelling out the key.
_POSITIONAL_NAMES = frozenset({"q", "query"})


def _positional_names(params: Iterable[ParamSpec]) -> tuple[str, ...]:
    """Return the optional parameters that should accept a bare positional value."""
    return tuple(
        param.name
        for param in params
        if not param.required and param.name in _POSITIONAL_NAMES
    )


def route_names(client: type = AioJikan) -> tuple[str, ...]:
    """Return the public API routes of the client, sorted by name."""
    names: list[str] = []
    for name in dir(client):
        if name.startswith("_") or name in _CLIENT_LIFECYCLE:
            continue
        if inspect.iscoroutinefunction(getattr(client, name, None)):
            names.append(name)
    return tuple(sorted(names))


def _build_spec(route: str) -> RouteSpec:
    """Build the derived spec of one route, before policy overrides."""
    func = getattr(AioJikan, route)
    hints = _type_hints(func)
    signature = inspect.signature(func)
    params = [
        _param_spec(route, param, hints)
        for param in signature.parameters.values()
        if param.name != "self"
    ]
    brief, description = _split_docstring(inspect.getdoc(func))
    return RouteSpec(
        route=route,
        name=_command_name(route),
        group=_group_of(route),
        brief=brief or _command_name(route),
        description=description or brief or _command_name(route),
        params=tuple(params),
        positional=_positional_names(params),
    )


def _validate(specs: Iterable[RouteSpec]) -> None:
    """Reject duplicate labels, unknown policy routes and bad renderer names."""
    specs = tuple(specs)
    owners: dict[str, str] = {}
    for spec in specs:
        if spec.renderer not in RENDERERS:
            raise ValueError(f"{spec.route}: unknown renderer {spec.renderer!r}")
        for label in (spec.name, *spec.aliases):
            owner = owners.get(label)
            if owner is not None:
                raise ValueError(
                    f"Duplicate command label {label!r} claimed by "
                    f"{owner!r} and {spec.route!r}"
                )
            owners[label] = spec.route

    stale = sorted(set(POLICY) - {spec.route for spec in specs})
    if stale:
        raise ValueError(f"POLICY references unknown route(s): {stale}")


def load_specs() -> tuple[RouteSpec, ...]:
    """Return the full route catalog, ordered by group and command name."""
    specs: list[RouteSpec] = []
    for route in route_names():
        spec = _build_spec(route)
        policy = POLICY.get(route)
        specs.append(policy.apply(spec) if policy is not None else spec)

    _validate(specs)
    return tuple(sorted(specs, key=lambda spec: (spec.group, spec.name)))
