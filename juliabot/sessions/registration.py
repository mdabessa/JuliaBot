"""Declarative metadata for starting session instances.

A registration is immutable code configuration. It contains no live state and
can therefore be indexed once when the bot starts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Hashable

from .types import Scope, TriggerType

if TYPE_CHECKING:
    from .session import Session


@dataclass(frozen=True)
class Registration:
    """Describe how a session can be created and constrained."""

    name: str
    session_class: type[Session]
    trigger: TriggerType
    scope: Scope = Scope.USER
    scope_key: Hashable | None = None
    owner_only: bool = True
    timeout: float = 60.0
    max_per_scope: int | None = 1
    resumable: bool = False
    persistent: bool = False

    def __post_init__(self) -> None:
        """Reject invalid registration limits early."""
        if not self.name:
            raise ValueError("Registration name cannot be empty")
        if self.timeout <= 0:
            raise ValueError("Registration timeout must be positive")
        if self.max_per_scope is not None and self.max_per_scope < 1:
            raise ValueError("max_per_scope must be positive or None")
