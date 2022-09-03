import os
import sys

sys.path.insert(1, os.getcwd())

import importlib
from time import sleep

import jikanpy as jk

from juliabot.models import AnimesNotifier


def get_anime(jikan: jk.Jikan, query: str) -> dict:
    search_result = jikan.search("anime", query)
    sleep(4)  # API Limit

    r = search_result["results"][0]
    return r


def main():
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

    jikan = jk.Jikan()

    for episode in episodes:
        try:
            mal = get_anime(jikan, episode["anime"][:100])
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

        except Exception:
            pass


if __name__ == "__main__":
    main()
