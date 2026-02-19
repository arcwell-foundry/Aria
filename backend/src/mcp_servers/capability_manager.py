"""MCPCapabilityManager — orchestrates the full capability lifecycle.

Coordinates discovery (Scout), evaluation (Analyst), installation,
connection management, health checks, and cleanup for external MCP servers.
"""

from __future__ import annotations

import logging
from typing import Any

from src.core.config import settings
from src.mcp_servers.capability_store import CapabilityStore
from src.mcp_servers.connection_pool import ExternalConnectionPool
from src.mcp_servers.models import (
    InstalledCapability,
    MCPServerInfo,
    SecurityAssessment,
)
from src.mcp_servers.registry import (
    register_external_tools,
    unregister_external_tools,
)

logger = logging.getLogger(__name__)


class MCPCapabilityManager:
    """Orchestrates discover → evaluate → install → connect → register lifecycle.

    Usage::

        manager = MCPCapabilityManager()

        # Discover and evaluate
        recommendations = await manager.discover_and_evaluate(
            user_id, "slack messaging", "Need to send Slack notifications"
        )

        # Present to user and get approval...

        # Install after approval
        server_info, assessment = recommendations[0]
        capability = await manager.install(user_id, server_info, assessment)

        # Later: uninstall
        await manager.uninstall(user_id, "mcp-server-slack")
    """

    def __init__(
        self,
        store: CapabilityStore | None = None,
        pool: ExternalConnectionPool | None = None,
    ) -> None:
        self._store = store or CapabilityStore()
        self._pool = pool or ExternalConnectionPool.instance()

    async def discover_and_evaluate(
        self,
        user_id: str,
        needed_capability: str,
        context: str = "",
        limit: int = 5,
    ) -> list[tuple[MCPServerInfo, SecurityAssessment]]:
        """Search registries and evaluate discovered servers.

        Runs the Scout's registry search followed by the Analyst's security
        evaluation on each result.

        Args:
            user_id: The user's UUID (for logging/context).
            needed_capability: Description of the capability needed.
            context: Additional context about why it's needed.
            limit: Maximum number of results to evaluate.

        Returns:
            List of (server_info, assessment) tuples, sorted by recommendation.
        """
        from src.agents.capabilities.mcp_discovery import MCPDiscoveryCapability
        from src.agents.capabilities.mcp_evaluator import MCPEvaluatorCapability

        # Discover
        discovery = MCPDiscoveryCapability()
        servers = await discovery.search_for_capability(
            needed_capability=needed_capability,
            context=context,
            limit=limit,
        )

        if not servers:
            logger.info(
                "No MCP servers found for capability '%s' (user %s)",
                needed_capability,
                user_id,
            )
            return []

        # Evaluate
        evaluator = MCPEvaluatorCapability()
        results = await evaluator.evaluate_batch(servers)

        logger.info(
            "Discovered and evaluated %d servers for '%s' (user %s)",
            len(results),
            needed_capability,
            user_id,
        )
        return results

    def present_recommendation(
        self,
        user_id: str,
        server_info: MCPServerInfo,
        assessment: SecurityAssessment,
    ) -> dict[str, Any]:
        """Format a recommendation for presentation to the user.

        Args:
            user_id: The user's UUID.
            server_info: Server metadata.
            assessment: Security assessment.

        Returns:
            Dict formatted for chat/UI display with all relevant information.
        """
        # Build tool list summary
        tool_names = [t.name for t in server_info.tools]
        tool_summary = ", ".join(tool_names[:5])
        if len(tool_names) > 5:
            tool_summary += f" (+{len(tool_names) - 5} more)"

        return {
            "type": "mcp_capability_recommendation",
            "server": {
                "name": server_info.name,
                "display_name": server_info.display_name or server_info.name,
                "publisher": server_info.publisher,
                "version": server_info.version,
                "description": server_info.description,
                "transport": server_info.transport,
                "tools": tool_summary,
                "tool_count": len(tool_names),
                "registry": server_info.registry_source,
                "downloads": server_info.download_count,
                "open_source": server_info.is_open_source,
                "repo_url": server_info.repo_url,
            },
            "assessment": {
                "risk": assessment.overall_risk,
                "recommendation": assessment.recommendation,
                "reasoning": assessment.reasoning,
                "publisher_verified": assessment.publisher_verified,
                "freshness_days": assessment.freshness_days,
                "adoption_score": round(assessment.adoption_score, 2),
            },
        }

    async def install(
        self,
        user_id: str,
        server_info: MCPServerInfo,
        assessment: SecurityAssessment,
        connection_config: dict[str, Any] | None = None,
    ) -> InstalledCapability:
        """Install an external MCP server for a user.

        Steps:
        1. Create ``installed_capabilities`` DB record
        2. Establish connection via ExternalConnectionPool
        3. Run health check
        4. Register tools in EXTERNAL_TOOL_SERVER_MAP
        5. Create DelegationTrace for audit

        Args:
            user_id: The user's UUID.
            server_info: Server metadata from discovery.
            assessment: Security evaluation result.
            connection_config: Override connection config (optional).

        Returns:
            The installed capability record.
        """
        if not settings.MCP_EXTERNAL_ENABLED:
            raise RuntimeError("External MCP servers are disabled")

        # Build connection config from server info if not provided
        if connection_config is None:
            connection_config = self._build_connection_config(server_info)

        # Serialize tools for storage
        tools_data = [t.to_dict() for t in server_info.tools]

        # 1. Create DB record
        capability = await self._store.install(
            user_id=user_id,
            server_name=server_info.name,
            server_display_name=server_info.display_name or server_info.name,
            registry_source=server_info.registry_source,
            registry_package_id=server_info.registry_package_id,
            transport=server_info.transport,
            connection_config=connection_config,
            declared_tools=tools_data,
            declared_permissions=server_info.permissions,
            security_assessment=assessment.to_dict(),
        )

        # 2. Establish connection
        try:
            conn = await self._pool.get_connection(
                user_id=user_id,
                server_name=server_info.name,
                transport=server_info.transport,
                connection_config=connection_config,
                declared_tools=tools_data,
            )

            # 3. Health check
            health = await conn.health_check()
            await self._store.update_health(user_id, server_info.name, health)

            if health == "unhealthy":
                logger.warning(
                    "Installed %s but health check failed (user %s)",
                    server_info.name,
                    user_id,
                )
        except Exception:
            logger.warning(
                "Installed %s but connection failed — will retry on first use (user %s)",
                server_info.name,
                user_id,
                exc_info=True,
            )

        # 4. Register tools in memory map
        register_external_tools(
            user_id=user_id,
            server_name=server_info.name,
            tools=tools_data,
        )

        # 5. Store workflow in ProceduralMemory (best-effort)
        try:
            await self._store_capability_workflow(user_id, server_info, capability)
        except Exception:
            logger.debug(
                "Failed to store procedural memory for %s", server_info.name, exc_info=True
            )

        logger.info(
            "Successfully installed capability '%s' for user %s "
            "(tools=%d, risk=%s, transport=%s)",
            server_info.name,
            user_id,
            len(server_info.tools),
            assessment.overall_risk,
            server_info.transport,
        )

        return capability

    async def uninstall(self, user_id: str, server_name: str) -> bool:
        """Uninstall an external MCP server.

        Removes DB record, closes connection, and unregisters tools.

        Args:
            user_id: The user's UUID.
            server_name: Server identifier to remove.

        Returns:
            True if successfully uninstalled, False if not found.
        """
        # 1. Close connection
        await self._pool.close_connection(user_id, server_name)

        # 2. Unregister tools from memory map
        unregister_external_tools(user_id, server_name)

        # 3. Delete DB record
        deleted = await self._store.uninstall(user_id, server_name)

        if deleted:
            logger.info("Uninstalled capability '%s' for user %s", server_name, user_id)
        return deleted

    async def recommend_removals(
        self, user_id: str, days_unused: int = 30
    ) -> list[InstalledCapability]:
        """Find capabilities that haven't been used recently.

        Args:
            user_id: The user's UUID.
            days_unused: Number of days without usage to flag.

        Returns:
            List of unused capabilities.
        """
        return await self._store.get_unused_capabilities(user_id, days_unused)

    async def refresh_health(self, user_id: str) -> dict[str, str]:
        """Run health checks on all installed capabilities.

        Updates the DB with fresh health status for each server.

        Args:
            user_id: The user's UUID.

        Returns:
            Dict mapping server_name to health status.
        """
        statuses = await self._pool.health_check_all(user_id)

        # Update DB for each checked server
        for server_name, status in statuses.items():
            await self._store.update_health(user_id, server_name, status)

        return statuses

    def _build_connection_config(
        self, server_info: MCPServerInfo
    ) -> dict[str, Any]:
        """Build default connection config from server info.

        Args:
            server_info: Server metadata.

        Returns:
            Transport-specific connection config dict.
        """
        if server_info.transport == "stdio":
            # For npm packages, default to npx
            if server_info.registry_source == "npm":
                return {
                    "command": "npx",
                    "args": ["-y", server_info.name],
                    "env": {},
                }
            # For Smithery packages
            return {
                "command": "npx",
                "args": ["-y", server_info.registry_package_id or server_info.name],
                "env": {},
            }
        elif server_info.transport == "sse":
            return {
                "url": server_info.registry_package_id or "",
                "headers": {},
            }
        return {}

    async def _store_capability_workflow(
        self,
        user_id: str,
        server_info: MCPServerInfo,
        capability: InstalledCapability,
    ) -> None:
        """Store an installation workflow in ProceduralMemory.

        Args:
            user_id: The user's UUID.
            server_info: Server metadata.
            capability: The installed capability record.
        """
        try:
            from src.memory.procedural import ProceduralMemoryService

            proc_memory = ProceduralMemoryService()
            tool_names = [t.name for t in server_info.tools]
            await proc_memory.create_workflow(
                user_id=user_id,
                name=f"mcp_install_{server_info.name}",
                description=(
                    f"Installed MCP server '{server_info.display_name or server_info.name}' "
                    f"from {server_info.registry_source}. "
                    f"Provides tools: {', '.join(tool_names[:5])}."
                ),
                steps=[
                    {
                        "action": "install_mcp_server",
                        "server_name": server_info.name,
                        "transport": server_info.transport,
                        "tool_count": len(tool_names),
                    }
                ],
                trigger=f"capability_install:{server_info.name}",
            )
        except Exception:
            # ProceduralMemory storage is best-effort
            logger.debug(
                "ProceduralMemory not available for capability workflow", exc_info=True
            )
