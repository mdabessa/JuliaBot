"""Commands generated from the Jikan anime routes.

Every route selected by ``ROUTES_ALLOWLIST`` becomes a command at cog init, so
the command list follows the installed ``jikan4`` package instead of being
hand-written. The allowlist shrinks away once the generic renderers land.
"""

from discord.ext import commands
from jikan4 import AioJikan

from ..client import Client
from ..config import BOT_JIKAN_RATE_LIMIT
from ..jikan_catalog import GROUP_ANIME, load_specs
from ..jikan_commands import build_commands

ROUTES_ALLOWLIST = frozenset({"get_anime_themes"})


class AnimeApiCog(commands.Cog, name="anime_api"):
    """Raw anime endpoints of the Jikan API."""

    embed_title = "Animes (API)."

    def __init__(self, bot: Client) -> None:
        self.bot = bot
        # Cog load order is alphabetical, so either cog may create the client
        # first; reusing it keeps a single per-IP rate limiter.
        self.jikan = getattr(bot, "jikan", None) or AioJikan(
            rate_limit=BOT_JIKAN_RATE_LIMIT
        )
        bot.jikan = self.jikan

        generated = build_commands(
            self,
            (spec for spec in load_specs() if spec.group == GROUP_ANIME),
            allowlist=ROUTES_ALLOWLIST,
        )
        self.__cog_commands__ = (*self.__cog_commands__, *generated)


async def setup(bot: Client):
    await bot.add_cog(AnimeApiCog(bot))
