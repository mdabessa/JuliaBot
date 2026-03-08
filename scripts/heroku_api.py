import logging
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import time

import heroku3

from juliabot.config import HEROKU_API_TOKEN


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def stop_dyno():
    conn = heroku3.from_key(HEROKU_API_TOKEN)

    apps = conn.apps()
    app = [app for app in apps if "juliabot" in app.name][0]

    formation = app.process_formation()
    formation[0].scale(0)
    logger.info("Dyno stopped!")
    time.sleep(5)


def start_dyno():
    conn = heroku3.from_key(HEROKU_API_TOKEN)

    apps = conn.apps()
    app = [app for app in apps if "juliabot" in app.name][0]

    formation = app.process_formation()
    formation[0].scale(1)
    logger.info("Dyno started!")
    time.sleep(5)
