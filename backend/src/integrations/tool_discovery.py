"""Composio tool discovery for goal planning.

Wraps the Composio SDK's tool search API to discover relevant integration
tools during plan_goal(). Results are cached for 15 minutes and the module
degrades gracefully when Composio is unavailable.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from src.core.cache import cached
from src.core.config import settings
from src.core.resilience import composio_circuit_breaker

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ComposioToolInfo:
    """Metadata for a single Composio tool/action."""

    slug: str  # e.g. "SALESFORCE_GET_CONTACTS"
    name: str  # e.g. "Get Contacts"
    description: str
    toolkit_slug: str  # e.g. "salesforce"
    toolkit_name: str  # e.g. "Salesforce"
    requires_auth: bool


class ComposioToolDiscovery:
    """Discovers Composio integration tools for goal planning.

    Uses the same lazy-init + asyncio.to_thread pattern as oauth.py.
    All SDK calls go through the composio_circuit_breaker.
    """

    _composio: Any = None

    @property
    def _client(self) -> Any:
        """Lazy initialization of Composio SDK client."""
        if self._composio is None:
            from composio import Composio

            api_key = (
                settings.COMPOSIO_API_KEY.get_secret_value()
                if settings.COMPOSIO_API_KEY is not None
                else ""
            )
            self._composio = Composio(api_key=api_key)
        return self._composio

    def _parse_tool(self, raw: Any) -> ComposioToolInfo | None:
        """Parse a raw Composio tool object into ComposioToolInfo.

        The SDK returns objects with varying attribute names depending on
        version. We try common patterns and skip tools we can't parse.
        """
        try:
            # The SDK tool objects expose attributes directly
            slug = getattr(raw, "slug", None) or getattr(raw, "name", None) or ""
            if not slug:
                # Dict-like response
                if isinstance(raw, dict):
                    slug = raw.get("slug", "") or raw.get("name", "")
                if not slug:
                    return None

            # Extract display name
            display_name = getattr(raw, "display_name", None) or getattr(
                raw, "displayName", None
            )
            if not display_name:
                if isinstance(raw, dict):
                    display_name = raw.get("display_name") or raw.get("displayName")
                if not display_name:
                    # Derive from slug: SALESFORCE_GET_CONTACTS -> Get Contacts
                    parts = str(slug).split("_")
                    # Drop the first part (toolkit prefix) if there are enough parts
                    name_parts = parts[1:] if len(parts) > 1 else parts
                    display_name = " ".join(p.capitalize() for p in name_parts)

            # Extract description
            description = getattr(raw, "description", "") or ""
            if not description and isinstance(raw, dict):
                description = raw.get("description", "")

            # Extract toolkit info
            toolkit_slug = ""
            toolkit_name = ""

            app_info = getattr(raw, "appName", None) or getattr(raw, "app_name", None)
            if app_info:
                toolkit_slug = str(app_info).lower()
                toolkit_name = str(app_info)
            elif isinstance(raw, dict):
                app_info = raw.get("appName") or raw.get("app_name", "")
                toolkit_slug = str(app_info).lower()
                toolkit_name = str(app_info)

            if not toolkit_slug:
                # Derive from slug prefix: SALESFORCE_GET_CONTACTS -> salesforce
                toolkit_slug = str(slug).split("_")[0].lower()
                toolkit_name = toolkit_slug.capitalize()

            requires_auth = True  # Composio tools generally require OAuth

            return ComposioToolInfo(
                slug=str(slug),
                name=str(display_name),
                description=str(description)[:200],  # Cap description length
                toolkit_slug=toolkit_slug,
                toolkit_name=toolkit_name,
                requires_auth=requires_auth,
            )
        except Exception as e:
            logger.debug("Failed to parse Composio tool: %s", e)
            return None

    async def _fetch_toolkit_tools(
        self, toolkit_slugs: list[str], limit: int = 30
    ) -> list[Any]:
        """Fetch tools for connected toolkits."""
        if not toolkit_slugs:
            return []

        client = self._client

        def _fetch() -> list[Any]:
            composio_circuit_breaker.check()
            try:
                result = client.tools.get_raw_composio_tools(
                    toolkits=toolkit_slugs, limit=limit
                )
                composio_circuit_breaker.record_success()
                return list(result) if result else []
            except Exception:
                composio_circuit_breaker.record_failure()
                raise

        return await asyncio.to_thread(_fetch)

    async def _fetch_search_tools(
        self, query: str, limit: int = 15
    ) -> list[Any]:
        """Search for tools matching a query."""
        if not query:
            return []

        client = self._client

        def _fetch() -> list[Any]:
            composio_circuit_breaker.check()
            try:
                result = client.tools.get_raw_composio_tools(
                    search=query, limit=limit
                )
                composio_circuit_breaker.record_success()
                return list(result) if result else []
            except Exception:
                composio_circuit_breaker.record_failure()
                raise

        return await asyncio.to_thread(_fetch)

    @cached(
        ttl=900,
        key_func=lambda *args, **kwargs: (
            f"tool_discovery:"
            f"{','.join(sorted(kwargs.get('connected_toolkit_slugs', args[3] if len(args) > 3 else [])))}:"
            f"{(kwargs.get('goal_title', args[1] if len(args) > 1 else ''))[:50]}"
        ),
    )
    async def discover_tools_for_goal(
        self,
        goal_title: str,
        goal_description: str,
        connected_toolkit_slugs: list[str],
    ) -> list[ComposioToolInfo]:
        """Discover relevant Composio tools for a goal.

        1. Fetches tools for user's connected integrations (toolkit-based).
        2. Searches for tools matching goal keywords (broader discovery).
        3. Deduplicates by slug and returns parsed ComposioToolInfo list.

        On any error, returns an empty list (never blocks planning).

        Args:
            goal_title: The goal title for keyword search.
            goal_description: The goal description for keyword search.
            connected_toolkit_slugs: Composio toolkit slugs the user has connected.

        Returns:
            List of ComposioToolInfo for discovered tools.
        """
        try:
            # Build search query from goal
            search_query = f"{goal_title} {goal_description}".strip()[:100]

            # Run both fetches concurrently
            toolkit_raw, search_raw = await asyncio.gather(
                self._fetch_toolkit_tools(connected_toolkit_slugs),
                self._fetch_search_tools(search_query),
                return_exceptions=True,
            )

            # Handle exceptions from gather
            if isinstance(toolkit_raw, BaseException):
                logger.warning("Toolkit tool fetch failed: %s", toolkit_raw)
                toolkit_raw = []
            if isinstance(search_raw, BaseException):
                logger.warning("Search tool fetch failed: %s", search_raw)
                search_raw = []

            # Deduplicate by slug
            seen_slugs: set[str] = set()
            tools: list[ComposioToolInfo] = []

            for raw in [*toolkit_raw, *search_raw]:
                parsed = self._parse_tool(raw)
                if parsed and parsed.slug not in seen_slugs:
                    seen_slugs.add(parsed.slug)
                    tools.append(parsed)

            logger.info(
                "Discovered %d Composio tools for goal '%s' (%d connected toolkits)",
                len(tools),
                goal_title[:40],
                len(connected_toolkit_slugs),
            )
            return tools

        except Exception as e:
            logger.warning(
                "Composio tool discovery failed, returning empty: %s", e
            )
            return []


# Module-level singleton
_discovery_instance: ComposioToolDiscovery | None = None


def get_tool_discovery() -> ComposioToolDiscovery:
    """Get or create the module-level ComposioToolDiscovery singleton."""
    global _discovery_instance
    if _discovery_instance is None:
        _discovery_instance = ComposioToolDiscovery()
    return _discovery_instance
