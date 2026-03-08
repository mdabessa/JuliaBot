"""Embed builders for anime-related bot messages.

This module centralizes the Discord embed formatting used by anime search
responses and episode notifications.
"""

from discord import Embed
from jikan4.models import Anime

from ..models import AnimesNotifier


def anime_embed(anime: Anime, color: int) -> Embed:
    """Build an embed with metadata for a single anime entry.

    Args:
        anime (Anime): Anime object returned by Jikan containing title,
            synopsis, score, media type, airing status, and links.
        color (int): Discord embed color value.

    Returns:
        Embed: A populated embed summarizing the selected anime.
    """
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
    embed.add_field(
        name="Lancando:", value="Sim" if anime.airing else "Nao", inline=False
    )
    embed.add_field(name="mal_id:", value=anime.mal_id, inline=False)
    embed.add_field(name="Links:", value=f"[MyAnimeList]({anime.url})", inline=False)

    return embed


def episode_embed(anime: AnimesNotifier, color: int) -> Embed:
    """Build an embed for a newly released anime episode notification.

    Args:
        anime (AnimesNotifier): Notification model with episode details,
            source URL, language information, and media image.
        color (int): Discord embed color value.

    Returns:
        Embed: A formatted embed describing the released episode.
    """
    dub = " [Dublado]" if anime.dubbed else ""

    embed = Embed(
        title=anime.name,
        url=anime.url,
        description=f"Episódio {anime.episode}" + dub,
        color=color,
    )

    embed.set_image(url=anime.image)
    embed.set_footer(
        text=f"Fonte: {anime.site} | Linguagem: {anime.lang} | mal_id: {anime.mal_id}"
    )

    return embed
