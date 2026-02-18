"""Tests for LLMClient extended thinking support."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_anthropic_client():
    """Create a mock Anthropic async client."""
    client = AsyncMock()
    return client


@pytest.fixture
def mock_thinking_response():
    """Create a mock API response with thinking and text blocks."""
    thinking_block = MagicMock()
    thinking_block.type = "thinking"
    thinking_block.thinking = "Let me analyze this step by step..."

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = '{"result": "analysis complete"}'

    response = MagicMock()
    response.content = [thinking_block, text_block]

    # Mock usage
    usage = MagicMock()
    usage.input_tokens = 100
    usage.output_tokens = 50
    usage.cache_read_input_tokens = 0
    usage.cache_creation_input_tokens = 0
    response.usage = usage

    return response


@pytest.fixture
def mock_no_thinking_response():
    """Create a mock API response with only text blocks (no thinking)."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "Simple response"

    response = MagicMock()
    response.content = [text_block]

    usage = MagicMock()
    usage.input_tokens = 50
    usage.output_tokens = 20
    usage.cache_read_input_tokens = 0
    usage.cache_creation_input_tokens = 0
    response.usage = usage

    return response


def test_thinking_budget_values() -> None:
    """THINKING_BUDGETS has correct values for each effort level."""
    from src.core.task_characteristics import THINKING_BUDGETS

    assert THINKING_BUDGETS["routine"] == 4096
    assert THINKING_BUDGETS["complex"] == 16384
    assert THINKING_BUDGETS["critical"] == 32768


def test_llm_response_dataclass() -> None:
    """LLMResponse holds text, thinking, and usage."""
    from src.core.llm import LLMResponse

    resp = LLMResponse(text="hello", thinking="thought process")
    assert resp.text == "hello"
    assert resp.thinking == "thought process"
    assert resp.usage is None

    resp2 = LLMResponse(text="hi")
    assert resp2.thinking == ""


@pytest.mark.asyncio
async def test_generate_with_thinking_returns_llm_response(
    mock_anthropic_client, mock_thinking_response
) -> None:
    """generate_response_with_thinking returns an LLMResponse."""
    from src.core.llm import LLMClient, LLMResponse

    with patch("src.core.llm._llm_circuit_breaker") as mock_cb:
        mock_cb.call = AsyncMock(return_value=mock_thinking_response)

        client = LLMClient.__new__(LLMClient)
        client._client = mock_anthropic_client
        client._model = "claude-sonnet-4-20250514"

        result = await client.generate_response_with_thinking(
            messages=[{"role": "user", "content": "test"}],
        )

        assert isinstance(result, LLMResponse)
        assert result.text == '{"result": "analysis complete"}'
        assert result.thinking == "Let me analyze this step by step..."
        assert result.usage is not None


@pytest.mark.asyncio
async def test_generate_with_thinking_does_not_set_temperature(
    mock_anthropic_client, mock_thinking_response
) -> None:
    """Temperature must NOT be passed when extended thinking is enabled."""
    from src.core.llm import LLMClient

    with patch("src.core.llm._llm_circuit_breaker") as mock_cb:
        mock_cb.call = AsyncMock(return_value=mock_thinking_response)

        client = LLMClient.__new__(LLMClient)
        client._client = mock_anthropic_client
        client._model = "claude-sonnet-4-20250514"

        await client.generate_response_with_thinking(
            messages=[{"role": "user", "content": "test"}],
        )

        # circuit_breaker.call(func, **kwargs) — kwargs are keyword args
        passed_kwargs = mock_cb.call.call_args.kwargs
        assert "temperature" not in passed_kwargs


@pytest.mark.asyncio
async def test_generate_with_thinking_sets_thinking_param(
    mock_anthropic_client, mock_thinking_response
) -> None:
    """The thinking parameter is set in kwargs."""
    from src.core.llm import LLMClient

    with patch("src.core.llm._llm_circuit_breaker") as mock_cb:
        mock_cb.call = AsyncMock(return_value=mock_thinking_response)

        client = LLMClient.__new__(LLMClient)
        client._client = mock_anthropic_client
        client._model = "claude-sonnet-4-20250514"

        await client.generate_response_with_thinking(
            messages=[{"role": "user", "content": "test"}],
            thinking_effort="complex",
        )

        call_kwargs = mock_cb.call.call_args.kwargs
        assert "thinking" in call_kwargs
        assert call_kwargs["thinking"]["type"] == "enabled"
        assert call_kwargs["thinking"]["budget_tokens"] == 16384


@pytest.mark.asyncio
async def test_budget_check_before_call(
    mock_anthropic_client, mock_thinking_response
) -> None:
    """When user_id is provided, governor.check_budget is called."""
    from src.core.llm import LLMClient

    mock_governor = MagicMock()
    mock_budget = MagicMock()
    mock_budget.can_proceed = True
    mock_budget.should_reduce_effort = False
    mock_governor.check_budget = AsyncMock(return_value=mock_budget)
    mock_governor.record_usage = AsyncMock()

    with (
        patch("src.core.llm._llm_circuit_breaker") as mock_cb,
        patch("src.core.llm.get_cost_governor", return_value=mock_governor),
    ):
        mock_cb.call = AsyncMock(return_value=mock_thinking_response)

        client = LLMClient.__new__(LLMClient)
        client._client = mock_anthropic_client
        client._model = "claude-sonnet-4-20250514"

        await client.generate_response_with_thinking(
            messages=[{"role": "user", "content": "test"}],
            user_id="user-123",
        )

        mock_governor.check_budget.assert_called_once_with("user-123")


@pytest.mark.asyncio
async def test_budget_exceeded_raises(
    mock_anthropic_client,
) -> None:
    """BudgetExceededError raised when can_proceed is False."""
    from src.core.exceptions import BudgetExceededError
    from src.core.llm import LLMClient

    mock_governor = MagicMock()
    mock_budget = MagicMock()
    mock_budget.can_proceed = False
    mock_budget.tokens_used_today = 2000000
    mock_budget.daily_budget = 2000000
    mock_governor.check_budget = AsyncMock(return_value=mock_budget)

    with (
        patch("src.core.llm.get_cost_governor", return_value=mock_governor),
    ):
        client = LLMClient.__new__(LLMClient)
        client._client = mock_anthropic_client
        client._model = "claude-sonnet-4-20250514"

        with pytest.raises(BudgetExceededError):
            await client.generate_response_with_thinking(
                messages=[{"role": "user", "content": "test"}],
                user_id="user-123",
            )


@pytest.mark.asyncio
async def test_cost_governor_downgrades_effort(
    mock_anthropic_client, mock_thinking_response
) -> None:
    """When should_reduce_effort is True, effort level is downgraded."""
    from src.core.llm import LLMClient

    mock_governor = MagicMock()
    mock_budget = MagicMock()
    mock_budget.can_proceed = True
    mock_budget.should_reduce_effort = True
    mock_governor.check_budget = AsyncMock(return_value=mock_budget)
    mock_governor.get_thinking_budget.return_value = "routine"  # downgraded
    mock_governor.record_usage = AsyncMock()

    with (
        patch("src.core.llm._llm_circuit_breaker") as mock_cb,
        patch("src.core.llm.get_cost_governor", return_value=mock_governor),
    ):
        mock_cb.call = AsyncMock(return_value=mock_thinking_response)

        client = LLMClient.__new__(LLMClient)
        client._client = mock_anthropic_client
        client._model = "claude-sonnet-4-20250514"

        await client.generate_response_with_thinking(
            messages=[{"role": "user", "content": "test"}],
            thinking_effort="critical",
            user_id="user-123",
        )

        mock_governor.get_thinking_budget.assert_called_once_with(mock_budget, "critical")

        # Verify that routine budget (4096) was used, not critical (32768)
        call_kwargs = mock_cb.call.call_args.kwargs
        assert call_kwargs["thinking"]["budget_tokens"] == 4096


@pytest.mark.asyncio
async def test_records_usage_after_call(
    mock_anthropic_client, mock_thinking_response
) -> None:
    """governor.record_usage is called after successful call."""
    from src.core.llm import LLMClient

    mock_governor = MagicMock()
    mock_budget = MagicMock()
    mock_budget.can_proceed = True
    mock_budget.should_reduce_effort = False
    mock_governor.check_budget = AsyncMock(return_value=mock_budget)
    mock_governor.record_usage = AsyncMock()

    with (
        patch("src.core.llm._llm_circuit_breaker") as mock_cb,
        patch("src.core.llm.get_cost_governor", return_value=mock_governor),
    ):
        mock_cb.call = AsyncMock(return_value=mock_thinking_response)

        client = LLMClient.__new__(LLMClient)
        client._client = mock_anthropic_client
        client._model = "claude-sonnet-4-20250514"

        await client.generate_response_with_thinking(
            messages=[{"role": "user", "content": "test"}],
            user_id="user-123",
        )

        mock_governor.record_usage.assert_called_once()
        call_args = mock_governor.record_usage.call_args
        assert call_args[0][0] == "user-123"


@pytest.mark.asyncio
async def test_extracts_thinking_blocks(
    mock_anthropic_client, mock_thinking_response
) -> None:
    """Thinking blocks are extracted into LLMResponse.thinking."""
    from src.core.llm import LLMClient

    with patch("src.core.llm._llm_circuit_breaker") as mock_cb:
        mock_cb.call = AsyncMock(return_value=mock_thinking_response)

        client = LLMClient.__new__(LLMClient)
        client._client = mock_anthropic_client
        client._model = "claude-sonnet-4-20250514"

        result = await client.generate_response_with_thinking(
            messages=[{"role": "user", "content": "test"}],
        )

        assert "Let me analyze" in result.thinking
        assert "analysis complete" in result.text


@pytest.mark.asyncio
async def test_no_thinking_block_returns_empty_string(
    mock_anthropic_client, mock_no_thinking_response
) -> None:
    """When no thinking blocks exist, thinking is empty string."""
    from src.core.llm import LLMClient

    with patch("src.core.llm._llm_circuit_breaker") as mock_cb:
        mock_cb.call = AsyncMock(return_value=mock_no_thinking_response)

        client = LLMClient.__new__(LLMClient)
        client._client = mock_anthropic_client
        client._model = "claude-sonnet-4-20250514"

        result = await client.generate_response_with_thinking(
            messages=[{"role": "user", "content": "test"}],
        )

        assert result.thinking == ""
        assert result.text == "Simple response"


@pytest.mark.asyncio
async def test_works_without_user_id(
    mock_anthropic_client, mock_thinking_response
) -> None:
    """No budget check when user_id is None; still returns LLMResponse."""
    from src.core.llm import LLMClient

    with patch("src.core.llm._llm_circuit_breaker") as mock_cb:
        mock_cb.call = AsyncMock(return_value=mock_thinking_response)

        client = LLMClient.__new__(LLMClient)
        client._client = mock_anthropic_client
        client._model = "claude-sonnet-4-20250514"

        result = await client.generate_response_with_thinking(
            messages=[{"role": "user", "content": "test"}],
            user_id=None,
        )

        assert isinstance(result, type(result))
        assert result.text == '{"result": "analysis complete"}'
