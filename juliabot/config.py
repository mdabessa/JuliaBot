from environs import Env
from os import environ
import time


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

try:
    time.tzset()
except AttributeError:
    print("tzset() not available on Windows")
