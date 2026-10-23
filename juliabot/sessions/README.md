# Session framework

Stateful Discord flows — pagination, confirmations, and durable per-channel rules — behind one
lifecycle, one dispatch path, and one persistence contract.

## Layers

| Layer | Module | Responsibility |
|---|---|---|
| Types | `types.py` | `TriggerType`, `Scope`, `Action`, `InteractionEvent`, `JSONValue` |
| Registration | `registration.py` | Immutable code configuration (trigger, scope, limits, timeout, resumable) |
| Registry | `registry.py` | Indexes registrations by trigger and scope key |
| Session | `session.py` | Identity, ownership, expiry, payload boundary, lifecycle hooks |
| Manager | `manager.py` | Live sessions, dispatch, ownership, limits, restore, sweep |
| Store | `store.py` | `MemoryStore`, `PostgresStore`, `StoredSession` |
| Patterns | `patterns/` | `PaginationSession`, `PromptSession`, `MessageRuleSession`, `ChannelEntryPointRule` |
| Transports | `transports/` | Buttons (persistent views) and channel messages |

Only `patterns/` and `transports/` import Discord. The manager indexes routing keys; it does not know
about messages, views, or buttons.

## Registering a session

A session is a class plus a `Registration`. Registration happens once, where the cog is created.

```python
from ..sessions import Action, Registration, Scope, TriggerType
from ..sessions.patterns import PaginationSession


class ItemPagination(PaginationSession[Item]):
    extra_actions = (
        Action("delete", "delete_current", label="Remover", style="danger"),
    )

    async def load_items(self):
        return await repository.list_items(self.owner_id)

    async def render_item(self, item, index, total):
        return build_embed(item, index, total)

    async def delete_item(self, item, event) -> bool:
        await repository.delete(item)
        return True


registration = Registration(
    name="feature.items",
    session_class=ItemPagination,
    trigger=TriggerType.COMPONENT,
    scope=Scope.USER,
    timeout=180,
    max_per_scope=1,
    resumable=True,
)
```

Start it from a command by normalizing the invocation into an `InteractionEvent` and calling
`manager.start(...)` with a JSON-safe payload. Persistence and restore use that payload; everything
else (messages, clients, ORM rows) stays in runtime attributes.

## Actions and ownership

- `Registration.owner_only` defaults to `True`.
- `Action.owner_only` overrides it per action; `None` inherits.
- Open navigation (`previous`/`next`) sets `owner_only=False`.
- For asymmetric rules use a pattern hook (`PromptSession.can_handle`) or a per-item check
  (`delete_item` returning `False`) instead of weakening the whole action.

## State and persistence

- Payloads contain only JSON-safe values: ids, numbers, strings, booleans, and lists of those.
- `to_payload()` must stay JSON-serializable; live objects belong in `_runtime` attributes.
- `resumable=True` writes a snapshot on start and after every successful interaction.
- Restore is lazy: boot loads routing keys only, persistent views are re-registered, and the first
  click loads the payload and runs `hydrate(event)`. Hydration receives the triggering interaction so
  patterns can reattach the original message and any clients (`interaction.client`).
- `persistent=True` means "never expires" (`expires_at = datetime.max`); use it for message rules.

## Message rules

`MessageRuleSession` receives every human message in its channel. The manager keeps one bucket per
channel plus a global bucket, so dispatch is two dictionary lookups regardless of how many channels
have rules.

```python
class WelcomeRule(ChannelEntryPointRule):
    async def on_channel_message(self, event) -> bool:
        await event.raw.channel.send(f"Bem-vindo, <@{event.user_id}>!")
        return True
```

`ChannelEntryPointRule` sends an anchor message with a persistent view and exposes an owner-only
`disable` action. Its `anchor_message_id` is persisted so the rule survives restarts.

## Efficiency contract

Tests in `tests/unit/sessions/` enforce:

- no store traffic for events without a matching session or channel rule;
- one `load_keys()` at boot and one `load()` per restored session, on first interaction only;
- no scans or list copies in dispatch paths;
- no live Discord/ORM objects inside payloads.

## Schema migrations

The `session` table is owned by versioned migrations, not by `create_all`:

```bash
python -m juliabot.migrations status [--json]
python -m juliabot.migrations upgrade [--to N] [--dry-run]
python -m juliabot.migrations downgrade --to N
```

See `juliabot/migrations/versions/` and the root `README.md`.

## Testing

- Unit tests live in `tests/unit/sessions/`.
- Shared fixtures (`FakeClock`, `FakeClient`, `CountingStore`) are in
  `tests/unit/sessions/conftest.py`.
- Use `FakeClock` instead of sleeping, and `CountingStore` to assert the query budget.
- `tests/unit/test_no_legacy_engine.py` guards that `juliabot.scripts` never returns.
