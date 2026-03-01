"""Ecosystem search service — discovers tools from Composio, MCP Registry, Smithery.

When ARIA hits a capability gap, this service searches external tool ecosystems
for solutions. Results are cached for 7 days and filtered by tenant whitelist.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.models.capability import EcosystemResult

logger = logging.getLogger(__name__)

# Static mapping of capabilities → known Composio apps (fallback when SDK unavailable)
_COMPOSIO_CAPABILITY_MAP: dict[str, list[dict[str, str]]] = {
    "read_crm_pipeline": [
        {"name": "Salesforce", "app": "SALESFORCE", "description": "CRM pipeline data"},
        {"name": "HubSpot", "app": "HUBSPOT", "description": "CRM pipeline data"},
        {"name": "Pipedrive", "app": "PIPEDRIVE", "description": "CRM pipeline data"},
    ],
    "read_email": [
        {"name": "Outlook", "app": "OUTLOOK365", "description": "Email access via Microsoft"},
        {"name": "Gmail", "app": "GMAIL", "description": "Email access via Google"},
    ],
    "read_calendar": [
        {"name": "Google Calendar", "app": "GOOGLE_CALENDAR", "description": "Calendar events"},
        {"name": "Outlook Calendar", "app": "OUTLOOK365", "description": "Calendar events"},
    ],
    "send_email": [
        {"name": "Outlook", "app": "OUTLOOK365", "description": "Send emails"},
        {"name": "Gmail", "app": "GMAIL", "description": "Send emails"},
    ],
    "monitor_competitor": [
        {"name": "Google Alerts", "app": "GOOGLE_ALERTS", "description": "Competitor monitoring"},
        {"name": "Mention", "app": "MENTION", "description": "Brand monitoring"},
    ],
    "track_patents": [
        {"name": "Google Patents", "app": "GOOGLE_PATENTS", "description": "Patent search"},
    ],
    "manage_tasks": [
        {"name": "Asana", "app": "ASANA", "description": "Task management"},
        {"name": "Linear", "app": "LINEAR", "description": "Project management"},
    ],
}


class EcosystemSearchService:
    """Searches external ecosystems for tools/skills when ARIA hits a capability gap.

    Search priority:
    1. Composio Tool Router (managed, production-grade, OAuth handled)
    2. MCP Registry (official, standardized)
    3. Smithery (broad community catalog)

    Results are cached for 7 days. Tenant whitelist is enforced.
    """

    def __init__(
        self,
        db_client: Any,
        tenant_config: Any = None,
    ) -> None:
        self._db = db_client
        self._tenant_config = tenant_config

    async def search_for_capability(
        self,
        capability_name: str,
        description: str,
        user_id: str,
    ) -> list[EcosystemResult]:
        """Search all allowed ecosystems for tools matching a capability need."""
        allowed_sources = (
            getattr(self._tenant_config, "allowed_ecosystem_sources", None)
            or ["composio"]
        )

        # Check cache first
        cached = await self._get_cached_results(capability_name)
        if cached:
            return [r for r in cached if r.source in allowed_sources]

        results: list[EcosystemResult] = []

        if "composio" in allowed_sources:
            results.extend(await self._search_composio(capability_name, description))

        if "mcp_registry" in allowed_sources:
            results.extend(await self._search_mcp_registry(capability_name, description))

        if "smithery" in allowed_sources:
            results.extend(await self._search_smithery(capability_name, description))

        # Cache results (best-effort)
        await self._cache_results(capability_name, results)

        return results

    async def _search_composio(
        self, capability_name: str, description: str
    ) -> list[EcosystemResult]:
        """Search Composio for managed toolkits. Falls back to static mapping."""
        try:
            try:
                from composio import ComposioToolSet

                toolset = ComposioToolSet()
                actions = toolset.find_actions_by_use_case(
                    use_case=description, limit=5
                )
                return [
                    EcosystemResult(
                        name=action.name,
                        source="composio",
                        description=getattr(action, "description", ""),
                        app=getattr(action, "app", None),
                        quality_estimate=0.85,
                        auth_type="oauth",
                        setup_time=30,
                    )
                    for action in actions
                ]
            except (ImportError, Exception):
                logger.info("Composio SDK unavailable, using static mapping")
                return self._static_composio_search(capability_name)
        except Exception:
            logger.warning("Composio search failed", exc_info=True)
            return []

    async def _search_mcp_registry(
        self, capability_name: str, description: str
    ) -> list[EcosystemResult]:
        """Search the official MCP Registry for community MCP servers."""
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    "https://registry.modelcontextprotocol.io/v0/servers",
                    params={"q": description, "limit": 5},
                )
                if response.status_code == 200:
                    servers = response.json().get("servers", [])
                    return [
                        EcosystemResult(
                            name=s.get("name", "Unknown"),
                            source="mcp_registry",
                            description=s.get("description", ""),
                            url=s.get("url", ""),
                            author=s.get("author", ""),
                            quality_estimate=0.70,
                            auth_type="varies",
                            setup_time=120,
                            last_updated=s.get("updated_at"),
                        )
                        for s in servers[:5]
                    ]
            return []
        except Exception:
            logger.warning("MCP Registry search failed", exc_info=True)
            return []

    async def _search_smithery(
        self, capability_name: str, description: str
    ) -> list[EcosystemResult]:
        """Search Smithery for MCP servers."""
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    "https://registry.smithery.ai/servers",
                    params={"q": description, "pageSize": 5},
                )
                if response.status_code == 200:
                    data = response.json()
                    servers = data.get("servers", data.get("results", []))
                    return [
                        EcosystemResult(
                            name=s.get("displayName", s.get("qualifiedName", "Unknown")),
                            source="smithery",
                            description=s.get("description", ""),
                            qualified_name=s.get("qualifiedName", ""),
                            quality_estimate=0.65,
                            auth_type="varies",
                            setup_time=180,
                            stars=s.get("stars", 0),
                        )
                        for s in servers[:5]
                    ]
            return []
        except Exception:
            logger.warning("Smithery search failed", exc_info=True)
            return []

    def _static_composio_search(self, capability_name: str) -> list[EcosystemResult]:
        """Static fallback mapping of capabilities to known Composio apps."""
        entries = _COMPOSIO_CAPABILITY_MAP.get(capability_name, [])
        return [
            EcosystemResult(
                name=e["name"],
                source="composio",
                description=e["description"],
                app=e.get("app"),
                quality_estimate=0.85,
                auth_type="oauth",
                setup_time=30,
            )
            for e in entries
        ]

    async def _get_cached_results(
        self, capability_name: str
    ) -> list[EcosystemResult] | None:
        """Check cache for recent results."""
        try:
            result = (
                self._db.table("ecosystem_search_cache")
                .select("*")
                .eq("capability_name", capability_name)
                .gt("expires_at", datetime.now(timezone.utc).isoformat())
                .execute()
            )
            if result.data:
                all_results: list[EcosystemResult] = []
                for row in result.data:
                    for r in row.get("results") or []:
                        r["source"] = row["search_source"]
                        all_results.append(EcosystemResult(**r))
                return all_results
        except Exception:
            logger.warning("Failed to check ecosystem cache", exc_info=True)
        return None

    async def _cache_results(
        self, capability_name: str, results: list[EcosystemResult]
    ) -> None:
        """Cache search results for 7 days."""
        try:
            for source in {r.source for r in results}:
                source_results = [
                    r.model_dump() for r in results if r.source == source
                ]
                self._db.table("ecosystem_search_cache").upsert({
                    "capability_name": capability_name,
                    "search_source": source,
                    "search_query": capability_name,
                    "results": source_results,
                    "result_count": len(source_results),
                }).execute()
        except Exception:
            logger.warning("Failed to cache ecosystem results", exc_info=True)
