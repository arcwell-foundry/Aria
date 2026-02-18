"""Tests for the Exa Web Intelligence MCP server."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.capability_tokens import DelegationCapabilityToken
from src.mcp_servers.exa.server import exa_mcp
from src.mcp_servers.middleware import DCTViolation


def _extract_dict(result: Any) -> dict[str, Any]:
    """Extract the dict payload from a FastMCP call_tool result.

    FastMCP.call_tool with ``convert_result=True`` returns either:
    - A ``(list[TextContent], dict)`` tuple when the tool has a typed return
      (unstructured content + structured output).
    - A ``list[TextContent]`` when there is no output schema.

    This helper handles both forms.
    """
    if isinstance(result, tuple):
        # Structured output path: second element is the dict
        return result[1]
    if isinstance(result, dict):
        return result
    # Fallback: list of content blocks
    assert isinstance(result, list), f"Expected list/tuple/dict, got {type(result)}"
    assert len(result) >= 1, "Expected at least one content block"
    return json.loads(result[0].text)


# ── Tool discovery ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_exa_lists_six_tools() -> None:
    """The exa server should expose exactly 6 tools."""
    tools = await exa_mcp.list_tools()
    names = {t.name for t in tools}
    assert len(tools) == 6
    assert names == {
        "exa_search_web",
        "exa_search_news",
        "exa_find_similar",
        "exa_answer",
        "exa_research",
        "exa_get_contents",
    }


# ── exa_search_web ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_exa_search_web_returns_results() -> None:
    """exa_search_web should return results from the Exa provider."""
    mock_result = MagicMock()
    mock_result.model_dump.return_value = {
        "url": "https://example.com",
        "title": "Test",
        "text": "content",
        "score": 0.9,
    }

    mock_provider = AsyncMock()
    mock_provider.search_fast = AsyncMock(return_value=[mock_result])

    with patch("src.mcp_servers.exa.tools._get_provider", return_value=mock_provider):
        raw = await exa_mcp.call_tool(
            "exa_search_web", {"query": "test"}
        )

    result = _extract_dict(raw)
    assert result["count"] == 1
    assert result["results"][0]["url"] == "https://example.com"
    assert result["results"][0]["title"] == "Test"


# ── exa_answer ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_exa_answer_returns_answer() -> None:
    """exa_answer should return the answer from the Exa provider."""
    mock_provider = AsyncMock()
    mock_provider.answer = AsyncMock(return_value="42")

    with patch("src.mcp_servers.exa.tools._get_provider", return_value=mock_provider):
        raw = await exa_mcp.call_tool(
            "exa_answer", {"question": "What is the meaning of life?"}
        )

    result = _extract_dict(raw)
    assert result["answer"] == "42"


# ── DCT enforcement (valid) ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_exa_search_news_with_valid_dct(scout_dct) -> None:  # noqa: ANN001
    """A scout DCT (which has read_news_apis) should be accepted for news."""
    mock_result = MagicMock()
    mock_result.model_dump.return_value = {
        "url": "https://news.example.com",
        "title": "Breaking News",
        "text": "content",
        "score": 0.8,
    }

    mock_provider = AsyncMock()
    mock_provider.search_news = AsyncMock(return_value=[mock_result])

    with patch("src.mcp_servers.exa.tools._get_provider", return_value=mock_provider):
        raw = await exa_mcp.call_tool(
            "exa_search_news",
            {"query": "pharma news", "dct": scout_dct.to_dict()},
        )

    result = _extract_dict(raw)
    assert result["count"] == 1


# ── DCT enforcement (denied) ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_exa_search_web_with_denied_dct() -> None:
    """A custom DCT that denies read_exa should be rejected for web search."""
    from mcp.server.fastmcp.exceptions import ToolError

    denied_dct = DelegationCapabilityToken(
        token_id=str(uuid.uuid4()),
        delegatee="custom-agent",
        goal_id="test-goal",
        allowed_actions=["read_news_apis"],
        denied_actions=["read_exa"],
        time_limit_seconds=300,
        created_at=datetime.now(UTC),
    )

    with pytest.raises(ToolError) as exc_info:
        await exa_mcp.call_tool(
            "exa_search_web",
            {"query": "test", "dct": denied_dct.to_dict()},
        )

    assert isinstance(exc_info.value.__cause__, DCTViolation)
    violation = exc_info.value.__cause__
    assert violation.tool_name == "exa_search_web"
    assert violation.delegatee == "custom-agent"
    assert violation.action == "read_exa"
