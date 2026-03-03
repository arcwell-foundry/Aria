"""Admin Tool Governance API.

Endpoints for IT admins to manage which toolkits are available
for their organization's users.

Routes:
- GET  /admin/tools/catalog          — available Composio toolkits
- GET  /admin/tools/config           — current toolkit configurations
- POST /admin/tools/config           — approve/configure a toolkit
- PATCH /admin/tools/config/{slug}   — update toolkit config
- GET  /admin/tools/requests         — pending user requests
- PATCH /admin/tools/requests/{id}   — approve/deny a request
- GET  /admin/tools/audit            — audit trail
"""

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.deps import AdminUser
from src.core.ws import ws_manager
from src.db.supabase import get_supabase_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/tools", tags=["admin-tools"])


# ------------------------------------------------------------------
# Models
# ------------------------------------------------------------------

class ToolkitConfigCreate(BaseModel):
    toolkit_slug: str
    display_name: str = ""
    category: str = "general"
    status: str = Field(default="approved", pattern="^(approved|denied|pending_review)$")
    max_seats: int | None = None
    notes: str | None = None
    config_json: dict[str, Any] = Field(default_factory=dict)


class ToolkitConfigUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(approved|denied|pending_review)$")
    max_seats: int | None = None
    notes: str | None = None
    config_json: dict[str, Any] | None = None


class RequestReviewBody(BaseModel):
    status: str = Field(..., pattern="^(approved|denied)$")
    admin_notes: str | None = None


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

async def _get_admin_company_id(admin_user: Any) -> str:
    """Get the company_id for the admin user."""
    db = get_supabase_client()
    result = (
        db.table("user_profiles")
        .select("company_id")
        .eq("id", str(admin_user.id))
        .limit(1)
        .execute()
    )
    record = result.data[0] if result and result.data else None
    if not record or not record.get("company_id"):
        raise HTTPException(status_code=400, detail="Admin has no company association")
    return record["company_id"]


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.get("/catalog")
async def get_toolkit_catalog(admin: AdminUser):
    """Get available Composio toolkits that can be approved."""
    company_id = await _get_admin_company_id(admin)
    db = get_supabase_client()

    # Get distinct composio apps from capability_graph
    graph_result = (
        db.table("capability_graph")
        .select("composio_app_name, provider_type, capability_category, quality_score, is_active")
        .not_.is_("composio_app_name", "null")
        .execute()
    )

    # Deduplicate by composio_app_name
    seen: dict[str, dict] = {}
    for row in (graph_result.data or []):
        app = row.get("composio_app_name", "")
        if app and app not in seen:
            seen[app] = row

    # Check which are already configured for this tenant
    config_result = (
        db.table("tenant_toolkit_config")
        .select("toolkit_slug, status")
        .eq("tenant_id", company_id)
        .execute()
    )
    config_map = {r["toolkit_slug"]: r["status"] for r in (config_result.data or [])}

    catalog = []
    for app_name, row in sorted(seen.items()):
        catalog.append({
            "composio_app_name": app_name,
            "provider_type": row.get("provider_type", ""),
            "capability_category": row.get("capability_category", ""),
            "quality_score": row.get("quality_score", 0),
            "is_active": row.get("is_active", True),
            "org_status": config_map.get(app_name, "not_configured"),
        })

    return {"catalog": catalog}


@router.get("/config")
async def list_toolkit_configs(admin: AdminUser):
    """List all toolkit configurations for the admin's org."""
    company_id = await _get_admin_company_id(admin)
    db = get_supabase_client()

    result = (
        db.table("tenant_toolkit_config")
        .select("*")
        .eq("tenant_id", company_id)
        .order("category")
        .order("display_name")
        .execute()
    )

    # Enrich with active seat count per toolkit
    toolkits = result.data or []
    for toolkit in toolkits:
        seat_result = (
            db.table("user_connections")
            .select("id", count="exact")
            .eq("toolkit_slug", toolkit["toolkit_slug"])
            .eq("status", "active")
            .execute()
        )
        toolkit["current_seats"] = seat_result.count or 0

    return {"toolkits": toolkits}


@router.post("/config")
async def create_toolkit_config(body: ToolkitConfigCreate, admin: AdminUser):
    """Approve or configure a toolkit for the org."""
    company_id = await _get_admin_company_id(admin)
    db = get_supabase_client()

    row = {
        "tenant_id": company_id,
        "toolkit_slug": body.toolkit_slug.upper(),
        "display_name": body.display_name or body.toolkit_slug,
        "category": body.category,
        "status": body.status,
        "approved_by": str(admin.id),
        "approved_at": datetime.now(UTC).isoformat(),
        "max_seats": body.max_seats,
        "notes": body.notes,
        "config_json": body.config_json,
    }

    result = (
        db.table("tenant_toolkit_config")
        .upsert(row, on_conflict="tenant_id,toolkit_slug")
        .execute()
    )

    return {"status": body.status, "toolkit": result.data[0] if result.data else row}


@router.patch("/config/{toolkit_slug}")
async def update_toolkit_config(toolkit_slug: str, body: ToolkitConfigUpdate, admin: AdminUser):
    """Update a toolkit configuration."""
    company_id = await _get_admin_company_id(admin)
    db = get_supabase_client()

    update_data: dict[str, Any] = {"updated_at": datetime.now(UTC).isoformat()}
    if body.status is not None:
        update_data["status"] = body.status
    if body.max_seats is not None:
        update_data["max_seats"] = body.max_seats
    if body.notes is not None:
        update_data["notes"] = body.notes
    if body.config_json is not None:
        update_data["config_json"] = body.config_json

    if len(update_data) == 1:  # only updated_at
        raise HTTPException(status_code=400, detail="No fields to update")

    result = (
        db.table("tenant_toolkit_config")
        .update(update_data)
        .eq("tenant_id", company_id)
        .eq("toolkit_slug", toolkit_slug.upper())
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Toolkit config not found")

    return {"status": "updated", "toolkit": result.data[0]}


@router.get("/requests")
async def list_access_requests(
    admin: AdminUser,
    status_filter: str | None = Query(None, alias="status"),
):
    """List user tool access requests for the admin's org."""
    company_id = await _get_admin_company_id(admin)
    db = get_supabase_client()

    query = (
        db.table("toolkit_access_requests")
        .select("*")
        .eq("tenant_id", company_id)
        .order("created_at", desc=True)
    )
    if status_filter:
        query = query.eq("status", status_filter)

    result = query.execute()
    return {"requests": result.data or []}


@router.patch("/requests/{request_id}")
async def review_access_request(
    request_id: str,
    body: RequestReviewBody,
    admin: AdminUser,
):
    """Approve or deny a user's tool access request."""
    company_id = await _get_admin_company_id(admin)
    db = get_supabase_client()

    # Fetch the request
    req_result = (
        db.table("toolkit_access_requests")
        .select("*")
        .eq("id", request_id)
        .eq("tenant_id", company_id)
        .limit(1)
        .execute()
    )
    request_data = req_result.data[0] if req_result and req_result.data else None
    if not request_data:
        raise HTTPException(status_code=404, detail="Request not found")
    user_id = request_data["user_id"]
    toolkit_slug = request_data["toolkit_slug"]

    # Update request status
    db.table("toolkit_access_requests").update({
        "status": body.status,
        "reviewed_by": str(admin.id),
        "reviewed_at": datetime.now(UTC).isoformat(),
        "admin_notes": body.admin_notes,
    }).eq("id", request_id).execute()

    # If approved, also create/update the toolkit config
    if body.status == "approved":
        db.table("tenant_toolkit_config").upsert({
            "tenant_id": company_id,
            "toolkit_slug": toolkit_slug.upper(),
            "display_name": request_data.get("toolkit_display_name", toolkit_slug),
            "category": "user_requested",
            "status": "approved",
            "approved_by": str(admin.id),
            "approved_at": datetime.now(UTC).isoformat(),
            "notes": f"Approved via user request from {user_id}",
        }, on_conflict="tenant_id,toolkit_slug").execute()

    # Notify the user via WebSocket
    try:
        event_type = "toolkit_request_approved" if body.status == "approved" else "toolkit_request_denied"
        msg = (
            f"Your request for {toolkit_slug.replace('_', ' ').title()} was "
            + ("approved! You can now connect it." if body.status == "approved" else "not approved.")
            + (f" Reason: {body.admin_notes}" if body.admin_notes and body.status == "denied" else "")
        )
        await ws_manager.send_to_user(user_id, {"type": event_type, "toolkit_slug": toolkit_slug, "message": msg})
    except Exception:
        logger.warning("Failed to notify user %s about request review", user_id)

    return {"status": body.status, "request_id": request_id}


@router.get("/audit")
async def tool_audit_trail(admin: AdminUser, limit: int = Query(default=100, le=500)):
    """Get tool router audit trail for the org."""
    company_id = await _get_admin_company_id(admin)
    db = get_supabase_client()

    # Get all user IDs in the company
    users_result = (
        db.table("user_profiles")
        .select("id")
        .eq("company_id", company_id)
        .execute()
    )
    user_ids = [u["id"] for u in (users_result.data or [])]

    if not user_ids:
        return {"audit_entries": []}

    result = (
        db.table("tool_router_audit_log")
        .select("*")
        .in_("user_id", user_ids)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )

    return {"audit_entries": result.data or []}
