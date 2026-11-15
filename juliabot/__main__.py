"""Entry point for running JuliaBot.

This module initializes logging, database, and the Discord bot client.
It detects if an instance is already running and starts the bot accordingly.
"""

import argparse
import logging
import signal

from .client import Client
from .config import DISCORD_TOKEN, TEST_MODE, setup_logging
from .models import BotConfig, init_db
from .utils import get_heartbeat_age, get_prefix, interrupt_on_sigterm, write_heartbeat

logger = logging.getLogger(__name__)

setup_logging()

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
    heartbeat_age = get_heartbeat_age()

    if heartbeat_age is None:
        write_heartbeat()
    elif heartbeat_age < 60 * 5:
        logger.warning("Bot já esta ativo!")
        exit(0)


error = None
try:
    # docker stop sends SIGTERM; without this the process dies before the
    # finally block below can delete the heartbeat row.
    signal.signal(signal.SIGTERM, interrupt_on_sigterm)
    bot = Client(command_prefix=get_prefix, help_command=None, test_mode=TEST_MODE)
    bot.run(DISCORD_TOKEN)
except Exception as e:
    error = e
finally:
    heartbeat = BotConfig.get("heartbeat")
    if heartbeat is not None:
        heartbeat.delete()

if error is not None:
    raise error
