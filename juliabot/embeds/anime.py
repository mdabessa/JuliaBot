from typing import List
from discord import Embed
from jikan4.models import Anime

from ..models import AnimesNotifier


def anime_embed(anime: Anime, color: int) -> Embed:
    embed = Embed(
        title=anime.title,
        url=anime.url,
        description=anime.synopsis,
        color=color,
    )

    embed.set_thumbnail(url=anime.images.jpg.image_url)
    embed.add_field(name="Episodios:", value=anime.episodes, inline=False)
    embed.add_field(name="Score (MyAnimeList):", value=anime.score, inline=False)
    embed.add_field(name="Tipo:", value=anime.type, inline=False)
    embed.add_field(name="Lancando:", value="Sim" if anime.airing else "Nao", inline=False)
    embed.add_field(name="mal_id:", value=anime.mal_id, inline=False)
    embed.add_field(name="Links:", value=f"[MyAnimeList]({anime.url})", inline=False)

    return embed


def episode_embed(anime: AnimesNotifier, color: int) -> Embed:
    dub = " [Dublado]" if anime.dubbed else ""

    embed = Embed(
        title=anime.name,
        url=anime.url,
        description=f"Episódio {anime.episode}" + dub,
        color=color,
    )

    embed.set_image(url=anime.image)
    embed.set_footer(text=f'Fonte: {anime.site} | Linguagem: {anime.lang} | mal_id: {anime.mal_id}')

    return embed
