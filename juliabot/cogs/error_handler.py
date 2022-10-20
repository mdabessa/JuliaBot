from discord.ext import commands


class ErrorHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Parametro requerido faltando: {error.param.name}")
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send("Você não tem permissão para usar esse comando.")
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.send("Eu não tenho permissão para fazer isso.")
        elif isinstance(error, commands.NotOwner):
            await ctx.send("Somente o dono do bot pode usar esse comando.")
        else:
            raise error


def setup(bot):
    bot.add_cog(ErrorHandler(bot))
