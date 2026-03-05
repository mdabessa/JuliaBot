from typing import TypeVar
from pydantic import BaseModel

import instructor


class ResponseFormat(BaseModel):
    response: str


T = TypeVar("T", bound=BaseModel)


def generate_response(
    messages: list[dict[str, str]],
    response_format: type[T] = ResponseFormat,
) -> T:
    """Gera resposta da IA, opcionalmente com function calling.
    
    Args:
        messages: Histórico de mensagens
        response_format: Modelo Pydantic para validar a resposta (opcional)
    
    Returns:
        response - Resposta da IA, já validada pelo modelo Pydantic
    """

    client = instructor.from_provider(
        "deepseek/deepseek-chat",
        base_url="https://api.deepseek.com",
    )

    response = client.create(
        response_model=response_format,
        messages=messages, # type: ignore
    )

    return response # type: ignore
