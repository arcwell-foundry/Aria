"""MCP Discovery capability — searches registries for MCP servers.

Used by the Scout agent's ``search_mcp_registries`` tool to find
external MCP servers that can fill a capability gap.
"""

from __future__ import annotations

import logging
from typing import Any

from src.mcp_servers.models import CapabilityGapEvent, MCPServerInfo
from src.mcp_servers.registry_scanner import UnifiedRegistryScanner

logger = logging.getLogger(__name__)


class MCPDiscoveryCapability:
    """Searches MCP registries to find servers matching a needed capability.

    Usage::

        discovery = MCPDiscoveryCapability()
        results = await discovery.search_for_capability("slack messaging")
    """

    def __init__(
        self,
        scanner: UnifiedRegistryScanner | None = None,
    ) -> None:
        self._scanner = scanner or UnifiedRegistryScanner()

    async def search_for_capability(
        self,
        needed_capability: str,
        context: str = "",
        limit: int = 5,
    ) -> list[MCPServerInfo]:
        """Search all registries for servers providing a capability.

        Args:
            needed_capability: Description of the needed capability
                (e.g. ``"slack messaging"``, ``"jira issue management"``).
            context: Optional context about why this capability is needed.
            limit: Maximum number of results.

        Returns:
            List of discovered MCP servers, sorted by popularity.
        """
        # Build a focused search query
        query = needed_capability
        if context:
            # Extract keywords from context to improve search relevance
            query = f"{needed_capability} {context[:100]}"

        logger.info(
            "Searching MCP registries for capability: %s (limit=%d)",
            needed_capability,
            limit,
        )

        results = await self._scanner.search(query, limit=limit)

        logger.info(
            "Found %d MCP servers for capability '%s'",
            len(results),
            needed_capability,
        )
        return results

    async def search_for_gap(
        self,
        gap_event: CapabilityGapEvent,
        limit: int = 5,
    ) -> list[MCPServerInfo]:
        """Search registries to fill a detected capability gap.

        Translates a ``CapabilityGapEvent`` into a registry search.

        Args:
            gap_event: The gap event describing the missing tool.
            limit: Maximum number of results.

        Returns:
            List of discovered MCP servers that might fill the gap.
        """
        # Derive search query from the requested tool name
        # e.g. "slack_send_message" → "slack send message"
        search_query = gap_event.requested_tool.replace("_", " ")

        context = ""
        if gap_event.task_context:
            context = gap_event.task_context
        elif gap_event.requesting_agent:
            context = f"needed by {gap_event.requesting_agent} agent"

        return await self.search_for_capability(
            needed_capability=search_query,
            context=context,
            limit=limit,
        )
