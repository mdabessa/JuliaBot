"""Commands generated from the Jikan manga routes."""

from ..client import Client
from ..jikan_catalog import GROUP_MANGA
from ..jikan_commands import GeneratedRoutesCog


class MangaCog(GeneratedRoutesCog, name="manga"):
    """Endpoints of the Jikan API for manga."""

    embed_title = ":books:Mangás."
    route_group = GROUP_MANGA


async def setup(bot: Client):
    await bot.add_cog(MangaCog(bot))
