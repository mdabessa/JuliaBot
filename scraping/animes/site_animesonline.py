from typing import Dict, List
from bs4 import BeautifulSoup
import requests


URL = 'https://animesonline.org'


def extract_number(string: str) -> int:
    number = ''
    for i in string:
        try:
            int(i)
            number += i
        
        except ValueError:
            pass

    
    if number == '':
        return
    
    else:
        return int(number)


def scrap_animes() -> List[Dict]:
    print(f'Scraping animes in {URL}')
    request = requests.get(URL)
    
    if request.status_code != 200:
        print(f'Request status: {request.status_code}')
        return []

    soup = BeautifulSoup(request.text, 'html.parser')

    div = soup.find('div', {'class': "animation-2 items full"})

    if div == None:
        return []

    _episodes = div.findChildren('article', recursive=False)
    print(f'Articles eps: {len(_episodes)}')

    episodes = []
    for ep in _episodes:
        try:
            poster = ep.findChild('div', {'class': 'poster'}, recursive=False)
            data = ep.findChild('div', {'class': 'data'}, recursive=False)

            image = poster.img['src']
            
            a_tag = data.h3.a
            number = extract_number(a_tag.contents[0])
            dub = 'dublado' in a_tag.contents[0].lower()

            link = a_tag['href']

            anime = data.span.contents[0]

            # Films and OVAs
            if number is None:
                continue

            episode = {
                'anime': anime,
                'episode': number,
                'image': image,
                'url': link,
                'dub': dub,
                'site': 'AnimesOnline'
            }

            episodes.append(episode)

        except Exception as e:
            print(e)

    return episodes
