"""Data models for MCP tool discovery, evaluation, and installation.

Defines the core dataclasses used across the capability management pipeline:
registry discovery results, security assessments, installed capability records,
and gap detection events.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MCPToolInfo:
    """Metadata for a single tool exposed by an MCP server.

    Attributes:
        name: Tool name as registered in the MCP server.
        description: Human-readable description of the tool.
        input_schema: JSON Schema dict for the tool's parameters.
        dct_action: DCT action string for permission enforcement.
    """

    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    dct_action: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "dct_action": self.dct_action,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MCPToolInfo:
        """Deserialize from a dictionary."""
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            input_schema=data.get("input_schema", {}),
            dct_action=data.get("dct_action", ""),
        )


@dataclass
class MCPServerInfo:
    """Registry discovery result for an MCP server package.

    Populated by registry scanners when searching for capabilities.

    Attributes:
        name: Package/server name (e.g. ``"mcp-server-slack"``).
        display_name: Human-readable display name.
        publisher: Publisher name or organization.
        version: Latest version string.
        description: Package description.
        transport: Connection transport type (``"stdio"`` or ``"sse"``).
        tools: List of tools this server exposes.
        permissions: Declared permission requirements.
        download_count: Total downloads (for popularity scoring).
        last_updated: When the package was last published.
        repo_url: Source repository URL (empty if closed-source).
        registry_source: Which registry this came from.
        registry_package_id: Unique identifier within the registry.
        is_open_source: Whether source code is publicly available.
        is_verified_publisher: Whether the publisher is verified.
    """

    name: str
    display_name: str = ""
    publisher: str = ""
    version: str = ""
    description: str = ""
    transport: str = "stdio"
    tools: list[MCPToolInfo] = field(default_factory=list)
    permissions: dict[str, Any] = field(default_factory=dict)
    download_count: int = 0
    last_updated: str = ""
    repo_url: str = ""
    registry_source: str = "unknown"
    registry_package_id: str = ""
    is_open_source: bool = False
    is_verified_publisher: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "publisher": self.publisher,
            "version": self.version,
            "description": self.description,
            "transport": self.transport,
            "tools": [t.to_dict() for t in self.tools],
            "permissions": self.permissions,
            "download_count": self.download_count,
            "last_updated": self.last_updated,
            "repo_url": self.repo_url,
            "registry_source": self.registry_source,
            "registry_package_id": self.registry_package_id,
            "is_open_source": self.is_open_source,
            "is_verified_publisher": self.is_verified_publisher,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MCPServerInfo:
        """Deserialize from a dictionary."""
        tools_data = data.get("tools", [])
        tools = [MCPToolInfo.from_dict(t) if isinstance(t, dict) else t for t in tools_data]
        return cls(
            name=data.get("name", ""),
            display_name=data.get("display_name", ""),
            publisher=data.get("publisher", ""),
            version=data.get("version", ""),
            description=data.get("description", ""),
            transport=data.get("transport", "stdio"),
            tools=tools,
            permissions=data.get("permissions", {}),
            download_count=data.get("download_count", 0),
            last_updated=data.get("last_updated", ""),
            repo_url=data.get("repo_url", ""),
            registry_source=data.get("registry_source", "unknown"),
            registry_package_id=data.get("registry_package_id", ""),
            is_open_source=data.get("is_open_source", False),
            is_verified_publisher=data.get("is_verified_publisher", False),
        )


@dataclass
class SecurityAssessment:
    """Result of an Analyst evaluation of an MCP server's security posture.

    Attributes:
        overall_risk: Risk level (``"low"``, ``"medium"``, ``"high"``, ``"critical"``).
        publisher_verified: Whether the publisher identity is verified.
        open_source: Whether the source code is publicly auditable.
        data_access_scope: Summary of data access requirements.
        recommendation: Overall recommendation (``"recommend"``, ``"caution"``, ``"reject"``).
        reasoning: Human-readable explanation of the assessment.
        freshness_days: Days since the package was last updated.
        adoption_score: Popularity/adoption score (0.0–1.0).
    """

    overall_risk: str = "medium"
    publisher_verified: bool = False
    open_source: bool = False
    data_access_scope: str = ""
    recommendation: str = "caution"
    reasoning: str = ""
    freshness_days: int = 0
    adoption_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary."""
        return {
            "overall_risk": self.overall_risk,
            "publisher_verified": self.publisher_verified,
            "open_source": self.open_source,
            "data_access_scope": self.data_access_scope,
            "recommendation": self.recommendation,
            "reasoning": self.reasoning,
            "freshness_days": self.freshness_days,
            "adoption_score": self.adoption_score,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SecurityAssessment:
        """Deserialize from a dictionary."""
        return cls(
            overall_risk=data.get("overall_risk", "medium"),
            publisher_verified=data.get("publisher_verified", False),
            open_source=data.get("open_source", False),
            data_access_scope=data.get("data_access_scope", ""),
            recommendation=data.get("recommendation", "caution"),
            reasoning=data.get("reasoning", ""),
            freshness_days=data.get("freshness_days", 0),
            adoption_score=data.get("adoption_score", 0.0),
        )


@dataclass
class InstalledCapability:
    """A user-installed external MCP server capability.

    Mirrors the ``installed_capabilities`` database table.
    """

    id: str
    user_id: str
    server_name: str
    server_display_name: str = ""
    registry_source: str = "unknown"
    registry_package_id: str = ""
    transport: str = "stdio"
    connection_config: dict[str, Any] = field(default_factory=dict)
    declared_tools: list[dict[str, Any]] = field(default_factory=list)
    declared_permissions: dict[str, Any] = field(default_factory=dict)
    security_assessment: dict[str, Any] = field(default_factory=dict)
    reliability_score: float = 0.5
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    last_used_at: datetime | None = None
    last_health_check_at: datetime | None = None
    health_status: str = "unknown"
    is_enabled: bool = True
    installed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "server_name": self.server_name,
            "server_display_name": self.server_display_name,
            "registry_source": self.registry_source,
            "registry_package_id": self.registry_package_id,
            "transport": self.transport,
            "connection_config": self.connection_config,
            "declared_tools": self.declared_tools,
            "declared_permissions": self.declared_permissions,
            "security_assessment": self.security_assessment,
            "reliability_score": self.reliability_score,
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "last_health_check_at": (
                self.last_health_check_at.isoformat() if self.last_health_check_at else None
            ),
            "health_status": self.health_status,
            "is_enabled": self.is_enabled,
            "installed_at": self.installed_at.isoformat() if self.installed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass
class CapabilityGapEvent:
    """Emitted when a requested tool is not found in any tool map.

    The OODA loop can pick this up asynchronously to trigger capability
    discovery via the Scout and Analyst agents.
    """

    user_id: str
    requested_tool: str
    requesting_agent: str = ""
    task_context: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary."""
        return {
            "user_id": self.user_id,
            "requested_tool": self.requested_tool,
            "requesting_agent": self.requesting_agent,
            "task_context": self.task_context,
            "timestamp": self.timestamp,
        }
