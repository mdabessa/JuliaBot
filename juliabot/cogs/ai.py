from discord.ext import commands
from openai.types.chat import ChatCompletionMessageParam, ChatCompletion

from ..ai import generate_response, build_available_tools, AIToolExecutor
from ..config import CHARACTER_LIMIT, MESSAGE_HISTORY_LIMIT, SYSTEM_PROMPT


class AI(commands.Cog, name="ai"):
    """Categoria relacionada a comandos e funções de inteligência artificial."""

    embed_title = ":robot: AI"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _build_message_history(
        self,
        ctx: commands.Context,
        question: str,
        messages: list[ChatCompletionMessageParam]
    ) -> None:
        """Constrói o histórico de mensagens do canal para contexto."""
    
        hist = await ctx.channel.history(limit=MESSAGE_HISTORY_LIMIT).flatten()
        count = len(question)

        for msg in reversed(hist):
            if msg.id == ctx.message.id:
                continue
            if count + len(msg.content) > CHARACTER_LIMIT:
                break
            count_updated = count + len(msg.content)
            
            if msg.author == self.bot.user:
                messages.insert(1, {"role": "assistant", "content": msg.content})
            else:
                messages.insert(1, {"role": "user", "content": f"{msg.author.display_name}: {msg.content}"})
            count = count_updated


    @commands.command(
        name="ask",
        brief="Converse com a IA",
        description="Faça perguntas ou converse com a IA. Ela pode executar comandos se necessário.",
        aliases=["pergunte", "converse"],
    )
    async def ask(self, ctx: commands.Context, *, question: str) -> None:
        """Pergunte algo à IA e receba uma resposta.

        Args:
            ctx (commands.Context): O contexto do comando.
            question (str): A pergunta ou mensagem para a IA.
        """
        if len(question) > CHARACTER_LIMIT:
            await ctx.send(
                f"❌ Desculpe, sua pergunta excede o limite de {CHARACTER_LIMIT} caracteres."
            )
            return

        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        await self._build_message_history(ctx, question, messages)
        messages.append({"role": "user", "content": question})

        try:
            available_tools = build_available_tools(self.bot)
            
            response, tool_calls = generate_response(messages, available_tools, use_tools=True)
            
            if response is None:
                await ctx.send("❌ Desculpe, não consegui gerar uma resposta.")
                return
            
            if response.strip() != "":
                await ctx.send(response)

            executor = AIToolExecutor(ctx, self.bot)
            for tool_call in tool_calls:
                success, tool_result = await executor.execute(tool_call["name"], tool_call["input"])
                print(f"Ferramenta executada: {tool_call['name']} -> {tool_result}")
                if not success:
                    await ctx.send(f"❌ Erro ao executar ferramenta '{tool_call['name']}' ({tool_call['input']}) : {tool_result}")
                    continue
            
        except Exception as e:
            await ctx.send(f"❌ Erro ao processar sua pergunta: {str(e)}")
            raise e


def setup(bot: commands.Bot):
    bot.add_cog(AI(bot))
