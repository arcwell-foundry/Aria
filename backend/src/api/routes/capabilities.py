"""API routes for MCP capability management.

Provides endpoints for searching, evaluating, installing, and managing
external MCP server capabilities.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/capabilities", tags=["capabilities"])


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------


class CapabilitySearchRequest(BaseModel):
    """Request body for searching MCP registries."""

    query: str = Field(..., description="Capability search query", min_length=1)
    context: str = Field("", description="Optional context about the need")
    limit: int = Field(5, ge=1, le=20, description="Max results")


class CapabilityEvaluateRequest(BaseModel):
    """Request body for evaluating an MCP server."""

    server_info: dict[str, Any] = Field(
        ..., description="Server metadata dict from registry search"
    )


class CapabilityInstallRequest(BaseModel):
    """Request body for installing an MCP server."""

    server_info: dict[str, Any] = Field(
        ..., description="Server metadata dict from registry search"
    )
    security_assessment: dict[str, Any] = Field(
        ..., description="Security assessment dict from evaluation"
    )
    connection_config: dict[str, Any] | None = Field(
        None, description="Optional override for connection config"
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("")
async def list_capabilities(current_user: CurrentUser) -> dict[str, Any]:
    """List all installed capabilities for the current user.

    Returns:
        Dict with ``capabilities`` list.
    """
    from src.mcp_servers.capability_store import CapabilityStore

    store = CapabilityStore()
    capabilities = await store.list_user_capabilities(str(current_user.id))
    return {
        "capabilities": [cap.to_dict() for cap in capabilities],
        "count": len(capabilities),
    }


@router.get("/unused")
async def get_unused_capabilities(
    current_user: CurrentUser, days: int = 30
) -> dict[str, Any]:
    """Get capabilities that haven't been used recently.

    Args:
        days: Number of days without usage to consider stale (default 30).

    Returns:
        Dict with ``unused`` capabilities list.
    """
    from src.mcp_servers.capability_store import CapabilityStore

    store = CapabilityStore()
    unused = await store.get_unused_capabilities(str(current_user.id), days_unused=days)
    return {
        "unused": [cap.to_dict() for cap in unused],
        "count": len(unused),
        "days_threshold": days,
    }


@router.get("/{server_name}")
async def get_capability(
    server_name: str, current_user: CurrentUser
) -> dict[str, Any]:
    """Get details of a specific installed capability.

    Args:
        server_name: The server identifier.

    Returns:
        Capability details dict.
    """
    from src.mcp_servers.capability_store import CapabilityStore

    store = CapabilityStore()
    capability = await store.get_by_server_name(str(current_user.id), server_name)
    if capability is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Capability '{server_name}' not found",
        )
    return capability.to_dict()


@router.post("/search")
async def search_capabilities(
    request: CapabilitySearchRequest, current_user: CurrentUser
) -> dict[str, Any]:
    """Search MCP registries for available servers.

    Searches Smithery, npm, and mcp.run in parallel.

    Returns:
        Dict with ``results`` list of server metadata.
    """
    from src.mcp_servers.capability_manager import MCPCapabilityManager

    manager = MCPCapabilityManager()
    recommendations = await manager.discover_and_evaluate(
        user_id=str(current_user.id),
        needed_capability=request.query,
        context=request.context,
        limit=request.limit,
    )

    results = [
        manager.present_recommendation(str(current_user.id), server, assessment)
        for server, assessment in recommendations
    ]

    return {
        "query": request.query,
        "results": results,
        "count": len(results),
    }


@router.post("/evaluate")
async def evaluate_capability(
    request: CapabilityEvaluateRequest, current_user: CurrentUser
) -> dict[str, Any]:
    """Evaluate an MCP server's security and reliability.

    Returns:
        Security assessment dict.
    """
    from src.agents.capabilities.mcp_evaluator import MCPEvaluatorCapability
    from src.mcp_servers.models import MCPServerInfo

    server_info = MCPServerInfo.from_dict(request.server_info)
    evaluator = MCPEvaluatorCapability()
    assessment = await evaluator.evaluate(server_info)
    return assessment.to_dict()


@router.post("/install")
async def install_capability(
    request: CapabilityInstallRequest, current_user: CurrentUser
) -> dict[str, Any]:
    """Install an MCP server capability.

    Requires prior user approval (the frontend should present the
    evaluation results before calling this endpoint).

    Returns:
        Installed capability details dict.
    """
    from src.mcp_servers.capability_manager import MCPCapabilityManager
    from src.mcp_servers.models import MCPServerInfo, SecurityAssessment

    server_info = MCPServerInfo.from_dict(request.server_info)
    assessment = SecurityAssessment.from_dict(request.security_assessment)

    # Reject critical-risk servers
    if assessment.overall_risk == "critical":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot install servers with critical security risk",
        )

    manager = MCPCapabilityManager()
    try:
        capability = await manager.install(
            user_id=str(current_user.id),
            server_info=server_info,
            assessment=assessment,
            connection_config=request.connection_config,
        )
        return {
            "installed": True,
            "capability": capability.to_dict(),
        }
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.delete("/{server_name}")
async def uninstall_capability(
    server_name: str, current_user: CurrentUser
) -> dict[str, Any]:
    """Uninstall an MCP server capability.

    Removes the DB record, closes the connection, and unregisters tools.

    Args:
        server_name: The server identifier to uninstall.

    Returns:
        Confirmation dict.
    """
    from src.mcp_servers.capability_manager import MCPCapabilityManager

    manager = MCPCapabilityManager()
    deleted = await manager.uninstall(str(current_user.id), server_name)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Capability '{server_name}' not found",
        )
    return {"uninstalled": True, "server_name": server_name}


@router.post("/{server_name}/health")
async def check_capability_health(
    server_name: str, current_user: CurrentUser
) -> dict[str, Any]:
    """Run a health check on a specific installed capability.

    Args:
        server_name: The server identifier to check.

    Returns:
        Dict with health status.
    """
    from src.mcp_servers.capability_store import CapabilityStore
    from src.mcp_servers.connection_pool import ExternalConnectionPool

    user_id = str(current_user.id)

    # Get capability from DB
    store = CapabilityStore()
    capability = await store.get_by_server_name(user_id, server_name)
    if capability is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Capability '{server_name}' not found",
        )

    # Get or create connection and check health
    pool = ExternalConnectionPool.instance()
    try:
        conn = await pool.get_connection(
            user_id=user_id,
            server_name=server_name,
            transport=capability.transport,
            connection_config=capability.connection_config,
        )
        health = await conn.health_check()
    except Exception as exc:
        health = "unhealthy"
        logger.warning("Health check failed for %s: %s", server_name, exc)

    # Update DB
    await store.update_health(user_id, server_name, health)

    return {
        "server_name": server_name,
        "health_status": health,
    }
