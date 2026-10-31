"""Commands generated from the Jikan anime routes."""

from ..client import Client
from ..jikan_catalog import GROUP_ANIME
from ..jikan_commands import GeneratedRoutesCog


class AnimeApiCog(GeneratedRoutesCog, name="anime_api"):
    """Endpoints of the Jikan API for a single anime."""

    embed_title = "Animes (API)."
    route_group = GROUP_ANIME


async def setup(bot: Client):
    await bot.add_cog(AnimeApiCog(bot))
