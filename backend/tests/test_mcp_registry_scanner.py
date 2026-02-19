"""Tests for MCP registry scanners."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mcp_servers.models import MCPServerInfo
from src.mcp_servers.registry_scanner import (
    MCPRunScanner,
    NpmMCPScanner,
    SmitheryScanner,
    UnifiedRegistryScanner,
)


@pytest.fixture
def smithery_scanner() -> SmitheryScanner:
    return SmitheryScanner()


@pytest.fixture
def npm_scanner() -> NpmMCPScanner:
    return NpmMCPScanner()


@pytest.fixture
def mcp_run_scanner() -> MCPRunScanner:
    return MCPRunScanner()


class TestSmitheryScanner:
    """Tests for SmitheryScanner."""

    @pytest.mark.asyncio
    async def test_search_formats_results(self, smithery_scanner: SmitheryScanner) -> None:
        """Smithery scanner returns correctly structured MCPServerInfo objects."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "servers": [
                {
                    "qualifiedName": "mcp-server-slack",
                    "displayName": "Slack MCP Server",
                    "vendor": "SlackHQ",
                    "version": "1.2.3",
                    "description": "Slack integration for MCP",
                    "transport": "stdio",
                    "tools": [
                        {"name": "send_message", "description": "Send a Slack message"},
                        {"name": "list_channels", "description": "List Slack channels"},
                    ],
                    "security": {"read": True},
                    "useCount": 5000,
                    "updatedAt": "2026-01-15T00:00:00Z",
                    "homepage": "https://github.com/slack/mcp-server-slack",
                    "verified": True,
                }
            ]
        }

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("src.mcp_servers.registry_scanner.httpx.AsyncClient", return_value=mock_client):
            results = await smithery_scanner.search("slack", limit=5)

        assert len(results) == 1
        server = results[0]
        assert isinstance(server, MCPServerInfo)
        assert server.name == "mcp-server-slack"
        assert server.display_name == "Slack MCP Server"
        assert server.publisher == "SlackHQ"
        assert server.version == "1.2.3"
        assert server.transport == "stdio"
        assert len(server.tools) == 2
        assert server.tools[0].name == "send_message"
        assert server.download_count == 5000
        assert server.registry_source == "smithery"
        assert server.is_verified_publisher is True
        assert server.is_open_source is True

    @pytest.mark.asyncio
    async def test_search_handles_http_error(self, smithery_scanner: SmitheryScanner) -> None:
        """Smithery scanner returns empty list on HTTP error."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=Exception("Connection failed"))

        with patch("src.mcp_servers.registry_scanner.httpx.AsyncClient", return_value=mock_client):
            results = await smithery_scanner.search("slack")

        assert results == []


class TestNpmMCPScanner:
    """Tests for NpmMCPScanner."""

    @pytest.mark.asyncio
    async def test_search_parses_npm_response(self, npm_scanner: NpmMCPScanner) -> None:
        """npm scanner correctly parses npm search API response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "objects": [
                {
                    "package": {
                        "name": "@modelcontextprotocol/mcp-server-github",
                        "version": "2.0.0",
                        "description": "GitHub MCP server",
                        "publisher": {"username": "anthropic"},
                        "date": "2026-02-01T00:00:00Z",
                        "links": {
                            "repository": "https://github.com/anthropic/mcp-servers"
                        },
                    },
                    "score": {"detail": {"popularity": 0.8}},
                }
            ]
        }

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("src.mcp_servers.registry_scanner.httpx.AsyncClient", return_value=mock_client):
            results = await npm_scanner.search("github")

        assert len(results) == 1
        server = results[0]
        assert server.name == "@modelcontextprotocol/mcp-server-github"
        assert server.publisher == "anthropic"
        assert server.registry_source == "npm"
        assert server.is_open_source is True


class TestUnifiedRegistryScanner:
    """Tests for UnifiedRegistryScanner."""

    @pytest.mark.asyncio
    async def test_searches_all_registries_in_parallel(self) -> None:
        """Unified scanner queries all registries and deduplicates."""
        # Create mock scanners
        smithery = AsyncMock(spec=SmitheryScanner)
        smithery.search = AsyncMock(return_value=[
            MCPServerInfo(
                name="mcp-server-slack",
                download_count=5000,
                registry_source="smithery",
            )
        ])

        npm = AsyncMock(spec=NpmMCPScanner)
        npm.search = AsyncMock(return_value=[
            MCPServerInfo(
                name="mcp-server-slack",  # duplicate
                download_count=3000,
                registry_source="npm",
            ),
            MCPServerInfo(
                name="mcp-server-github",
                download_count=8000,
                registry_source="npm",
            ),
        ])

        mcp_run = AsyncMock(spec=MCPRunScanner)
        mcp_run.search = AsyncMock(return_value=[])

        scanner = UnifiedRegistryScanner(scanners=[smithery, npm, mcp_run])
        results = await scanner.search("integration", limit=10)

        # Should deduplicate: 2 unique servers
        assert len(results) == 2
        # Should be sorted by download_count descending
        assert results[0].name == "mcp-server-github"
        assert results[0].download_count == 8000
        # Slack should use the Smithery version (higher downloads)
        slack_result = next(r for r in results if r.name == "mcp-server-slack")
        assert slack_result.download_count == 5000
        assert slack_result.registry_source == "smithery"

    @pytest.mark.asyncio
    async def test_handles_scanner_failure_gracefully(self) -> None:
        """Unified scanner continues when one registry fails."""
        working_scanner = AsyncMock()
        working_scanner.search = AsyncMock(return_value=[
            MCPServerInfo(name="working-server", download_count=100)
        ])

        broken_scanner = AsyncMock()
        broken_scanner.search = AsyncMock(side_effect=Exception("Registry down"))

        scanner = UnifiedRegistryScanner(scanners=[working_scanner, broken_scanner])
        results = await scanner.search("test")

        assert len(results) == 1
        assert results[0].name == "working-server"

    @pytest.mark.asyncio
    async def test_respects_limit(self) -> None:
        """Unified scanner returns at most `limit` results."""
        mock_scanner = AsyncMock()
        mock_scanner.search = AsyncMock(return_value=[
            MCPServerInfo(name=f"server-{i}", download_count=100 - i)
            for i in range(10)
        ])

        scanner = UnifiedRegistryScanner(scanners=[mock_scanner])
        results = await scanner.search("test", limit=3)

        assert len(results) == 3


class TestScoutMCPDiscovery:
    """Test Scout agent's MCP discovery integration."""

    @pytest.mark.asyncio
    async def test_scout_discovers_mcp_server_for_gap(self) -> None:
        """Scout's search_mcp_registries delegates to MCPDiscoveryCapability."""
        from src.agents.capabilities.mcp_discovery import MCPDiscoveryCapability
        from src.mcp_servers.models import CapabilityGapEvent

        mock_scanner = AsyncMock()
        mock_scanner.search = AsyncMock(return_value=[
            MCPServerInfo(
                name="mcp-server-jira",
                display_name="Jira MCP Server",
                publisher="atlassian",
                description="Manage Jira issues",
                registry_source="smithery",
                download_count=2000,
            )
        ])

        discovery = MCPDiscoveryCapability(scanner=UnifiedRegistryScanner(scanners=[mock_scanner]))

        gap = CapabilityGapEvent(
            user_id="user-123",
            requested_tool="jira_create_issue",
            requesting_agent="operator",
            task_context="User asked to create a Jira ticket",
        )

        results = await discovery.search_for_gap(gap, limit=3)

        assert len(results) == 1
        assert results[0].name == "mcp-server-jira"
        mock_scanner.search.assert_called_once()
