"""Error handling cog for command exceptions.

Centralized error handler providing user-friendly messages for common
command execution errors.
"""

import traceback

from discord.ext import commands
from sqlalchemy.exc import PendingRollbackError

from ..client import Client
from ..models import rollback


class ErrorHandlerCog(commands.Cog):
    """Handles and reports command execution errors.

    Provides user-friendly error messages for common failures like missing
    permissions, invalid arguments, and database issues.
    """

    def __init__(self, bot: Client):
        self.bot = bot

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            await ctx.send("Comando não encontrado.")
            return

        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Parametro requerido faltando: {error.param.name}")
            return

        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Você não tem permissão para usar esse comando.")
            return

        if isinstance(error, commands.BotMissingPermissions):
            await ctx.send("Eu não tenho permissão para fazer isso.")
            return

        if isinstance(error, commands.NotOwner):
            await ctx.send("Somente o dono do bot pode usar esse comando.")
            return

        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(
                f"Esse comando está em cooldown. Tente novamente em {error.retry_after:.2f} segundos."
            )
            return

        if isinstance(error, PendingRollbackError):
            await ctx.send("Erro ao salvar no banco de dados, tente novamente.")
            rollback()
            return

        await ctx.send(f"Erro: {error}")
        traceback.print_exception(type(error), error, error.__traceback__)


async def setup(bot: Client):
    await bot.add_cog(ErrorHandlerCog(bot))
