from typing import Dict, List
from bs4 import BeautifulSoup
import requests


URL = "https://animeshouse.net"


def extract_number(string: str) -> int:
    number = ""
    for i in string:
        try:
            int(i)
            number += i

        except ValueError:
            pass

    if number == "":
        return

    else:
        return int(number)


def scrap_animes() -> List[Dict]:
    print(f"Scraping animes in {URL}")
    request = requests.get(URL)

    if request.status_code != 200:
        print(f"Request status: {request.status_code}")
        return []

    soup = BeautifulSoup(request.text, "html.parser")

    _episodes = soup.find_all("article", "item se episodes")
    print(f"Articles eps: {len(_episodes)}")

    episodes = []
    for ep in _episodes:
        try:
            div_poster = ep.find("div", class_="poster")
            div_data = ep.find("div", class_="data")

            image = div_poster.img["src"]
            link = div_poster.a["href"]

            anime = div_data.a.string
            number = extract_number(div_data.div.string.replace("Episódio ", ""))
            dub = "dublado" in div_data.div.string.lower()

            # Films and OVAs
            if number is None:
                continue

            episode = {
                "anime": anime,
                "episode": number,
                "image": image,
                "url": link,
                "dub": dub,
                "site": "AnimesHouse",
                "lang": "pt-BR",
            }

            episodes.append(episode)

        except Exception as e:
            print(e)

    return episodes
