"""Unit tests for Composio meta tool definitions and dispatch."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.composio_tools import (
    COMPOSIO_META_TOOL_NAMES,
    _openai_to_anthropic,
    execute_composio_meta_tool,
    get_composio_meta_tool_definitions,
)


# ---------------------------------------------------------------------------
# Tool names
# ---------------------------------------------------------------------------


class TestMetaToolNames:
    """Verify all expected meta tool slugs are defined."""

    def test_contains_all_five_tools(self) -> None:
        expected = {
            "COMPOSIO_SEARCH_TOOLS",
            "COMPOSIO_MANAGE_CONNECTIONS",
            "COMPOSIO_MULTI_EXECUTE_TOOL",
            "COMPOSIO_REMOTE_WORKBENCH",
            "COMPOSIO_REMOTE_BASH_TOOL",
        }
        assert COMPOSIO_META_TOOL_NAMES == expected

    def test_is_frozenset(self) -> None:
        assert isinstance(COMPOSIO_META_TOOL_NAMES, frozenset)


# ---------------------------------------------------------------------------
# OpenAI → Anthropic conversion
# ---------------------------------------------------------------------------


class TestOpenAIToAnthropicConversion:
    """Test format conversion from OpenAI tool defs to Anthropic."""

    def test_standard_openai_format(self) -> None:
        openai_tool = {
            "type": "function",
            "function": {
                "name": "COMPOSIO_SEARCH_TOOLS",
                "description": "Search for tools",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                    },
                    "required": ["query"],
                },
            },
        }
        result = _openai_to_anthropic(openai_tool)
        assert result is not None
        assert result["name"] == "COMPOSIO_SEARCH_TOOLS"
        assert result["description"] == "Search for tools"
        assert result["input_schema"]["type"] == "object"
        assert "query" in result["input_schema"]["properties"]

    def test_flat_format_fallback(self) -> None:
        """Some SDK versions return tools with top-level keys."""
        flat_tool = {
            "name": "COMPOSIO_SEARCH_TOOLS",
            "description": "Search",
            "parameters": {"type": "object", "properties": {}},
        }
        result = _openai_to_anthropic(flat_tool)
        assert result is not None
        assert result["name"] == "COMPOSIO_SEARCH_TOOLS"
        assert result["input_schema"]["type"] == "object"

    def test_malformed_tool_returns_none(self) -> None:
        result = _openai_to_anthropic({"type": "function"})
        assert result is None

    def test_empty_dict_returns_none(self) -> None:
        result = _openai_to_anthropic({})
        assert result is None

    def test_missing_description_defaults_empty(self) -> None:
        openai_tool = {
            "type": "function",
            "function": {
                "name": "COMPOSIO_SEARCH_TOOLS",
                "parameters": {"type": "object", "properties": {}},
            },
        }
        result = _openai_to_anthropic(openai_tool)
        assert result is not None
        assert result["description"] == ""

    def test_missing_parameters_defaults_empty_object(self) -> None:
        openai_tool = {
            "type": "function",
            "function": {
                "name": "COMPOSIO_SEARCH_TOOLS",
                "description": "Search",
            },
        }
        result = _openai_to_anthropic(openai_tool)
        assert result is not None
        assert result["input_schema"] == {"type": "object", "properties": {}}


# ---------------------------------------------------------------------------
# get_composio_meta_tool_definitions
# ---------------------------------------------------------------------------


class TestGetDefinitions:
    """Test fetching and filtering meta tool definitions."""

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_failure(self) -> None:
        """When the session manager raises, return [] gracefully."""
        with patch(
            "src.integrations.composio_sessions.get_session_manager"
        ) as mock_gsm:
            mock_manager = MagicMock()
            mock_manager.get_tools = AsyncMock(side_effect=RuntimeError("no API key"))
            mock_gsm.return_value = mock_manager

            result = await get_composio_meta_tool_definitions("user-123")
            assert result == []

    @pytest.mark.asyncio
    async def test_filters_to_meta_tools_only(self) -> None:
        """Non-meta tools from the session are excluded."""
        raw_tools = [
            {
                "type": "function",
                "function": {
                    "name": "COMPOSIO_SEARCH_TOOLS",
                    "description": "Search",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "OUTLOOK_GET_MAIL",
                    "description": "Get mail",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ]

        with patch(
            "src.integrations.composio_sessions.get_session_manager"
        ) as mock_gsm:
            mock_manager = MagicMock()
            mock_manager.get_tools = AsyncMock(return_value=raw_tools)
            mock_gsm.return_value = mock_manager

            result = await get_composio_meta_tool_definitions("user-123")
            assert len(result) == 1
            assert result[0]["name"] == "COMPOSIO_SEARCH_TOOLS"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_tools(self) -> None:
        with patch(
            "src.integrations.composio_sessions.get_session_manager"
        ) as mock_gsm:
            mock_manager = MagicMock()
            mock_manager.get_tools = AsyncMock(return_value=[])
            mock_gsm.return_value = mock_manager

            result = await get_composio_meta_tool_definitions("user-123")
            assert result == []


# ---------------------------------------------------------------------------
# execute_composio_meta_tool
# ---------------------------------------------------------------------------


class TestExecuteMetaTool:
    """Test meta tool execution wrapper."""

    @pytest.mark.asyncio
    async def test_returns_error_on_failure(self) -> None:
        with patch(
            "src.integrations.composio_sessions.get_session_manager"
        ) as mock_gsm:
            mock_manager = MagicMock()
            mock_manager.execute_meta_tool = AsyncMock(
                side_effect=RuntimeError("connection refused")
            )
            mock_gsm.return_value = mock_manager

            result = await execute_composio_meta_tool(
                user_id="user-123",
                tool_name="COMPOSIO_SEARCH_TOOLS",
                tool_input={"query": "email"},
            )
            assert result["successful"] is False
            assert "connection refused" in result["error"]

    @pytest.mark.asyncio
    async def test_passes_through_success(self) -> None:
        expected = {"data": {"tools": ["a", "b"]}, "error": None, "successful": True}

        with patch(
            "src.integrations.composio_sessions.get_session_manager"
        ) as mock_gsm:
            mock_manager = MagicMock()
            mock_manager.execute_meta_tool = AsyncMock(return_value=expected)
            mock_gsm.return_value = mock_manager

            result = await execute_composio_meta_tool(
                user_id="user-123",
                tool_name="COMPOSIO_SEARCH_TOOLS",
                tool_input={"query": "email"},
            )
            assert result == expected


# ---------------------------------------------------------------------------
# Dispatch routing (integration-style)
# ---------------------------------------------------------------------------


class TestDispatchRouting:
    """Verify that _run_tool_loop dispatches to the right handler."""

    @pytest.mark.asyncio
    async def test_meta_tool_routes_to_composio(self) -> None:
        """A tool call with a meta tool name should use execute_composio_meta_tool."""
        mock_tc = MagicMock()
        mock_tc.name = "COMPOSIO_SEARCH_TOOLS"
        mock_tc.id = "tool-use-1"
        mock_tc.input = {"query": "slack"}

        # The dispatch logic is inline in _run_tool_loop — test the routing
        # condition directly.
        assert mock_tc.name in COMPOSIO_META_TOOL_NAMES

    @pytest.mark.asyncio
    async def test_email_tool_does_not_match_meta(self) -> None:
        """An email tool name should NOT match COMPOSIO_META_TOOL_NAMES."""
        assert "read_recent_emails" not in COMPOSIO_META_TOOL_NAMES
        assert "search_emails" not in COMPOSIO_META_TOOL_NAMES
        assert "draft_email_reply" not in COMPOSIO_META_TOOL_NAMES
