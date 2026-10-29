# Plan — Expose every Jikan v4 route as a Discord command (generated, not hand-written)

Epic branch: `epic/jikan-command-generation`

Tracks issue #5. Every Jikan endpoint exposed by the `jikan4` client becomes a
Discord command **without hand-writing one command per endpoint**, so updating
`jikan4` keeps the bot in sync with no code change here.

Status: **plan only — no implementation started.**

---

## 1. Decisions (resolved)

| # | Question | Decision |
|---|----------|----------|
| 1 | Where does the route metadata come from now? | **Adapter now.** Introspect `AioJikan` at import time in `juliabot/jikan_catalog.py`. A package-side `jikan4/spec.py` is a later, optional follow-up (§9). |
| 2 | Command argument style | **Hybrid:** required params positional, everything else `key=value`, both accepted in the same invocation. |
| 3 | Destructive/abusive routes | **`hidden=True`** (reachable, but absent from `!help`). |
| 4 | Cog layout | **Split by resource family** (several cogs, not one). |
| 5 | Jikan coverage | `jikan4` **1.0.0** now ships every route (97 methods). The bot targets that surface. |

Supporting decisions taken while writing this plan:

| # | Decision | Why |
|---|----------|-----|
| 6 | **No code generation to files.** Commands are built at runtime on cog init. | A generated `.py` + regenerate step is hand-writing with extra diff noise, and it can drift from the installed package. |
| 7 | **One `AioJikan` instance per bot**, shared through `bot.jikan`. | Two clients = two independent `AsyncLimiter`s = ~2× the per-IP budget. |
| 8 | **No env feature flag.** Use an in-code `ROUTES_ALLOWLIST` during development, empty (all on) at the end. | A 97-command surface that can be switched off by env var is a config axis nobody will test; `git revert` is the rollback. |
| 9 | Registered by **extending `self.__cog_commands__`** in `__init__`, not by `exec`/metaclass tricks. | `Cog.__new__` builds a per-instance tuple and `_inject` registers each entry — supported, and instance-safe. |
| 10 | **Collisions are skipped with a warning, never raised.** | `Cog._inject` rolls back the *whole* cog on `CommandRegistrationError`; one bad generated alias would take the curated anime commands down with it. |
| 11 | Generic renderers only. Curated embeds stay curated. | `search_anime` / `anime_list` keep their hand-written embeds and reaction pagination. |

---

## 2. Current state (verified)

| Fact | Evidence |
|------|----------|
| `AioJikan` is created in `AnimesCog.__init__` and published as `bot.jikan`. | [animes.py](../juliabot/cogs/animes.py) — `self.jikan = AioJikan(rate_limit=BOT_JIKAN_RATE_LIMIT)` |
| Only 2 of 97 routes are used today (`search_anime`, `get_anime`). | same file; session pagination calls `self._jikan.search_anime(...)` |
| `SCRAP_JIKAN_RATE_LIMIT` is configured but unused. | [config.py](../juliabot/config.py) — no reader outside `config.py` |
| `jikan4` is unpinned. | [requirements.txt](../requirements.txt) — bare `jikan4` |
| `jikan4` 1.0.0: 97 route methods, 97 route functions, 1:1 names, all async, all documented (first line usable as `brief`), 9/97 with `Args:`. | probe against `.venv` (2026-10-29) |
| Command params can be inspected without `exec`: `Command.params` is a plain dict built from the callback signature. | `discord/ext/commands/core.py:548` |
| `!help <cmd>` renders `command.signature`, which returns `command.usage` verbatim when set. | `core.py:1207-1211`, [help.py](../juliabot/cogs/help.py) `_command_embed` |
| Help lists whatever `cog.walk_commands()` yields, filtered by `brief`/`aliases`/checks. | [help.py](../juliabot/cogs/help.py) `_visible_commands` |
| No `aiohttp` error handling exists → a 404 currently surfaces as `Erro: <repr>`. | [error_handler.py](../juliabot/cogs/error_handler.py) |
| Test drift guard only scans `cls.__dict__`, so generated commands escape it silently. | [test_cog_commands.py](../tests/unit/test_cog_commands.py) `_collect_defined_commands` |
| Tests swap `animes_module.AioJikan` for a 2-method fake. | [test_cog_commands.py](../tests/unit/test_cog_commands.py) `_make_animes_cog` |

### Surface census (jikan4 1.0.0)

| Family | Count | Examples |
|--------|------:|----------|
| anime | 26 | `get_anime`, `get_anime_themes`, `get_anime_stacks`, `search_anime`, `get_anime_deleted` |
| manga | 18 | `get_manga`, `get_manga_reviews`, `search_manga` |
| character | 9 | `get_characters`, `get_character_voices` |
| person | 8 + 1 | `get_person`, `get_people` |
| season | 6 | `get_seasons`, `get_seasons_now`, `get_schedules` |
| producer | 5 | `get_producers`, `get_producer_external` |
| top | 5 | `get_top_anime`, `get_top_reviews` |
| random | 4 | `get_random_anime`, `get_random_person` |
| article / genre / news | 3 each | `get_articles`, `get_genres_anime`, `get_news` |
| recommendation / review / stack | 2 each | `get_recommendations_anime`, `get_reviews_manga`, `get_stacks` |

### Response shapes (drives the renderer)

| Shape | Models | Renderer |
|-------|-------:|----------|
| `data: list` + `pagination` | 30 | paginated items |
| `data: list`, no pagination | 12 | single-page (chunked) list |
| `data: object` | 7 | key/value embed |
| no `data` (root entity) | 9 | entity embed |
| anything else / too large | — | fenced JSON, then `.json` attachment |

---

## 3. Design

### 3.1 Registry — `juliabot/jikan_catalog.py`

Single source of truth, produced by a function so the producer can be swapped
later (introspection → `jikan4.spec`) without touching consumers.

```python
@dataclass(frozen=True)
class RouteSpec:
    route: str                  # AioJikan method name
    name: str                   # command name
    group: str                  # "anime" | "manga" | "catalog"
    brief: str
    description: str
    params: tuple[ParamSpec, ...]
    positional: tuple[str, ...] = ()   # derived: "q"/"query"
    aliases: tuple[str, ...] = ()
    hidden: bool = False
    curated: bool = False       # hand-written command already covers it
    renderer: str = "auto"      # "auto" | "embed" | "debug"
    cooldown: tuple[int, int] = (1, 5)

@dataclass(frozen=True)
class ParamSpec:
    name: str
    annotation: type            # int | float | bool | str
    required: bool
    default: object = None

def load_specs() -> tuple[RouteSpec, ...]: ...
```

`load_specs()` details:

- Enumerate `jikan4.AioJikan` public coroutine methods (skip `close`, skip
  dunders).
- Read `inspect.signature` (skip `self`), keep only `POSITIONAL_OR_KEYWORD`
  params (there are no `*args`/`**kwargs` on the client), normalize
  `X | None` to `X` + optional.
- `brief` = first line of `inspect.getdoc`.
- `description` = full docstring (trimmed).
- `name` = route minus the leading `get_` (`get_anime_themes` → `anime_themes`);
  `search_*` keeps its name.
- Apply `POLICY` overrides (below), then assert uniqueness of names + aliases.
- Deterministic ordering (family, then name) so `!help` output is stable.

`POLICY: dict[str, RoutePolicy]` holds only what cannot be derived:

| Route | Policy |
|-------|--------|
| `get_anime` | name `anime_info` (free the `anime` alias, which belongs to `search_anime`) |
| `get_manga` | name `manga_info` (symmetry with `anime_info`) |
| `search_anime` | `curated=True` — the hand-written command in the animes cog owns it |
| `get_anime_deleted`, `get_anime_unapproved`, `get_anime_denied` | `hidden=True` |
| `get_manga_deleted`, `get_manga_unapproved`, `get_manga_denied` | `hidden=True` |
| `get_anime_ids`, `get_manga_ids`, `get_character_ids`, `get_person_ids`, `get_producer_ids` | `hidden=True`, `renderer="debug"` (bulk dumps) |
| `get_random_anime`, `get_random_manga`, `get_random_character`, `get_random_person` | `renderer="embed"` |
| `get_anime_themes`, `get_anime_videos`, `get_anime_statistics`, `get_anime_moreinfo`, `get_manga_moreinfo`, `get_manga_statistics` | `renderer="embed"` |
| `get_anime`, `get_seasons_now`, `get_schedules`, `get_top_anime`, `get_random_anime`, `get_characters` | short aliases (`ani`, `now`, `sched`, `ta`, `ra`, `chars`) |

The positional search term is derived, not policy: a route's `q`/`query`
parameter joins the required parameters as a positional, so `!search_manga
naruto` and `!characters luffy` work without naming the key.

Everything else keeps the derived name, no alias, `auto` renderer.

**Note on "never touch the bot again":** with a new route added upstream, a new
command appears automatically. What stays manual, by necessity, is *polish*
(alias, pt-BR wording, a nicer embed) and *placement* when an entirely new
resource family appears.

### 3.2 Command generation — `juliabot/jikan_commands.py` + per-family cogs

The helper lives outside `juliabot/cogs/` on purpose: `Client.setup_hook` loads
every `juliabot/cogs/*.py` as an extension, so a module there without a `setup`
entry point would break startup.

For each spec:

```python
def build_command(cog, spec) -> commands.Command
```

- Dispatcher is a closure: `async def _dispatch(command_cog, ctx, *, raw: str = "")`
  — one keyword-only rest parameter, so discord.py does no conversion and the
  whole argument grammar lives in our parser (§3.3). Nothing internal is
  mutated: no fabricated `inspect.Parameter`, no `exec`. Relies on the
  supported `*, arg` rest idiom, and on `Command.signature` honoring `usage`.
- The leading `command_cog` parameter is required: `Cog._inject` sets
  `command.cog`, and discord.py then invokes `callback(cog, ctx, ...)`. The
  closure's `__qualname__` is set to `"<CogClass>.<command>"` so discord.py
  skips both leading parameters when inspecting the signature, leaving only
  `raw` in `command.params`.
- `usage` is set from `spec.params` so `!help anime_themes` prints
  `anime_themes <anime_id> [sfw=bool] [sfw_strict=bool]`.
- `brief` / `description` / `aliases` from the spec; `extras={"route": spec.route}`
  so the passthrough and error messages can round-trip.
- `commands.cooldown(*spec.cooldown, commands.BucketType.user)` is applied to the
  callback before constructing the command, which is where `Command.__init__`
  reads it from.
- Parsing failures are caught inside the dispatcher and answered with the
  `JikanArgumentError` message, so `error_handler.py` needs no new branch.
- Registration in `__init__`:
  ```python
  generated = build_commands(self, load_specs(), allowlist=ROUTES_ALLOWLIST)
  self.__cog_commands__ = (*self.__cog_commands__, *generated)
  ```
  **Before** extending, each name/alias is checked against
  `bot.get_command(name)` and against the local set; on conflict it is logged
  and skipped (`logger.warning`), so a name clash can never abort cog injection.

### 3.3 Argument grammar — `juliabot/jikan_args.py`

```
!anime_themes 1
!anime_full 1 sfw=yes
!anime_stacks 1 page=2 sort=desc
!top_anime type=tv filter=bypopularity
```

Rules:

1. Tokenize `raw` on whitespace, honoring `"quoted values"` (needed for
   `query="full metal"`). A quote only opens a quoted group at a token start or
   right after `=`, so `k-on's` stays a literal value instead of failing as an
   unbalanced quote.
2. Tokens without `=` fill `spec.positional_names` in declaration order (the
   required parameters, plus the route's `q`/`query` search term); extras are an
   error (never silently dropped).
3. Tokens with `=` must match a declared param of the route; unknown key →
   error listing the valid keys.
4. Coerce by `ParamSpec.annotation`: `int`, `float`, `bool`, `str`.
   Booleans accept `yes/no`, `sim/não`, `true/false`, `1/0`, `on/off`.
   A bare boolean name is a flag (`sfw` → `sfw=True`), but only once every
   positional slot is filled, so `!search_manga sfw` still searches for "sfw".
   Bad value → error naming the key and the expected type.
5. Duplicate key / duplicate positional → error.
6. Errors are `commands.UserInputError` subclasses carrying a pt-BR message, so
   the existing error handler keeps working and the command is never half-run.

`ParamSpec` types come straight from the client annotations, so a new upstream
param is typed automatically.

### 3.4 Renderers — `juliabot/jikan_render.py`

`render(payload, spec, color) -> RenderResult` where `RenderResult` carries
`content`, `embeds` and/or `file` for one Discord message:

| Input | Output |
|-------|--------|
| `data: list` (with or without `pagination`) | bullet pages, at most 10 embeds, footer with `N resultado(s) • página i/N` plus the API page/`has_next_page` note |
| `data: object` | key/value embed; empty values and empty nested models are dropped |
| root entity (`Anime`, `Character`, `StackDetail`, …) | title, url, thumbnail, synopsis, then fields in a curated order (`type`, `episodes`, `status`, `score`, `rank`, `members`, …) before the remaining keys |
| `renderer="debug"` or an unstructured payload | inline fenced JSON up to 1900 chars, `.json` attachment above that |

Navigation over paginated results is **not** part of this step: a paginated
route renders its current API page and the caller passes `page=` to move. The
button pagination lands in step 6.

The renderer never raises: an unexpected payload (or a bug in a branch) falls
back to the JSON path, because a rendering problem must not fail the command.

Item rendering handles both model items and primitives (`*_ids` returns ints,
`SeasonCalendar` returns season objects).

Discord budgets enforced by the renderer: title 256, description 4096, field
value 1024, 25 fields, footer 2048, at most 10 embeds per message.

`model_dump()` is used with an `hasattr(obj, "model_dump")` fallback to `.dict()`
so a pydantic v1 install cannot break rendering.

### 3.5 Errors and rate limiting — `juliabot/jikan_errors.py`

`call_route(client, spec, kwargs)` wraps the coroutine and translates:

| Exception | Message |
|-----------|---------|
| `aiohttp.ClientResponseError` 404 | `Não encontrei nada com esse id/critério.` |
| 429 | `A API do MyAnimeList está limitando as requisições. Tente em Xs.` |
| 5xx | `A API do MyAnimeList está instável agora.` |
| `asyncio.TimeoutError` | `A consulta demorou demais e foi cancelada.` |
| `aiohttp.ClientError` | `Não consegui falar com a API do MyAnimeList.` |

Rate limits:

- `AsyncLimiter` inside the client already caps the **per-IP** budget; there is
  exactly one client (§Decision 7), so the budget is not double-spent.
- Per-user `commands.cooldown` (default 1/5s) protects the shared budget from a
  single user.
- 429 is surfaced, never retried in a loop (the limiter already paces us).

### 3.6 Cog layout

| Cog | Title | Contents | Count |
|-----|-------|----------|------:|
| `animes` *(existing, untouched)* | `:japanese_goblin:Animes.` | curated: `search_anime`, `anime_list`, `add_anime`, `set_anime_lang`, `anime_channel`, `set_anime_channel` | 6 |
| `anime_api` *(new)* | `Animes (API).` | generated `get_anime_*` | 25 |
| `manga` *(new)* | `Mangás.` | generated `get_manga_*` + `search_manga` | 18 |
| `mal` *(new)* | `MyAnimeList.` | characters, people, persons, producers, seasons, schedules, top, genres, magazines, articles, news, reviews, recommendations, random, stacks | 53 |

`mal` holds ~53 tokens (~1.1k chars) → the existing `_cog_fields` splitter emits
two continuation fields and `_chunk_cogs` gives it its own help page, which is
already handled. `hidden=True` routes are excluded from the listing, so the
visible count is lower.

Rationale for four cogs rather than one: a single cog with 96 tokens produces an
unreadable wall, and `_chunk_cogs` would give it a page of its own while the
other cogs' pages shrink. Four cogs keeps `!help` at ~2–3 pages and mirrors how
people look things up.

### 3.7 Passthrough — `!jikan`

Kept, and public:

- `!jikan <route> [k=v ...]` — resolve `route` against `load_specs()`; if the
  route is unknown, suggest the closest names.
- `!jikan --list [family]` — paginated list of routes + `brief`.
- `!jikan --schema <route>` — parameters, types, defaults, docstring.
- Hidden routes are reachable here, but only for the bot owner.

This is what makes "zero bot changes" literally true even for a route the
generator skipped due to a name collision, and it is the debugging hatch when an
upstream route returns an unexpected shape.

### 3.8 What is automatic vs. what needs a human

| Upstream change | Bot action needed |
|-----------------|-------------------|
| new param on an existing route | none |
| new route in an existing family | none (new command appears) |
| new resource family | place it in a cog + a `POLICY` group (one line) |
| route removed / renamed | `POLICY` entry goes stale → completeness test fails, pointing at it |
| nicer wording/alias/embed | always human (and that is fine) |

---

## 4. Branch and commit strategy

Epic branch `epic/jikan-command-generation` off `main`. Every feature branch is
cut from the epic branch and merged back with `--no-ff`, so each step stays
visible on the epic's history. One commit per logical step; no squashing inside
a feature branch.

```
main
└── epic/jikan-command-generation          (epic; only merge commits + the plan)
    ├── feat/jikan-route-catalog           2 commits
    ├── feat/jikan-argument-parser         2 commits
    ├── feat/jikan-command-generator       2 commits
    ├── feat/jikan-renderers               2 commits
    ├── feat/jikan-errors-and-limits       1 commit
    ├── feat/jikan-api-cogs                3 commits
    ├── feat/jikan-passthrough             1 commit
    └── docs/jikan-commands                1 commit
```

Final: PR `epic/jikan-command-generation` → `main`. Merge with `--no-ff` so every
step commit under the epic stays greppable from `main`.

---

## 5. Steps

Every step ends with: `black`, `isort`, targeted `pytest`, and a green full
`pytest` before it is merged into the epic.

### Step 0 — epic branch and this plan
Commit: `docs: add plan for generated Jikan commands (#5)`

### Step 1 — `feat/jikan-route-catalog`
| Commit | Contents |
|--------|----------|
| `feat(jikan): add route catalog built from AioJikan` | `juliabot/jikan_catalog.py` (`RouteSpec`, `ParamSpec`, `POLICY`, `load_specs`) |
| `test(jikan): cover catalog completeness and policy` | `tests/unit/test_jikan_catalog.py`; pin `jikan4>=1.0,<2.0` in `requirements.txt` |

Tests:
- one spec per public `AioJikan` coroutine (excluding `close`);
- `spec.route` resolves to a coroutine on the client;
- names and aliases are unique across the catalog;
- every `POLICY` key resolves to a real route (**stale-policy guard**);
- `get_anime` does not produce the name/alias `anime`;
- `search_anime` is flagged `curated` so the generator skips it;
- hidden routes match the policy, bulk dumps use the debug renderer;
- parameters use only supported types and required ones precede optional ones;
- `positional_names` / `usage` render the search term and `key=value` params;
- duplicate labels, stale policy and unknown renderers raise.

Nothing is registered → zero behaviour change, safe to land first.

### Step 2 — `feat/jikan-argument-parser`
| Commit | Contents |
|--------|----------|
| `feat(jikan): parse positional and key=value command arguments` | `juliabot/jikan_args.py` |
| `test(jikan): cover argument parsing` | `tests/unit/test_jikan_args.py` |

Tests: positional fill, `k=v` coercion for each type, quoted values (including
an apostrophe inside a value), unknown key, missing required, duplicate key,
overflow positional, bool spellings and bare boolean flags.

Deliberate scope: the parser returns only the arguments the user supplied and
raises `JikanArgumentError` (a `commands.UserInputError`); the generated
commands in step 3 catch it and answer with the message, so
`error_handler.py` stays untouched.

### Step 3 — `feat/jikan-command-generator`
| Commit | Contents |
|--------|----------|
| `feat(jikan): generate commands from the route catalog` | `juliabot/jikan_commands.py` (`build_command(s)`, collision guard) and `juliabot/cogs/anime_api.py` with `ROUTES_ALLOWLIST = {"get_anime_themes"}` |
| `test(jikan): register generated commands with help metadata` | `tests/unit/test_jikan_commands.py`; new cog added to the cog smoke and drift lists |

Tests: command registered on the cog; `brief`/`description`/`aliases`/`usage`
populated; `command.params` holds only the rest parameter; dispatcher calls the
route with parsed kwargs; argument errors answer without calling the API; name
clashes (existing command or duplicate in the batch) are skipped without
raising; oversized payloads are split under the 2000-char limit; a real
`commands.Bot` registers the command and survives a reload.

Also in this step, `AnimesCog` reuses `bot.jikan` instead of always creating a
client, because `anime_api` loads first (alphabetically) and two clients would
mean two per-IP rate limiters.

### Step 4 — `feat/jikan-renderers`
| Commit | Contents |
|--------|----------|
| `feat(jikan): render list, object and entity payloads` | `juliabot/jikan_render.py`; the dispatcher renders instead of dumping JSON |
| `test(jikan): cover renderer branches with a mocked _get` | list (paginated, flat, primitives, empty), object, entity, debug JSON, attachment, broken payload, plus one real `AioJikan` call with `_get` mocked |

Step 6 note: `anime_api` is created in step 3, so this step only swaps the
response path.

### Step 5 — `feat/jikan-errors-and-limits`
Commit: `feat(jikan): translate API errors and enforce cooldowns`
— `juliabot/jikan_errors.py` + tests for 404/429/5xx/timeout/connection and the
cooldown decoration.

### Step 6 — `feat/jikan-api-cogs`
| Commit | Contents |
|--------|----------|
| `feat(jikan): add generated anime API cog` | `juliabot/cogs/anime_api.py` |
| `feat(jikan): add generated manga cog` | `juliabot/cogs/manga.py` |
| `feat(jikan): add generated MAL catalog cog` | `juliabot/cogs/mal.py`; `ROUTES_ALLOWLIST` emptied |

Includes `GenericRoutePagination` (`resumable=True`, rebinds `bot.jikan` on
`hydrate` like `_bind_runtime`) and the help-page sanity assertions.

### Step 7 — `feat/jikan-passthrough`
Commit: `feat(jikan): add !jikan passthrough with list and schema`
— `!jikan <route> [k=v]`, `--list`, `--schema`, owner-only hidden routes.

### Step 8 — `docs/jikan-commands`
Commit: `docs: document generated Jikan commands`
— README `Commands` section, `!help` wording, the generated-command contract
(what is automatic), and the `k=v` grammar.

### Step 9 (optional, separate repo) — `mdabessa/jikan4` `feat/route-spec`
Add `jikan4/spec.py` carrying API facts only (path, param descriptions,
response model, `paginated`), plus a package-side completeness test. Release
1.1.0. Then a bot follow-up `feat/jikan-package-spec` swaps `load_specs()`'s
producer and keeps introspection as fallback, giving generated commands proper
per-parameter descriptions. Not required for any acceptance criterion below.

---

## 6. Verification

Per step:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_jikan_catalog.py -q
.\.venv\Scripts\python.exe -m black --check juliabot tests
.\.venv\Scripts\python.exe -m isort --check-only --profile black juliabot tests
```

Before merging the epic: full `.\.venv\Scripts\python.exe -m pytest -q`.

Manual smoke (guild with `TEST_MODE=true`):

1. `!help !anime_api` — generated commands listed with aliases.
2. `!anime_themes 1` — list/object render.
3. `!anime_info 999999999` — friendly 404.
4. `!anime_stacks 1 page=2 sort=desc` — `k=v` path.
5. `!top_anime type=tv` — no positional required.
6. `!jikan --list`, `!jikan --schema get_anime_stacks`.
7. `!reload` twice — no duplicate-registration failure, no lost commands.
8. `!sessions` during an open paginated route — payload is JSON-only.

---

## 7. Risks and mitigations

| Risk | Mitigation |
|------|-----------|
| One colliding alias kills the whole cog (`_inject` rollback) | Pre-flight check per name and alias; skip + warn (§Decision 10) |
| Help becomes an unreadable wall | 4 cogs, `hidden` set excluded, `--list` paginated |
| Double per-IP rate limit | Single shared client (§Decision 7) |
| `jikan4` upgrade silently changes a signature | Catalog is built from the live signature, so commands follow; the stale-policy test catches removals |
| Renderer surprises on new models | Shape-driven, not route-driven; fenced JSON fallback always works |
| Tests break because the existing fake client has 2 methods | Generator tolerates partial clients; new tests use a 3-method fake |
| `.venv` runs Python 3.14 while `.python-version` says 3.10 | Generated code stays 3.10-compatible (no 3.11+ syntax); the interpreter mismatch itself is a separate hygiene item, not part of this epic |
| pydantic v1 install (requirements does not pin it) | `model_dump` / `.dict()` fallback |

---

## 8. Acceptance criteria map (issue #5)

| Criterion | Covered by |
|-----------|-----------|
| Route registry as single source of truth | Step 1 — `juliabot/jikan_catalog.py` |
| Every public `AioJikan` method reachable through a command | Step 6 (generated) + Step 7 (passthrough) + Step 3 (hidden routes) |
| `!help` lists new commands with `brief`/`aliases` | Steps 3, 6, 8 |
| Invalid `mal_id`, 404 and 429 return friendly messages | Step 5 |
| Cooldowns and per-IP rate limit respected | Steps 3, 5, 6 |
| Tests: registry completeness, help metadata, renderer with mocked `_get` | Steps 1, 3, 4 |
| README / `!help` documentation | Step 8 |

---

## 9. Out of scope

- Curated embeds for anything beyond `search_anime` / `anime_list` (a "make the
  top 10 routes pretty" task can follow the epic).
- Slash commands / app command tree.
- Caching Jikan responses.
- Migrating the anime notifier or anything scraping-related.

---

## 10. Resolved open questions (record)

1. **Adapter now**, package spec later (§9). The 1.0.0 update means the adapter
   already covers the full surface, so blocking on a package release would buy
   only better parameter descriptions.
2. **`k=v` and positional, together** (§3.3) — required params positional,
   optional params by name. Pure positional is unusable at 19 params
   (`search_manga`); pure `k=v` is noisy for the common `!anime_themes 1`.
3. **Hidden**, not owner-only (§Decision 3) — no new permissions to configure
   and `!help` stays honest; the passthrough still reaches them.
4. **Cogs split by family** (§3.6).
5. **jikan4 1.0.0 surface** is the target: 97 routes, 1:1 with `jikan4.routes`.
