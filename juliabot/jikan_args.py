"""Parse Discord message text into Jikan route keyword arguments.

Generated commands receive the whole argument tail as one string. This module
turns that string into the keyword arguments of the route, accepting both
positional values and ``key=value`` pairs in the same invocation.
"""

from __future__ import annotations

from typing import Any

from discord.ext import commands

from .jikan_catalog import ParamSpec, RouteSpec

TRUE_VALUES = frozenset(
    {"yes", "y", "true", "t", "1", "enable", "enabled", "on", "sim"}
)
FALSE_VALUES = frozenset(
    {"no", "n", "false", "f", "0", "disable", "disabled", "off", "nao", "não"}
)
_QUOTES = frozenset({'"', "'"})


class JikanArgumentError(commands.UserInputError):
    """Raised when the user's arguments cannot be mapped to the route."""


def _tokenize(raw: str) -> list[str]:
    """Split the argument tail on whitespace, keeping quoted groups intact.

    A quote only opens a quoted section at the start of a token or right after
    ``=``, so `it's` stays a literal value instead of failing as unbalanced.
    """
    tokens: list[str] = []
    current: list[str] = []
    quote: str | None = None
    started = False

    for char in raw:
        if quote is not None:
            if char == quote:
                quote = None
            else:
                current.append(char)
            continue
        if char in _QUOTES and (not started or current[-1] == "="):
            quote = char
            started = True
            continue
        if char.isspace():
            if started:
                tokens.append("".join(current))
                current = []
                started = False
            continue
        current.append(char)
        started = True

    if quote is not None:
        raise JikanArgumentError("Tem aspas sem fechar na mensagem.")
    if started:
        tokens.append("".join(current))
    return tokens


def _coerce(param: ParamSpec, value: str) -> Any:
    """Convert one raw value to the type declared by the client method."""
    annotation = param.annotation
    if annotation is str:
        return value

    if annotation is bool:
        lowered = value.strip().lower()
        if lowered in TRUE_VALUES:
            return True
        if lowered in FALSE_VALUES:
            return False
        raise JikanArgumentError(
            f"`{param.name}` aceita sim ou não (recebi `{value}`)."
        )

    if annotation is int:
        try:
            return int(value)
        except ValueError:
            raise JikanArgumentError(
                f"`{param.name}` precisa ser um número inteiro (recebi `{value}`)."
            ) from None

    if annotation is float:
        try:
            return float(value)
        except ValueError:
            raise JikanArgumentError(
                f"`{param.name}` precisa ser um número (recebi `{value}`)."
            ) from None

    return value


def _accepted_keys(spec: RouteSpec) -> str:
    """List the keyword names the route accepts."""
    return ", ".join(param.name for param in spec.params) or "nenhum"


def _usage_hint(spec: RouteSpec) -> str:
    """Return the usage line appended to argument errors."""
    return f"Uso: {spec.usage}"


def _store(target: dict[str, Any], name: str, value: Any) -> None:
    """Record one argument, rejecting duplicates."""
    if name in target:
        raise JikanArgumentError(f"`{name}` foi informado mais de uma vez.")
    target[name] = value


def parse_arguments(spec: RouteSpec, raw: str | None = None) -> dict[str, Any]:
    """Return the route kwargs described by ``raw``.

    Only the arguments the user actually supplied are returned, so the client
    keeps applying its own defaults.
    """
    tokens = _tokenize(raw or "")
    params = {param.name: param for param in spec.params}
    positional = list(spec.positional_names)
    provided: dict[str, Any] = {}
    filled = 0

    for token in tokens:
        key, separator, value = token.partition("=")
        if separator:
            if not key:
                raise JikanArgumentError(
                    f"Parâmetro inválido: `{token}`.\n{_usage_hint(spec)}"
                )
            param = params.get(key)
            if param is None:
                raise JikanArgumentError(
                    f"Parâmetro desconhecido: `{key}`.\n"
                    f"Parâmetros: {_accepted_keys(spec)}"
                )
            _store(provided, key, _coerce(param, value))
            continue

        if filled < len(positional):
            name = positional[filled]
            filled += 1
            _store(provided, name, _coerce(params[name], token))
            continue

        # A bare boolean name is a flag, but only once the positional slots are
        # taken, so `!search_manga sfw` still searches for "sfw".
        param = params.get(token)
        if param is not None and param.annotation is bool:
            _store(provided, token, True)
            continue

        raise JikanArgumentError(f"Valor extra: `{token}`.\n{_usage_hint(spec)}")

    missing = [
        param.name for param in spec.required_params if param.name not in provided
    ]
    if missing:
        raise JikanArgumentError(
            f"Faltou informar: {', '.join(missing)}.\n{_usage_hint(spec)}"
        )

    return {
        param.name: provided[param.name]
        for param in spec.params
        if param.name in provided
    }
