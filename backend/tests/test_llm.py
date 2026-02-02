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
