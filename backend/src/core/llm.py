"""LLM client module for Claude API interactions.

Routes requests through LiteLLM for multi-model support and Langfuse
observability.  Extended thinking remains on the Anthropic SDK directly
(LiteLLM's thinking support is fragile for response parsing).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import anthropic
import litellm
from litellm import acompletion

from src.core.config import settings
from src.core.model_config import DEFAULT_CONFIG, MODEL_ROUTES
from src.core.resilience import claude_api_circuit_breaker
from src.core.task_characteristics import THINKING_BUDGETS
from src.core.task_types import TaskType

if TYPE_CHECKING:
    from src.core.cost_governor import CostGovernor, LLMUsage
    from src.core.usage_logger import UsageLogger

# ---------------------------------------------------------------------------
# LiteLLM / Langfuse configuration
# ---------------------------------------------------------------------------
litellm.success_callback = ["langfuse"]
litellm.failure_callback = ["langfuse"]
litellm.set_verbose = False  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Default model - can be overridden per request
DEFAULT_MODEL = "claude-sonnet-4-20250514"
DEFAULT_MAX_TOKENS = 4096

# Use the enhanced circuit breaker from resilience module
_llm_circuit_breaker = claude_api_circuit_breaker


# ---------------------------------------------------------------------------
# Dataclasses (unchanged public API)
# ---------------------------------------------------------------------------


@dataclass
class ToolUseRequest:
    """Represents a tool use request from the LLM."""

    id: str
    name: str
    input: dict[str, Any]


@dataclass
class LLMToolResponse:
    """Response from an LLM call that may include tool use requests."""

    text: str
    tool_calls: list[ToolUseRequest] = field(default_factory=list)
    stop_reason: str = "end_turn"
    usage: LLMUsage | None = field(default=None, repr=False)
    _raw_response: Any = field(default=None, repr=False)


@dataclass
class LLMResponse:
    """Structured response from an LLM call with optional thinking trace."""

    text: str
    thinking: str = ""
    usage: LLMUsage | None = field(default=None, repr=False)


# ---------------------------------------------------------------------------
# Module-level cost governor singleton (lazy-initialized)
# ---------------------------------------------------------------------------
_cost_governor: CostGovernor | None = None


def get_cost_governor() -> CostGovernor:
    """Get or create the module-level CostGovernor singleton."""
    global _cost_governor
    if _cost_governor is None:
        from src.core.cost_governor import CostGovernor

        _cost_governor = CostGovernor()
    return _cost_governor


# ---------------------------------------------------------------------------
# Private helpers: format translation between Anthropic & OpenAI schemas
# ---------------------------------------------------------------------------


def _prepend_system_message(
    system_prompt: str | None,
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert a separate system_prompt into an OpenAI-style system message.

    LiteLLM expects the system prompt as the first message with
    ``role: "system"`` rather than a separate ``system`` kwarg.
    """
    if not system_prompt:
        return list(messages)
    return [
        {
            "role": "system",
            "content": system_prompt,
            "cache_control": {"type": "ephemeral"},
        },
        *messages,
    ]


def _translate_messages_for_litellm(
    system_prompt: str | None,
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Translate Anthropic multi-block messages to OpenAI format.

    Handles ``tool_use`` / ``tool_result`` content blocks that appear in
    multi-turn tool-calling conversations.
    """
    translated: list[dict[str, Any]] = []

    if system_prompt:
        translated.append({
            "role": "system",
            "content": system_prompt,
            "cache_control": {"type": "ephemeral"},
        })

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content")

        # Simple string content — pass through
        if isinstance(content, str):
            translated.append({"role": role, "content": content})
            continue

        # List of content blocks (Anthropic multi-block format)
        if isinstance(content, list):
            text_parts: list[str] = []
            tool_calls_out: list[dict[str, Any]] = []
            tool_results: list[dict[str, Any]] = []

            for block in content:
                btype = block.get("type") if isinstance(block, dict) else None

                if btype == "text":
                    text_parts.append(block.get("text", ""))
                elif btype == "tool_use":
                    tool_calls_out.append({
                        "id": block["id"],
                        "type": "function",
                        "function": {
                            "name": block["name"],
                            "arguments": json.dumps(block["input"]),
                        },
                    })
                elif btype == "tool_result":
                    result_content = block.get("content", "")
                    if isinstance(result_content, list):
                        result_content = "\n".join(
                            b.get("text", "") for b in result_content if isinstance(b, dict)
                        )
                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": block.get("tool_use_id", ""),
                        "content": str(result_content),
                    })
                else:
                    # Unknown block type — treat as text
                    text_parts.append(str(block.get("text", block)))

            # Emit assistant message with tool_calls if present
            if tool_calls_out:
                assistant_msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": "\n".join(text_parts) if text_parts else None,
                    "tool_calls": tool_calls_out,
                }
                translated.append(assistant_msg)
            elif tool_results:
                # tool_result blocks come in user role in Anthropic format;
                # OpenAI expects them as separate tool messages
                for tr in tool_results:
                    translated.append(tr)
            elif text_parts:
                translated.append({"role": role, "content": "\n".join(text_parts)})
            else:
                translated.append({"role": role, "content": ""})
        else:
            # Fallback
            translated.append({"role": role, "content": str(content) if content else ""})

    return translated


def _anthropic_tools_to_openai(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert Anthropic tool definitions to OpenAI function-calling format.

    Anthropic: ``{name, description, input_schema}``
    OpenAI:    ``{type: "function", function: {name, description, parameters}}``
    """
    converted: list[dict[str, Any]] = []
    for tool in tools:
        converted.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {}),
            },
        })
    return converted


def _openai_tool_calls_to_anthropic(
    tool_calls: list[Any] | None,
) -> list[ToolUseRequest]:
    """Convert OpenAI tool call objects to Anthropic-style ToolUseRequest list."""
    if not tool_calls:
        return []

    result: list[ToolUseRequest] = []
    for tc in tool_calls:
        func = tc.function if hasattr(tc, "function") else tc.get("function", {})
        name = func.name if hasattr(func, "name") else func.get("name", "")
        args_str = func.arguments if hasattr(func, "arguments") else func.get("arguments", "{}")
        tc_id = tc.id if hasattr(tc, "id") else tc.get("id", "")

        try:
            parsed_input = json.loads(args_str) if isinstance(args_str, str) else args_str
        except json.JSONDecodeError:
            parsed_input = {"raw": args_str}

        result.append(ToolUseRequest(id=tc_id, name=name, input=parsed_input))
    return result


def _litellm_usage_to_llm_usage(usage: Any) -> "LLMUsage":
    """Build an LLMUsage from a LiteLLM/OpenAI-style usage object."""
    from src.core.cost_governor import LLMUsage

    if usage is None:
        return LLMUsage()

    return LLMUsage(
        input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        output_tokens=getattr(usage, "completion_tokens", 0) or 0,
        thinking_tokens=0,
        cache_read_tokens=0,
        cache_creation_tokens=0,
    )


def _build_langfuse_metadata(
    task: TaskType | None = None,
    tenant_id: str = "",
    user_id: str = "",
    agent_id: str = "",
    goal_id: str = "",
) -> dict[str, Any]:
    """Build metadata dict for Langfuse traces."""
    meta: dict[str, Any] = {}
    if task:
        meta["task_type"] = task.value
    if tenant_id:
        meta["tenant_id"] = tenant_id
    if user_id:
        meta["trace_user_id"] = user_id
    if agent_id:
        meta["agent_id"] = agent_id
    if goal_id:
        meta["goal_id"] = goal_id
    return meta


# ---------------------------------------------------------------------------
# LLMClient
# ---------------------------------------------------------------------------


class LLMClient:
    """Async client for Claude API interactions.

    Routes standard calls through LiteLLM for multi-model support and
    Langfuse observability.  Extended thinking calls use the Anthropic SDK
    directly.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        usage_logger: UsageLogger | None = None,
    ) -> None:
        """Initialize LLM client.

        Args:
            model: Claude model to use for generation.
            usage_logger: Optional UsageLogger for persisting usage metrics.
        """
        self._api_key = settings.ANTHROPIC_API_KEY.get_secret_value()
        self._model = model
        # Anthropic SDK client — used for extended thinking
        self._client = anthropic.AsyncAnthropic(api_key=self._api_key)
        # LiteLLM model string for standard calls
        self._litellm_model = f"anthropic/{model}"
        if usage_logger is not None:
            self._usage_logger = usage_logger
        else:
            self._usage_logger = self._create_default_usage_logger()

    @staticmethod
    def _create_default_usage_logger() -> UsageLogger | None:
        """Auto-create UsageLogger with the Supabase singleton.

        Returns None (disabling logging) if Supabase is unavailable,
        e.g. in unit tests without DB configuration.
        """
        try:
            from src.core.usage_logger import UsageLogger as _UL
            from src.db.supabase import SupabaseClient
            return _UL(SupabaseClient.get_client())
        except Exception:
            logger.debug("UsageLogger auto-creation skipped (no Supabase client)")
            return None

    def _fire_usage_log(self, **kwargs: Any) -> None:
        """Fire-and-forget usage logging. Errors are suppressed."""
        usage_logger = getattr(self, "_usage_logger", None)
        if not usage_logger:
            return
        task = asyncio.create_task(usage_logger.log(**kwargs))
        task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)

    # ------------------------------------------------------------------
    # New task-aware generation method
    # ------------------------------------------------------------------

    async def generate(
        self,
        messages: list[dict[str, Any]],
        *,
        task: TaskType = TaskType.GENERAL,
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        tenant_id: str = "",
        user_id: str = "",
        agent_id: str = "",
        goal_id: str = "",
    ) -> str:
        """Task-aware generation using model routing configuration.

        Looks up model/temperature/max_tokens from ``MODEL_ROUTES`` for the
        given ``task``, falling back to caller overrides or the route defaults.

        Args:
            messages: Conversation messages.
            task: TaskType for model routing.
            system_prompt: Optional system prompt.
            max_tokens: Override max tokens (uses route config if None).
            temperature: Override temperature (uses route config if None).
            tenant_id: Tenant ID for Langfuse tracing.
            user_id: User ID for budget checks and tracing.
            agent_id: Agent ID for tracing.
            goal_id: Goal ID for tracing.

        Returns:
            Generated text response.
        """
        config = MODEL_ROUTES.get(task, DEFAULT_CONFIG)
        effective_model = config.model
        effective_max_tokens = max_tokens if max_tokens is not None else config.max_tokens
        effective_temperature = temperature if temperature is not None else config.temperature

        # Budget check
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

        litellm_messages = _prepend_system_message(system_prompt, messages)
        metadata = _build_langfuse_metadata(task, tenant_id, user_id, agent_id, goal_id)

        logger.debug(
            "Calling LiteLLM (task-routed)",
            extra={
                "model": effective_model,
                "task": task.value,
                "message_count": len(messages),
            },
        )

        start = time.time()
        try:
            response = await _llm_circuit_breaker.call(
                acompletion,
                model=effective_model,
                messages=litellm_messages,
                max_tokens=effective_max_tokens,
                temperature=effective_temperature,
                api_key=self._api_key,
                metadata=metadata,
            )
        except Exception as exc:
            # Fallback model on failure
            if config.fallback:
                logger.warning(
                    "Primary model %s failed for task %s, trying fallback %s",
                    effective_model,
                    task.value,
                    config.fallback,
                )
                start = time.time()
                try:
                    response = await acompletion(
                        model=config.fallback,
                        messages=litellm_messages,
                        max_tokens=effective_max_tokens,
                        temperature=effective_temperature,
                        api_key=self._api_key,
                        metadata=metadata,
                    )
                except Exception as fallback_exc:
                    latency_ms = int((time.time() - start) * 1000)
                    self._fire_usage_log(
                        tenant_id=tenant_id,
                        user_id=user_id,
                        agent_id=agent_id,
                        task_type=task.value,
                        model=config.fallback,
                        latency_ms=latency_ms,
                        status="error",
                        error_message=str(fallback_exc),
                        goal_id=goal_id,
                    )
                    raise
            else:
                latency_ms = int((time.time() - start) * 1000)
                self._fire_usage_log(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    agent_id=agent_id,
                    task_type=task.value,
                    model=effective_model,
                    latency_ms=latency_ms,
                    status="error",
                    error_message=str(exc),
                    goal_id=goal_id,
                )
                raise

        latency_ms = int((time.time() - start) * 1000)
        text_content = response.choices[0].message.content or ""

        resp_usage = getattr(response, "usage", None)
        self._fire_usage_log(
            tenant_id=tenant_id,
            user_id=user_id,
            agent_id=agent_id,
            task_type=task.value,
            model=getattr(response, "model", effective_model),
            input_tokens=getattr(resp_usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(resp_usage, "completion_tokens", 0) or 0,
            latency_ms=latency_ms,
            goal_id=goal_id,
        )

        # Record usage
        if user_id:
            try:
                usage = _litellm_usage_to_llm_usage(response.usage)
                governor = get_cost_governor()
                await governor.record_usage(user_id, usage)
            except Exception:
                logger.exception("Failed to record LLM usage for user %s", user_id)

        return str(text_content)

    # ------------------------------------------------------------------
    # generate_response — signature unchanged, now routes through LiteLLM
    # ------------------------------------------------------------------

    async def generate_response(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = 0.7,
        user_id: str | None = None,
        task: TaskType = TaskType.GENERAL,
        tenant_id: str = "",
        agent_id: str = "",
        goal_id: str = "",
    ) -> str:
        """Generate a response from Claude.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            system_prompt: Optional system prompt for context.
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature (0-1).
            user_id: Optional user ID for cost governance. When provided,
                budget is checked before the call and usage is recorded after.
            task: TaskType for observability tagging.
            tenant_id: Tenant ID for cost tracking.
            agent_id: Agent/service identifier for tracing.
            goal_id: Goal ID for tracing.

        Returns:
            Generated text response.

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

        litellm_messages = _prepend_system_message(system_prompt, messages)
        metadata = _build_langfuse_metadata(task, tenant_id, user_id or "", agent_id, goal_id)

        logger.debug(
            "Calling Claude API via LiteLLM",
            extra={
                "model": self._litellm_model,
                "message_count": len(messages),
                "has_system": system_prompt is not None,
                "task": task.value,
            },
        )

        start = time.time()
        try:
            response = await _llm_circuit_breaker.call(
                acompletion,
                model=self._litellm_model,
                messages=litellm_messages,
                max_tokens=max_tokens,
                temperature=temperature,
                api_key=self._api_key,
                metadata=metadata,
            )
        except Exception as exc:
            latency_ms = int((time.time() - start) * 1000)
            self._fire_usage_log(
                tenant_id=tenant_id,
                user_id=user_id or "",
                agent_id=agent_id,
                task_type=task.value,
                model=self._litellm_model,
                latency_ms=latency_ms,
                status="error",
                error_message=str(exc),
                goal_id=goal_id,
            )
            raise

        latency_ms = int((time.time() - start) * 1000)

        # Extract text from response (OpenAI format)
        text_content: str = str(response.choices[0].message.content or "")

        logger.debug(
            "Claude API response received",
            extra={"response_length": len(text_content)},
        )

        resp_usage = getattr(response, "usage", None)
        self._fire_usage_log(
            tenant_id=tenant_id,
            user_id=user_id or "",
            agent_id=agent_id,
            task_type=task.value,
            model=getattr(response, "model", self._litellm_model),
            input_tokens=getattr(resp_usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(resp_usage, "completion_tokens", 0) or 0,
            latency_ms=latency_ms,
            goal_id=goal_id,
        )

        # Record usage (when user_id provided, fail-open)
        if user_id:
            try:
                usage = _litellm_usage_to_llm_usage(response.usage)
                governor = get_cost_governor()
                await governor.record_usage(user_id, usage)
            except Exception:
                logger.exception("Failed to record LLM usage for user %s", user_id)

        return text_content

    # ------------------------------------------------------------------
    # generate_response_with_tools — now routes through LiteLLM
    # ------------------------------------------------------------------

    async def generate_response_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        system_prompt: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = 0.7,
        user_id: str | None = None,
        task: TaskType = TaskType.GENERAL,
        tenant_id: str = "",
        agent_id: str = "",
        goal_id: str = "",
    ) -> LLMToolResponse:
        """Generate a response from Claude with tool use support.

        When the model decides to use a tool, it returns tool_calls in the
        response. The caller is responsible for executing the tools and
        feeding results back via a follow-up call.

        Args:
            messages: List of message dicts (supports 'content' as str or list).
            tools: List of Anthropic-format tool definitions.
            system_prompt: Optional system prompt for context.
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature (0-1).
            user_id: Optional user ID for cost governance.
            task: TaskType for observability tagging.
            tenant_id: Tenant ID for cost tracking.
            agent_id: Agent/service identifier for tracing.
            goal_id: Goal ID for tracing.

        Returns:
            LLMToolResponse with text, tool_calls, and stop_reason.
        """
        # Budget check
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

        # Translate to OpenAI formats
        litellm_messages = _translate_messages_for_litellm(system_prompt, messages)
        openai_tools = _anthropic_tools_to_openai(tools)
        metadata = _build_langfuse_metadata(task, tenant_id, user_id or "", agent_id, goal_id)

        logger.debug(
            "Calling Claude API with tools via LiteLLM",
            extra={
                "model": self._litellm_model,
                "message_count": len(messages),
                "tool_count": len(tools),
                "task": task.value,
            },
        )

        start = time.time()
        try:
            response = await _llm_circuit_breaker.call(
                acompletion,
                model=self._litellm_model,
                messages=litellm_messages,
                max_tokens=max_tokens,
                temperature=temperature,
                tools=openai_tools,
                api_key=self._api_key,
                metadata=metadata,
            )
        except Exception as exc:
            latency_ms = int((time.time() - start) * 1000)
            self._fire_usage_log(
                tenant_id=tenant_id,
                user_id=user_id or "",
                agent_id=agent_id,
                task_type=task.value,
                model=self._litellm_model,
                latency_ms=latency_ms,
                status="error",
                error_message=str(exc),
                goal_id=goal_id,
            )
            raise

        latency_ms = int((time.time() - start) * 1000)

        choice = response.choices[0]
        message = choice.message

        # Extract text content
        text = str(message.content or "")

        # Convert tool calls back to Anthropic format
        tool_calls = _openai_tool_calls_to_anthropic(message.tool_calls)

        # Map finish_reason: "tool_calls" → "tool_use", "stop" → "end_turn"
        finish_reason = getattr(choice, "finish_reason", "stop") or "stop"
        if finish_reason == "tool_calls":
            stop_reason = "tool_use"
        elif finish_reason == "stop":
            stop_reason = "end_turn"
        else:
            stop_reason = finish_reason

        resp_usage = getattr(response, "usage", None)
        self._fire_usage_log(
            tenant_id=tenant_id,
            user_id=user_id or "",
            agent_id=agent_id,
            task_type=task.value,
            model=getattr(response, "model", self._litellm_model),
            input_tokens=getattr(resp_usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(resp_usage, "completion_tokens", 0) or 0,
            latency_ms=latency_ms,
            goal_id=goal_id,
        )

        # Record usage (fail-open)
        usage: LLMUsage | None = None
        if user_id:
            try:
                usage = _litellm_usage_to_llm_usage(response.usage)
                governor = get_cost_governor()
                await governor.record_usage(user_id, usage)
            except Exception:
                logger.exception("Failed to record tool-use LLM usage for user %s", user_id)

        return LLMToolResponse(
            text=text,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            usage=usage,
            _raw_response=response,
        )

    # ------------------------------------------------------------------
    # generate_response_with_thinking — stays on Anthropic SDK
    # ------------------------------------------------------------------

    async def generate_response_with_thinking(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        thinking_effort: str = "complex",
        user_id: str | None = None,
        task: TaskType = TaskType.GENERAL,
        tenant_id: str = "",
        agent_id: str = "",
        goal_id: str = "",
    ) -> LLMResponse:
        """Generate a response with extended thinking enabled.

        Returns an ``LLMResponse`` containing both the text output and the
        thinking trace.  Temperature is omitted (Anthropic forbids it when
        extended thinking is active).

        This method uses the Anthropic SDK directly (not LiteLLM) because
        LiteLLM's thinking support is fragile for response parsing.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            system_prompt: Optional system prompt for context.
            max_tokens: Maximum tokens in response.
            thinking_effort: One of "routine", "complex", "critical".
            user_id: Optional user ID for cost governance.
            task: TaskType for observability tagging.
            tenant_id: Tenant ID for cost tracking.
            agent_id: Agent/service identifier for tracing.
            goal_id: Goal ID for tracing.

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

        # Anthropic API requires max_tokens > budget_tokens when thinking is enabled.
        # Ensure max_tokens is at least budget_tokens + 1024 for a reasonable text response.
        effective_max_tokens = max(max_tokens, budget_tokens + 1024)

        # Build kwargs — no temperature when thinking is enabled
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": effective_max_tokens,
            "messages": messages,
            "thinking": {
                "type": "enabled",
                "budget_tokens": budget_tokens,
            },
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        logger.debug(
            "Calling Claude API with extended thinking (Anthropic SDK)",
            extra={
                "model": self._model,
                "thinking_effort": effort,
                "budget_tokens": budget_tokens,
                "message_count": len(messages),
            },
        )

        start = time.time()
        try:
            response = await _llm_circuit_breaker.call(
                self._client.messages.create, **kwargs
            )
        except Exception as exc:
            latency_ms = int((time.time() - start) * 1000)
            self._fire_usage_log(
                tenant_id=tenant_id,
                user_id=user_id or "",
                agent_id=agent_id,
                task_type=task.value,
                model=self._model,
                latency_ms=latency_ms,
                status="error",
                error_message=str(exc),
                goal_id=goal_id,
            )
            raise

        latency_ms = int((time.time() - start) * 1000)

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

        self._fire_usage_log(
            tenant_id=tenant_id,
            user_id=user_id or "",
            agent_id=agent_id,
            task_type=task.value,
            model=self._model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            latency_ms=latency_ms,
            goal_id=goal_id,
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

    # ------------------------------------------------------------------
    # stream_response — now routes through LiteLLM
    # ------------------------------------------------------------------

    async def stream_response(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = 0.7,
        user_id: str | None = None,
        task: TaskType = TaskType.GENERAL,
        tenant_id: str = "",
        agent_id: str = "",
        goal_id: str = "",
    ) -> AsyncIterator[str]:
        """Stream a response from Claude token by token.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            system_prompt: Optional system prompt for context.
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature (0-1).
            user_id: Optional user ID for cost governance.
            task: TaskType for observability tagging.
            tenant_id: Tenant ID for cost tracking.
            agent_id: Agent/service identifier for tracing.
            goal_id: Goal ID for tracing.

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

        litellm_messages = _prepend_system_message(system_prompt, messages)
        metadata = _build_langfuse_metadata(task, tenant_id, user_id or "", agent_id, goal_id)

        logger.debug(
            "Streaming Claude API response via LiteLLM",
            extra={
                "model": self._litellm_model,
                "message_count": len(messages),
                "has_system": system_prompt is not None,
                "task": task.value,
            },
        )

        _llm_circuit_breaker.check()
        start = time.time()
        try:
            response = await acompletion(
                model=self._litellm_model,
                messages=litellm_messages,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=True,
                stream_options={"include_usage": True},
                api_key=self._api_key,
                metadata=metadata,
            )

            stream_usage: Any = None
            async for chunk in response:
                # Accumulate usage from the final chunk
                if hasattr(chunk, "usage") and chunk.usage is not None:
                    stream_usage = chunk.usage

                if chunk.choices and chunk.choices[0].delta:
                    delta_content = chunk.choices[0].delta.content
                    if delta_content:
                        yield delta_content

            latency_ms = int((time.time() - start) * 1000)

            # Fire usage log after stream completes
            if stream_usage is not None:
                self._fire_usage_log(
                    tenant_id=tenant_id,
                    user_id=user_id or "",
                    agent_id=agent_id,
                    task_type=task.value,
                    model=self._litellm_model,
                    input_tokens=getattr(stream_usage, "prompt_tokens", 0) or 0,
                    output_tokens=getattr(stream_usage, "completion_tokens", 0) or 0,
                    latency_ms=latency_ms,
                    goal_id=goal_id,
                )
            else:
                self._fire_usage_log(
                    tenant_id=tenant_id,
                    user_id=user_id or "",
                    agent_id=agent_id,
                    task_type=task.value,
                    model=self._litellm_model,
                    input_tokens=0,
                    output_tokens=0,
                    latency_ms=latency_ms,
                    goal_id=goal_id,
                )

            # Record usage after stream completes
            if user_id and stream_usage is not None:
                try:
                    usage = _litellm_usage_to_llm_usage(stream_usage)
                    governor = get_cost_governor()
                    await governor.record_usage(user_id, usage)
                except Exception:
                    logger.exception(
                        "Failed to record streaming usage for user %s", user_id
                    )

            _llm_circuit_breaker.record_success()
        except Exception as exc:
            latency_ms = int((time.time() - start) * 1000)
            self._fire_usage_log(
                tenant_id=tenant_id,
                user_id=user_id or "",
                agent_id=agent_id,
                task_type=task.value,
                model=self._litellm_model,
                latency_ms=latency_ms,
                status="error",
                error_message=str(exc),
                goal_id=goal_id,
            )
            _llm_circuit_breaker.record_failure()
            raise
