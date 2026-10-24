"""Debug utilities cog for bot owners.

Provides commands to reload cogs, inspect running sessions, and execute
commands as other users.
"""

from discord.ext import commands

from ..client import Client


class DebugCog(commands.Cog):
    """Debug and administrative utilities.

    Restricted to bot owner. Provides cog reloading, session inspection,
    and command execution utilities.
    """

    embed_title = "debug"

    def __init__(self, bot: Client) -> None:
        self.bot = bot

    async def cog_check(self, ctx: commands.Context):
        return await ctx.bot.is_owner(ctx.author)

    @commands.command(
        name="reload",
        brief="Recarregar commandos.",
        description="Recarrega todos os cogs do bot.",
    )
    async def reload_cogs(self, ctx: commands.Context):
        msg = await ctx.send("Recarregando cogs...")
        exts = self.bot.extensions.copy()
        for ext in exts:
            await msg.edit(content=f"Recarregando {ext}...")
            self.bot.reload_extension(ext)

        await msg.edit(content="Cogs regarregados com sucesso!")

    @commands.command(
        name="sessions",
        brief="Listar todas as sessões rodando.",
        aliases=["scripts", "get_scripts"],
    )
    async def get_all_sessions(self, ctx: commands.Context):
        sessions = self.bot.sessions.active()
        if not sessions:
            await ctx.send("Nenhuma sessão rodando no momento.")
            return

        for session in sessions:
            await ctx.send(
                f"```Nome: {session.registration.name}\n"
                f"ID: {session.id}\n"
                f"Payload: {session.to_payload()}```"
            )

    @commands.command(
        name="exec",
        brief="Executar um comando no nome de um usuário.",
        description="Executa um comando no nome de um usuário.",
    )
    async def exec_as_user(
        self, ctx: commands.Context, user: commands.UserConverter, *, command: str
    ):
        new_message = ctx.message
        new_message.author = user
        new_message.content = ctx.prefix + command
        await self.bot.process_commands(new_message)


async def setup(bot: Client):
    await bot.add_cog(DebugCog(bot))
