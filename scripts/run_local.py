import os
import time

from heroku_api import stop_dyno


stop_dyno()

root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

commands = [
        f"cd {root_path}",
        r".\.venv\Scripts\activate",
        r"python -m juliabot",
    ]

while True:
    command = " && ".join(commands)
    r = os.system(command)
    print(f"Bot exited with code {r}")

    time.sleep(60)
