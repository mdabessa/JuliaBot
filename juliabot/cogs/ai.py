import inspect
from collections.abc import Callable
from typing import Any, Union, get_args, get_origin

from discord import Guild, Member, Message, Role, TextChannel, User
from discord.ext import commands
from openai.types.chat import ChatCompletionMessageParam

from ..ai import generate_response
from ..config import CHARACTER_LIMIT, MESSAGE_HISTORY_LIMIT, SYSTEM_PROMPT


def _get_param_type_and_description(annotation: Any) -> tuple[str, str]:
    """Detecta o tipo JSON Schema e descrição para uma anotação Python complexa.
    
    Args:
        annotation: Anotação de tipo Python (pode ser complexa)
        
    Returns:
        (tipo_json_schema, descrição)
    """
    type_mapping = {
        User: ("string", "ID ou menção de um usuário Discord"),
        Member: ("string", "ID ou menção de um membro do servidor"),
        TextChannel: ("string", "ID ou menção de um canal de texto"),
        Role: ("string", "ID ou menção de um cargo"),
        Message: ("string", "ID de uma mensagem"),
        Guild: ("string", "ID de um servidor Discord"),
        str: ("string", "Texto"),
        int: ("integer", "Número inteiro"),
        float: ("number", "Número decimal"),
        bool: ("boolean", "Verdadeiro ou falso"),
    }
    
    if annotation == inspect.Parameter.empty:
        return "string", "Parâmetro de texto"
    
    if annotation in type_mapping:
        param_type, description = type_mapping[annotation]
        return param_type, description
    
    annotation_name = annotation.__class__.__name__ if hasattr(annotation, '__class__') else str(annotation)
    annotation_str = str(annotation)
    
    # Detectar tipos do discord.py por nome
    if "discord." in annotation_str or "discord." in annotation_name:
        if "User" in annotation_str:
            return "string", "ID ou menção de um usuário Discord"
        elif "Channel" in annotation_str or "TextChannel" in annotation_str:
            return "string", "ID ou menção de um canal de texto"
        elif "Role" in annotation_str:
            return "string", "ID ou menção de um cargo"
        elif "Member" in annotation_str:
            return "string", "ID ou menção de um membro"
        elif "Message" in annotation_str:
            return "string", "ID de uma mensagem"
        elif "Guild" in annotation_str:
            return "string", "ID de um servidor"
    
    # Detectar converters customizados
    if "Converter" in annotation_name or "converter" in annotation_str.lower():
        if "Date" in annotation_str:
            return "string", "Data (ex: '25/12/2024' ou '25/12/2024-15:30')"
        elif "DeltaToDate" in annotation_str:
            return "string", "Intervalo de tempo (ex: '2day5hour' para 2 dias e 5 horas ou '1a3month5days4hour10min' para 1 ano, 3 meses, 5 dias, 4 horas e 10 minutos)"
        elif "NextDate" in annotation_str:
            return "string", "Próxima data (ex: 'day2' para o próximo dia 2 do mês ou 'day15hour10' para o próximo dia 15 do mês às 10 horas)"
        
        print(f"Converter detectado, mas tipo específico desconhecido: {annotation} (str: {annotation_str}, name: {annotation_name})")
        return "string", f"Parâmetro convertido ({annotation_name})"
    
    # Tratar Optional[T] (que é Union[T, None])
    origin = get_origin(annotation)
    if origin is Union:
        args = get_args(annotation)
        # Optional[T] é Union[T, None], pegar o primeiro que não seja None
        for arg in args:
            if arg is not type(None):
                return _get_param_type_and_description(arg)
    
    # Tratar Union[T1, T2, ...]
    if origin is Union:
        args = get_args(annotation)
        # Tentar encontrar um tipo útil
        for arg in args:
            if arg is not type(None):
                return _get_param_type_and_description(arg)
    
    print(f"Tipo desconhecido para anotação: {annotation} (str: {annotation_str}, name: {annotation_name})")
    return "string", f"Parâmetro ({annotation_name})"


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
        
        param_type, param_description = _get_param_type_and_description(param.annotation)
        
        properties[param_name] = {
            "type": param_type,
            "description": param_description
        }
        
        if param.default == inspect.Parameter.empty:
            required.append(param_name)
    
    return properties, required


def build_available_command_tools(bot: commands.Bot) -> list[dict]:
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


class AI(commands.Cog, name="ai"):
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
            available_tools = build_available_command_tools(self.bot)
            
            response, tool_calls = generate_response(messages, available_tools)
            response_text = response.response
            
            
            if response_text.strip() != "":
                await ctx.send(response_text)

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
        messages: list[ChatCompletionMessageParam] = [
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
    bot.add_cog(AI(bot))
