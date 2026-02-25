"""Tests for Composio tool discovery in goal planning.

Covers:
- ComposioToolInfo dataclass construction
- ComposioToolDiscovery.discover_tools_for_goal() with mocked SDK
- Graceful degradation when Composio is unavailable
- _build_agent_tools_prompt() prompt generation
- _annotate_task_resources() resource enrichment
- _integration_types_to_toolkit_slugs() mapping
"""

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Stub composio SDK if not installed
if "composio" not in sys.modules:
    sys.modules["composio"] = MagicMock()


# ---------------------------------------------------------------------------
# ComposioToolInfo tests
# ---------------------------------------------------------------------------

class TestComposioToolInfo:
    """Test ComposioToolInfo dataclass."""

    def test_basic_creation(self) -> None:
        from src.integrations.tool_discovery import ComposioToolInfo

        tool = ComposioToolInfo(
            slug="SALESFORCE_GET_CONTACTS",
            name="Get Contacts",
            description="Retrieve contacts from Salesforce",
            toolkit_slug="salesforce",
            toolkit_name="Salesforce",
            requires_auth=True,
        )
        assert tool.slug == "SALESFORCE_GET_CONTACTS"
        assert tool.name == "Get Contacts"
        assert tool.toolkit_slug == "salesforce"
        assert tool.requires_auth is True

    def test_frozen_dataclass(self) -> None:
        from src.integrations.tool_discovery import ComposioToolInfo

        tool = ComposioToolInfo(
            slug="GMAIL_SEND",
            name="Send Email",
            description="Send an email via Gmail",
            toolkit_slug="gmail",
            toolkit_name="Gmail",
            requires_auth=True,
        )
        with pytest.raises(AttributeError):
            tool.slug = "MODIFIED"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ComposioToolDiscovery tests
# ---------------------------------------------------------------------------

class TestComposioToolDiscovery:
    """Test ComposioToolDiscovery.discover_tools_for_goal()."""

    def _make_raw_tool(
        self,
        slug: str = "SALESFORCE_GET_CONTACTS",
        display_name: str = "Get Contacts",
        description: str = "Retrieve contacts",
        app_name: str = "salesforce",
    ) -> SimpleNamespace:
        """Create a mock raw Composio tool object."""
        return SimpleNamespace(
            slug=slug,
            display_name=display_name,
            description=description,
            appName=app_name,
        )

    @pytest.mark.asyncio
    async def test_discover_tools_for_goal_basic(self) -> None:
        from src.integrations.tool_discovery import ComposioToolDiscovery

        discovery = ComposioToolDiscovery()

        raw_tools = [
            self._make_raw_tool("SF_GET_CONTACTS", "Get Contacts", "Get CRM contacts", "salesforce"),
            self._make_raw_tool("SF_CREATE_LEAD", "Create Lead", "Create a new lead", "salesforce"),
        ]
        search_tools = [
            self._make_raw_tool("GMAIL_SEND", "Send Email", "Send email via Gmail", "gmail"),
        ]

        with patch.object(discovery, "_fetch_toolkit_tools", new_callable=AsyncMock) as mock_toolkit, \
             patch.object(discovery, "_fetch_search_tools", new_callable=AsyncMock) as mock_search:
            mock_toolkit.return_value = raw_tools
            mock_search.return_value = search_tools

            result = await discovery.discover_tools_for_goal(
                goal_title="Contact leads",
                goal_description="Reach out to potential customers",
                connected_toolkit_slugs=["salesforce"],
            )

        assert len(result) == 3
        slugs = {t.slug for t in result}
        assert "SF_GET_CONTACTS" in slugs
        assert "SF_CREATE_LEAD" in slugs
        assert "GMAIL_SEND" in slugs

    @pytest.mark.asyncio
    async def test_deduplication_by_slug(self) -> None:
        from src.integrations.tool_discovery import ComposioToolDiscovery

        discovery = ComposioToolDiscovery()

        same_tool = self._make_raw_tool("SF_GET_CONTACTS", "Get Contacts", "desc", "salesforce")

        with patch.object(discovery, "_fetch_toolkit_tools", new_callable=AsyncMock) as mock_toolkit, \
             patch.object(discovery, "_fetch_search_tools", new_callable=AsyncMock) as mock_search:
            mock_toolkit.return_value = [same_tool]
            mock_search.return_value = [same_tool]  # duplicate

            result = await discovery.discover_tools_for_goal(
                goal_title="Test",
                goal_description="Test dedup",
                connected_toolkit_slugs=["salesforce"],
            )

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_graceful_degradation_on_error(self) -> None:
        from src.integrations.tool_discovery import ComposioToolDiscovery

        discovery = ComposioToolDiscovery()

        with patch.object(discovery, "_fetch_toolkit_tools", new_callable=AsyncMock) as mock_toolkit, \
             patch.object(discovery, "_fetch_search_tools", new_callable=AsyncMock) as mock_search:
            mock_toolkit.side_effect = RuntimeError("API down")
            mock_search.side_effect = RuntimeError("API down")

            # Use unique goal_title to avoid @cached returning stale results
            result = await discovery.discover_tools_for_goal(
                goal_title="Error scenario unique key",
                goal_description="Test error handling",
                connected_toolkit_slugs=["nonexistent_toolkit"],
            )

        assert result == []

    @pytest.mark.asyncio
    async def test_partial_failure_toolkit_only(self) -> None:
        """If toolkit fetch fails but search succeeds, we still get results."""
        from src.integrations.tool_discovery import ComposioToolDiscovery

        discovery = ComposioToolDiscovery()

        with patch.object(discovery, "_fetch_toolkit_tools", new_callable=AsyncMock) as mock_toolkit, \
             patch.object(discovery, "_fetch_search_tools", new_callable=AsyncMock) as mock_search:
            mock_toolkit.side_effect = RuntimeError("Toolkit fetch failed")
            mock_search.return_value = [
                self._make_raw_tool("GMAIL_SEND", "Send Email", "Send", "gmail"),
            ]

            result = await discovery.discover_tools_for_goal(
                goal_title="Email outreach",
                goal_description="Send emails",
                connected_toolkit_slugs=[],
            )

        assert len(result) == 1
        assert result[0].slug == "GMAIL_SEND"

    @pytest.mark.asyncio
    async def test_empty_connected_toolkits(self) -> None:
        from src.integrations.tool_discovery import ComposioToolDiscovery

        discovery = ComposioToolDiscovery()

        with patch.object(discovery, "_fetch_toolkit_tools", new_callable=AsyncMock) as mock_toolkit, \
             patch.object(discovery, "_fetch_search_tools", new_callable=AsyncMock) as mock_search:
            mock_toolkit.return_value = []
            mock_search.return_value = []

            result = await discovery.discover_tools_for_goal(
                goal_title="Research",
                goal_description="Research competitors",
                connected_toolkit_slugs=[],
            )

        assert result == []

    def test_parse_tool_dict_input(self) -> None:
        """_parse_tool can handle dict-like responses."""
        from src.integrations.tool_discovery import ComposioToolDiscovery

        discovery = ComposioToolDiscovery()
        raw = {
            "slug": "HUBSPOT_GET_DEALS",
            "display_name": "Get Deals",
            "description": "Retrieve deals from HubSpot",
            "appName": "hubspot",
        }
        result = discovery._parse_tool(raw)
        assert result is not None
        assert result.slug == "HUBSPOT_GET_DEALS"
        assert result.name == "Get Deals"
        assert result.toolkit_slug == "hubspot"

    def test_parse_tool_missing_slug_returns_none(self) -> None:
        from src.integrations.tool_discovery import ComposioToolDiscovery

        discovery = ComposioToolDiscovery()
        result = discovery._parse_tool({})
        assert result is None

    def test_parse_tool_derives_name_from_slug(self) -> None:
        """When display_name is missing, name is derived from slug."""
        from src.integrations.tool_discovery import ComposioToolDiscovery

        discovery = ComposioToolDiscovery()
        raw = SimpleNamespace(slug="SALESFORCE_CREATE_LEAD", description="", appName="salesforce")
        result = discovery._parse_tool(raw)
        assert result is not None
        assert result.name == "Create Lead"


# ---------------------------------------------------------------------------
# GoalExecutionService helper method tests
# ---------------------------------------------------------------------------

class TestGoalExecutionServiceHelpers:
    """Test the new helper methods on GoalExecutionService."""

    def _make_service(self) -> MagicMock:
        """Create a minimal GoalExecutionService mock with real methods."""
        from src.services.goal_execution import GoalExecutionService

        # Patch the constructor to avoid DB/LLM initialization
        with patch.object(GoalExecutionService, "__init__", lambda _self: None):
            svc = GoalExecutionService()
        return svc

    def test_integration_types_to_toolkit_slugs(self) -> None:
        from src.services.goal_execution import GoalExecutionService

        result = GoalExecutionService._integration_types_to_toolkit_slugs(
            ["gmail", "salesforce", "unknown_type"]
        )
        assert "gmail" in result
        assert "salesforce" in result
        assert len(result) == 2  # unknown_type is skipped

    def test_integration_types_to_toolkit_slugs_empty(self) -> None:
        from src.services.goal_execution import GoalExecutionService

        result = GoalExecutionService._integration_types_to_toolkit_slugs([])
        assert result == []

    def test_build_agent_tools_prompt_no_discovery(self) -> None:
        from src.services.goal_execution import GoalExecutionService

        prompt = GoalExecutionService._build_agent_tools_prompt([], ["gmail"])
        assert "## Available Agents & Their Tools" in prompt
        assert "hunter" in prompt
        assert "analyst" in prompt
        assert "## Composio Integration Tools Available" not in prompt

    def test_build_agent_tools_prompt_with_discovery(self) -> None:
        from src.integrations.tool_discovery import ComposioToolInfo
        from src.services.goal_execution import GoalExecutionService

        tools = [
            ComposioToolInfo(
                slug="SALESFORCE_GET_CONTACTS",
                name="Get Contacts",
                description="Get CRM contacts",
                toolkit_slug="salesforce",
                toolkit_name="Salesforce",
                requires_auth=True,
            ),
            ComposioToolInfo(
                slug="GMAIL_SEND_EMAIL",
                name="Send Email",
                description="Send via Gmail",
                toolkit_slug="gmail",
                toolkit_name="Gmail",
                requires_auth=True,
            ),
        ]

        prompt = GoalExecutionService._build_agent_tools_prompt(
            tools, ["gmail"]  # gmail is connected, salesforce is not
        )
        assert "## Composio Integration Tools Available" in prompt
        assert "Salesforce [NOT CONNECTED]" in prompt
        assert "Gmail [CONNECTED]" in prompt
        assert "SALESFORCE_GET_CONTACTS" in prompt
        assert "GMAIL_SEND_EMAIL" in prompt

    def test_annotate_task_resources_builtin_tools(self) -> None:
        svc = self._make_service()
        tasks = [
            {
                "title": "Research competitors",
                "tools_needed": ["exa_search", "pubmed_search"],
            }
        ]
        total, connected = svc._annotate_task_resources(tasks, [], [])
        assert total == 2
        assert connected == 2  # both are built-in
        assert tasks[0]["resource_status"][0]["connected"] is True
        assert tasks[0]["resource_status"][1]["connected"] is True

    def test_annotate_task_resources_with_discovery(self) -> None:
        from src.integrations.tool_discovery import ComposioToolInfo

        svc = self._make_service()

        discovered = [
            ComposioToolInfo(
                slug="SALESFORCE_GET_CONTACTS",
                name="Get Contacts",
                description="Get CRM contacts",
                toolkit_slug="salesforce",
                toolkit_name="Salesforce",
                requires_auth=True,
            ),
        ]

        tasks = [
            {
                "title": "Get CRM data",
                "tools_needed": ["SALESFORCE_GET_CONTACTS", "exa_search"],
            }
        ]

        total, connected = svc._annotate_task_resources(
            tasks, ["salesforce"], discovered
        )
        assert total == 2
        assert connected == 2  # salesforce is connected, exa_search is built-in

        sf_resource = tasks[0]["resource_status"][0]
        assert sf_resource["display_name"] == "Get Contacts"
        assert sf_resource["toolkit"] == "Salesforce"
        assert sf_resource["connected"] is True
        assert "setup_instruction" not in sf_resource

    def test_annotate_task_resources_unconnected_composio_tool(self) -> None:
        from src.integrations.tool_discovery import ComposioToolInfo

        svc = self._make_service()

        discovered = [
            ComposioToolInfo(
                slug="HUBSPOT_GET_DEALS",
                name="Get Deals",
                description="Get deals from HubSpot",
                toolkit_slug="hubspot",
                toolkit_name="HubSpot",
                requires_auth=True,
            ),
        ]

        tasks = [
            {
                "title": "Check deals",
                "tools_needed": ["HUBSPOT_GET_DEALS"],
            }
        ]

        # User does NOT have hubspot connected
        total, connected = svc._annotate_task_resources(
            tasks, ["gmail"], discovered
        )
        assert total == 1
        assert connected == 0

        resource = tasks[0]["resource_status"][0]
        assert resource["connected"] is False
        assert resource["display_name"] == "Get Deals"
        assert "setup_instruction" in resource
        assert "HubSpot" in resource["setup_instruction"]

    def test_annotate_task_resources_fallback_for_unknown_tool(self) -> None:
        svc = self._make_service()

        tasks = [
            {
                "title": "Send email",
                "tools_needed": ["composio_email_send"],
            }
        ]

        # No discovered tools — falls back to _check_tool_connected
        total, connected = svc._annotate_task_resources(
            tasks, ["gmail"], []
        )
        assert total == 1
        assert connected == 1  # gmail is connected, composio_email_send maps to it

    def test_annotate_task_resources_auth_required_connected(self) -> None:
        """Test that auth_required integrations are annotated when connected."""
        svc = self._make_service()

        tasks = [
            {
                "title": "Sync with Salesforce",
                "tools_needed": [],
                "auth_required": ["salesforce"],
            }
        ]

        # User has Salesforce connected
        total, connected = svc._annotate_task_resources(
            tasks, ["salesforce"], []
        )
        assert total == 1
        assert connected == 1

        resource = tasks[0]["resource_status"][0]
        assert resource["connected"] is True
        assert resource["tool"] == "salesforce"
        assert resource["display_name"] == "Salesforce"
        assert "setup_instruction" not in resource

    def test_annotate_task_resources_auth_required_not_connected(self) -> None:
        """Test that auth_required integrations show setup instruction when not connected."""
        svc = self._make_service()

        tasks = [
            {
                "title": "Sync with HubSpot",
                "tools_needed": [],
                "auth_required": ["hubspot"],
            }
        ]

        # User does NOT have hubspot connected
        total, connected = svc._annotate_task_resources(
            tasks, ["gmail"], []
        )
        assert total == 1
        assert connected == 0

        resource = tasks[0]["resource_status"][0]
        assert resource["connected"] is False
        assert resource["tool"] == "hubspot"
        assert resource["display_name"] == "HubSpot"
        assert "setup_instruction" in resource
        assert "HubSpot" in resource["setup_instruction"]

    def test_annotate_task_resources_auth_required_and_tools_needed(self) -> None:
        """Test that both auth_required and tools_needed are processed."""
        svc = self._make_service()

        tasks = [
            {
                "title": "Research and sync",
                "tools_needed": ["exa_search"],  # built-in
                "auth_required": ["salesforce"],  # needs integration
            }
        ]

        total, connected = svc._annotate_task_resources(
            tasks, ["salesforce"], []
        )
        assert total == 2  # exa_search + salesforce
        assert connected == 2  # both connected

        # Check both resources are present
        tools = [r["tool"] for r in tasks[0]["resource_status"]]
        assert "exa_search" in tools
        assert "salesforce" in tools

    def test_annotate_task_resources_auth_required_no_duplicate(self) -> None:
        """Test that auth_required doesn't duplicate tools_needed entries."""
        svc = self._make_service()

        tasks = [
            {
                "title": "CRM work",
                "tools_needed": ["salesforce"],
                "auth_required": ["salesforce"],  # Same as tools_needed
            }
        ]

        total, connected = svc._annotate_task_resources(
            tasks, ["salesforce"], []
        )
        assert total == 1  # Only one entry, not two
        assert connected == 1


# ---------------------------------------------------------------------------
# Singleton test
# ---------------------------------------------------------------------------

class TestSingleton:
    """Test get_tool_discovery singleton."""

    def test_returns_same_instance(self) -> None:
        from src.integrations import tool_discovery

        # Reset singleton
        tool_discovery._discovery_instance = None

        a = tool_discovery.get_tool_discovery()
        b = tool_discovery.get_tool_discovery()
        assert a is b

        # Clean up
        tool_discovery._discovery_instance = None
