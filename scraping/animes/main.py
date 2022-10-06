import os
import sys

sys.path.insert(1, os.getcwd())

import asyncio
import importlib

from jikan4.aiojikan import AioJikan

from juliabot.models import AnimesNotifier



async def main():
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

        eps = mod.scrap_animes()
        sites.append(eps)


    for episodes in sites:
        c = 0
        for episode in episodes:
            if c >= 5:
                break

            async with AioJikan() as aio_jikan:
                mal = await aio_jikan.search_anime('anime', episode["anime"][:100])
                await asyncio.sleep(4) # To avoid 429 error


            if mal["data"]:
                mal = mal["data"][0]
                
            else:
                print(f"Anime {episode['anime']} not found")
                continue

            mal_id = mal["mal_id"]

            anime = AnimesNotifier.get(
                mal_id, episode["episode"], episode["dub"], episode["lang"]
            )

            if anime is not None:
                print(episode["anime"], "its already in database.")
                c += 1
                continue

            c = 0

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



if __name__ == "__main__":
    asyncio.run(main())
