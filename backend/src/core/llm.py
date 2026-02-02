"""LLM client module for Claude API interactions."""

import logging
from typing import Any

import anthropic

from src.core.config import settings

logger = logging.getLogger(__name__)

# Default model - can be overridden per request
DEFAULT_MODEL = "claude-sonnet-4-20250514"
DEFAULT_MAX_TOKENS = 4096


class LLMClient:
    """Async client for Claude API interactions.

    Provides a simple interface for generating responses from Claude.
    """

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        """Initialize LLM client.

        Args:
            model: Claude model to use for generation.
        """
        self._api_key = settings.ANTHROPIC_API_KEY.get_secret_value()
        self._model = model
        self._client = anthropic.AsyncAnthropic(api_key=self._api_key)

    async def generate_response(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = 0.7,
    ) -> str:
        """Generate a response from Claude.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            system_prompt: Optional system prompt for context.
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature (0-1).

        Returns:
            Generated text response.

        Raises:
            anthropic.APIError: If API call fails.
        """
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": messages,
            "temperature": temperature,
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        logger.debug(
            "Calling Claude API",
            extra={
                "model": self._model,
                "message_count": len(messages),
                "has_system": system_prompt is not None,
            },
        )

        response = await self._client.messages.create(**kwargs)

        # Extract text from response
        text_content: str = str(response.content[0].text)

        logger.debug(
            "Claude API response received",
            extra={"response_length": len(text_content)},
        )

        return text_content
