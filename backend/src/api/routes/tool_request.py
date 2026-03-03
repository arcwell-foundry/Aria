"""User Tool Request API.

Endpoints for users to request access to toolkits not yet approved
by their organization's admin.

Routes:
- POST /tools/request  — submit a request
- GET  /tools/requests — view own requests
"""

import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from src.api.deps import CurrentUser
from src.db.supabase import get_supabase_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tools", tags=["tools"])


class ToolRequestCreate(BaseModel):
    toolkit_slug: str
    toolkit_display_name: str = ""
    reason: str = ""


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

async def _get_user_tenant_id(user_id: str) -> str:
    db = get_supabase_client()
    result = (
        db.table("user_profiles")
        .select("company_id")
        .eq("id", user_id)
        .limit(1)
        .execute()
    )
    record = result.data[0] if result and result.data else None
    return record.get("company_id", "") if record else ""


async def _is_toolkit_approved(tenant_id: str, toolkit_slug: str) -> bool:
    if not tenant_id:
        return False
    db = get_supabase_client()
    result = (
        db.table("tenant_toolkit_config")
        .select("status")
        .eq("tenant_id", tenant_id)
        .eq("toolkit_slug", toolkit_slug.upper())
        .eq("status", "approved")
        .limit(1)
        .execute()
    )
    record = result.data[0] if result and result.data else None
    return record is not None


async def _has_pending_request(user_id: str, toolkit_slug: str) -> bool:
    db = get_supabase_client()
    result = (
        db.table("toolkit_access_requests")
        .select("id")
        .eq("user_id", user_id)
        .eq("toolkit_slug", toolkit_slug.upper())
        .eq("status", "pending")
        .limit(1)
        .execute()
    )
    record = result.data[0] if result and result.data else None
    return record is not None


async def _create_request(user_id: str, tenant_id: str, body: ToolRequestCreate) -> dict[str, Any]:
    db = get_supabase_client()
    result = (
        db.table("toolkit_access_requests")
        .insert({
            "user_id": user_id,
            "tenant_id": tenant_id,
            "toolkit_slug": body.toolkit_slug.upper(),
            "toolkit_display_name": body.toolkit_display_name or body.toolkit_slug,
            "reason": body.reason,
            "status": "pending",
            "discovered_via": "user_request",
        })
        .execute()
    )
    return result.data[0] if result.data else {}


async def _notify_admins(tenant_id: str, toolkit_slug: str, display_name: str) -> None:
    """Notify all admins in the tenant via WebSocket."""
    db = get_supabase_client()
    admins = (
        db.table("user_profiles")
        .select("id")
        .eq("company_id", tenant_id)
        .eq("role", "admin")
        .execute()
    )
    try:
        from src.core.ws import ws_manager
        for admin in (admins.data or []):
            await ws_manager.send_to_user(admin["id"], {
                "type": "toolkit_access_request",
                "toolkit_slug": toolkit_slug,
                "message": f"New tool request: {display_name or toolkit_slug}",
            })
    except Exception:
        logger.warning("Failed to notify admins about tool request for %s", toolkit_slug)


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.post("/request")
async def request_tool_access(body: ToolRequestCreate, user: CurrentUser):
    """User requests access to a toolkit not yet approved by admin."""
    tenant_id = await _get_user_tenant_id(str(user.id))

    # Check if already approved
    if await _is_toolkit_approved(tenant_id, body.toolkit_slug):
        return {"status": "already_approved", "message": "This tool is already available. You can connect it now."}

    # Check for existing pending request
    if await _has_pending_request(str(user.id), body.toolkit_slug):
        return {"status": "already_pending", "message": "Your request is already being reviewed."}

    # Create request
    request_data = await _create_request(str(user.id), tenant_id, body)

    # Notify admins
    await _notify_admins(tenant_id, body.toolkit_slug, body.toolkit_display_name)

    return {"status": "submitted", "message": "Your request has been submitted for admin review.", "request": request_data}


@router.get("/requests")
async def list_own_requests(user: CurrentUser):
    """List the current user's own tool access requests."""
    db = get_supabase_client()
    result = (
        db.table("toolkit_access_requests")
        .select("*")
        .eq("user_id", str(user.id))
        .order("created_at", desc=True)
        .execute()
    )
    return {"requests": result.data or []}
