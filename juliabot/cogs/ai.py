import json
import inspect
from typing import Any
from collections.abc import Callable

from discord.ext import commands
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

from ..config import DEEPSEEK_API_KEY

SYSTEM_PROMPT = """Você é um bot de Discord chamado JuliaBot.
Pode usar emojis e formatação de texto do Discord para tornar suas respostas mais expressivas e fáceis de ler.

Você tem acesso a ferramentas para executar comandos do bot quando necessário. Use-as com sabedoria e apenas quando apropriado.
Sempre forneça uma resposta amigável ao usuário, mesmo se executar um comando."""

CHARACTER_LIMIT = 2000
MESSAGE_HISTORY_LIMIT = 30


def _build_tool_properties_from_signature(func: Callable) -> tuple[dict, list]:
    """Extrai parâmetros da assinatura de uma função.
    
    Returns:
        (properties, required_params) - Dicionário de propriedades e lista de params obrigatórios
    """
    sig = inspect.signature(func)
    properties = {}
    required = []
    
    params_to_skip = {"self", "ctx"}
    
    for param_name, param in sig.parameters.items():
        if param_name in params_to_skip:
            continue
            
        param_type = "string"
        if param.annotation != inspect.Parameter.empty:
            if param.annotation == int:
                param_type = "integer"
            elif param.annotation == float:
                param_type = "number"
            elif param.annotation == bool:
                param_type = "boolean"
            elif param.annotation == str:
                param_type = "string"
            else:
                print(f"Tipo de parâmetro '{param.annotation}' não é suportado, usando 'string' por padrão.")
        
        properties[param_name] = {
            "type": param_type,
            "description": f"Parâmetro {param_name}"
        }
        
        if param.default == inspect.Parameter.empty:
            required.append(param_name)
    
    return properties, required


def build_available_tools(bot: commands.Bot) -> list[dict]:
    """Constrói dinamicamente a lista de ferramentas disponíveis baseado nos cogs do bot.
    
    Args:
        bot: Instância do bot Discord
        
    Returns:
        Lista de ferramentas no formato OpenAI
    """
    tools = []
    
    for cog_name, cog in bot.cogs.items():
        if cog_name.lower() in ["ai", "error_handler"]:
            continue
            
        for command in cog.get_commands():
            if command.name in ["say"]:
                continue

            description = command.description or command.brief or f"Executa o comando {command.name}"
            
            properties, required = _build_tool_properties_from_signature(command.callback)
            
            if not properties:
                parameters = {
                    "type": "object",
                    "properties": {}
                }
            else:
                parameters = {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            
            tool = {
                "type": "function",
                "function": {
                    "name": command.name,
                    "description": description,
                    "parameters": parameters
                }
            }
            
            tools.append(tool)
    
    return tools


class AIToolExecutor:
    """Executar ferramentas solicitadas pela IA."""

    def __init__(self, ctx: commands.Context, bot: commands.Bot) -> None:
        self.ctx = ctx
        self.bot = bot

    async def execute(self, tool_name: str, tool_input: dict[str, Any]) -> tuple[bool, str]:
        """Executa um comando do bot baseado no nome da ferramenta.
        
        Args:
            tool_name: Nome do comando a executar
            tool_input: Argumentos para o comando
            
        Returns:
            (success, message) - Se a execução foi bem-sucedida e mensagem de resultado
        """
        try:
            command = self.bot.get_command(tool_name)
            
            if not command:
                return False, f"Comando '{tool_name}' não encontrado."
            
            args = []
            kwargs = {}
            
            sig = inspect.signature(command.callback)
            for param_name, param in sig.parameters.items():
                if param_name in ["self", "ctx"]:
                    continue
                    
                if param_name in tool_input:
                    value = tool_input[param_name]
                    if param.kind == inspect.Parameter.VAR_POSITIONAL:
                        args.append(value)
                    elif param.kind == inspect.Parameter.VAR_KEYWORD:
                        kwargs.update(value if isinstance(value, dict) else {param_name: value})
                    else:
                        kwargs[param_name] = value
            
            await command.callback(command.cog, self.ctx, *args, **kwargs)
            
            return True, f"Comando '{tool_name}' executado com sucesso."
            
        except Exception as e:
            return False, f"Erro ao executar '{tool_name}': {str(e)}"


def generate_response(
    messages: list[ChatCompletionMessageParam],
    available_tools: list[dict],
    use_tools: bool = True
) -> tuple[str | None, list[dict[str, Any]]]:
    """Gera resposta da IA, opcionalmente com function calling.
    
    Args:
        messages: Histórico de mensagens
        available_tools: Lista de ferramentas disponíveis
        use_tools: Se deve usar function calling
    
    Returns:
        (response_text, tool_calls) - Tupla com resposta e ferramentas a executar
    """
    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
    
    kwargs = {
        "model": "deepseek-chat",
        "messages": messages,
        "stream": False,
        "max_tokens": 1000,
        "temperature": 1.3,
    }
    
    if use_tools and available_tools:
        kwargs["tools"] = available_tools
    
    response = client.chat.completions.create(**kwargs)
    
    tool_calls = []
    if hasattr(response.choices[0].message, "tool_calls") and response.choices[0].message.tool_calls:
        tool_calls = [
            {
                "name": call.function.name,
                "input": json.loads(call.function.arguments)
            }
            for call in response.choices[0].message.tool_calls
        ]
    
    return response.choices[0].message.content, tool_calls


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

        # Construir histórico de mensagens
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        await self._build_message_history(ctx, question, messages)
        messages.append({"role": "user", "content": question})

        try:
            # Construir ferramentas dinamicamente
            available_tools = build_available_tools(self.bot)
            
            # Chamar a IA com tools
            response, tool_calls = generate_response(messages, available_tools, use_tools=True)
            
            if response is None:
                await ctx.send("❌ Desculpe, não consegui gerar uma resposta.")
                return
            
            if response.strip() != "":
                await ctx.send(response)

            # Executar ferramentas se solicitadas
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
