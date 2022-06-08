from .config import DISCORD_TOKEN
from .client import Client
from .utils import get_prefix


bot = Client(command_prefix=get_prefix)
bot.run(DISCORD_TOKEN)
