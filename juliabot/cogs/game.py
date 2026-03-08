"""Text adventure game cog with AI integration.

Provides a text-based adventure game engine powered by LLM responses.
"""

from typing import Optional

from discord.ext import commands
from pydantic import BaseModel

from ..ai import generate_response
from ..client import Client


class GameResponse(BaseModel):
    game_response: str
    grammar_correction: str | None = None


class GameSession:
    """Manages conversation state for a text adventure game session."""

    def __init__(self, channel_id: int):
        self.channel_id = channel_id
        self.messages = []

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the session history.

        Args:
            role (str): Message role ('system', 'user', or 'assistant').
            content (str): Message content text.
        """
        self.messages.append({"role": role, "content": content})

    def get_context(self) -> list[dict[str, str]]:
        """Generate the current session context for the AI.

        Returns:
            list: Messages in OpenAI chat format including system prompt.
        """
        system_prompt = "You are a helpful assistant for a text-based adventure game. Respond to the player's actions and guide them through the story."
        context = [{"role": "system", "content": system_prompt}, *self.messages]
        return context


class GameCog(commands.Cog):
    """Text adventure game management.

        Manages game sessions and AI-powered narrative generation for text
    adventure games.
    """

    embed_title = ":video_game: Text Adventure Game"

    def __init__(self, bot: Client):
        self.bot = bot
        self.sessions: dict[int, GameSession] = {}

    @commands.command(name="startgame")
    async def start_game(self, ctx, seed: Optional[str] = None):
        """Inicia uma nova sessão de jogo para o canal."""
        if ctx.channel.id in self.sessions:
            await ctx.send("Já existe uma sessão de jogo ativa neste canal.")
            return

        session = GameSession(ctx.channel.id)
        self.sessions[ctx.channel.id] = session

        start_message = "Guide the player through the text-based adventure. You can use the formatting schema of Discord to enhance the storytelling experience.\nA new game session has started. The player is ready to begin their adventure. Generate the initial game scenario."
        if seed:
            start_message += f"\nThe seed for this game is: {seed}"

        session.add_message("system", start_message)
        context = session.get_context()
        response = generate_response(context)

        content = response.response.strip()
        session.add_message("assistant", content)

        await ctx.send(content)

    @commands.command(name="play")
    async def play(self, ctx, *, action: str):
        """Processa a ação do jogador e gera uma resposta da IA."""
        session = self.sessions.get(ctx.channel.id)
        if not session:
            await ctx.send(
                "Nenhuma sessão de jogo ativa. Use `!startgame` para iniciar uma nova sessão."
            )
            return

        session.add_message("user", action)

        context = session.get_context()
        response = generate_response(context, response_format=GameResponse)

        session.add_message("assistant", response.game_response)

        msg = f"{response.game_response}"
        if response.grammar_correction:
            msg += f"\n\n**Grammar Correction:** {response.grammar_correction}"

        await ctx.send(msg)

    @commands.command(name="endgame")
    async def end_game(self, ctx):
        """Encerra a sessão de jogo ativa no canal."""
        if ctx.channel.id not in self.sessions:
            await ctx.send("Nenhuma sessão de jogo ativa para encerrar.")
            return

        del self.sessions[ctx.channel.id]
        await ctx.send(
            "Sessão de jogo encerrada. Use `!startgame` para iniciar uma nova sessão."
        )


async def setup(bot: Client):
    await bot.add_cog(GameCog(bot))
