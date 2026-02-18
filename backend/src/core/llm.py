"""LLM client module for Claude API interactions."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import anthropic

from src.core.config import settings
from src.core.resilience import claude_api_circuit_breaker
from src.core.task_characteristics import THINKING_BUDGETS

if TYPE_CHECKING:
    from src.core.cost_governor import CostGovernor, LLMUsage

logger = logging.getLogger(__name__)

# Default model - can be overridden per request
DEFAULT_MODEL = "claude-sonnet-4-20250514"
DEFAULT_MAX_TOKENS = 4096

# Use the enhanced circuit breaker from resilience module
_llm_circuit_breaker = claude_api_circuit_breaker

@dataclass
class LLMResponse:
    """Structured response from an LLM call with optional thinking trace."""

    text: str
    thinking: str = ""
    usage: LLMUsage | None = field(default=None, repr=False)


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

    async def generate_response_with_thinking(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        thinking_effort: str = "complex",
        user_id: str | None = None,
    ) -> LLMResponse:
        """Generate a response with extended thinking enabled.

        Returns an ``LLMResponse`` containing both the text output and the
        thinking trace.  Temperature is omitted (Anthropic forbids it when
        extended thinking is active).

        Args:
            messages: List of message dicts with 'role' and 'content'.
            system_prompt: Optional system prompt for context.
            max_tokens: Maximum tokens in response.
            thinking_effort: One of "routine", "complex", "critical".
            user_id: Optional user ID for cost governance.

        Returns:
            LLMResponse with text, thinking trace, and usage.

        Raises:
            anthropic.APIError: If API call fails.
            BudgetExceededError: If user's daily budget is exhausted.
        """
        from src.core.cost_governor import LLMUsage
        from src.core.exceptions import BudgetExceededError

        effort = thinking_effort

        # Budget check (when user_id provided)
        if user_id:
            governor = get_cost_governor()
            budget = await governor.check_budget(user_id)
            if not budget.can_proceed:
                raise BudgetExceededError(
                    user_id=user_id,
                    tokens_used=budget.tokens_used_today,
                    daily_budget=budget.daily_budget,
                )
            if budget.should_reduce_effort:
                effort = governor.get_thinking_budget(budget, effort)

        budget_tokens = THINKING_BUDGETS.get(effort, THINKING_BUDGETS["complex"])

        # Build kwargs — no temperature when thinking is enabled
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": messages,
            "thinking": {
                "type": "enabled",
                "budget_tokens": budget_tokens,
            },
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        logger.debug(
            "Calling Claude API with extended thinking",
            extra={
                "model": self._model,
                "thinking_effort": effort,
                "budget_tokens": budget_tokens,
                "message_count": len(messages),
            },
        )

        response = await _llm_circuit_breaker.call(
            self._client.messages.create, **kwargs
        )

        # Extract thinking and text blocks
        thinking_parts: list[str] = []
        text_parts: list[str] = []
        for block in response.content:
            block_type = getattr(block, "type", None)
            if block_type == "thinking":
                thinking_parts.append(getattr(block, "thinking", ""))
            elif block_type == "text":
                text_parts.append(getattr(block, "text", ""))

        usage = LLMUsage.from_anthropic_response(response)

        logger.debug(
            "Claude API thinking response received",
            extra={
                "thinking_length": sum(len(p) for p in thinking_parts),
                "response_length": sum(len(p) for p in text_parts),
                "total_tokens": usage.total_tokens,
            },
        )

        # Record usage (fail-open)
        if user_id:
            try:
                governor = get_cost_governor()
                await governor.record_usage(user_id, usage)
            except Exception:
                logger.exception("Failed to record thinking usage for user %s", user_id)

        return LLMResponse(
            text="\n".join(text_parts),
            thinking="\n".join(thinking_parts),
            usage=usage,
        )

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
