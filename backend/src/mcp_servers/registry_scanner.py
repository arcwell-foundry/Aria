"""MCP registry scanners — discover external MCP servers from public registries.

Supports Smithery, npm, and mcp.run registries via a unified interface.
``UnifiedRegistryScanner`` searches all registries in parallel and deduplicates
results by package name.
"""

from __future__ import annotations

import abc
import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from src.core.config import settings
from src.mcp_servers.models import MCPServerInfo, MCPToolInfo

logger = logging.getLogger(__name__)


class MCPRegistryScanner(abc.ABC):
    """Abstract base class for MCP registry scanners."""

    @abc.abstractmethod
    async def search(self, query: str, limit: int = 10) -> list[MCPServerInfo]:
        """Search the registry for MCP servers matching a query.

        Args:
            query: Search query string.
            limit: Maximum number of results.

        Returns:
            List of discovered MCP server metadata.
        """

    @abc.abstractmethod
    async def get_details(self, package_id: str) -> MCPServerInfo | None:
        """Get detailed information about a specific package.

        Args:
            package_id: Unique identifier within the registry.

        Returns:
            Server info if found, None otherwise.
        """

    @property
    @abc.abstractmethod
    def registry_name(self) -> str:
        """Human-readable name of this registry."""


class SmitheryScanner(MCPRegistryScanner):
    """Scanner for the Smithery MCP registry (registry.smithery.ai)."""

    @property
    def registry_name(self) -> str:
        return "smithery"

    async def search(self, query: str, limit: int = 10) -> list[MCPServerInfo]:
        """Search Smithery for MCP servers."""
        url = f"{settings.MCP_REGISTRY_SMITHERY_URL}/servers"
        params = {"q": query, "limit": limit}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

            servers = data.get("servers", data) if isinstance(data, dict) else data
            if not isinstance(servers, list):
                servers = []

            results: list[MCPServerInfo] = []
            for item in servers[:limit]:
                if not isinstance(item, dict):
                    continue
                tools = [
                    MCPToolInfo(
                        name=t.get("name", ""),
                        description=t.get("description", ""),
                        input_schema=t.get("inputSchema", {}),
                    )
                    for t in item.get("tools", [])
                    if isinstance(t, dict)
                ]
                results.append(
                    MCPServerInfo(
                        name=item.get("qualifiedName", item.get("name", "")),
                        display_name=item.get("displayName", item.get("name", "")),
                        publisher=item.get("vendor", item.get("author", "")),
                        version=item.get("version", ""),
                        description=item.get("description", ""),
                        transport=item.get("transport", "stdio"),
                        tools=tools,
                        permissions=item.get("security", {}),
                        download_count=item.get("useCount", 0),
                        last_updated=item.get("updatedAt", ""),
                        repo_url=item.get("homepage", ""),
                        registry_source="smithery",
                        registry_package_id=item.get("qualifiedName", item.get("name", "")),
                        is_open_source=bool(item.get("homepage", "")),
                        is_verified_publisher=item.get("verified", False),
                    )
                )
            return results

        except Exception:
            logger.warning("Smithery search failed for query '%s'", query, exc_info=True)
            return []

    async def get_details(self, package_id: str) -> MCPServerInfo | None:
        """Get details for a specific Smithery server."""
        url = f"{settings.MCP_REGISTRY_SMITHERY_URL}/servers/{package_id}"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                item = response.json()

            if not isinstance(item, dict):
                return None

            tools = [
                MCPToolInfo(
                    name=t.get("name", ""),
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema", {}),
                )
                for t in item.get("tools", [])
                if isinstance(t, dict)
            ]

            return MCPServerInfo(
                name=item.get("qualifiedName", item.get("name", "")),
                display_name=item.get("displayName", item.get("name", "")),
                publisher=item.get("vendor", item.get("author", "")),
                version=item.get("version", ""),
                description=item.get("description", ""),
                transport=item.get("transport", "stdio"),
                tools=tools,
                permissions=item.get("security", {}),
                download_count=item.get("useCount", 0),
                last_updated=item.get("updatedAt", ""),
                repo_url=item.get("homepage", ""),
                registry_source="smithery",
                registry_package_id=item.get("qualifiedName", item.get("name", "")),
                is_open_source=bool(item.get("homepage", "")),
                is_verified_publisher=item.get("verified", False),
            )

        except Exception:
            logger.warning("Smithery get_details failed for %s", package_id, exc_info=True)
            return None


class NpmMCPScanner(MCPRegistryScanner):
    """Scanner for npm packages tagged with ``mcp-server``."""

    @property
    def registry_name(self) -> str:
        return "npm"

    async def search(self, query: str, limit: int = 10) -> list[MCPServerInfo]:
        """Search npm for MCP server packages."""
        url = f"{settings.MCP_REGISTRY_NPMJS_URL}/-/v1/search"
        params = {"text": f"{query} keywords:mcp-server", "size": limit}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

            results: list[MCPServerInfo] = []
            for obj in data.get("objects", [])[:limit]:
                pkg = obj.get("package", {})
                name = pkg.get("name", "")
                publisher_info = pkg.get("publisher", {})
                repo_links = pkg.get("links", {})

                results.append(
                    MCPServerInfo(
                        name=name,
                        display_name=name,
                        publisher=publisher_info.get("username", ""),
                        version=pkg.get("version", ""),
                        description=pkg.get("description", ""),
                        transport="stdio",
                        download_count=obj.get("score", {})
                        .get("detail", {})
                        .get("popularity", 0),
                        last_updated=pkg.get("date", ""),
                        repo_url=repo_links.get("repository", ""),
                        registry_source="npm",
                        registry_package_id=name,
                        is_open_source=bool(repo_links.get("repository", "")),
                        is_verified_publisher=False,
                    )
                )
            return results

        except Exception:
            logger.warning("npm search failed for query '%s'", query, exc_info=True)
            return []

    async def get_details(self, package_id: str) -> MCPServerInfo | None:
        """Get npm package details."""
        url = f"{settings.MCP_REGISTRY_NPMJS_URL}/{package_id}"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()

            latest_version = data.get("dist-tags", {}).get("latest", "")
            latest_info = data.get("versions", {}).get(latest_version, {})
            repo = data.get("repository", {})
            repo_url = repo.get("url", "") if isinstance(repo, dict) else str(repo)

            return MCPServerInfo(
                name=data.get("name", package_id),
                display_name=data.get("name", package_id),
                publisher=data.get("author", {}).get("name", "")
                if isinstance(data.get("author"), dict)
                else str(data.get("author", "")),
                version=latest_version,
                description=data.get("description", ""),
                transport="stdio",
                last_updated=data.get("time", {}).get(latest_version, ""),
                repo_url=repo_url,
                registry_source="npm",
                registry_package_id=package_id,
                is_open_source=bool(repo_url),
                is_verified_publisher=False,
            )

        except Exception:
            logger.warning("npm get_details failed for %s", package_id, exc_info=True)
            return None


class MCPRunScanner(MCPRegistryScanner):
    """Scanner for the mcp.run registry."""

    @property
    def registry_name(self) -> str:
        return "mcp_run"

    async def search(self, query: str, limit: int = 10) -> list[MCPServerInfo]:
        """Search mcp.run for servers."""
        url = f"{settings.MCP_REGISTRY_MCP_RUN_URL}/api/servers"
        params = {"q": query, "limit": limit}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

            servers = data.get("servers", data) if isinstance(data, dict) else data
            if not isinstance(servers, list):
                servers = []

            results: list[MCPServerInfo] = []
            for item in servers[:limit]:
                if not isinstance(item, dict):
                    continue
                tools = [
                    MCPToolInfo(
                        name=t.get("name", ""),
                        description=t.get("description", ""),
                    )
                    for t in item.get("tools", [])
                    if isinstance(t, dict)
                ]
                results.append(
                    MCPServerInfo(
                        name=item.get("name", ""),
                        display_name=item.get("displayName", item.get("name", "")),
                        publisher=item.get("author", ""),
                        version=item.get("version", ""),
                        description=item.get("description", ""),
                        transport=item.get("transport", "sse"),
                        tools=tools,
                        download_count=item.get("installCount", 0),
                        last_updated=item.get("updatedAt", ""),
                        repo_url=item.get("sourceUrl", ""),
                        registry_source="mcp_run",
                        registry_package_id=item.get("id", item.get("name", "")),
                        is_open_source=bool(item.get("sourceUrl", "")),
                        is_verified_publisher=item.get("verified", False),
                    )
                )
            return results

        except Exception:
            logger.warning("mcp.run search failed for query '%s'", query, exc_info=True)
            return []

    async def get_details(self, package_id: str) -> MCPServerInfo | None:
        """Get mcp.run server details."""
        url = f"{settings.MCP_REGISTRY_MCP_RUN_URL}/api/servers/{package_id}"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                item = response.json()

            if not isinstance(item, dict):
                return None

            tools = [
                MCPToolInfo(
                    name=t.get("name", ""),
                    description=t.get("description", ""),
                )
                for t in item.get("tools", [])
                if isinstance(t, dict)
            ]

            return MCPServerInfo(
                name=item.get("name", ""),
                display_name=item.get("displayName", item.get("name", "")),
                publisher=item.get("author", ""),
                version=item.get("version", ""),
                description=item.get("description", ""),
                transport=item.get("transport", "sse"),
                tools=tools,
                download_count=item.get("installCount", 0),
                last_updated=item.get("updatedAt", ""),
                repo_url=item.get("sourceUrl", ""),
                registry_source="mcp_run",
                registry_package_id=item.get("id", item.get("name", "")),
                is_open_source=bool(item.get("sourceUrl", "")),
                is_verified_publisher=item.get("verified", False),
            )

        except Exception:
            logger.warning(
                "mcp.run get_details failed for %s", package_id, exc_info=True
            )
            return None


class UnifiedRegistryScanner:
    """Searches all MCP registries in parallel and deduplicates results.

    Usage::

        scanner = UnifiedRegistryScanner()
        results = await scanner.search("slack integration", limit=5)
    """

    def __init__(
        self,
        scanners: list[MCPRegistryScanner] | None = None,
    ) -> None:
        self._scanners = scanners or [
            SmitheryScanner(),
            NpmMCPScanner(),
            MCPRunScanner(),
        ]

    async def search(self, query: str, limit: int = 10) -> list[MCPServerInfo]:
        """Search all registries in parallel and return deduplicated results.

        Results are deduplicated by package name (first occurrence wins,
        prioritized by download count).

        Args:
            query: Search query string.
            limit: Maximum results to return.

        Returns:
            Deduplicated list of MCP server metadata, sorted by download count.
        """
        tasks = [scanner.search(query, limit=limit) for scanner in self._scanners]
        all_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Flatten and deduplicate
        seen_names: dict[str, MCPServerInfo] = {}
        for result in all_results:
            if isinstance(result, Exception):
                logger.warning("Registry search failed: %s", result)
                continue
            for server in result:
                key = server.name.lower()
                if key not in seen_names:
                    seen_names[key] = server
                else:
                    # Keep the one with more downloads
                    existing = seen_names[key]
                    if server.download_count > existing.download_count:
                        seen_names[key] = server

        # Sort by download count descending
        sorted_results = sorted(
            seen_names.values(), key=lambda s: s.download_count, reverse=True
        )
        return sorted_results[:limit]

    async def get_details(
        self, registry_source: str, package_id: str
    ) -> MCPServerInfo | None:
        """Get details from a specific registry.

        Args:
            registry_source: Registry name (smithery, npm, mcp_run).
            package_id: Package identifier within that registry.

        Returns:
            Server info if found, None otherwise.
        """
        for scanner in self._scanners:
            if scanner.registry_name == registry_source:
                return await scanner.get_details(package_id)
        logger.warning("Unknown registry source: %s", registry_source)
        return None
