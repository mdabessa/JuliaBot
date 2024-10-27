import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import heroku3
import time

from juliabot.config import HEROKU_API_TOKEN


def stop_dyno():
    conn = heroku3.from_key(HEROKU_API_TOKEN)

    apps = conn.apps()
    app = [app for app in apps if 'juliabot' in app.name][0]

    formation = app.process_formation()
    formation[0].scale(0)
    print('Dyno stopped!')
    time.sleep(5)


def start_dyno():
    conn = heroku3.from_key(HEROKU_API_TOKEN)

    apps = conn.apps()
    app = [app for app in apps if 'juliabot' in app.name][0]

    formation = app.process_formation()
    formation[0].scale(1)
    print('Dyno started!')
    time.sleep(5)
