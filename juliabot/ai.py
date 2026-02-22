import json
import inspect
from typing import Any, get_origin, get_args, Union
from collections.abc import Callable

from discord.ext import commands
from discord import User, TextChannel, Member, Role, Message, Guild
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam, ChatCompletion

from .config import DEEPSEEK_API_KEY



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
    
    response: ChatCompletion = client.chat.completions.create(**kwargs)
    
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

