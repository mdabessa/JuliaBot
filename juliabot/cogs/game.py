from discord.ext import commands
from pydantic import BaseModel

from ..ai import generate_response


class GameResponse(BaseModel):
    game_response: str
    grammar_correction: str | None = None


class GameSession:
    """Representa uma sessão de jogo para um usuário."""
    
    def __init__(self, channel_id: int):
        self.channel_id = channel_id
        self.messages = []
        
    def add_message(self, role: str, content: str) -> None:
        """Adiciona uma mensagem ao histórico da sessão."""
        self.messages.append({"role": role, "content": content})
    
    def get_context(self) -> list[dict[str, str]]:
        """Gera o contexto atual da sessão para a IA."""
        system_prompt = "You are a helpful assistant for a text-based adventure game. Respond to the player's actions and guide them through the story."
        context = [
            {"role": "system", "content": system_prompt},
            *self.messages
        ]
        return context


class Game(commands.Cog):
    """Cog para gerenciar sessões de jogo."""
    
    embed_title = ":video_game: Text Adventure Game"
    
    def __init__(self, bot):
        self.bot = bot
        self.sessions: dict[int, GameSession] = {}
    
    @commands.command(name="startgame")
    async def start_game(self, ctx):
        """Inicia uma nova sessão de jogo para o canal."""
        if ctx.channel.id in self.sessions:
            await ctx.send("Já existe uma sessão de jogo ativa neste canal.")
            return
        
        session = GameSession(ctx.channel.id)
        self.sessions[ctx.channel.id] = session

        session.add_message("system", "A new game session has started. The player is ready to begin their adventure. Generate the initial game scenario.")
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
            await ctx.send("Nenhuma sessão de jogo ativa. Use `!startgame` para iniciar uma nova sessão.")
            return
        
        session.add_message("user", action)
        
        context = session.get_context()
        response = generate_response(context, response_format=GameResponse)
        
        session.add_message("assistant", response.game_response)
        

        msg = f"{response.game_response}"
        if response.grammar_correction:
            msg += f"\n\n**Grammar Correction:** {response.grammar_correction}"

        await ctx.send(msg)


def setup(bot):
    bot.add_cog(Game(bot))
    
