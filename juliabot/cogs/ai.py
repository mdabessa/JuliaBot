from discord.ext import commands

from ..gemini_api import generate_response


class AI(commands.Cog, name="ai"):
    """Categoria relacionada a comandos e funções de inteligência artificial."""

    embed_title = ":robot:AI."

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(
        name="ask",
        brief="Converse com a IA.",
        description="Faça perguntas ou inicie uma conversa com a IA.",
        aliases=["pergunte", "converse"],
    )
    async def ask(self, ctx: commands.Context, *, question: str) -> None:
        """
        Pergunte algo à IA e receba uma resposta.

        Args:
            ctx (commands.Context): O contexto do comando.
            question (str): A pergunta ou mensagem para a IA.
        """
        try:
            response = generate_response(question)
            await ctx.send(response)
        except Exception as e:
            await ctx.send(f"Erro ao gerar resposta: {e}")


def setup(bot: commands.Bot):
    bot.add_cog(AI(bot))
