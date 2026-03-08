"""Configuration module for JuliaBot.

Loads environment variables and provides default values for database connections,
API tokens, rate limits, and logging configuration.
"""

import logging
import time
from os import environ

from environs import Env

logger = logging.getLogger("juliabot")

env = Env()
env.read_env()

DATABASE_URL = environ["DATABASE_URL"]
DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://")


try:
    DISCORD_TOKEN = environ["DISCORD_TOKEN"]
except KeyError:
    DISCORD_TOKEN = ""

try:
    PREFIX = environ["PREFIX"]
except KeyError:
    PREFIX = "!"

try:
    ANIME_SCRAP_TIME = int(environ["ANIME_SCRAP_TIME"])
except KeyError:
    ANIME_SCRAP_TIME = 3600

try:
    TZ = environ["TZ"]
except KeyError:
    TZ = "UTC"


# Jikan's rate limit is per IP, so the default limit (60 requests per minute) should be split across all services (DiscordBot and Scraper)
try:
    BOT_JIKAN_RATE_LIMIT = int(environ["BOT_JIKAN_RATE_LIMIT"])
except KeyError:
    BOT_JIKAN_RATE_LIMIT = 50

try:
    SCRAP_JIKAN_RATE_LIMIT = int(environ["SCRAP_JIKAN_RATE_LIMIT"])
except KeyError:
    SCRAP_JIKAN_RATE_LIMIT = 10

try:
    HEROKU_API_TOKEN = environ["HEROKU_API_TOKEN"]
except KeyError:
    HEROKU_API_TOKEN = None

try:
    DEEPSEEK_API_KEY = environ["DEEPSEEK_API_KEY"]
except KeyError:
    DEEPSEEK_API_KEY = None

try:
    GITHUB_REPOSITORY = environ["GITHUB_REPOSITORY"]
except KeyError:
    GITHUB_REPOSITORY = None

logger.info(
    f"Github repository configured: {GITHUB_REPOSITORY if GITHUB_REPOSITORY else 'No'}"
)

SYSTEM_PROMPT = """Você é um bot de Discord chamado JuliaBot.
Pode usar a formatação de texto do Discord e seguir o estilo de comunicação típico do ambiente, incluindo emojis, gírias, abreviações e uma linguagem mais casual.

Você tem acesso a comandos do bot para realizar ações no servidor, como enviar mensagens, gerenciar usuários, etc.
"""

CHARACTER_LIMIT = 2000
MESSAGE_HISTORY_LIMIT = 30


# Setup logging
def setup_logging():
    """Configure root and juliabot logging using a consistent format.

    Sets up a stream handler with ISO 8601 timestamp formatting. Configures
    the full root logger and the juliabot-specific logger to INFO level.
    Logging is only configured if no handlers already exist.
    """
    root_logger = logging.getLogger()

    if not root_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-8s %(name)s %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)

    logging.getLogger("juliabot").setLevel(logging.INFO)


try:
    time.tzset()
except AttributeError:
    logger.warning("tzset() not available on Windows")
