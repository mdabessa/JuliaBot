from discord.ext.commands import Bot
from discord import Message
from jikan4.aiojikan import AioJikan

from .models import Server
from .config import PREFIX


def get_prefix(bot: Bot, message: Message) -> str:
    if message.guild:
        server = Server.get_or_create(str(message.guild.id))
        return server.prefix
    else:
        return PREFIX


async def search_anime(search_type: str, query: str):
    async with AioJikan() as aio_jikan:
        return await aio_jikan.search_anime(search_type, query)


async def get_anime(id: int):
    async with AioJikan() as aio_jikan:
        return await aio_jikan.get_anime(id)
