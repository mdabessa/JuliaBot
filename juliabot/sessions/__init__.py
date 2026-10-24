"""Public API for JuliaBot's interactive session framework."""

from .manager import SessionManager
from .registration import Registration
from .registry import Registry
from .session import Session
from .store import MemoryStore, PostgresStore, SessionStore, StoredSession
from .types import Action, InteractionEvent, JSONValue, Scope, TriggerType

__all__ = [
    "Action",
    "InteractionEvent",
    "JSONValue",
    "MemoryStore",
    "PostgresStore",
    "Registration",
    "Registry",
    "Scope",
    "Session",
    "SessionManager",
    "SessionStore",
    "StoredSession",
    "TriggerType",
]
