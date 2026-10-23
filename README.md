# JuliaBot
JuliaBot is a Discord bot written in Python using the [discord.py](https://github.com/Rapptz/discord.py) library. It is designed to be a general purpose bot with a variety of utility and anime related features.

## Features
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
