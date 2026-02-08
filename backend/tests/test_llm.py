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


@pytest.mark.asyncio
async def test_generate_response_calls_anthropic_api() -> None:
    """Test generate_response calls Anthropic API with messages."""
    from src.core.llm import LLMClient

    with patch("src.core.llm.anthropic.AsyncAnthropic") as mock_anthropic:
        mock_client = AsyncMock()
        mock_anthropic.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Hello, I'm ARIA!")]
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("src.core.llm.settings") as mock_settings:
            mock_settings.ANTHROPIC_API_KEY.get_secret_value.return_value = "test-key"
            client = LLMClient()

        messages = [{"role": "user", "content": "Hello"}]
        result = await client.generate_response(messages)

        assert result == "Hello, I'm ARIA!"
        mock_client.messages.create.assert_called_once()


@pytest.mark.asyncio
async def test_generate_response_includes_system_prompt() -> None:
    """Test generate_response includes system prompt when provided."""
    from src.core.llm import LLMClient

    with patch("src.core.llm.anthropic.AsyncAnthropic") as mock_anthropic:
        mock_client = AsyncMock()
        mock_anthropic.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Response")]
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("src.core.llm.settings") as mock_settings:
            mock_settings.ANTHROPIC_API_KEY.get_secret_value.return_value = "test-key"
            client = LLMClient()

        messages = [{"role": "user", "content": "Hello"}]
        system = "You are ARIA, an AI assistant."
        await client.generate_response(messages, system_prompt=system)

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["system"] == system


@pytest.mark.asyncio
async def test_generate_response_opens_circuit_after_repeated_failures() -> None:
    """Test that repeated API failures open the circuit breaker."""
    from src.core.circuit_breaker import CircuitBreakerOpen
    from src.core.llm import LLMClient, _llm_circuit_breaker

    # Reset circuit breaker state from any previous tests
    _llm_circuit_breaker.record_success()

    with patch("src.core.llm.anthropic.AsyncAnthropic") as mock_anthropic:
        mock_client = AsyncMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create = AsyncMock(
            side_effect=Exception("API down")
        )

        with patch("src.core.llm.settings") as mock_settings:
            mock_settings.ANTHROPIC_API_KEY.get_secret_value.return_value = "test-key"
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
    _llm_circuit_breaker.record_success()


@pytest.mark.asyncio
async def test_generate_response_circuit_resets_on_success() -> None:
    """Test that a successful call resets the circuit breaker."""
    from src.core.llm import LLMClient, _llm_circuit_breaker

    # Reset circuit breaker state from any previous tests
    _llm_circuit_breaker.record_success()

    with patch("src.core.llm.anthropic.AsyncAnthropic") as mock_anthropic:
        mock_client = AsyncMock()
        mock_anthropic.return_value = mock_client

        call_count = 0

        async def side_effect(**kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                raise Exception("API down")
            resp = MagicMock()
            resp.content = [MagicMock(text="recovered")]
            return resp

        mock_client.messages.create = AsyncMock(side_effect=side_effect)

        with patch("src.core.llm.settings") as mock_settings:
            mock_settings.ANTHROPIC_API_KEY.get_secret_value.return_value = "test-key"
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
    _llm_circuit_breaker.record_success()
