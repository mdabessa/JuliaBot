"""AI response generation with structured output validation.

This module provides helpers for making API calls to LLM providers with
Pydantic-based response validation using the instructor library.
"""

from typing import TypeVar

import instructor
from pydantic import BaseModel


class ResponseFormat(BaseModel):
    """Default response format for unstructured AI replies."""

    response: str


T = TypeVar("T", bound=BaseModel)


def generate_response(
    messages: list[dict[str, str]],
    response_format: type[T] = ResponseFormat,
) -> T:
    """Generate an AI response with structured output validation.

    Calls the DeepSeek Chat API via instructor, which enforces strict Pydantic
    model validation on the response. This enables function calling and
    structured outputs when using a custom ``response_format`` model.

    Args:
        messages (list[dict[str, str]]): Message history in OpenAI chat format,
            with ``role`` and ``content`` keys per message.
        response_format (type[T], optional): Pydantic model class to enforce on
            the API response. Defaults to ``ResponseFormat``.

    Returns:
        T: Validated response instance of the requested model type.

    Raises:
        instructor.InstructorException: If the API call fails or response
        validation against the model fails.
    """

    client = instructor.from_provider(
        "deepseek/deepseek-chat",
        base_url="https://api.deepseek.com",
    )

    response = client.create(
        response_model=response_format,
        messages=messages,  # type: ignore
    )

    return response  # type: ignore
