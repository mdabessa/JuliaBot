"""Indexed lookup of code-level session registrations.

The registry is the hot path for new events. It keeps registrations grouped by
trigger and scope key so dispatch does not scan every registration on every
message.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Hashable

from .registration import Registration
from .types import TriggerType


class Registry:
    """Index registrations by name, trigger, and optional scope key."""

    def __init__(self) -> None:
        self._by_name: dict[str, Registration] = {}
        self._by_trigger: dict[
            TriggerType, dict[Hashable | None, list[Registration]]
        ] = defaultdict(lambda: defaultdict(list))

    def register(self, registration: Registration) -> None:
        """Add a registration and reject duplicate names."""
        if registration.name in self._by_name:
            raise ValueError(f"Registration already exists: {registration.name}")

        self._by_name[registration.name] = registration
        self._by_trigger[registration.trigger][registration.scope_key].append(
            registration
        )

    def get(self, name: str) -> Registration | None:
        """Return a registration by name, if it exists."""
        return self._by_name.get(name)

    def match(
        self, trigger: TriggerType, scope_key: Hashable | None = None
    ) -> tuple[Registration, ...]:
        """Return global registrations and registrations for ``scope_key``.

        The two indexed buckets are concatenated directly; unrelated scopes are
        never visited.
        """
        buckets = self._by_trigger.get(trigger)
        if buckets is None:
            return ()

        global_matches = buckets.get(None, ())
        scoped_matches = () if scope_key is None else buckets.get(scope_key, ())
        return tuple(global_matches) + tuple(scoped_matches)

    def __len__(self) -> int:
        """Return the number of registered session kinds."""
        return len(self._by_name)
