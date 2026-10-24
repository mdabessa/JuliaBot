"""AI conversation cog with structured responses.

Provides command-based questions and optional raw-message conversations in
channels where the AI rule is enabled.
"""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

from discord import TextChannel
from discord.ext import commands

from ..ai import generate_response
from ..client import Client
from ..config import CHARACTER_LIMIT, MESSAGE_HISTORY_LIMIT, SYSTEM_PROMPT
from ..sessions import (
    InteractionEvent,
    Registration,
    Registry,
    Scope,
    SessionManager,
    TriggerType,
)
from ..sessions.patterns import ChannelEntryPointRule

logger = logging.getLogger(__name__)

AI_CHANNEL = "ai.channel"


async def build_message_history(
    *,
    channel,
    question: str,
    messages: list[dict[str, str]],
    bot_user,
    exclude_message_id: int | None = None,
    breakpoint_prefixes: tuple[str, ...] = (),
) -> None:
    """Insert recent channel messages into the AI conversation context.

    Stops at the character budget or at a breakpoint command, whichever comes
    first. Messages are inserted after the system prompt in chronological order.
    """
    hist = channel.history(limit=MESSAGE_HISTORY_LIMIT)
    count = len(question)

    async for msg in hist:
        if exclude_message_id is not None and msg.id == exclude_message_id:
            continue
        if count + len(msg.content) > CHARACTER_LIMIT:
            break
        if any(msg.content.startswith(prefix) for prefix in breakpoint_prefixes):
            break

        count_updated = count + len(msg.content)

        if msg.author == bot_user:
            messages.insert(1, {"role": "assistant", "content": msg.content})
        else:
            messages.insert(
                1,
                {
                    "role": "user",
                    "content": f"{msg.author.display_name}: {msg.content}",
                },
            )
        count = count_updated


class AIConversationRule(ChannelEntryPointRule):
    """Answer raw messages in an enabled channel using channel history."""

    anchor_text = (
        "🤖 **IA ativa neste canal.**\n"
        "Envie uma mensagem para conversar com a IA. Use o botão abaixo para desativar."
    )
    disabled_text = "🤖 A IA foi desativada neste canal."

    async def on_channel_message(self, event: InteractionEvent) -> bool:
        """Reply to a channel message unless it is a command or empty."""
        message = event.raw
        bot = getattr(message, "client", None)
        if bot is None:
            return False

        prefixes = await self._prefixes(bot, message)
        content = (message.content or "").strip()
        if not content or content.startswith(tuple(prefixes)):
            return False

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        breakpoints = tuple(
            f"{prefix}{name}" for prefix in prefixes for name in ("breakpoint", "bp")
        )
        await build_message_history(
            channel=message.channel,
            question=content,
            messages=messages,
            bot_user=getattr(bot, "user", None),
            exclude_message_id=getattr(message, "id", None),
            breakpoint_prefixes=breakpoints,
        )
        messages.append(
            {"role": "user", "content": f"{message.author.display_name}: {content}"}
        )

        try:
            response = await asyncio.to_thread(generate_response, messages)
        except Exception:
            logger.exception("AI channel response failed: session=%s", self.id)
            return False

        text = response.response
        if not text.strip():
            return False

        await message.reply(text)
        return True

    @staticmethod
    async def _prefixes(bot, message) -> tuple[str, ...]:
        """Return the configured command prefixes for a message's guild."""
        value = await bot.get_prefix(message)
        return (value,) if isinstance(value, str) else tuple(value)


class AICog(commands.Cog, name="ai"):
    """AI conversation assistance.

    Provides commands to ask questions and have conversations with an AI
    assistant with channel history context.
    """

    embed_title = ":robot: AI"

    def __init__(self, bot: Client) -> None:
        self.bot = bot
        if not hasattr(bot, "sessions"):
            bot.sessions = SessionManager(Registry())
        if bot.sessions.registry.get(AI_CHANNEL) is None:
            bot.sessions.registry.register(
                Registration(
                    name=AI_CHANNEL,
                    session_class=AIConversationRule,
                    trigger=TriggerType.MESSAGE,
                    scope=Scope.CHANNEL,
                    persistent=True,
                    resumable=True,
                    max_per_scope=1,
                )
            )

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

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        await build_message_history(
            channel=ctx.channel,
            question=question,
            messages=messages,
            bot_user=self.bot.user,
            exclude_message_id=ctx.message.id,
            breakpoint_prefixes=self._breakpoint_prefixes(ctx.prefix),
        )
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
        name="ai_history",
        brief="Mostra o histórico de mensagens usadas pela IA",
        description="Exibe as mensagens recentes do canal que serão usadas como contexto para a IA, até o limite de caracteres.",
        aliases=["aih"],
    )
    async def ai_history(self, ctx: commands.Context) -> None:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        await build_message_history(
            channel=ctx.channel,
            question="",
            messages=messages,
            bot_user=self.bot.user,
            exclude_message_id=ctx.message.id,
            breakpoint_prefixes=self._breakpoint_prefixes(ctx.prefix),
        )

        if len(messages) <= 1:
            await ctx.send(
                "Nenhuma mensagem recente encontrada para o histórico da IA."
            )
            return

        history_text = "\n\n".join(
            f"**{msg['role'].capitalize()}**: {msg['content']}" for msg in messages
        )

        await ctx.send(f"📜 **Histórico de mensagens para a IA:**\n{history_text}")

    @staticmethod
    def _breakpoint_prefixes(prefix: str | None) -> tuple[str, ...]:
        """Return the breakpoint commands for a context prefix."""
        if not prefix:
            return ()
        return (f"{prefix}breakpoint", f"{prefix}bp")

    def _ai_rule(self, channel_id: int):
        """Return the AI rule active in a channel, if any."""
        return next(
            (
                rule
                for rule in self.bot.sessions.message_rules(channel_id)
                if rule.registration.name == AI_CHANNEL
            ),
            None,
        )

    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    @commands.command(
        name="ai_channel",
        brief="Ativa a IA neste canal.",
        description=(
            "Ativa respostas automáticas da IA para mensagens deste canal. "
            "Mensagens de comando são ignoradas."
        ),
        aliases=["aichat", "canal_ia"],
    )
    async def ai_channel(
        self, ctx: commands.Context, channel: TextChannel = None
    ) -> None:
        channel = channel or ctx.channel
        if self._ai_rule(channel.id) is not None:
            await ctx.send("A IA já está ativa neste canal.")
            return

        event = InteractionEvent(
            transport=TriggerType.MESSAGE,
            key=f"{AI_CHANNEL}:{channel.id}",
            user_id=ctx.author.id,
            guild_id=getattr(ctx.guild, "id", None),
            channel_id=channel.id,
            message_id=ctx.message.id,
            raw=SimpleNamespace(channel=channel),
        )
        await self.bot.sessions.start(AI_CHANNEL, event)
        await ctx.send(f"IA ativada em {channel.mention}.")

    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    @commands.command(
        name="ai_channel_disable",
        brief="Desativa a IA neste canal.",
        description="Desativa as respostas automáticas da IA neste canal.",
        aliases=["aichat_off", "desativar_ia"],
    )
    async def ai_channel_disable(
        self, ctx: commands.Context, channel: TextChannel = None
    ) -> None:
        channel = channel or ctx.channel
        rule = self._ai_rule(channel.id)
        if rule is None:
            await ctx.send("A IA não está ativa neste canal.")
            return

        await rule.shutdown(channel)
        await ctx.send("IA desativada neste canal.")


async def setup(bot: Client):
    await bot.add_cog(AICog(bot))
