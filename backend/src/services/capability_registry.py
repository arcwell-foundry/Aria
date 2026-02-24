"""Capability Registry — ARIA self-awareness service.

Discovers what ARIA can actually do at startup (agents, capabilities, skills,
API keys, MCP servers) and provides per-user live status (integrations,
recent usage, installed MCP).  The rendered output is injected into the
system prompt so ARIA never hallucinates about her own capabilities.
"""

from __future__ import annotations

import ast
import asyncio
import importlib
import inspect
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class AgentInfo:
    """Discovered agent metadata."""

    name: str
    description: str
    tools: list[str]
    module: str


@dataclass
class CapabilityInfo:
    """Discovered capability metadata."""

    capability_name: str
    agent_types: list[str]
    oauth_scopes: list[str]
    docstring: str | None
    module: str


@dataclass
class SkillDefinitionInfo:
    """Discovered skill definition metadata from YAML."""

    name: str
    description: str
    agent_assignment: str | None


@dataclass
class ApiKeyStatus:
    """Presence status for a configured API key."""

    key_name: str
    configured: bool
    enables: list[str]


@dataclass
class McpServerInfo:
    """Built-in MCP server status."""

    name: str
    path: str
    enabled: bool


@dataclass
class StaticSnapshot:
    """Everything discoverable from code and config at startup."""

    agents: list[AgentInfo] = field(default_factory=list)
    capabilities: list[CapabilityInfo] = field(default_factory=list)
    skill_definitions: list[SkillDefinitionInfo] = field(default_factory=list)
    api_keys: list[ApiKeyStatus] = field(default_factory=list)
    mcp_servers: list[McpServerInfo] = field(default_factory=list)
    scan_time_ms: int = 0


@dataclass
class IntegrationStatus:
    """User integration from the database."""

    integration_type: str
    display_name: str
    status: str
    sync_status: str | None
    last_sync_at: str | None
    last_sync_error: str | None


@dataclass
class LiveSnapshot:
    """Per-user live status from the database."""

    integrations: list[IntegrationStatus] = field(default_factory=list)
    agents_used_24h: list[str] = field(default_factory=list)
    activity_count_24h: int = 0
    recent_errors: list[str] = field(default_factory=list)
    installed_mcp_count: int = 0
    fetched_at: float = 0.0


@dataclass
class FullSnapshot:
    """Combined static + live snapshot."""

    static: StaticSnapshot
    live: LiveSnapshot


# ---------------------------------------------------------------------------
# Mapping: API key → what it enables
# ---------------------------------------------------------------------------

_API_KEY_MAP: dict[str, list[str]] = {
    "ANTHROPIC_API_KEY": ["all agents (LLM)"],
    "EXA_API_KEY": ["Hunter", "Scout", "Analyst web_research"],
    "COMPOSIO_API_KEY": ["Operator (CRM, calendar)"],
    "TAVUS_API_KEY": ["Video"],
    "DAILY_API_KEY": ["Video sessions"],
    "NEO4J_PASSWORD": ["Knowledge graph"],
    "OPENAI_API_KEY": ["Embeddings (Graphiti)"],
    "STRIPE_SECRET_KEY": ["Billing"],
    "RESEND_API_KEY": ["Transactional email"],
}

# Agent files to skip during import (not real agents)
_SKIP_AGENT_FILES = {
    "__init__",
    "base",
    "orchestrator",
    "dynamic_factory",
    "skill_aware_agent",
}

# ---------------------------------------------------------------------------
# Core service
# ---------------------------------------------------------------------------


class CapabilityRegistry:
    """Singleton registry that introspects ARIA's own capabilities."""

    def __init__(self) -> None:
        self._static: StaticSnapshot | None = None
        self._live_cache: dict[str, LiveSnapshot] = {}
        self._live_cache_ttl: float = 300.0  # 5 minutes

    # ------------------------------------------------------------------
    # A) Static scan — called once at startup
    # ------------------------------------------------------------------

    def scan_static(self) -> StaticSnapshot:
        """Discover everything introspectable from code and config.

        Returns the cached StaticSnapshot.
        """
        start = time.perf_counter()

        agents = self._discover_agents()
        capabilities = self._discover_capabilities()
        skill_defs = self._discover_skill_definitions()
        api_keys = self._check_api_keys()
        mcp_servers = self._discover_mcp_servers()

        elapsed_ms = int((time.perf_counter() - start) * 1000)

        self._static = StaticSnapshot(
            agents=agents,
            capabilities=capabilities,
            skill_definitions=skill_defs,
            api_keys=api_keys,
            mcp_servers=mcp_servers,
            scan_time_ms=elapsed_ms,
        )

        logger.info(
            "Capability registry static scan completed: "
            "%d agents, %d capabilities, %d skill definitions, %d API keys, %d MCP servers (%d ms)",
            len(agents),
            len(capabilities),
            len(skill_defs),
            sum(1 for k in api_keys if k.configured),
            len(mcp_servers),
            elapsed_ms,
        )

        return self._static

    def _discover_agents(self) -> list[AgentInfo]:
        """Import agent modules and extract name, description, tool names."""
        agents_dir = Path(__file__).resolve().parent.parent / "agents"
        results: list[AgentInfo] = []

        for py_file in sorted(agents_dir.glob("*.py")):
            stem = py_file.stem
            if stem in _SKIP_AGENT_FILES:
                continue

            module_name = f"src.agents.{stem}"
            try:
                mod = importlib.import_module(module_name)
            except Exception:
                logger.debug("Could not import agent module %s", module_name)
                continue

            # Find BaseAgent subclasses defined in this module
            from src.agents.base import BaseAgent

            for _attr_name, obj in inspect.getmembers(mod, inspect.isclass):
                if (
                    issubclass(obj, BaseAgent)
                    and obj is not BaseAgent
                    and obj.__module__ == mod.__name__
                ):
                    name = getattr(obj, "name", stem)
                    description = getattr(obj, "description", "")
                    tools = self._extract_tool_names(py_file)

                    results.append(
                        AgentInfo(
                            name=name,
                            description=description,
                            tools=tools,
                            module=module_name,
                        )
                    )

        return results

    @staticmethod
    def _extract_tool_names(py_file: Path) -> list[str]:
        """Parse _register_tools() via AST to get dict keys without instantiation."""
        try:
            source = py_file.read_text()
            tree = ast.parse(source)
        except Exception:
            return []

        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name != "_register_tools":
                continue

            # Find the return statement with a dict literal
            for child in ast.walk(node):
                if isinstance(child, ast.Return) and child.value is not None:
                    return_val = child.value
                    if isinstance(return_val, ast.Dict):
                        keys: list[str] = []
                        for key in return_val.keys:
                            if isinstance(key, ast.Constant) and isinstance(
                                key.value, str
                            ):
                                keys.append(key.value)
                        if keys:
                            return keys

        return []

    def _discover_capabilities(self) -> list[CapabilityInfo]:
        """Scan agents/capabilities/*.py for BaseCapability subclasses."""
        cap_dir = Path(__file__).resolve().parent.parent / "agents" / "capabilities"
        results: list[CapabilityInfo] = []

        for py_file in sorted(cap_dir.glob("*.py")):
            stem = py_file.stem
            if stem.startswith("_"):
                continue

            module_name = f"src.agents.capabilities.{stem}"
            try:
                mod = importlib.import_module(module_name)
            except Exception:
                logger.debug("Could not import capability module %s", module_name)
                continue

            from src.agents.capabilities.base import BaseCapability

            for _attr_name, obj in inspect.getmembers(mod, inspect.isclass):
                if (
                    issubclass(obj, BaseCapability)
                    and obj is not BaseCapability
                    and obj.__module__ == mod.__name__
                ):
                    results.append(
                        CapabilityInfo(
                            capability_name=getattr(obj, "capability_name", stem),
                            agent_types=list(getattr(obj, "agent_types", [])),
                            oauth_scopes=list(getattr(obj, "oauth_scopes", [])),
                            docstring=obj.__doc__,
                            module=module_name,
                        )
                    )

        return results

    def _discover_skill_definitions(self) -> list[SkillDefinitionInfo]:
        """Scan skills/definitions/*/skill.yaml for metadata."""
        defs_dir = Path(__file__).resolve().parent.parent / "skills" / "definitions"
        results: list[SkillDefinitionInfo] = []

        if not defs_dir.exists():
            return results

        for yaml_file in sorted(defs_dir.glob("*/skill.yaml")):
            try:
                data = yaml.safe_load(yaml_file.read_text())
                if not isinstance(data, dict):
                    continue
                results.append(
                    SkillDefinitionInfo(
                        name=data.get("name", yaml_file.parent.name),
                        description=data.get("description", ""),
                        agent_assignment=data.get("agent_assignment"),
                    )
                )
            except Exception:
                logger.debug("Could not parse %s", yaml_file)

        return results

    def _check_api_keys(self) -> list[ApiKeyStatus]:
        """Check config settings for API key presence."""
        try:
            from src.core.config import settings
        except Exception:
            return []

        results: list[ApiKeyStatus] = []
        for key_name, enables in _API_KEY_MAP.items():
            value = getattr(settings, key_name, None)
            # SecretStr → check get_secret_value(), plain str → bool()
            if value is None:
                configured = False
            elif hasattr(value, "get_secret_value"):
                configured = bool(value.get_secret_value())
            else:
                configured = bool(value)

            results.append(
                ApiKeyStatus(key_name=key_name, configured=configured, enables=enables)
            )

        return results

    def _discover_mcp_servers(self) -> list[McpServerInfo]:
        """Check config for built-in MCP servers."""
        try:
            from src.core.config import settings
        except Exception:
            return []

        global_enabled = getattr(settings, "MCP_SERVERS_ENABLED", True)

        servers: list[McpServerInfo] = []
        for attr, label in [
            ("MCP_LIFESCI_PATH", "Life Sciences"),
            ("MCP_EXA_PATH", "Exa Search"),
            ("MCP_BUSINESS_PATH", "Business"),
        ]:
            path = getattr(settings, attr, "")
            servers.append(
                McpServerInfo(
                    name=label,
                    path=path or "",
                    enabled=global_enabled and bool(path),
                )
            )

        return servers

    # ------------------------------------------------------------------
    # B) Live status — per user, 5-min cache
    # ------------------------------------------------------------------

    async def get_live_status(self, user_id: str) -> LiveSnapshot:
        """Fetch per-user live status from the database.

        Results are cached for 5 minutes.

        Args:
            user_id: Authenticated user UUID.

        Returns:
            LiveSnapshot with integration status, recent usage, and installed MCP.
        """
        cached = self._live_cache.get(user_id)
        if cached and (time.time() - cached.fetched_at) < self._live_cache_ttl:
            return cached

        integrations, usage, mcp_count = await asyncio.gather(
            self._fetch_integrations(user_id),
            self._fetch_recent_usage(user_id),
            self._fetch_installed_mcp(user_id),
            return_exceptions=True,
        )

        # Handle exceptions gracefully
        if isinstance(integrations, BaseException):
            logger.debug("Failed to fetch integrations: %s", integrations)
            integrations = []
        if isinstance(usage, BaseException):
            logger.debug("Failed to fetch recent usage: %s", usage)
            usage = ([], 0, [])
        if isinstance(mcp_count, BaseException):
            logger.debug("Failed to fetch installed MCP: %s", mcp_count)
            mcp_count = 0

        agents_used, activity_count, recent_errors = usage  # type: ignore[misc]

        snapshot = LiveSnapshot(
            integrations=integrations,  # type: ignore[arg-type]
            agents_used_24h=agents_used,
            activity_count_24h=activity_count,
            recent_errors=recent_errors,
            installed_mcp_count=mcp_count,  # type: ignore[arg-type]
            fetched_at=time.time(),
        )

        self._live_cache[user_id] = snapshot
        return snapshot

    async def _fetch_integrations(self, user_id: str) -> list[IntegrationStatus]:
        """Query user_integrations table."""
        try:
            from src.db.supabase import SupabaseClient

            client = SupabaseClient.get_client()
            resp = (
                client.table("user_integrations")
                .select(
                    "integration_type, display_name, status, sync_status, last_sync_at, last_sync_error"
                )
                .eq("user_id", user_id)
                .execute()
            )
            return [
                IntegrationStatus(
                    integration_type=row.get("integration_type", ""),
                    display_name=row.get("display_name", ""),
                    status=row.get("status", "unknown"),
                    sync_status=row.get("sync_status"),
                    last_sync_at=row.get("last_sync_at"),
                    last_sync_error=row.get("last_sync_error"),
                )
                for row in (resp.data or [])
            ]
        except Exception as e:
            logger.debug("user_integrations query failed: %s", e)
            return []

    async def _fetch_recent_usage(
        self, user_id: str
    ) -> tuple[list[str], int, list[str]]:
        """Query aria_activity for last 24h."""
        try:
            from datetime import datetime, timedelta, timezone

            from src.db.supabase import SupabaseClient

            client = SupabaseClient.get_client()
            since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

            resp = (
                client.table("aria_activity")
                .select("agent_name, activity_type, error_message")
                .eq("user_id", user_id)
                .gte("created_at", since)
                .order("created_at", desc=True)
                .limit(100)
                .execute()
            )
            rows = resp.data or []

            agents_used = sorted({r["agent_name"] for r in rows if r.get("agent_name")})
            activity_count = len(rows)
            recent_errors = [
                r["error_message"]
                for r in rows
                if r.get("error_message")
            ][:3]

            return agents_used, activity_count, recent_errors
        except Exception as e:
            logger.debug("aria_activity query failed: %s", e)
            return [], 0, []

    async def _fetch_installed_mcp(self, user_id: str) -> int:
        """Count user's installed external MCP servers."""
        try:
            from src.db.supabase import SupabaseClient

            client = SupabaseClient.get_client()
            resp = (
                client.table("installed_capabilities")
                .select("id", count="exact")
                .eq("user_id", user_id)
                .execute()
            )
            return resp.count or 0
        except Exception as e:
            logger.debug("installed_capabilities query failed: %s", e)
            return 0

    # ------------------------------------------------------------------
    # C) Full snapshot
    # ------------------------------------------------------------------

    async def get_full_snapshot(self, user_id: str) -> FullSnapshot:
        """Combine static and live snapshots.

        Args:
            user_id: Authenticated user UUID.

        Returns:
            FullSnapshot with both static and live data.
        """
        if self._static is None:
            self.scan_static()

        live = await self.get_live_status(user_id)
        return FullSnapshot(static=self._static, live=live)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # D) Render for cognitive context — injected into system prompt
    # ------------------------------------------------------------------

    def render_for_cognitive_context(self, snapshot: FullSnapshot) -> str:
        """Render factual-only text for system prompt injection.

        Target: <500 tokens (~2000 chars).

        Args:
            snapshot: Combined static + live snapshot.

        Returns:
            Plain text block suitable for system prompt.
        """
        parts: list[str] = []

        # Agents & tools
        parts.append("**Agents & Tools:**")
        for agent in snapshot.static.agents:
            tools_str = ", ".join(agent.tools) if agent.tools else "(no tools parsed)"
            parts.append(f"- {agent.name}: {tools_str}")

        # Connected integrations
        active = [
            i for i in snapshot.live.integrations if i.status == "active"
        ]
        inactive = [
            i for i in snapshot.live.integrations if i.status != "active"
        ]
        if active:
            items: list[str] = []
            for i in active:
                label = i.display_name or i.integration_type
                detail = f" (last sync {i.last_sync_at})" if i.last_sync_at else ""
                items.append(f"{label}{detail}")
            parts.append(f"\n**Connected Integrations:** {', '.join(items)}")
        if inactive:
            names = [i.display_name or i.integration_type for i in inactive]
            parts.append(f"**Not Connected:** {', '.join(names)}")

        # API keys
        configured = [k for k in snapshot.static.api_keys if k.configured]
        not_configured = [k for k in snapshot.static.api_keys if not k.configured]
        if configured:
            labels = []
            for k in configured:
                # Readable label from key name
                label = k.key_name.replace("_API_KEY", "").replace("_SECRET_KEY", "").replace("_PASSWORD", "").replace("_", " ").title()
                labels.append(label)
            parts.append(f"\n**External APIs:** {', '.join(labels)} (configured)")
        if not_configured:
            labels = []
            for k in not_configured:
                label = k.key_name.replace("_API_KEY", "").replace("_SECRET_KEY", "").replace("_PASSWORD", "").replace("_", " ").title()
                labels.append(label)
            parts.append(f"**Not Configured:** {', '.join(labels)}")

        # Skills & MCP
        cap_count = len(snapshot.static.capabilities)
        skill_count = len(snapshot.static.skill_definitions)
        builtin_mcp = len([s for s in snapshot.static.mcp_servers if s.enabled])
        user_mcp = snapshot.live.installed_mcp_count
        parts.append(
            f"\n**Skills:** {cap_count} native capabilities, {skill_count} skill definitions"
        )
        parts.append(
            f"**MCP Servers:** {builtin_mcp} built-in, {user_mcp} user-installed"
        )

        # 24h activity
        if snapshot.live.agents_used_24h:
            agents_str = ", ".join(snapshot.live.agents_used_24h)
            errors_str = (
                f"{len(snapshot.live.recent_errors)} error(s)"
                if snapshot.live.recent_errors
                else "No errors"
            )
            parts.append(
                f"\n**24h Activity:** {agents_str} active. "
                f"{snapshot.live.activity_count_24h} actions. {errors_str}."
            )

        text = "\n".join(parts)

        # Token budget check (~4 chars per token)
        estimated_tokens = len(text) // 4
        if estimated_tokens > 500:
            # Truncate skill details first
            text = self._truncate_to_budget(text)

        return text

    @staticmethod
    def _truncate_to_budget(text: str) -> str:
        """Truncate text to ~500 tokens if needed."""
        max_chars = 500 * 4  # ~2000 chars
        if len(text) <= max_chars:
            return text
        return text[:max_chars].rsplit("\n", 1)[0] + "\n..."

    # ------------------------------------------------------------------
    # E) Cache invalidation
    # ------------------------------------------------------------------

    def invalidate_user_cache(self, user_id: str) -> None:
        """Clear per-user live cache.

        Called after integration connect/disconnect.

        Args:
            user_id: User whose cache to clear.
        """
        self._live_cache.pop(user_id, None)

    # ------------------------------------------------------------------
    # Serialization helpers (for REST API)
    # ------------------------------------------------------------------

    def to_dict(self, snapshot: FullSnapshot) -> dict[str, Any]:
        """Serialize a FullSnapshot to a JSON-compatible dict.

        Args:
            snapshot: Combined snapshot.

        Returns:
            Dictionary representation.
        """
        return {
            "static": {
                "agents": [
                    {
                        "name": a.name,
                        "description": a.description,
                        "tools": a.tools,
                        "module": a.module,
                    }
                    for a in snapshot.static.agents
                ],
                "capabilities": [
                    {
                        "capability_name": c.capability_name,
                        "agent_types": c.agent_types,
                        "oauth_scopes": c.oauth_scopes,
                        "module": c.module,
                    }
                    for c in snapshot.static.capabilities
                ],
                "skill_definitions": [
                    {
                        "name": s.name,
                        "description": s.description,
                        "agent_assignment": s.agent_assignment,
                    }
                    for s in snapshot.static.skill_definitions
                ],
                "api_keys": [
                    {
                        "key_name": k.key_name,
                        "configured": k.configured,
                        "enables": k.enables,
                    }
                    for k in snapshot.static.api_keys
                ],
                "mcp_servers": [
                    {
                        "name": m.name,
                        "path": m.path,
                        "enabled": m.enabled,
                    }
                    for m in snapshot.static.mcp_servers
                ],
                "scan_time_ms": snapshot.static.scan_time_ms,
            },
            "live": {
                "integrations": [
                    {
                        "integration_type": i.integration_type,
                        "display_name": i.display_name,
                        "status": i.status,
                        "sync_status": i.sync_status,
                        "last_sync_at": i.last_sync_at,
                        "last_sync_error": i.last_sync_error,
                    }
                    for i in snapshot.live.integrations
                ],
                "agents_used_24h": snapshot.live.agents_used_24h,
                "activity_count_24h": snapshot.live.activity_count_24h,
                "recent_errors": snapshot.live.recent_errors,
                "installed_mcp_count": snapshot.live.installed_mcp_count,
            },
        }


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_registry: CapabilityRegistry | None = None


def get_capability_registry() -> CapabilityRegistry:
    """Return the singleton CapabilityRegistry instance."""
    global _registry
    if _registry is None:
        _registry = CapabilityRegistry()
    return _registry
