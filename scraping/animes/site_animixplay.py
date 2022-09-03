from typing import Dict, List
from bs4 import BeautifulSoup
import requests


URL = "https://animixplay.to"


def extract_number(string: str) -> int:
    number = string.split(" ")[1]
    number = number.split("/")[0]

    return int(number)


def scrap_animes() -> List[Dict]:
    print(f"Scraping animes in {URL}")
    request = requests.get(URL)

    if request.status_code != 200:
        print(f"Request status: {request.status_code}")
        return []

    soup = BeautifulSoup(request.text, "html.parser")

    div = soup.find("div", {"id": "resultplace"})
    ul = div.find("ul", {"class": "searchresult"})
    _episodes = ul.findChildren("li", recursive=False)
    print(f"li eps: {len(_episodes)}")
    episodes = []
    for ep in _episodes:
        try:
            a = ep.findChild("a", recursive=False)
            anime = a["title"]
            href = a["href"]

            searchimg = a.findChild("div", {"class": "searchimg"}, recursive=False)
            image = searchimg.img["src"]

            details = a.findChild("div", {"class": "details"}, recursive=False)
            number = details.findChild("p", {"class": "infotext"}, recursive=False)
            number = extract_number(number.string)

            episode = {
                "anime": anime,
                "episode": number,
                "image": image,
                "url": URL+href,
                "dub": False,
                "site": "AnimixPlay",
                "lang": "en-US",
            }

            episodes.append(episode)

        except Exception as e:
            print(f"Error: {e}")

    return episodes
