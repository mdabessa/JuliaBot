import argparse
import datetime

from .client import Client
from .config import DISCORD_TOKEN
from .models import BotConfig, init_db
from .utils import get_prefix

parser = argparse.ArgumentParser(description="JuliaBot")
parser.add_argument(
    "-f",
    "--force",
    action="store_true",
    help="Permite forçar a execução do bot mesmo que já exista uma instância ativa.",
)

args = parser.parse_args()

init_db()


if not args.force:
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

if error is not None:
    raise error
