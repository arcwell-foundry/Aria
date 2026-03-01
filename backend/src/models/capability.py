"""Pydantic models for ARIA's self-provisioning capability system.

Defines the data structures for capability providers, gaps, and resolution
strategies used by CapabilityGraphService, GapDetectionService, and
ProvisioningConversation.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class CapabilityProvider(BaseModel):
    """A concrete provider that can fulfill an abstract capability."""

    id: str
    capability_name: str
    capability_category: str
    provider_name: str
    provider_type: str  # native, composio_oauth, composio_api_key, composite, mcp_server, user_provided
    quality_score: float = Field(ge=0, le=1)
    setup_time_seconds: int = 0
    user_friction: str = "none"
    estimated_cost_per_use: float = 0
    composio_app_name: Optional[str] = None
    composio_action_name: Optional[str] = None
    required_capabilities: Optional[list[str]] = None
    domain_constraint: Optional[str] = None
    limitations: Optional[str] = None
    life_sciences_priority: bool = False
    is_active: bool = True
    health_status: str = "unknown"


class ResolutionStrategy(BaseModel):
    """A ranked strategy for filling a capability gap."""

    strategy_type: str  # direct_integration, composite, ecosystem_discovered, skill_created, user_provided, web_fallback
    provider_name: str
    quality: float = Field(ge=0, le=1)
    setup_time_seconds: int = 0
    user_friction: str = "none"
    estimated_cost_per_use: float = 0
    composio_app: Optional[str] = None
    description: str = ""
    action_label: str = ""
    auto_usable: bool = False
    ecosystem_source: Optional[str] = None
    ecosystem_data: Optional[dict[str, Any]] = None


class CapabilityGap(BaseModel):
    """A detected gap between what a goal step needs and what is available."""

    capability: str
    step: dict[str, Any]
    severity: str  # blocking, degraded
    current_provider: Optional[str] = None
    current_quality: float = 0
    can_proceed: bool = False
    auto_resolved: bool = False
    resolved_with: Optional[ResolutionStrategy] = None
    resolutions: list[ResolutionStrategy] = Field(default_factory=list)
