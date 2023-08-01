# JuliaBot
JuliaBot is a Discord bot written in Python using the [discord.py](https://github.com/Rapptz/discord.py) library. It is designed to be a general purpose bot with a variety of utility and anime related features.

## Features
- Anime, manga, and character search using the [Jikan v4 API](https://jikan.moe/)
- New animes episodes notification based on web scraping from multiple anime streaming sites
- Subscribing to anime series to receive notifications
- Reminder system for setting reminders
- Translation command
- Rocket League match analysis using the [Ballchasing API](https://ballchasing.com/doc/api)

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

## License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details
