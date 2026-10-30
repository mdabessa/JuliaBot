"""Commands generated from the remaining Jikan routes (characters, people,
producers, seasons, top lists, genres, articles, news, reviews, stacks)."""

from ..client import Client
from ..jikan_catalog import GROUP_CATALOG
from ..jikan_commands import GeneratedRoutesCog


class MalCog(GeneratedRoutesCog, name="mal"):
    """Catalogue endpoints of the MyAnimeList API."""

    embed_title = ":mag:MyAnimeList."
    route_group = GROUP_CATALOG


async def setup(bot: Client):
    await bot.add_cog(MalCog(bot))
