from discord.ext import commands

from ..ai import generate_response
from ..config import CHARACTER_LIMIT, MESSAGE_HISTORY_LIMIT, SYSTEM_PROMPT


class AICog(commands.Cog, name="ai"):
    """Categoria relacionada a comandos e funções de inteligência artificial."""

    embed_title = ":robot: AI"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _build_message_history(
        self,
        ctx: commands.Context,
        question: str,
        messages: list[dict[str, str]]
    ) -> None:
        """Constrói o histórico de mensagens do canal para contexto."""
    
        hist = await ctx.channel.history(limit=MESSAGE_HISTORY_LIMIT).flatten()
        count = len(question)

        for msg in hist:
            if msg.id == ctx.message.id:
                continue
            if count + len(msg.content) > CHARACTER_LIMIT:
                break
            if msg.content.startswith(ctx.prefix + "breakpoint") or msg.content.startswith(ctx.prefix + "bp"):
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

        messages= [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        await self._build_message_history(ctx, question, messages)
        messages.append({"role": "user", "content": question})

        try:
            response = generate_response(messages)
            response_text = response.response
            
            if response_text.strip() != "":
                await ctx.send(response_text)
            
        except Exception as e:
            await ctx.send(f"❌ Erro ao processar sua pergunta: {str(e)}")
            raise e


    @commands.command(
        name="breakpoint",
        brief="Adiciona um ponto de quebra no histórico do chat",
        description="Adiciona um ponto de quebra no histórico do chat, fazendo com que mensagens anteriores não sejam consideradas no contexto da IA.",
        aliases=["bp"],
    )
    async def breakpoint(self, ctx: commands.Context) -> None:
        await ctx.message.add_reaction("👍")

    @commands.command(
        name='ai_history',
        brief='Mostra o histórico de mensagens usadas pela IA',
        description='Exibe as mensagens recentes do canal que serão usadas como contexto para a IA, até o limite de caracteres.',
        aliases=['aih'],
    )
    async def ai_history(self, ctx: commands.Context) -> None:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        await self._build_message_history(ctx, "", messages)
        
        if len(messages) <= 1:
            await ctx.send("Nenhuma mensagem recente encontrada para o histórico da IA.")
            return
        
        history_text = "\n\n".join(
            f"**{msg['role'].capitalize()}**: {msg['content']}" for msg in messages
        )
        
        await ctx.send(f"📜 **Histórico de mensagens para a IA:**\n{history_text}")


def setup(bot: commands.Bot):
    bot.add_cog(AICog(bot))
