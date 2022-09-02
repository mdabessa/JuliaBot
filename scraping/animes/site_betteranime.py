from typing import Dict, List
from bs4 import BeautifulSoup
import requests


URL = "https://betteranime.net"


def split_name(string: str) -> List[str]:
    cont = string.split("-Episódio ")
    name = cont[0]
    episode = int(cont[1].split(" ")[0])
    name = name.replace(" - Dublado", "")
    name = name.replace("nd Season", "")

    return [name, episode]


def scrap_animes() -> List[Dict]:
    print(f"Scraping animes in {URL}")
    request = requests.get(URL)

    if request.status_code != 200:
        print(f"Request status: {request.status_code}")
        return []

    soup = BeautifulSoup(request.text, "html.parser")

    _episodes = soup.find_all("article", "col-lg-3 col-md-4 col-sm-6 card-horizontal")
    print(f"Articles eps: {len(_episodes)}")

    episodes = []
    for ep in _episodes:
        try:
            tag_img = ep.find("img")

            cont = split_name(tag_img["alt"])
            anime = cont[0]
            number = cont[1]
            dub = "dublado" in tag_img["alt"].lower()

            image = tag_img["src"]
            if image[0] == "/":
                image = "https:" + image

            link = ep.a["href"]

            episode = {
                "anime": anime,
                "episode": number,
                "image": image,
                "url": link,
                "dub": dub,
                "site": "BetterAnime",
                "lang": "pt-BR",
            }

            episodes.append(episode)

        except Exception as e:
            print(e)

    return episodes
