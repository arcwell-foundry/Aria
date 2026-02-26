"""Tests for LLM client module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def test_llm_client_initializes_with_settings() -> None:
    """Test LLMClient initializes with API key from settings."""
    from src.core.llm import LLMClient

    with patch("src.core.llm.settings") as mock_settings:
        mock_settings.ANTHROPIC_API_KEY.get_secret_value.return_value = "test-key"
        client = LLMClient()
        assert client._api_key == "test-key"
        assert client._litellm_model == "anthropic/claude-sonnet-4-20250514"


@pytest.mark.asyncio
async def test_generate_response_calls_litellm() -> None:
    """Test generate_response calls LiteLLM acompletion with messages."""
    from src.core.llm import LLMClient

    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content="Hello, I'm ARIA!"))
    ]
    mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)

    mock_acompletion = AsyncMock(return_value=mock_response)

    with (
        patch("src.core.llm.settings") as mock_settings,
        patch("src.core.llm._llm_circuit_breaker") as mock_cb,
    ):
        mock_settings.ANTHROPIC_API_KEY.get_secret_value.return_value = "test-key"
        mock_cb.call = AsyncMock(return_value=mock_response)

        client = LLMClient()
        messages = [{"role": "user", "content": "Hello"}]
        result = await client.generate_response(messages)

        assert result == "Hello, I'm ARIA!"
        mock_cb.call.assert_called_once()


@pytest.mark.asyncio
async def test_generate_response_includes_system_prompt() -> None:
    """Test generate_response prepends system prompt as system message."""
    from src.core.llm import LLMClient

    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content="Response"))
    ]
    mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)

    with (
        patch("src.core.llm.settings") as mock_settings,
        patch("src.core.llm._llm_circuit_breaker") as mock_cb,
    ):
        mock_settings.ANTHROPIC_API_KEY.get_secret_value.return_value = "test-key"
        mock_cb.call = AsyncMock(return_value=mock_response)

        client = LLMClient()
        messages = [{"role": "user", "content": "Hello"}]
        system = "You are ARIA, an AI assistant."
        await client.generate_response(messages, system_prompt=system)

        # The circuit breaker call forwards kwargs to acompletion;
        # verify system prompt was prepended as first message
        call_kwargs = mock_cb.call.call_args.kwargs
        passed_messages = call_kwargs["messages"]
        assert passed_messages[0]["role"] == "system"
        assert passed_messages[0]["content"] == system


@pytest.mark.asyncio
async def test_generate_response_opens_circuit_after_repeated_failures() -> None:
    """Test that repeated API failures open the circuit breaker."""
    from src.core.resilience import CircuitBreakerOpen
    from src.core.llm import LLMClient, _llm_circuit_breaker

    # Reset circuit breaker state from any previous tests
    _llm_circuit_breaker.reset()

    with patch("src.core.llm.settings") as mock_settings:
        mock_settings.ANTHROPIC_API_KEY.get_secret_value.return_value = "test-key"

        # Patch acompletion at the module level to raise errors
        with patch("src.core.llm.acompletion", new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.side_effect = Exception("API down")

            client = LLMClient()
            messages = [{"role": "user", "content": "Hello"}]

            # Exhaust the failure threshold (5)
            for _ in range(5):
                with pytest.raises(Exception, match="API down"):
                    await client.generate_response(messages)

            # Next call should raise CircuitBreakerOpen
            with pytest.raises(CircuitBreakerOpen):
                await client.generate_response(messages)

    # Reset for other tests
    _llm_circuit_breaker.reset()


@pytest.mark.asyncio
async def test_generate_response_circuit_resets_on_success() -> None:
    """Test that a successful call resets the circuit breaker."""
    from src.core.llm import LLMClient, _llm_circuit_breaker

    # Reset circuit breaker state from any previous tests
    _llm_circuit_breaker.reset()

    call_count = 0

    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 3:
            raise Exception("API down")
        resp = MagicMock()
        resp.choices = [MagicMock(message=MagicMock(content="recovered"))]
        resp.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
        return resp

    with patch("src.core.llm.settings") as mock_settings:
        mock_settings.ANTHROPIC_API_KEY.get_secret_value.return_value = "test-key"

        with patch("src.core.llm.acompletion", new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.side_effect = side_effect

            client = LLMClient()
            messages = [{"role": "user", "content": "Hello"}]

            # 3 failures (under threshold of 5)
            for _ in range(3):
                with pytest.raises(Exception, match="API down"):
                    await client.generate_response(messages)

            # Success should reset the counter
            result = await client.generate_response(messages)
            assert result == "recovered"

    # Reset for other tests
    _llm_circuit_breaker.reset()


@pytest.mark.asyncio
async def test_generate_method_uses_task_routing() -> None:
    """Test the new generate() method uses MODEL_ROUTES for task-based config."""
    from src.core.llm import LLMClient
    from src.core.task_types import TaskType

    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content="Routed response"))
    ]
    mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)

    with (
        patch("src.core.llm.settings") as mock_settings,
        patch("src.core.llm._llm_circuit_breaker") as mock_cb,
    ):
        mock_settings.ANTHROPIC_API_KEY.get_secret_value.return_value = "test-key"
        mock_cb.call = AsyncMock(return_value=mock_response)

        client = LLMClient()
        result = await client.generate(
            messages=[{"role": "user", "content": "test"}],
            task=TaskType.ANALYST_RESEARCH,
        )

        assert result == "Routed response"
        call_kwargs = mock_cb.call.call_args.kwargs
        # ANALYST_RESEARCH should use Sonnet model from MODEL_ROUTES
        assert "anthropic/" in call_kwargs["model"]
        # ANALYST_RESEARCH has temperature 0.3
        assert call_kwargs["temperature"] == 0.3
