from environs import Env
from os import environ


env = Env()
env.read_env()

DATABASE_URL = environ["DATABASE_URL"]
DISCORD_TOKEN = environ["DISCORD_TOKEN"]


