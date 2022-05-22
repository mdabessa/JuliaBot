from modules.config import DISCORD_TOKEN
from modules.client import Client

bot = Client()
bot.run(DISCORD_TOKEN)
