"""API routes for ARIA self-awareness capability registry.

Provides endpoints for querying ARIA's discovered capabilities (agents,
skills, integrations, API keys, MCP servers) and invalidating per-user
cache after integration changes.

Distinct from ``capabilities.py`` which manages MCP server installation.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from src.api.deps import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/aria/capabilities", tags=["aria-capabilities"])


@router.get("/snapshot")
async def get_capability_snapshot(current_user: CurrentUser) -> dict[str, Any]:
    """Return ARIA's full capability snapshot for this user.

    Combines static discovery (agents, skills, API keys) with per-user
    live status (integrations, recent usage, installed MCP servers).

    Returns the same structured data that ARIA sees internally — same
    truth for frontend UI and chat.
    """
    from src.services.capability_registry import get_capability_registry

    registry = get_capability_registry()
    snapshot = await registry.get_full_snapshot(current_user.id)
    return registry.to_dict(snapshot)


@router.post("/invalidate-cache")
async def invalidate_cache(current_user: CurrentUser) -> dict[str, str]:
    """Force refresh of per-user capability cache.

    Call after connecting or disconnecting an integration so ARIA
    immediately reflects the change.
    """
    from src.services.capability_registry import get_capability_registry

    registry = get_capability_registry()
    registry.invalidate_user_cache(current_user.id)
    return {"status": "cache_invalidated"}
