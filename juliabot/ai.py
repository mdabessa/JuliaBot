import json
from typing import Any

from openai import OpenAI
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam

from .config import DEEPSEEK_API_KEY


def generate_response(
    messages: list[ChatCompletionMessageParam],
    available_tools: list[dict] | None = None,
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
    
    if available_tools:
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

