import os
import sys

sys.path.insert(1, os.getcwd())

import asyncio
from main import main

from juliabot.config import ANIME_SCRAP_TIME


async def loop():
    while True:
        try:
            await main()
        except Exception as e:
            print(e)

        await asyncio.sleep(ANIME_SCRAP_TIME)


if __name__ == "__main__":
    asyncio.run(loop())
