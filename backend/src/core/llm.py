"""LLM client module for Claude API interactions."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

import anthropic

from src.core.config import settings
from src.core.resilience import claude_api_circuit_breaker

if TYPE_CHECKING:
    from src.core.cost_governor import CostGovernor

logger = logging.getLogger(__name__)

# Default model - can be overridden per request
DEFAULT_MODEL = "claude-sonnet-4-20250514"
DEFAULT_MAX_TOKENS = 4096

# Use the enhanced circuit breaker from resilience module
_llm_circuit_breaker = claude_api_circuit_breaker

# Module-level cost governor singleton (lazy-initialized)
_cost_governor: CostGovernor | None = None


def get_cost_governor() -> CostGovernor:
    """Get or create the module-level CostGovernor singleton."""
    global _cost_governor
    if _cost_governor is None:
        from src.core.cost_governor import CostGovernor

        _cost_governor = CostGovernor()
    return _cost_governor


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
        user_id: str | None = None,
    ) -> str:
        """Generate a response from Claude.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            system_prompt: Optional system prompt for context.
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature (0-1).
            user_id: Optional user ID for cost governance. When provided,
                budget is checked before the call and usage is recorded after.

        Returns:
            Generated text response.

        Raises:
            anthropic.APIError: If API call fails.
            BudgetExceededError: If user's daily budget is exhausted.
        """
        # Budget check (when user_id provided)
        if user_id:
            from src.core.cost_governor import LLMUsage
            from src.core.exceptions import BudgetExceededError

            governor = get_cost_governor()
            budget = await governor.check_budget(user_id)
            if not budget.can_proceed:
                raise BudgetExceededError(
                    user_id=user_id,
                    tokens_used=budget.tokens_used_today,
                    daily_budget=budget.daily_budget,
                )

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

        response = await _llm_circuit_breaker.call(self._client.messages.create, **kwargs)

        # Extract text from response
        text_content: str = str(response.content[0].text)

        logger.debug(
            "Claude API response received",
            extra={"response_length": len(text_content)},
        )

        # Record usage (when user_id provided, fail-open)
        if user_id:
            try:
                from src.core.cost_governor import LLMUsage

                usage = LLMUsage.from_anthropic_response(response)
                governor = get_cost_governor()
                await governor.record_usage(user_id, usage)
            except Exception:
                logger.exception("Failed to record LLM usage for user %s", user_id)

        return text_content

    async def stream_response(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = 0.7,
        user_id: str | None = None,
    ) -> AsyncIterator[str]:
        """Stream a response from Claude token by token.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            system_prompt: Optional system prompt for context.
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature (0-1).
            user_id: Optional user ID for cost governance.

        Yields:
            Text chunks as they arrive from the API.

        Raises:
            anthropic.APIError: If API call fails.
            BudgetExceededError: If user's daily budget is exhausted.
        """
        # Budget check (when user_id provided)
        if user_id:
            from src.core.exceptions import BudgetExceededError

            governor = get_cost_governor()
            budget = await governor.check_budget(user_id)
            if not budget.can_proceed:
                raise BudgetExceededError(
                    user_id=user_id,
                    tokens_used=budget.tokens_used_today,
                    daily_budget=budget.daily_budget,
                )

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": messages,
            "temperature": temperature,
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        logger.debug(
            "Streaming Claude API response",
            extra={
                "model": self._model,
                "message_count": len(messages),
                "has_system": system_prompt is not None,
            },
        )

        _llm_circuit_breaker.check()
        try:
            async with self._client.messages.stream(**kwargs) as stream:
                async for text in stream.text_stream:
                    yield text

                # Record usage after stream completes
                if user_id:
                    try:
                        from src.core.cost_governor import LLMUsage

                        final_message = await stream.get_final_message()
                        usage = LLMUsage.from_anthropic_response(final_message)
                        governor = get_cost_governor()
                        await governor.record_usage(user_id, usage)
                    except Exception:
                        logger.exception(
                            "Failed to record streaming usage for user %s", user_id
                        )

            _llm_circuit_breaker.record_success()
        except Exception:
            _llm_circuit_breaker.record_failure()
            raise
