"""Tests for MCP capability manager orchestration."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mcp_servers.capability_manager import MCPCapabilityManager
from src.mcp_servers.models import (
    InstalledCapability,
    MCPServerInfo,
    MCPToolInfo,
    SecurityAssessment,
)


def _make_server_info(
    name: str = "mcp-server-test",
    transport: str = "stdio",
    tools: list[MCPToolInfo] | None = None,
    **kwargs: object,
) -> MCPServerInfo:
    """Helper to create MCPServerInfo for tests."""
    return MCPServerInfo(
        name=name,
        display_name=kwargs.get("display_name", name),  # type: ignore[arg-type]
        publisher=kwargs.get("publisher", "test-publisher"),  # type: ignore[arg-type]
        version=kwargs.get("version", "1.0.0"),  # type: ignore[arg-type]
        description=kwargs.get("description", "Test server"),  # type: ignore[arg-type]
        transport=transport,
        tools=tools or [MCPToolInfo(name="test_tool", description="A test tool")],
        registry_source=kwargs.get("registry_source", "npm"),  # type: ignore[arg-type]
        registry_package_id=kwargs.get("registry_package_id", name),  # type: ignore[arg-type]
        download_count=kwargs.get("download_count", 1000),  # type: ignore[arg-type]
    )


def _make_assessment(**kwargs: object) -> SecurityAssessment:
    """Helper to create SecurityAssessment for tests."""
    return SecurityAssessment(
        overall_risk=kwargs.get("overall_risk", "low"),  # type: ignore[arg-type]
        recommendation=kwargs.get("recommendation", "recommend"),  # type: ignore[arg-type]
        publisher_verified=kwargs.get("publisher_verified", True),  # type: ignore[arg-type]
        open_source=kwargs.get("open_source", True),  # type: ignore[arg-type]
        reasoning=kwargs.get("reasoning", "Looks good"),  # type: ignore[arg-type]
    )


def _make_installed_capability(
    server_name: str = "mcp-server-test",
    **kwargs: object,
) -> InstalledCapability:
    """Helper to create InstalledCapability for tests."""
    return InstalledCapability(
        id=kwargs.get("id", "cap-123"),  # type: ignore[arg-type]
        user_id=kwargs.get("user_id", "user-123"),  # type: ignore[arg-type]
        server_name=server_name,
        transport=kwargs.get("transport", "stdio"),  # type: ignore[arg-type]
        connection_config=kwargs.get("connection_config", {}),  # type: ignore[arg-type]
        declared_tools=kwargs.get("declared_tools", [{"name": "test_tool"}]),  # type: ignore[arg-type]
        is_enabled=kwargs.get("is_enabled", True),  # type: ignore[arg-type]
        health_status=kwargs.get("health_status", "healthy"),  # type: ignore[arg-type]
    )


class TestMCPCapabilityManager:
    """Tests for the capability manager orchestration."""

    @pytest.mark.asyncio
    async def test_full_install_flow(self) -> None:
        """Install flow: store record → connect → health check → register tools."""
        mock_store = AsyncMock()
        mock_pool = AsyncMock()
        mock_conn = AsyncMock()

        # Store returns installed capability
        installed = _make_installed_capability()
        mock_store.install = AsyncMock(return_value=installed)
        mock_store.update_health = AsyncMock(return_value=installed)

        # Pool returns connection
        mock_pool.get_connection = AsyncMock(return_value=mock_conn)
        mock_conn.health_check = AsyncMock(return_value="healthy")

        server_info = _make_server_info()
        assessment = _make_assessment()

        with patch("src.mcp_servers.capability_manager.settings") as mock_settings:
            mock_settings.MCP_EXTERNAL_ENABLED = True
            with patch("src.mcp_servers.capability_manager.register_external_tools") as mock_register:
                manager = MCPCapabilityManager(store=mock_store, pool=mock_pool)
                result = await manager.install("user-123", server_info, assessment)

        # Verify store was called
        mock_store.install.assert_called_once()
        install_kwargs = mock_store.install.call_args
        assert install_kwargs.kwargs["user_id"] == "user-123"
        assert install_kwargs.kwargs["server_name"] == "mcp-server-test"

        # Verify connection was established
        mock_pool.get_connection.assert_called_once()

        # Verify health check was run
        mock_conn.health_check.assert_called_once()

        # Verify tools were registered
        mock_register.assert_called_once_with(
            user_id="user-123",
            server_name="mcp-server-test",
            tools=[{"name": "test_tool", "description": "A test tool", "input_schema": {}, "dct_action": ""}],
        )

        assert result.server_name == "mcp-server-test"

    @pytest.mark.asyncio
    async def test_uninstall_cleans_up_everything(self) -> None:
        """Uninstall removes DB record, closes connection, and unregisters tools."""
        mock_store = AsyncMock()
        mock_pool = AsyncMock()
        mock_store.uninstall = AsyncMock(return_value=True)

        with patch("src.mcp_servers.capability_manager.unregister_external_tools") as mock_unregister:
            manager = MCPCapabilityManager(store=mock_store, pool=mock_pool)
            result = await manager.uninstall("user-123", "mcp-server-test")

        assert result is True
        mock_pool.close_connection.assert_called_once_with("user-123", "mcp-server-test")
        mock_unregister.assert_called_once_with("user-123", "mcp-server-test")
        mock_store.uninstall.assert_called_once_with("user-123", "mcp-server-test")

    @pytest.mark.asyncio
    async def test_uninstall_returns_false_when_not_found(self) -> None:
        """Uninstall returns False when the capability doesn't exist."""
        mock_store = AsyncMock()
        mock_pool = AsyncMock()
        mock_store.uninstall = AsyncMock(return_value=False)

        with patch("src.mcp_servers.capability_manager.unregister_external_tools"):
            manager = MCPCapabilityManager(store=mock_store, pool=mock_pool)
            result = await manager.uninstall("user-123", "nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_unused_capability_detection(self) -> None:
        """Capabilities unused for 30+ days are flagged for removal."""
        stale_cap = _make_installed_capability(
            server_name="unused-server",
        )

        mock_store = AsyncMock()
        mock_store.get_unused_capabilities = AsyncMock(return_value=[stale_cap])

        manager = MCPCapabilityManager(store=mock_store)
        unused = await manager.recommend_removals("user-123", days_unused=30)

        assert len(unused) == 1
        assert unused[0].server_name == "unused-server"
        mock_store.get_unused_capabilities.assert_called_once_with("user-123", 30)

    @pytest.mark.asyncio
    async def test_present_recommendation_format(self) -> None:
        """Recommendation presentation includes all required fields."""
        server_info = _make_server_info(
            name="mcp-server-slack",
            display_name="Slack MCP Server",
            publisher="SlackHQ",
            tools=[
                MCPToolInfo(name="send_message"),
                MCPToolInfo(name="list_channels"),
            ],
        )
        assessment = _make_assessment(
            overall_risk="low",
            recommendation="recommend",
            reasoning="Verified publisher, open source",
        )

        manager = MCPCapabilityManager()
        rec = manager.present_recommendation("user-123", server_info, assessment)

        assert rec["type"] == "mcp_capability_recommendation"
        assert rec["server"]["name"] == "mcp-server-slack"
        assert rec["server"]["display_name"] == "Slack MCP Server"
        assert rec["server"]["tool_count"] == 2
        assert rec["assessment"]["risk"] == "low"
        assert rec["assessment"]["recommendation"] == "recommend"

    @pytest.mark.asyncio
    async def test_install_disabled_raises(self) -> None:
        """Installing when external MCP is disabled raises RuntimeError."""
        with patch("src.mcp_servers.capability_manager.settings") as mock_settings:
            mock_settings.MCP_EXTERNAL_ENABLED = False
            manager = MCPCapabilityManager()

            with pytest.raises(RuntimeError, match="disabled"):
                await manager.install(
                    "user-123",
                    _make_server_info(),
                    _make_assessment(),
                )

    @pytest.mark.asyncio
    async def test_refresh_health_updates_db(self) -> None:
        """Health refresh checks all connections and updates DB."""
        mock_store = AsyncMock()
        mock_pool = AsyncMock()
        mock_pool.health_check_all = AsyncMock(
            return_value={"server-a": "healthy", "server-b": "degraded"}
        )

        manager = MCPCapabilityManager(store=mock_store, pool=mock_pool)
        statuses = await manager.refresh_health("user-123")

        assert statuses == {"server-a": "healthy", "server-b": "degraded"}
        assert mock_store.update_health.call_count == 2


class TestCapabilityGapDetection:
    """Test gap event emission in MCPToolClient."""

    @pytest.mark.asyncio
    async def test_capability_gap_triggers_event(self) -> None:
        """MCPToolClient emits gap event when tool not found."""
        from src.mcp_servers.client import MCPToolClient

        client = MCPToolClient(user_id="user-123")

        with pytest.raises(ValueError, match="Unknown MCP tool"):
            await client.call_tool(
                "nonexistent_tool",
                {"arg": "value"},
                delegatee="operator",
            )
