import json
from typing import Any, TypeVar
from pydantic import BaseModel

from openai import OpenAI
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam

from .config import DEEPSEEK_API_KEY


class ResponseFormat(BaseModel):
    response: str


T = TypeVar("T", bound=BaseModel)


def generate_response(
    messages: list[dict[str, str]],
    available_tools: list[dict] | None = None,
    response_format: type[T] = ResponseFormat,
) -> tuple[T, list[dict[str, Any]]]:
    """Gera resposta da IA, opcionalmente com function calling.
    
    Args:
        messages: Histórico de mensagens
        available_tools: Lista de ferramentas disponíveis
        response_format: Modelo Pydantic para validar a resposta (opcional)
    
    Returns:
        (response, tool_calls) - Tupla com resposta e ferramentas a executar
    """
    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
    
    json_response_format = response_format.model_json_schema()

    messages[0]["content"] += "\n\nThe response must be exclusively in JSON format, following this schema:\n" + json.dumps(json_response_format)

    kwargs = {
        "model": "deepseek-chat",
        "messages": messages,
        "max_completion_tokens": 1000,
        "temperature": 1.3,
    }
    
    if available_tools:
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


    raw_response = response.choices[0].message.content
    response_text = raw_response.strip()
    if response_text.startswith("```json"):
        response_text = response_text[len("```json"):].strip()
    if response_text.endswith("```"):
        response_text = response_text[:-len("```")].strip()

    content_parsed = response_format.model_validate_json(response_text)
    
    return content_parsed, tool_calls
