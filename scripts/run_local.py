import logging
import os
import time

from heroku_api import stop_dyno


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

stop_dyno()

root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

commands = [
    f"cd {root_path}",
    r".\.venv\Scripts\activate",
    r"python -m juliabot",
]

while True:
    command = " && ".join(commands)
    r = os.system(command)
    logger.warning(f"Bot exited with code {r}")

    time.sleep(60)
