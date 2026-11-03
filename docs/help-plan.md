# Plan — `!help`: two-level navigation + fuzzy fallback

Branch: `feat/help-two-level-navigation`

Tracks issues **#7** and **#11**. #7 built the paginated listing; #11 records that
the listing is now drowned by the generated Jikan commands. This plan keeps the
#7 rendering work intact and changes *what page 1 shows* and *how deep the listing
goes*, so the help surface stops growing with the API surface.

Status: **plan only — no implementation started.**

---

## 1. Problem statement

### 1.1 Measured shape of the command surface

| Thing | Count | Source |
|---|---|---|
| Generated Jikan commands | **96** — `anime_api` 25, `manga` 18, `mal` 53 | `PLAN.md` §3.6, `juliabot/jikan_commands.py::build_commands` |
| Hidden routes excluded from help | 11 — 6 `_HIDDEN_ROUTES` + 5 `_BULK_DUMPS` | `juliabot/jikan_catalog.py::POLICY` |
| Hand-written commands | ~40 across ~12 cogs | `grep` of `@commands.command` in `juliabot/cogs/` |
| Cogs with visible commands | ~15 (`debug` is owner-only via `cog_check`) | `juliabot/cogs/*.py` `embed_title` |
| `COGS_PER_PAGE` | **3** | `juliabot/cogs/help.py` |
| Resulting `!help` pages | **~5–6** | 15 cogs ÷ 3, with `mal` consuming a page largely alone |

So ~70% of the command surface is generated, and it occupies roughly half the
pages. Issue #11 is a direct consequence.

### 1.2 Two facts that constrain every solution

1. **Filtering the generated cogs out is not enough.** With `COGS_PER_PAGE = 3`,
   a curated-only listing (~12 cogs) is still ~4 pages of the same dense grid.
   The fix has to change the *layout of page 1*, not only its contents.

2. **Clickable drill-down is not free in the current session framework.**
   - `PaginationSession.render()` (`juliabot/sessions/patterns/pagination.py:158`)
     calls `edit(content=None, embed=embed)` — it never passes `view=`, so buttons
     cannot be swapped per page.
   - `SessionButton`'s `custom_id` (`juliabot/sessions/transports/buttons.py::build_custom_id`)
     encodes only `sess:<session_id>:<action_name>`. There is no room for per-item
     state such as "open category `mal`".
   - `max_per_scope=1` + `Scope.CHANNEL` means starting a *second* session to drill
     down silently closes the index you came from (`SessionManager.dispatch`,
     `juliabot/sessions/manager.py:116`, returns `False` for a closed key).

   Consequence: a genuinely clickable two-level menu needs a framework change.
   This plan deliberately does **not** take one.

### 1.3 Why not the alternatives

| Option | Verdict |
|---|---|
| A. Tier filter only | Not sufficient — still ~4 pages (§1.2.1) |
| C. Select-menu menu | Needs a new transport + `render(view=...)`; deferred (§8) |
| D. `commands.Group` restructuring | Breaks invocation surface, collision guard, `!jikan` passthrough and every test; no advantage over B |
| E. Delete the 96 generated commands, keep `!jikan` only | Cheapest possible, but loses short names/aliases/cooldowns; revisit when usage data exists (§8) |

---

## 2. Decisions

| # | Decision | Why |
|---|---|---|
| 1 | **Two levels inside one session** (`help.pages`), with the existing `cog` payload key acting as the level selector | `payload["cog"]` already exists (`HelpPagination.requested_cog`). One session means `Categorias` can return to the index without hitting `max_per_scope=1`. |
| 2 | **Level 1 is a description *list*, not the 3-column grid** | A grid of 15 cogs is exactly the wall #11 complains about. One line per category fits one embed and stays scannable. |
| 3 | **Level 2 keeps the #7 dense grid, per cog** | Preserves the look that works, and drops the 3-cog page cap — a cog page only splits when a single cog outgrows an embed. |
| 4 | **Generated cogs are grouped by a new presentation attribute `help_section`** on the cog, read with `getattr(cog, "help_section", "")` | `juliabot/cogs/help.py` must not import `juliabot/jikan_commands.py` (that would pull `jikan4` into a generic help module). Duck-typed attribute, same spirit as the existing `embed_title` convention. |
| 5 | **`help_section = "API do MyAnimeList"` is declared once on `GeneratedRoutesCog`** | All three generated cogs inherit it from one line. |
| 6 | **Drill entries stay textual**: `!help <cog>` and `!help !<cog>` are unchanged, plus a `Categorias` button to go back in-session | Zero framework change. Both command forms already work today. |
| 7 | **Fuzzy fallback (option F) on a miss** using `difflib.get_close_matches` over command names, aliases and cog names | `difflib` is already the house pattern (`juliabot/cogs/jikan.py::_suggestions`). Removes the "one extra hop" sting of level 1. |
| 8 | **`hidden=True` semantics untouched** | It already means "owner-only / not for everyone". Marking generated commands hidden would hide them from owners too and conflate two policies. |
| 9 | **`!help <command>` detail embed unchanged** | It is the documented drill-down from #7 and needs no work. |
| 10 | **No changes under `juliabot/sessions/`** | Keeps the blast radius inside `cogs/help.py` + one attribute on `jikan_commands.py`. |

---

## 3. Design

### 3.1 Collecting a cog's visible commands

Existing helpers are kept as-is: `_command_label`, `_cog_title`, `_clip`,
`_cog_fields`, `_chunk_cogs`, `_visible_commands`, `resolve_prefix`.

New intermediate, so both levels agree on what is visible:

```python
@dataclass(frozen=True)
class CogEntry:
    name: str          # registered cog name, e.g. "mal"
    title: str         # embed_title, e.g. ":mag:MyAnimeList."
    section: str       # help_section, "" for hand-written cogs
    command_count: int
```

```python
async def collect_cogs(ctx) -> list[CogEntry]
```

- Walks `bot.cogs` in registration order (alphabetical) and uses
  `_visible_commands(cog, ctx)` for the count, so owner-only cogs such as `debug`
  report `0` for everyone else and disappear from the index.
- Costs one `can_run` evaluation per command (~136 total, all pure predicate
  checks, no I/O). Acceptable; do not pre-filter with `len(cog.get_commands())`,
  which would report commands the caller cannot run.

### 3.2 Level 1 — the index page

```python
async def build_help_index(ctx, prefix="!") -> list[HelpPage]
```

Returns a list (not a single page) only so an index that outgrows Discord's
4096-character description can spill. At 15 cogs it is always one page.

Description layout, grouped by `section`, empty sections omitted:

```
**Comandos**
`:brain:Core.` — 5 · `!help core`
`:game_die:Diversão.` — 2 · `!help fun`
...

**API do MyAnimeList**
`Animes (API).` — 25 · `!help anime_api`
`:books:Mangás.` — 18 · `!help manga`
`:mag:MyAnimeList.` — 53 · `!help mal`

`!help <comando>` para detalhes · `!help <categoria>` para abrir.
```

- No fields, no footer pagination when there is a single page.
- `HelpPage` gains a `kind: str` discriminator (`"index"` / `"commands"`) so
  `render_item` knows which layout to build. `fields` stays `()` for the index.
- The `Comandos` section is always emitted first, which is the mitigation for
  "common commands are now one hop away" (§7).

### 3.3 Level 2 — one cog's pages

```python
async def build_cog_pages(ctx, prefix, cog_name) -> list[HelpPage]
```

- `_visible_commands(cog, ctx)` → `_cog_fields(title, tokens)` → `_chunk_cogs`,
  but with the **3-cog cap removed** and `MAX_FIELDS_PER_PAGE` / `MAX_FIELD_VALUE`
  / `MAX_EMBED_LENGTH` still enforced.
- Embed title becomes the cog's `embed_title` (falling back to `PAGE_TITLE`), so
  level 2 is self-describing.
- Reuses `_cog_fields`' continuation-field spill for a cog that outgrows 1024
  characters in one value (`mal`'s 53 tokens land around ~900–1100 chars, so it
  may produce a `mal (1/2)`, `mal (2/2)` pair — that is the intended behaviour).
- `HelpPage.cogs` keeps holding the cog name so the existing jump logic and tests
  keep working.

### 3.4 Session

```python
class HelpPagination(PaginationSession[HelpPage]):
    extra_actions = (
        Action("index", "show_index", owner_only=False, label="Categorias"),
    )
```

- `load_items()` → `build_cog_pages(...)` when `self.requested_cog` is set, else
  `build_help_index(...)`. Payload `index` is clamped as today.
- `show_index(event)`:
  - `set_payload("cog", "")`, `set_payload("index", 0)`;
  - rebuild `self._items` through a private `_reload()` helper (the pattern only
    calls `load_items()` from `start()`/`hydrate()`, so a level switch has to
    refresh `_items` itself);
  - `await self.render()`.
- `render_item` builds the index layout when `item.kind == "index"`, otherwise the
  dense grid with `Página {i+1}/{total}` footer as today.
- Registration unchanged: `help.pages`, `COMPONENT`, `Scope.CHANNEL`,
  `max_per_scope=1`, `timeout=120`, `resumable=False`.

Known cosmetic limitation: `render()` cannot rebuild the view, so `Categorias`
is present on the index too (where it is a harmless no-op re-render). Accepted
rather than patched, because patching means touching `sessions/` (§10).

### 3.5 Command wiring

```python
async def help(self, ctx, argument: Optional[str] = None):
    if argument is None:                       # level 1
        start session with payload {"index": 0}
    if argument/argument[1:] is a command:     # unchanged detail embed
    if argument/argument[1:] is a cog:         # level 2, payload {"cog": name}
    else:                                      # F: miss + suggestions
        "Nenhum comando/categoria encontrado com o nome de `<argument>`!"
        + " Talvez você quis dizer: `a`, `b`."
```

Order is unchanged from #7: command first, cog second, so `!help ping` never
shadows a command with a same-named cog.

### 3.6 Fuzzy fallback (option F)

```python
def _suggestions(candidates: Iterable[str], query: str) -> str
```

- Candidate pool: visible command names, their aliases, cog names, cog titles.
- `difflib.get_close_matches(query, candidates, n=3, cutoff=0.6)`, rendered as
  `` Talvez você quis dizer: `a`, `b`. `` — same wording shape as
  `juliabot/cogs/jikan.py::_suggestions`.
- Best-effort: any failure to build the pool degrades to the current plain
  message rather than erroring the command.

---

## 4. Implementation slices

Each slice leaves the bot runnable and `pytest` green.

1. **Builders.** Add `CogEntry`, `collect_cogs`, `build_help_index`,
   `build_cog_pages`, `HelpPage.kind`. Keep `HelpPagination` on the old flat
   builder for this slice so only the pure-function tests move.
2. **Session level switch.** Point `load_items()` at the new builders, add
   `show_index` + `extra_actions`. Level 1 now renders the index; `!help <cog>`
   renders level 2.
3. **Section grouping.** Add `help_section = "API do MyAnimeList"` to
   `GeneratedRoutesCog` and group the index by `getattr(cog, "help_section", "")`.
4. **Fuzzy fallback.** Add `_suggestions` and wire the miss branch.

---

## 5. Test impact (explicit)

| File | Change |
|---|---|
| `tests/unit/test_help_pages.py` | `build_help_pages` disappears. Rewrite around `build_help_index` / `build_cog_pages`. Keep the budget tests (30-command cog, 26 cogs, "no command may be dropped") but retarget them at per-cog pages. The `PADDING_FIELD` / `% 3` assertions move to level 2 only. |
| `tests/unit/test_cog_commands.py::_run_help_help` | Currently asserts `field.name` contains `":question:Help."` and `field.value` contains `` `help` (ajuda) `` on page 1. Level 1 is now a description list, so this case asserts the index lists both cogs with counts and keeps `embed.title == "Lista de Comandos"`; the alias assertion moves to a per-cog case. |
| `tests/unit/test_cog_commands.py::_run_help_help_cog_jump` | Still valid (`payload["index"] == 0`, first field is the cog's title) — the embed title assertion needs to become the cog title. |
| `tests/unit/test_jikan_commands.py::test_help_lists_every_visible_generated_command_within_budget` | Today it concatenates `build_help_pages` fields. Change to: the index lists the three generated cog lines under the API section, then concatenate `build_cog_pages` for `anime_api`, `manga`, `mal` and assert every non-`hidden`, non-`curated` spec still appears and every hidden one does not. |
| New cases | `test_index_lists_every_cog_with_a_count`; `test_index_stays_one_page_with_26_cogs`; `test_index_groups_generated_cogs_under_the_api_section`; `test_cog_page_ignores_the_three_cog_cap`; `test_show_index_returns_to_level_one`; `test_unknown_argument_suggests_close_matches`; `test_unknown_argument_without_matches_keeps_the_plain_message`. |

`tests/smoke/test_cogs_smoke.py` needs no change (imports only).

---

## 6. Acceptance criteria

- `!help` sends **one** embed listing categories with command counts, one line
  per cog, curated cogs first and generated cogs under `API do MyAnimeList`.
- Page 1 does not change size when a route is added to `jikan4`.
- `!help <cog>` and `!help !<cog>` open that cog's command grid; a cog no longer
  shares a page with two others.
- `Categorias` returns to the index without closing and reopening the session.
- `!help <command>` still renders the detail embed with description, aliases and
  signature.
- `!help <unknown>` still reports "Nenhum comando/categoria encontrado…" and adds
  up to three suggestions when close matches exist.
- Commands failing `can_run` / `cog_check` (e.g. `debug` for non-owners) are
  absent from both the index counts and the cog pages; failures stay logged.
- No page exceeds 25 fields / 1024 chars per value / 6000 chars total; the index
  stays inside 4096 description characters.
- `juliabot/sessions/` is untouched.

---

## 7. Risks and trade-offs

| Risk | Assessment / mitigation |
|---|---|
| **Aliases leave page 1**, which #7 explicitly added | Accepted. Aliases remain on level 2 and in the detail embed, and the fuzzy fallback (F) covers "I half-remember the name". Revisit if it hurts. |
| **Common commands are now one hop away** | Mitigated by ordering: the `Comandos` section is first and curated cogs are cheap to scan. If it still hurts, a "Populares" line on the index is the follow-up lever. |
| **`!help` now evaluates `can_run` for every command** | ~136 predicate checks, no I/O. If it ever matters, cache per invocation — the index needs the counts anyway. |
| **Index grows with cog count** | Bounded by the description chunker; 4096 chars is ~90 lines, i.e. far more cogs than exist. |
| **`Categorias` is visible at level 1 too** | Cosmetic; it re-renders the same index. Fixing it means `render(view=...)`, see §8. |
| **Drilling by command closes the index session** (`max_per_scope=1`) | The old message correctly drops its buttons thanks to the `close()` fix from #7. The way back is `!help` or the `Categorias` button inside the drilled session. |
| **`mal`'s 53 commands may still feel long** on its own page | It is one cog, one page, with continuation fields — strictly better than sharing a page with two other cogs. |

---

## 8. Out of scope

- **Select-menu transport** (`juliabot/sessions/transports/selects.py`) and
  `render(view=...)`. This is the path to a real clickable menu, but it touches
  every session and should be its own issue.
- **Per-item buttons** ("open this command's detail") — `custom_id` has no room
  for item state.
- **Option E** — deleting the 96 generated commands in favour of `!jikan <route>`.
  Worth revisiting with usage data; `!jikan --list` already renders a better
  96-route index than `!help` can.
- **Slash-command / `app_commands` help** (also excluded by #7).
- **Search across briefs and descriptions** — F only matches names.

---

## 9. Open questions

1. Should #7 be closed as shipped before this lands, so #11 is the only tracker?
2. Do we have any signal that the 96 generated commands are invoked at all? If
   not, one week of command-usage logging would settle §8's option E far more
   cheaply than re-litigating it.
3. Index ordering inside `Comandos`: registration order (alphabetical today) or
   a hand-picked "most used first" list?

---

## 10. Appendix — facts this plan relies on

- `juliabot/cogs/help.py` — `COGS_PER_PAGE = 3`, `HELP_PAGES = "help.pages"`,
  `PAGE_TITLE = "Lista de Comandos"`, `PADDING_FIELD`, `_cog_fields`,
  `_chunk_cogs`, `_visible_commands`, `build_help_pages`, `HelpPagination`
  (`requested_cog` reads `payload["cog"]`), `HelpCog.help`.
- `juliabot/jikan_commands.py:168` — `build_commands` (skips `spec.curated`,
  logs collisions); `GeneratedRoutesCog` extends `self.__cog_commands__`.
- `juliabot/jikan_catalog.py:151` — `_HIDDEN_ROUTES`; `POLICY` adds
  `hidden=True` for 6 crawl routes + 5 bulk dumps.
- `juliabot/sessions/patterns/pagination.py:158` — `render()` edits the embed
  only, never the view.
- `juliabot/sessions/transports/buttons.py::build_custom_id` — `sess:<id>:<action>`.
- `juliabot/sessions/manager.py:116` — `dispatch` returns `False` for closed
  sessions; actions are resolved by name from `session.actions` and the handler
  must render itself.
- `juliabot/sessions/session.py` — `Action(name, handler, owner_only, label,
  emoji, style)`; `extra_actions` is a class-level tuple.
