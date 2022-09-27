from environs import Env
from os import environ


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
