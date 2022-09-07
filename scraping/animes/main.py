import os
import sys

sys.path.insert(1, os.getcwd())

import asyncio
import importlib
from time import sleep

import jikanpy as jk

from juliabot.models import AnimesNotifier



async def main():
    dir_path = os.path.dirname(os.path.realpath(__file__))
    files = os.listdir(os.path.join(dir_path))

    files = [
        f.replace(".py", "")
        for f in files
        if f.endswith(".py") and f.startswith("site_")
    ]

    episodes = []
    for file in files:
        mod = importlib.import_module(file, "/scraping/animes")

        eps = mod.scrap_animes()
        episodes.extend(eps)

    for episode in episodes:
        try:
            async with jk.AioJikan() as aio_jikan:
                mal = await aio_jikan.search('anime', episode["anime"][:100])
        
        # 500 Internal Server Error
        except jk.exceptions.APIException:
            try:
                jikan = jk.Jikan()
                mal = jikan.search('anime', episode["anime"][:100])
            except Exception as e:
                print(e)
                continue

        mal = mal["results"][0]
        mal_id = mal["mal_id"]

        anime = AnimesNotifier.get(
            mal_id, episode["episode"], episode["dub"], episode["lang"]
        )

        if anime is not None:
            print(episode["anime"], "its already in database.")
            continue

        AnimesNotifier(
            mal_id=mal_id,
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

        await asyncio.sleep(4) # To avoid 429 error


if __name__ == "__main__":
    asyncio.run(main())
