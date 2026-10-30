# JuliaBot
JuliaBot is a Discord bot written in Python using the [discord.py](https://github.com/Rapptz/discord.py) library. It is designed to be a general purpose bot with a variety of utility and anime related features.

## Features
- Every route of the `jikan4` client exposed as a Discord command, generated at startup
- Anime, manga, and character search using the [Jikan v4 API](https://jikan.moe/)
- New animes episodes notification based on web scraping from multiple anime streaming sites
- Subscribing to anime series to receive notifications
- Reminder system for setting reminders
- Translation command
- Interactive session framework: button pagination, prompts, and per-channel message rules

## Installation
1. Clone the repository
2. Install the requirements using `pip install -r requirements.txt`
3. Create a file called `.env` in the root directory of the repository
4. Configure the `.env` file with the following variables:
    - `DISCORD_TOKEN`: The token of the Discord bot
    - `DATABASE_URL`: The URL of the PostgreSQL database
    - `PREFIX`: The prefix for the bot. Defaults to `!`
    - `ANIME_SCRAP_TIME`: The time in seconds between each web scraping for new anime episodes. Defaults to `3600`
    - `BOT_JIKAN_RATE_LIMIT`: The rate limit per minute for the Jikan API to the bot. Defaults to `50`
    - `SCRAP_JIKAN_RATE_LIMIT`: The rate limit per minute for the Jikan API to the web scraper. Defaults to `10`
5. Run the bot using `python -m juliabot`

## Commands
The help command can be used to get a list of all commands and can be passed a command name to get more information about a specific command. The prefix can be changed using the `prefix` command.

## Jikan API commands
Every route of the `jikan4` client is a Discord command. The command list is built from the
installed package at startup, so bumping `jikan4` adds the new routes as commands without touching
this repository.

The routes are split by resource family:

| Cog | Commands | Examples |
| --- | --- | --- |
| `anime_api` | 25 | `anime_info`, `anime_full`, `anime_themes`, `anime_episodes`, `anime_characters` |
| `manga` | 18 | `manga_info`, `manga_full`, `manga_news`, `manga_reviews`, `search_manga` |
| `mal` | 53 | `top_anime`, `seasons`, `schedules`, `characters`, `people`, `producers`, `genres_anime`, `articles`, `news`, `stacks` |

The hand-written anime search and watchlist commands (`search_anime`, `anime_list`, `add_anime`,
`set_anime_lang`, `anime_channel`, `set_anime_channel`) keep their own embeds and live in the
`animes` cog.

### Arguments
Required arguments come first, positionally; everything else is `key=value`:

```
!anime_themes 1
!anime_info 1
!anime_full 1 sfw=yes
!anime_stacks 1 page=2 sort=desc
!top_anime type=tv filter=bypopularity
!search_manga naruto page=2
!characters "spike spiegel"
```

Booleans accept `yes/no`, `sim/não`, `true/false`, `1/0` and `on/off`, and a bare name is a flag
(`!anime_full 1 sfw`). Values with spaces can be quoted. Route names come from the client, so
`get_anime_themes`'s command is `anime_themes`; `get_anime` is exposed as `anime_info` because `anime`
is already an alias of `search_anime`.

Routes that return a paginated list render one result at a time with `Anterior`/`Próximo`
buttons that walk the results and fetch the next API page at the boundary. Everything else renders as
an embed, and payloads that do not fit become a JSON attachment.

### Passthrough
`!jikan` reaches any route directly, including the hidden ones:

```
!jikan get_anime_themes 1
!jikan --list [anime|manga|catalog]
!jikan --schema get_anime_stacks
```

`--schema` prints the parameters, their types and defaults. Crawlable routes (`*_deleted`,
`*_unapproved`, `*_denied`, `*_ids`) are hidden from `!help` and from `--list`, and only the bot
owner can call them.

### Adding or changing routes
Nothing here needs to change when `jikan4` gains a route: the catalog is derived from the client's
signatures and response models. Only deliberate presentation choices live in
`juliabot/jikan_catalog.py`'s `POLICY` table — command renames, aliases, hidden routes and renderer
hints. See [PLAN.md](PLAN.md) for the full design.

## Testing
To run the tests, use the command `pytest` in the root directory of the repository.

## Interactive sessions
Multi-step interactions (pagination, confirmations, durable channel rules) are built on
`juliabot/sessions/`. Adding a new dialogue means declaring a session class, a `Registration`, and a
JSON-safe payload; buttons, ownership, expiry, and restart restoration are handled by the framework.
See [juliabot/sessions/README.md](juliabot/sessions/README.md).

## Database schema updates
The schema is managed by versioned, reversible migrations in `juliabot/migrations/versions/`. Each
script defines `upgrade()` and `downgrade()`, and applied versions are tracked in the
`schema_migration` table.

On startup, `init_db()` creates the legacy tables and applies any pending migrations, so a normal
deploy needs no extra step. For controlled deploys and CI:

```bash
python -m juliabot.migrations status --json
python -m juliabot.migrations upgrade --dry-run
python -m juliabot.migrations upgrade
python -m juliabot.migrations downgrade --to 0
```

`--database-url` overrides `DATABASE_URL`. Exit codes: `0` success, `1` migration error,
`2` configuration error.

Legacy tables still receive conservative `ADD COLUMN` updates for simple columns. Tables listed in
`models.MIGRATION_MANAGED_TABLES` (currently `session`) are owned exclusively by migrations and are
excluded from `create_all` and from the automatic column sync.

## License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details
