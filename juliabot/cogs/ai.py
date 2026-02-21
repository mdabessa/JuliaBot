from discord.ext import commands
from openai import OpenAI

from ..config import DEEPSEEK_API_KEY


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

        character_limit = 2000
        if len(question) > character_limit:
            await ctx.send(f"Desculpe, sua pergunta excede o limite de {character_limit} caracteres.")
            return

        count = len(question)
        hist = await ctx.channel.history(limit=30).flatten()
        messages = []
        for msg in hist:
            if msg.id == ctx.message.id: continue
            if count + len(msg.content) > character_limit: break
            count += len(msg.content)
            if msg.author == self.bot.user:
                messages.insert(0, {"role": "assistant", "content": msg.content})
            else:
                messages.insert(0, {"role": "user", "content": f"{msg.author.display_name}: {msg.content}"})
        
        messages.append({"role": "user", "content": question})

        client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            stream=False,
            max_tokens=1000,
            temperature=1.3,
        )

        await ctx.send(response.choices[0].message.content)


def setup(bot: commands.Bot):
    bot.add_cog(AI(bot))
#