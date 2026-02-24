"""Tests for MCPToolClient."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mcp_servers.client import MCPToolClient
from src.mcp_servers.middleware import DCTViolation
from src.mcp_servers.registry import TOOL_SERVER_MAP


# ── list_tools ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_tools_returns_all() -> None:
    """list_tools() with no filter should return every registered tool."""
    client = MCPToolClient("u-1")
    result = await client.list_tools()
    assert len(result) == len(TOOL_SERVER_MAP)
    # Verify expected count from the registry (lifesci 6 + exa 6 + business 5 = 17)
    assert len(result) == 17


@pytest.mark.asyncio
async def test_list_tools_filtered_by_server() -> None:
    """list_tools(server_name='lifesci') should return only lifesci tools."""
    client = MCPToolClient("u-1")
    result = await client.list_tools(server_name="lifesci")
    assert len(result) == 6
    assert all(t["server"] == "lifesci" for t in result)


# ── call_tool routing ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_call_tool_unknown_raises() -> None:
    """Calling an unknown tool should raise ValueError."""
    client = MCPToolClient("u-1")
    with pytest.raises(ValueError, match="Unknown MCP tool"):
        await client.call_tool("nonexistent", {})


@pytest.mark.asyncio
async def test_call_tool_routes_to_correct_server() -> None:
    """call_tool should resolve the tool to the correct server via the registry."""
    mock_server = AsyncMock()
    mock_server.call_tool = AsyncMock(return_value={"ok": True})

    with patch("src.mcp_servers.client.get_server", return_value=mock_server) as mock_get:
        client = MCPToolClient("u-1")
        result = await client.call_tool("pubmed_search", {"query": "test"})

    mock_get.assert_called_once_with("lifesci")
    assert result == {"ok": True}


# ── Delegation trace lifecycle ────────────────────────────────────────


@pytest.mark.asyncio
async def test_call_tool_creates_and_completes_trace(
    mock_trace_service: AsyncMock,
) -> None:
    """A successful call_tool should start and complete a delegation trace."""
    mock_server = AsyncMock()
    mock_server.call_tool = AsyncMock(return_value={"data": "value"})

    with patch("src.mcp_servers.client.get_server", return_value=mock_server):
        client = MCPToolClient("u-1", delegation_trace_service=mock_trace_service)
        await client.call_tool(
            "pubmed_search",
            {"query": "test"},
            goal_id="goal-1",
            delegatee="analyst",
        )

    mock_trace_service.start_trace.assert_called_once()
    mock_trace_service.complete_trace.assert_called_once()
    # Verify trace_id was passed through
    complete_kwargs = mock_trace_service.complete_trace.call_args
    assert complete_kwargs.kwargs["trace_id"] == "trace-123"
    assert complete_kwargs.kwargs["status"] == "completed"


@pytest.mark.asyncio
async def test_call_tool_fails_trace_on_error(
    mock_trace_service: AsyncMock,
) -> None:
    """A failed call_tool should start and then fail the delegation trace."""
    mock_server = AsyncMock()
    mock_server.call_tool = AsyncMock(side_effect=RuntimeError("boom"))

    with patch("src.mcp_servers.client.get_server", return_value=mock_server):
        client = MCPToolClient("u-1", delegation_trace_service=mock_trace_service)
        with pytest.raises(RuntimeError, match="boom"):
            await client.call_tool(
                "pubmed_search",
                {"query": "test"},
                goal_id="goal-1",
                delegatee="analyst",
            )

    mock_trace_service.start_trace.assert_called_once()
    mock_trace_service.fail_trace.assert_called_once()
    fail_kwargs = mock_trace_service.fail_trace.call_args
    assert fail_kwargs.kwargs["trace_id"] == "trace-123"
    assert "boom" in fail_kwargs.kwargs["error_message"]


# ── Client-side DCT fail-fast ────────────────────────────────────────


@pytest.mark.asyncio
async def test_client_side_dct_failfast(scout_dct) -> None:  # noqa: ANN001
    """Client should reject a tool call before reaching the server if DCT denies it.

    The scout agent does not have write_crm permission, so calling crm_write
    should raise DCTViolation at the client level without ever calling the server.
    """
    client = MCPToolClient("u-1")

    with pytest.raises(DCTViolation):
        await client.call_tool(
            "crm_write",
            {"data": {"name": "Test"}},
            dct=scout_dct,
        )
