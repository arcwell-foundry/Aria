"""Tests for MCP server evaluator capability."""

import pytest

from src.agents.capabilities.mcp_evaluator import MCPEvaluatorCapability
from src.mcp_servers.models import MCPServerInfo, MCPToolInfo


@pytest.fixture
def evaluator() -> MCPEvaluatorCapability:
    return MCPEvaluatorCapability()


class TestMCPEvaluatorCapability:
    """Tests for security assessment logic."""

    @pytest.mark.asyncio
    async def test_evaluates_low_risk_server(
        self, evaluator: MCPEvaluatorCapability
    ) -> None:
        """Verified publisher + open source + popular → recommend."""
        server = MCPServerInfo(
            name="mcp-server-github",
            publisher="anthropic",
            version="2.0.0",
            description="GitHub integration",
            tools=[
                MCPToolInfo(name="list_repos", description="List repositories"),
                MCPToolInfo(name="create_issue", description="Create an issue"),
            ],
            permissions={"read": ["repos", "issues"]},
            download_count=5000,
            last_updated="2026-02-01T00:00:00Z",
            repo_url="https://github.com/anthropic/mcp-servers",
            is_open_source=True,
            is_verified_publisher=True,
        )

        assessment = await evaluator.evaluate(server)

        assert assessment.overall_risk == "low"
        assert assessment.recommendation == "recommend"
        assert assessment.publisher_verified is True
        assert assessment.open_source is True
        assert assessment.adoption_score >= 0.7

    @pytest.mark.asyncio
    async def test_flags_high_permission_server(
        self, evaluator: MCPEvaluatorCapability
    ) -> None:
        """Unverified + write access + low adoption → caution."""
        server = MCPServerInfo(
            name="shady-mcp-server",
            publisher="unknown-dev",
            version="0.1.0",
            description="Does everything",
            tools=[MCPToolInfo(name="do_stuff", description="Does stuff")],
            permissions={"write": ["filesystem"], "delete": ["records"]},
            download_count=15,
            last_updated="2026-01-01T00:00:00Z",
            repo_url="",  # closed source
            is_open_source=False,
            is_verified_publisher=False,
        )

        assessment = await evaluator.evaluate(server)

        assert assessment.overall_risk in ("medium", "high")
        assert assessment.recommendation == "caution"
        assert assessment.publisher_verified is False
        assert assessment.open_source is False
        assert "write" in assessment.data_access_scope.lower() or "delete" in assessment.data_access_scope.lower()

    @pytest.mark.asyncio
    async def test_evaluation_penalizes_stale_packages(
        self, evaluator: MCPEvaluatorCapability
    ) -> None:
        """Package not updated in 6+ months gets penalized."""
        server = MCPServerInfo(
            name="old-mcp-server",
            publisher="some-dev",
            version="1.0.0",
            description="Old server",
            tools=[MCPToolInfo(name="old_tool")],
            download_count=10,  # Low adoption compounds staleness
            last_updated="2025-01-01T00:00:00Z",  # Over a year old
            repo_url="",  # Closed source
            is_open_source=False,
            is_verified_publisher=False,
        )

        assessment = await evaluator.evaluate(server)

        assert assessment.freshness_days > 180
        # Staleness + low adoption + closed source should push risk higher than low
        assert assessment.overall_risk != "low"
        assert "stale" in assessment.reasoning.lower()

    @pytest.mark.asyncio
    async def test_evaluate_batch_sorts_by_recommendation(
        self, evaluator: MCPEvaluatorCapability
    ) -> None:
        """Batch evaluation sorts results: recommend → caution → reject."""
        good_server = MCPServerInfo(
            name="good-server",
            publisher="verified-org",
            download_count=10000,
            last_updated="2026-02-15T00:00:00Z",
            repo_url="https://github.com/org/good",
            is_open_source=True,
            is_verified_publisher=True,
        )

        mediocre_server = MCPServerInfo(
            name="mediocre-server",
            publisher="unknown",
            download_count=50,
            last_updated="2025-06-01T00:00:00Z",
            is_open_source=False,
            is_verified_publisher=False,
        )

        results = await evaluator.evaluate_batch([mediocre_server, good_server])

        # Good server should be first (recommend)
        assert results[0][0].name == "good-server"
        assert results[0][1].recommendation == "recommend"
        # Mediocre server second
        assert results[1][0].name == "mediocre-server"

    @pytest.mark.asyncio
    async def test_no_permissions_declared(
        self, evaluator: MCPEvaluatorCapability
    ) -> None:
        """Server with no explicit permissions gets neutral assessment."""
        server = MCPServerInfo(
            name="simple-server",
            publisher="dev",
            download_count=200,
            last_updated="2026-02-10T00:00:00Z",
            repo_url="https://github.com/dev/simple",
            is_open_source=True,
            is_verified_publisher=False,
            permissions={},
        )

        assessment = await evaluator.evaluate(server)

        assert "no explicit permissions" in assessment.data_access_scope.lower()
