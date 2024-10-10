import datetime

from .config import DISCORD_TOKEN
from .client import Client
from .utils import get_prefix
from .models import init_db, BotConfig


init_db()

heartbeat = BotConfig.get("heartbeat")
now = datetime.datetime.now()

if heartbeat is None:
    BotConfig("heartbeat", now.strftime("%d/%m/%Y %H:%M:%S"))
else:
    date = datetime.datetime.strptime(heartbeat.value, "%d/%m/%Y %H:%M:%S")
    if (now - date).seconds < 60 * 5:
        print("Bot já esta ativo!")
        exit(0)

error = None
try:
    bot = Client(command_prefix=get_prefix, help_command=None)
    bot.run(DISCORD_TOKEN)
except Exception as e:
    error = e
finally:
    heartbeat = BotConfig.get("heartbeat")
    if heartbeat is not None:
        heartbeat.delete()

raise error
