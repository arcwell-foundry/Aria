"""Unit tests for Composio meta tool definitions and dispatch."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.composio_tools import (
    COMPOSIO_META_TOOL_NAMES,
    _extract_toolkit_from_tool,
    _filter_search_results_by_governance,
    _get_approved_toolkits,
    _get_user_tenant_id,
    _is_toolkit_approved,
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


# ---------------------------------------------------------------------------
# Governance filtering
# ---------------------------------------------------------------------------


class TestGovernanceHelpers:
    """Test governance helper functions."""

    @pytest.mark.asyncio
    async def test_get_user_tenant_id_found(self) -> None:
        """Tenant ID is returned when user has company association."""
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
            data={"company_id": "company-123"}
        )
        with patch(
            "src.db.supabase.get_supabase_client", return_value=mock_db
        ):
            result = await _get_user_tenant_id("user-1")
            assert result == "company-123"

    @pytest.mark.asyncio
    async def test_get_user_tenant_id_not_found(self) -> None:
        """None is returned when user has no company."""
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
            data=None
        )
        with patch(
            "src.db.supabase.get_supabase_client", return_value=mock_db
        ):
            result = await _get_user_tenant_id("user-1")
            assert result is None

    @pytest.mark.asyncio
    async def test_get_approved_toolkits_with_config(self) -> None:
        """Returns set of approved toolkits when config exists."""
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {"toolkit_slug": "GMAIL"},
                {"toolkit_slug": "SALESFORCE"},
            ]
        )
        with patch(
            "src.db.supabase.get_supabase_client", return_value=mock_db
        ):
            result = await _get_approved_toolkits("company-1")
            assert result == {"GMAIL", "SALESFORCE"}

    @pytest.mark.asyncio
    async def test_get_approved_toolkits_empty_returns_none(self) -> None:
        """Returns None (permissive) when no config rows exist."""
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )
        with patch(
            "src.db.supabase.get_supabase_client", return_value=mock_db
        ):
            result = await _get_approved_toolkits("company-1")
            # Empty config = permissive mode
            assert result is None

    @pytest.mark.asyncio
    async def test_is_toolkit_approved_no_tenant(self) -> None:
        """Permissive mode when user has no tenant."""
        with patch(
            "src.services.composio_tools._get_user_tenant_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            is_approved, has_config = await _is_toolkit_approved("user-1", "SLACK")
            assert is_approved is True
            assert has_config is False

    @pytest.mark.asyncio
    async def test_is_toolkit_approved_no_config(self) -> None:
        """Permissive mode when tenant has no toolkit config."""
        with (
            patch(
                "src.services.composio_tools._get_user_tenant_id",
                new_callable=AsyncMock,
                return_value="company-1",
            ),
            patch(
                "src.services.composio_tools._get_approved_toolkits",
                new_callable=AsyncMock,
                return_value=None,  # No config = permissive
            ),
        ):
            is_approved, has_config = await _is_toolkit_approved("user-1", "SLACK")
            assert is_approved is True
            assert has_config is False

    @pytest.mark.asyncio
    async def test_is_toolkit_approved_explicitly_approved(self) -> None:
        """Approved when toolkit is in approved set."""
        with (
            patch(
                "src.services.composio_tools._get_user_tenant_id",
                new_callable=AsyncMock,
                return_value="company-1",
            ),
            patch(
                "src.services.composio_tools._get_approved_toolkits",
                new_callable=AsyncMock,
                return_value={"GMAIL", "SALESFORCE"},
            ),
        ):
            is_approved, has_config = await _is_toolkit_approved("user-1", "GMAIL")
            assert is_approved is True
            assert has_config is True

    @pytest.mark.asyncio
    async def test_is_toolkit_approved_not_in_approved_set(self) -> None:
        """Not approved when toolkit not in approved set."""
        with (
            patch(
                "src.services.composio_tools._get_user_tenant_id",
                new_callable=AsyncMock,
                return_value="company-1",
            ),
            patch(
                "src.services.composio_tools._get_approved_toolkits",
                new_callable=AsyncMock,
                return_value={"GMAIL", "SALESFORCE"},
            ),
        ):
            is_approved, has_config = await _is_toolkit_approved("user-1", "SLACK")
            assert is_approved is False
            assert has_config is True


class TestExtractToolkitFromTool:
    """Test toolkit slug extraction from various tool formats."""

    def test_toolkit_as_string(self) -> None:
        assert _extract_toolkit_from_tool({"toolkit": "GMAIL"}) == "GMAIL"

    def test_toolkit_as_dict_with_slug(self) -> None:
        assert _extract_toolkit_from_tool({"toolkit": {"slug": "SLACK"}}) == "SLACK"

    def test_app_as_string(self) -> None:
        assert _extract_toolkit_from_tool({"app": "SALESFORCE"}) == "SALESFORCE"

    def test_app_as_dict(self) -> None:
        assert _extract_toolkit_from_tool({"app": {"name": "VEEVA"}}) == "VEEVA"

    def test_appName_key(self) -> None:
        assert _extract_toolkit_from_tool({"appName": "OUTLOOK"}) == "OUTLOOK"

    def test_parse_from_tool_name(self) -> None:
        assert _extract_toolkit_from_tool({"name": "GMAIL_SEND_EMAIL"}) == "GMAIL"

    def test_returns_none_for_unknown_format(self) -> None:
        assert _extract_toolkit_from_tool({"description": "some tool"}) is None


class TestFilterSearchResultsByGovernance:
    """Test governance filtering of search results."""

    @pytest.mark.asyncio
    async def test_permissive_mode_no_tenant(self) -> None:
        """Tools pass through unchanged when no tenant."""
        tools = [{"name": "GMAIL_SEND_EMAIL"}, {"name": "SLACK_SEND_MESSAGE"}]
        with patch(
            "src.services.composio_tools._get_user_tenant_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await _filter_search_results_by_governance("user-1", tools)
            assert len(result) == 2
            assert "_approved" not in result[0]
            assert "_needs_admin_approval" not in result[0]

    @pytest.mark.asyncio
    async def test_permissive_mode_no_config(self) -> None:
        """Tools pass through unchanged when no tenant config."""
        tools = [{"name": "GMAIL_SEND_EMAIL"}]
        with (
            patch(
                "src.services.composio_tools._get_user_tenant_id",
                new_callable=AsyncMock,
                return_value="company-1",
            ),
            patch(
                "src.services.composio_tools._get_approved_toolkits",
                new_callable=AsyncMock,
                return_value=None,  # No config = permissive
            ),
        ):
            result = await _filter_search_results_by_governance("user-1", tools)
            assert len(result) == 1
            assert "_approved" not in result[0]

    @pytest.mark.asyncio
    async def test_approved_toolkit_passes(self) -> None:
        """Approved tool gets _approved flag."""
        tools = [{"name": "GMAIL_SEND_EMAIL"}]
        with (
            patch(
                "src.services.composio_tools._get_user_tenant_id",
                new_callable=AsyncMock,
                return_value="company-1",
            ),
            patch(
                "src.services.composio_tools._get_approved_toolkits",
                new_callable=AsyncMock,
                return_value={"GMAIL"},
            ),
        ):
            result = await _filter_search_results_by_governance("user-1", tools)
            assert len(result) == 1
            assert result[0]["_approved"] is True
            assert result[0]["_toolkit_slug"] == "GMAIL"
            assert "_needs_admin_approval" not in result[0]

    @pytest.mark.asyncio
    async def test_unapproved_toolkit_flagged(self) -> None:
        """Unapproved tool gets _needs_admin_approval flag."""
        tools = [{"name": "SLACK_SEND_MESSAGE"}]
        with (
            patch(
                "src.services.composio_tools._get_user_tenant_id",
                new_callable=AsyncMock,
                return_value="company-1",
            ),
            patch(
                "src.services.composio_tools._get_approved_toolkits",
                new_callable=AsyncMock,
                return_value={"GMAIL"},  # Only GMAIL approved
            ),
        ):
            result = await _filter_search_results_by_governance("user-1", tools)
            assert len(result) == 1
            assert result[0]["_approved"] is False
            assert result[0]["_toolkit_slug"] == "SLACK"
            assert result[0]["_needs_admin_approval"] is True
            assert "not approved" in result[0]["_approval_reason"].lower()


class TestExecuteMetaToolWithGovernance:
    """Test execute_composio_meta_tool applies governance."""

    @pytest.mark.asyncio
    async def test_search_tools_applies_governance(self) -> None:
        """SEARCH_TOOLS result is filtered by governance."""
        raw_result = {
            "data": {
                "tools": [
                    {"name": "GMAIL_SEND_EMAIL"},
                    {"name": "SLACK_SEND_MESSAGE"},
                ]
            },
            "successful": True,
        }

        mock_manager = MagicMock()
        mock_manager.execute_meta_tool = AsyncMock(return_value=raw_result)

        with (
            patch(
                "src.integrations.composio_sessions.get_session_manager",
                return_value=mock_manager,
            ),
            patch(
                "src.services.composio_tools._get_user_tenant_id",
                new_callable=AsyncMock,
                return_value="company-1",
            ),
            patch(
                "src.services.composio_tools._get_approved_toolkits",
                new_callable=AsyncMock,
                return_value={"GMAIL"},
            ),
        ):
            result = await execute_composio_meta_tool(
                user_id="user-1",
                tool_name="COMPOSIO_SEARCH_TOOLS",
                tool_input={"query": "email"},
            )

            assert result["successful"] is True
            assert result["data"]["_governance_applied"] is True
            tools = result["data"]["tools"]
            # GMAIL should be approved
            gmail_tool = next(t for t in tools if t.get("_toolkit_slug") == "GMAIL")
            assert gmail_tool["_approved"] is True
            # SLACK should need approval
            slack_tool = next(t for t in tools if t.get("_toolkit_slug") == "SLACK")
            assert slack_tool["_needs_admin_approval"] is True

    @pytest.mark.asyncio
    async def test_manage_connections_blocks_unapproved(self) -> None:
        """MANAGE_CONNECTIONS blocks connect URL for unapproved toolkits."""
        raw_result = {
            "data": {
                "redirectUrl": "https://connect.composio.io/...",
                "connectionId": "conn-123",
            },
            "successful": True,
        }

        mock_manager = MagicMock()
        mock_manager.execute_meta_tool = AsyncMock(return_value=raw_result)

        with (
            patch(
                "src.integrations.composio_sessions.get_session_manager",
                return_value=mock_manager,
            ),
            patch(
                "src.services.composio_tools._is_toolkit_approved",
                new_callable=AsyncMock,
                return_value=(False, True),  # Not approved, has config
            ),
        ):
            result = await execute_composio_meta_tool(
                user_id="user-1",
                tool_name="COMPOSIO_MANAGE_CONNECTIONS",
                tool_input={"toolkit": "SLACK"},
            )

            assert result["successful"] is True
            assert result["data"]["_needs_admin_approval"] is True
            assert result["data"]["_connect_blocked"] is True
            assert "redirectUrl" not in result["data"]

    @pytest.mark.asyncio
    async def test_manage_connections_allows_approved(self) -> None:
        """MANAGE_CONNECTIONS allows connect URL for approved toolkits."""
        raw_result = {
            "data": {
                "redirectUrl": "https://connect.composio.io/...",
                "connectionId": "conn-123",
            },
            "successful": True,
        }

        mock_manager = MagicMock()
        mock_manager.execute_meta_tool = AsyncMock(return_value=raw_result)

        with (
            patch(
                "src.integrations.composio_sessions.get_session_manager",
                return_value=mock_manager,
            ),
            patch(
                "src.services.composio_tools._is_toolkit_approved",
                new_callable=AsyncMock,
                return_value=(True, True),  # Approved, has config
            ),
        ):
            result = await execute_composio_meta_tool(
                user_id="user-1",
                tool_name="COMPOSIO_MANAGE_CONNECTIONS",
                tool_input={"toolkit": "GMAIL"},
            )

            assert result["successful"] is True
            assert result["data"]["_approved"] is True
            assert result["data"]["redirectUrl"] == "https://connect.composio.io/..."

    @pytest.mark.asyncio
    async def test_manage_connections_permissive_when_no_config(self) -> None:
        """MANAGE_CONNECTIONS allows all when no config (permissive default)."""
        raw_result = {
            "data": {
                "redirectUrl": "https://connect.composio.io/...",
            },
            "successful": True,
        }

        mock_manager = MagicMock()
        mock_manager.execute_meta_tool = AsyncMock(return_value=raw_result)

        with (
            patch(
                "src.integrations.composio_sessions.get_session_manager",
                return_value=mock_manager,
            ),
            patch(
                "src.services.composio_tools._is_toolkit_approved",
                new_callable=AsyncMock,
                return_value=(True, False),  # Permissive (no config)
            ),
        ):
            result = await execute_composio_meta_tool(
                user_id="user-1",
                tool_name="COMPOSIO_MANAGE_CONNECTIONS",
                tool_input={"toolkit": "SLACK"},
            )

            assert result["successful"] is True
            assert result["data"]["_approved"] is True
            assert "redirectUrl" in result["data"]
