from typing import Optional

from discord import Embed
from discord.ext import commands


class Help(commands.Cog, name="help"):
    """Categoria relacionada para ajudar e descrever os comandos do bot."""

    embed_title = ":question:Help."

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(brief="Ajuda", aliases=["ajuda"])
    async def help(self, ctx: commands.Context, argument: Optional[str] = None):
        prefix = await self.bot.get_prefix(ctx.message)

        if argument is not None:
            command = self.bot.get_command(argument)
            cog = self.bot.get_cog(argument)

            # Help Command
            if command is not None:
                desc = command.help if command.help is not None else command.brief

                embed = Embed(title=f"{prefix}{command.name}", color=self.bot.color)

                embed.add_field(name="Descrição:", value=desc, inline=False)
                if command.aliases:
                    embed.add_field(
                        name="Aliases:",
                        value=f" ".join([f"`{x}`" for x in command.aliases]),
                        inline=False,
                    )

                embed.add_field(
                    name="Exemplo:",
                    value=f"{prefix}{command.name} {command.signature}",
                    inline=False,
                )

                await ctx.send(embed=embed)

            # Help Cog
            elif cog is not None:
                embed = Embed(
                    title=cog.embed_title,
                    description=cog.description,
                    color=self.bot.color,
                )
                for cmd in cog.get_commands():
                    try:
                        if await cmd.can_run(ctx):
                            embed.add_field(
                                name=f"`{prefix}{cmd.name}`",
                                value=cmd.brief,
                                inline=False,
                            )
                    except Exception:
                        pass

                await ctx.send(embed=embed)

            else:
                await ctx.send(
                    f"Nenhum comando/categoria encontrado com o nome de `{argument}`!"
                )

        else:
            embed = Embed(
                title="Lista de Comandos",
                description=f"{prefix}help `comando`|`categoria`",
                color=self.bot.color,
            )

            for _, cog in self.bot.cogs.items():
                commands = []
                for cmd in cog.get_commands():
                    try:
                        if await cmd.can_run(ctx):
                            commands.append(cmd)
                    except Exception:
                        pass

                if commands:
                    text = ""
                    for cmd in commands:
                        text += f'[`{cmd.name}`](https://www.google.com "{cmd.brief}") '

                    embed.add_field(name=cog.embed_title, value=text, inline=True)

            for _ in range(0, len(embed.fields) % 3):
                embed.add_field(name="** **", value="** **", inline=True)

            await ctx.send(embed=embed)


def setup(bot: commands.Bot):
    bot.add_cog(Help(bot))
