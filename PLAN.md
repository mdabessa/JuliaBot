# Plan — Mirror one-shot Discord reminders to a Nextcloud calendar

Epic branch: `epic/nextcloud-reminder-sync`

Every `!rm` (one-shot reminder) also creates one event in an **existing**
Nextcloud calendar, so the reminder is visible on every device that syncs with
Nextcloud. The calendar never writes back: Discord stays the only place a
reminder is created, delivered and removed. Forgetting to implement "remove" is
deliberate — the UID convention below keeps that door open at zero cost.

Status: **implemented on `epic/nextcloud-reminder-sync`** (steps 2–5). The prerequisite
`fix/reminder-utc` (PR #13) must land in `main` before the epic merges, and `main` must then be
merged into the epic.

---

## 1. Decisions (resolved)

| # | Question | Decision |
|---|----------|----------|
| 1 | Direction of the sync | **Discord → Nextcloud only.** The calendar is never read. |
| 2 | Which commands are mirrored | **`rm` only.** `rml` is untouched and out of scope. |
| 3 | Deletion | **Not implemented.** `rm` writes; nothing removes. See §3.8. |
| 4 | Whose reminders | **Owner *user* filter** — `REMINDER_CALENDAR_USER_ID`. Not a guild filter. |
| 5 | Target calendar | An **existing** calendar, selected by its display name and resolved to a href at runtime (§3.3). |
| 6 | UTC/date correctness | **Separate PR, merged first.** Enumerated in §5 Step 1; this epic is cut from `main` after it lands. |
| 7 | Duplicate notifications | **Accepted.** The bot notifies as today; Nextcloud/phone may notify too. |
| 8 | Alarm inside the event | **None.** No `VALARM` is written; each calendar's own default reminder applies. |
| 9 | Failure policy | **Best effort.** A Nextcloud timeout or outage must never break `!rm`. |
| 10 | Idempotency | `UID` derived from the reminder row id + `If-None-Match: *` on `PUT`. |

Supporting decisions taken while writing this plan:

| # | Decision | Why |
|---|----------|-----|
| 11 | **No schema change.** The event text is built from `ctx.message.content` at creation time. | `Reminder` has no text column; adding one is only needed if events must ever be re-synced (§3.8). |
| 12 | **Feature-flagged by configuration.** Enabled only when all four `NEXTCLOUD_*` variables are set. | Tests, local runs and any other deployment stay untouched; no half-configured state. |
| 13 | **`aiohttp`, not `requests`.** | The hook runs on the event loop; `requests` would block it. `aiohttp` is already installed as a discord.py dependency, and gets pinned explicitly. |
| 14 | Event is **zero-length** with `DTSTART` in UTC. | Matches "a moment in time". No `DTEND` means no busy block and no fake 15-minute meeting. |
| 15 | **App password**, never the account password. | Works with 2FA, and can be revoked on its own. |

---

## 2. Current state (verified)

| Fact | Evidence |
|------|----------|
| `Reminder` stores `server_id, channel_id, message_id, user_id, time_created, time_reminder, date_command` — **no text column**. The body is the Discord message refetched by id. | [models.py](juliabot/models.py) — `class Reminder`; [reminder.py](juliabot/cogs/reminder.py) `message.reply(...)` |
| `time_reminder` is `Column(DateTime)` → `TIMESTAMP WITHOUT TIME ZONE`, so an aware UTC value is stored with its offset dropped. | [models.py](juliabot/models.py) — `time_reminder = Column(DateTime, nullable=False)` |
| `reminder` is a **legacy** table: `init_db()` only creates tables and adds missing columns, it never changes a type. | [models.py](juliabot/models.py) — `MIGRATION_MANAGED_TABLES = frozenset({"session"})`, `init_db` |
| A versioned migration framework exists, with a dialect-aware timestamp helper. | [migrations/runner.py](juliabot/migrations/runner.py), [versions/0001_create_session.py](juliabot/migrations/versions/0001_create_session.py) |
| `get_expired()` compares an **aware** `now` against a **naive** column. | [models.py](juliabot/models.py) — `cls.time_reminder <= now` |
| `get_date_str()` / `get_created_str()` / the `rml` preview call `.astimezone()` on values read from the database. | [models.py](juliabot/models.py), [embeds/reminder.py](juliabot/embeds/reminder.py) |
| `.astimezone()` applied to a **naive** value assumes host-local time — correct only while the host runs UTC. | same sites; reproduced reasoning in §3.1 |
| Naive `datetime.now()` followed by `.astimezone(tz)` is **correct** (it round-trips to the true instant). | [core.py](juliabot/cogs/core.py) `current_time`, [converters.py](juliabot/converters.py) default `start` |
| `Model.__init__` commits immediately, so `reminder.id` exists as soon as the constructor returns. | [models.py](juliabot/models.py) — `session.add(self); self.update()` |
| `Model.__init__` and `delete()` are synchronous. | same file |
| The bot has **no inbound HTTP**: the Procfile declares no `web:` process. | [Procfile](Procfile) |
| Nextcloud calendar reminders support **email** and **Nextcloud notifications**; there is no "call a URL at event time". | Nextcloud user manual, Calendar → Set up reminders |
| CalDAV principal: `https://<host>/remote.php/dav/principals/users/<user>/`; calendars live under `.../dav/calendars/<user>/<calendar>/`. | Nextcloud user manual, Synchronizing with iOS |
| Credentials should be an **app password**: Settings → Security → Devices & sessions. | same page |
| `aiohttp` is installed (discord.py dependency) but not declared; `requests` is declared. | [requirements.txt](requirements.txt) |

---

## 3. Design

### 3.1 Prerequisite — UTC correctness (separate PR)

This epic does not fix timekeeping; it depends on it. The event's `DTSTART` is an
**absolute instant**, so a reminder stored 3 hours off is mirrored 3 hours off.
The prerequisite PR (`fix/reminder-utc`) makes the storage unambiguous:

1. `time_reminder` becomes `Column(DateTime(timezone=True))` plus migration
   `0002`, which reinterprets the existing naive values as UTC:

   ```sql
   ALTER TABLE reminder
     ALTER COLUMN time_reminder TYPE timestamp with time zone
     USING time_reminder AT TIME ZONE 'UTC';
   ```

   No-op outside PostgreSQL (SQLite cannot `ALTER COLUMN TYPE`).
2. One `as_utc(value)` helper, used at every read boundary, so Postgres (aware)
   and SQLite (naive) behave identically: a naive value is **UTC**, never host
   local.
3. `get_expired()` compares two aware values — removing the dependence on the
   Postgres session `TimeZone` setting, which is what silently shifts every
   reminder after a host migration.
4. `Server.get_timezone()` falls back to UTC when the row or the field is
   missing, instead of raising `AttributeError` / `pytz.timezone(None)` at six
   call sites.
5. The heartbeat is stored as ISO-8601 UTC (reading the legacy format during a
   transition), instead of a local wall-clock string compared with `.seconds`.

Accepted invariant after this PR: **every `datetime` that crosses a module
boundary is aware and in UTC.** The server timezone is a *display* concern only.

### 3.2 Event shape — `juliabot/nextcloud.py`

```
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//JuliaBot//reminder//EN
BEGIN:VEVENT
UID:juliabot-reminder-42@juliabot
DTSTAMP:20261109T120000Z
DTSTART:20261109T150000Z
SUMMARY:Lembrete: pagar aluguel
DESCRIPTION:Criado por !rm em #geral
 https://discord.com/channels/10/20/1000
END:VEVENT
END:VCALENDAR
```

| Field | Source | Notes |
|-------|--------|-------|
| `UID` | `juliabot-reminder-<reminder.id>@juliabot` | stable, derived from the PK |
| `DTSTAMP` | now, UTC | RFC 5545 requires it |
| `DTSTART` | `as_utc(reminder.time_reminder)` | formatted `%Y%m%dT%H%M%SZ`; no `DTEND` ⇒ zero length |
| `SUMMARY` | `ctx.message.content`, first line, escaped, clipped to ~120 chars | prefix `Lembrete: ` |
| `DESCRIPTION` | channel name + a `discord.com/channels/...` permalink | lets the phone jump back to the conversation |

Two details that are easy to get wrong and are handled in the builder:

- **Text escaping** for `\`, `;`, `,` and newlines (RFC 5545 §3.3.11), before
  clipping — clipping first can cut an escape sequence in half.
- **Line folding** at 75 octets (§3.1), so long summaries/permalinks stay valid.

`build_event(...) -> str` is pure: no clock, no I/O, no config. `DTSTAMP` is
passed in, so the golden test is deterministic.

### 3.3 Resolving the calendar

The user names the calendar; CalDAV needs a href, and the href's id is an opaque
slug that can change if the calendar is renamed or recreated.

1. `PROPFIND` `Depth: 1` on `/remote.php/dav/calendars/<user>/` asking for
   `{DAV:}displayname` and `{DAV:}resourcetype` (calendars only).
2. Match `displayname` against `NEXTCLOUD_CALENDAR`, exactly then
   case-insensitively.
3. Cache the resolved href for the process lifetime; resolve lazily on the first
   mirrored reminder, not at import time.
4. Zero matches → log the available names once and disable the mirror.
   More than one match → log and disable rather than guess.

### 3.4 Module layout

`juliabot/nextcloud.py`:

| Symbol | Responsibility |
|--------|----------------|
| `build_event(uid, start, summary, description, stamp) -> str` | pure iCalendar text |
| `escape_text(value)` / `fold_line(line)` | RFC 5545 helpers |
| `NextcloudConfig.from_env() -> NextcloudConfig \| None` | `None` when incomplete ⇒ feature off |
| `CalendarClient(session, config)` | `resolve_calendar()`, `put_event(uid, ics)` |
| `publish_reminder(client, reminder, message) -> None` | orchestration used by the cog |

The client takes an `aiohttp.ClientSession` (or a fake) by injection, so no test
touches the network. Writes use `PUT <href><uid>.ics` with
`If-None-Match: *`, so a re-run is a benign `412` instead of a duplicate.

### 3.5 Hook

In `AnimesCog`'s sibling, `_ReminderCog.remind_me`, immediately after
`Reminder(...)` returns (the row and its id already exist):

```
if reminder.user_id == config.owner_id and config.enabled:
    asyncio.create_task(publish(reminder, ctx))   # fire and forget
```

- The reply to the user is **not** awaited on Nextcloud.
- The task swallows and logs every exception (`logger.warning`, with the
  reminder id), including `asyncio.TimeoutError` at 5 s.
- A task reference is kept in a set and discarded on completion, so the task
  cannot be garbage-collected mid-flight.

### 3.6 Configuration

| Variable | Meaning |
|----------|---------|
| `NEXTCLOUD_URL` | e.g. `https://cloud.example.com` |
| `NEXTCLOUD_USER` | Nextcloud login |
| `NEXTCLOUD_APP_PASSWORD` | from Settings → Security → Devices & sessions |
| `NEXTCLOUD_CALENDAR` | display name of an **existing** calendar |
| `REMINDER_CALENDAR_USER_ID` | Discord user id whose reminders are mirrored |

All five present ⇒ enabled. Credentials are never logged; the URL and calendar
name are.

### 3.7 Testing

| Level | Coverage |
|-------|----------|
| Pure | `build_event` golden file; escaping (`;` `,` newline, backslash); folding; summary clipping; `DTSTART` is UTC regardless of the process TZ |
| Client | fake `aiohttp` session: href resolution happy path / no match / ambiguous; `PUT` uses `If-None-Match: *`; `412` is treated as success |
| Cog | `!rm` from the owner schedules a publish; a non-owner does not; a raising publisher still leaves `!rm` replying normally |
| Config | incomplete env ⇒ disabled; complete env ⇒ enabled |

No test performs network I/O or reads the host timezone.

### 3.8 What this deliberately does not do

- **No removal.** `!rm` creates; deleting a reminder, or deleting the event, is
  not mirrored. The UID gives a future "remove" a handle for free: `DELETE
  <href><uid>.ics`.
- **No updates.** An existing UID is left alone (`412`). Re-syncing would need
  the message text, which is not stored (§1 #11).
- **No `rml`.** Recurring reminders carry a free-form `date_command`, not an
  `RRULE`; mapping it would be a separate design.
- **No calendar → Discord.** Nothing is read; the next Nextcloud edit is invisible
  to the bot.
- **No notification channel.** No webhook, no `VALARM`, no email template.

---

## 4. Branch and commit strategy

Prerequisite PR first, then the epic. The epic is cut from `main` **after**
`fix/reminder-utc` is merged, so the mirror never ships on top of the timezone
bug.

```
main
├── fix/reminder-utc                        5 commits   (separate PR)
└── epic/nextcloud-reminder-sync            (epic; plan + merge commits)
    ├── feat/nextcloud-ical-builder         1 commit
    ├── feat/nextcloud-caldav-client        2 commits
    ├── feat/reminder-calendar-sync         2 commits
    └── docs/nextcloud-config               1 commit
```

Every feature branch is cut from the epic and merged back with `--no-ff`, so each
step stays visible. One commit per logical step; no squashing inside a feature
branch. Final: PR `epic/nextcloud-reminder-sync` → `main`, also `--no-ff`.

---

## 5. Steps

Every step ends with `black`, `isort`, the targeted `pytest`, and a green full
`pytest` before it is merged into the epic.

### Step 0 — epic branch and this plan
Commit: `docs: add plan for one-way Nextcloud reminder sync`

### Step 1 — `fix/reminder-utc` (separate PR, merged before the epic)

| Commit | Contents |
|--------|----------|
| `fix(time): store reminder times as timestamptz` | `0002` migration with `USING ... AT TIME ZONE 'UTC'`; model column type; migration tests |
| `fix(time): treat naive database timestamps as UTC` | `as_utc()` helper; `get_date_str`, `get_created_str`, `embeds/reminder.py`; tests |
| `fix(time): compare reminders against an explicit UTC now` | `get_expired()`; fake-clock test |
| `fix(config): fall back to UTC when a server has no timezone` | `Server.get_timezone()` + the six call sites |
| `fix(health): store the heartbeat as ISO-8601 UTC` | `core.py` + `__main__.py`, reading the legacy format |

### Step 2 — `feat/nextcloud-ical-builder`

| Commit | Contents |
|--------|----------|
| `feat(nextcloud): build iCalendar events for reminders` | `juliabot/nextcloud.py` builder + escaping/folding; golden and edge-case tests |

### Step 3 — `feat/nextcloud-caldav-client`

| Commit | Contents |
|--------|----------|
| `feat(nextcloud): read Nextcloud settings from the environment` | `NextcloudConfig`, feature flag, README env rows |
| `feat(nextcloud): resolve a calendar and publish events` | `CalendarClient` (PROPFIND resolution, cached href, `PUT` with `If-None-Match`), fake-session tests |

### Step 4 — `feat/reminder-calendar-sync`

| Commit | Contents |
|--------|----------|
| `feat(reminder): publish one-shot reminders to the calendar` | hook in `remind_me`, owner filter, fire-and-forget task, failure tolerance |
| `test(reminder): cover the calendar mirror for owner and non-owner` | cog-level tests with a fake client |

### Step 5 — `docs/nextcloud-config`

| Commit | Contents |
|--------|----------|
| `docs: document the Nextcloud reminder mirror` | README feature bullet + configuration section |

---

## 6. Acceptance criteria

- [ ] `!rm` from the owner creates exactly one event with `UID
      juliabot-reminder-<id>@juliabot` in the configured existing calendar.
- [ ] Re-running the publish for the same reminder id does not duplicate it.
- [ ] `!rm` still replies and still stores the reminder when Nextcloud is
      unreachable, slow, or returns an error.
- [ ] `!rm` from a non-owner user creates no event.
- [ ] The event `DTSTART` equals the stored reminder instant in UTC and does not
      depend on the process timezone.
- [ ] No `VALARM`, no `DTEND`, no attendee, no busy block.
- [ ] `rml` and the reminder loop behave exactly as before.
- [ ] Nothing reads the calendar; no `web:` process is added to the Procfile.
- [ ] Missing configuration leaves the feature off and the bot unchanged.
- [ ] Full `pytest` green; the prerequisite PR merged first.

## 7. Risks

| Risk | Mitigation |
|------|------------|
| A reminder stored with the wrong instant is mirrored wrongly | Prerequisite PR + a test asserting `DTSTART` is UTC regardless of process TZ |
| Calendar href changes (renamed/recreated calendar) | Resolve lazily and cache; log the available names when resolution fails |
| A slow Nextcloud stalls `!rm` | Fire-and-forget task, 5 s timeout, exceptions swallowed and logged |
| Event text contains iCalendar metacharacters | Escaping before clipping, covered by tests |
| Secrets leak into logs | Only URL and calendar name are logged; the password never is |
| Writing into the user's personal calendar by mistake | Explicit `NEXTCLOUD_CALENDAR` display-name match; ambiguity disables the mirror instead of guessing |

## 8. Verification (manual)

1. Point the four variables at a scratch calendar and create a reminder a few
   minutes ahead: the event must appear with the right local time.
2. Run the bot once with `TZ=UTC` and once with `TZ=America/Sao_Paulo` against
   the same database: `!time` and `!list_reminders` must print identical values,
   and the mirrored `DTSTART` must not change.
3. Stop Nextcloud (or use a bogus host): `!rm` must still confirm to the user.
4. Create a reminder from a second Discord account: no event appears.

## 9. Out of scope (explicit)

Removing or updating events, `rml`/RRULE mapping, reading the calendar,
webhooks, `VALARM`, per-guild calendars, and multi-user sync. Each of these is a
separate design, not a follow-up commit in this epic.
