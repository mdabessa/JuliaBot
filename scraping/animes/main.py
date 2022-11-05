import os
import sys

sys.path.insert(1, os.getcwd())

import asyncio
import importlib

from jikan4 import AioJikan

from juliabot.models import AnimesNotifier
from juliabot.config import SCRAP_JIKAN_RATE_LIMIT


async def main():
    jikan = AioJikan(rate_limit=SCRAP_JIKAN_RATE_LIMIT)
    dir_path = os.path.dirname(os.path.realpath(__file__))
    files = os.listdir(os.path.join(dir_path))

    files = [
        f.replace(".py", "")
        for f in files
        if f.endswith(".py") and f.startswith("site_")
    ]

    sites = []
    for file in files:
        mod = importlib.import_module(file, "/scraping/animes")
        
        try:
            eps = mod.scrap_animes()
            sites.append(eps)

        except Exception as e:
            print(f"Error in {file} : {e}")


    for episodes in sites:
        c = 0
        for episode in episodes:
            if c >= 5:
                break

            mal = await jikan.search_anime("anime", episode["anime"][:100])

            if mal.data:
                mal = mal.data[0]

            else:
                print(f"Anime {episode['anime']} not found")
                continue

            anime = AnimesNotifier.get(
                mal.mal_id, episode["episode"], episode["dub"], episode["lang"]
            )

            if anime is not None:
                print(episode["anime"], "its already in database.")
                c += 1
                continue

            c = 0

            AnimesNotifier(
                mal_id=mal.mal_id,
                episode=episode["episode"],
                name=episode["anime"],
                image=episode["image"],
                url=episode["url"],
                site=episode["site"],
                dubbed=episode["dub"],
                lang=episode["lang"],
            )

            print(
                f'\t{episode["anime"]} Episode {episode["episode"]}, was added to database.'
            )


if __name__ == "__main__":
    asyncio.run(main())
