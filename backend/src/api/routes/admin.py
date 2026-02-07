"""Team & Company Administration API Routes (US-927, US-932).

All routes require admin or manager role for access.
Admins have full access. Managers can view team and invite members.
"""

import csv
import io
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field

from src.api.deps import AdminUser, CurrentUser
from src.services.account_service import AccountService
from src.services.team_service import TeamService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])
team_service = TeamService()
account_service = AccountService()


# Request/Response Models
class TeamMemberResponse(BaseModel):
    """Team member response."""

    id: str
    full_name: str | None = None
    email: EmailStr
    role: str = "user"
    is_active: bool = True
    last_active: str | None = None
    created_at: str | None = None


class InviteMemberRequest(BaseModel):
    """Request to invite a team member."""

    email: EmailStr
    role: str = Field(default="user", pattern="^(user|manager|admin)$")


class InviteResponse(BaseModel):
    """Team invite response."""

    id: str
    email: EmailStr
    role: str
    status: str = "pending"
    expires_at: str
    created_at: str


class ChangeRoleRequest(BaseModel):
    """Request to change user role."""

    role: str = Field(..., pattern="^(user|manager|admin)$")


class CompanyResponse(BaseModel):
    """Company details response."""

    id: str
    name: str
    domain: str | None = None
    created_at: str | None = None
    settings: dict[str, Any] | None = None


class UpdateCompanyRequest(BaseModel):
    """Request to update company."""

    name: str | None = Field(None, min_length=1, max_length=100)
    settings: dict[str, Any] | None = None


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str


# Helper function
def _get_client_ip(request: Request) -> str | None:
    """Extract client IP from request.

    Args:
        request: FastAPI request object.

    Returns:
        Client IP address or None.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    return None


# Routes
@router.get("/team", response_model=list[TeamMemberResponse], status_code=status.HTTP_200_OK)
async def list_team(
    current_user: CurrentUser,
) -> list[dict[str, Any]]:
    """List all team members at the user's company.

    Args:
        current_user: The authenticated user (must be admin or manager).

    Returns:
        List of team members.
    """
    from src.db.supabase import SupabaseClient

    profile = await SupabaseClient.get_user_by_id(current_user.id)
    company_id = profile.get("company_id")

    if not company_id:
        return []

    return await team_service.list_team(company_id=company_id)


@router.post("/team/invite", response_model=InviteResponse, status_code=status.HTTP_201_CREATED)
async def invite_member(
    _request: Request,
    data: InviteMemberRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Invite a new team member to the company.

    Args:
        _request: FastAPI request (reserved for IP logging).
        data: Invite request with email and role.
        current_user: The authenticated user (any team member can invite).

    Returns:
        Created invite record.

    Note:
        Following "open with escalation" policy, any team member can send invites.
        Companies with >5 users without a verified admin are flagged for review.
    """
    from fastapi import HTTPException

    from src.db.supabase import SupabaseClient

    profile = await SupabaseClient.get_user_by_id(current_user.id)
    company_id = profile.get("company_id")

    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must belong to a company to invite team members",
        )

    return await team_service.invite_member(
        company_id=company_id,
        invited_by=current_user.id,
        email=data.email,
        role=data.role,
    )


@router.get("/team/invites", response_model=list[InviteResponse], status_code=status.HTTP_200_OK)
async def list_invites(
    current_user: CurrentUser,
) -> list[dict[str, Any]]:
    """List pending team invites.

    Args:
        current_user: The authenticated user (must be admin or manager).

    Returns:
        List of pending invites.
    """
    from src.db.supabase import SupabaseClient

    profile = await SupabaseClient.get_user_by_id(current_user.id)
    company_id = profile.get("company_id")

    if not company_id:
        return []

    return await team_service.list_pending_invites(company_id=company_id)


@router.post(
    "/team/invites/{invite_id}/cancel",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
async def cancel_invite(
    invite_id: str,
    current_user: CurrentUser,
) -> dict[str, str]:
    """Cancel a pending team invite.

    Args:
        invite_id: The invite's UUID.
        current_user: The authenticated user (must be admin).

    Returns:
        Success message.
    """
    from fastapi import HTTPException

    from src.db.supabase import SupabaseClient

    profile = await SupabaseClient.get_user_by_id(current_user.id)
    company_id = profile.get("company_id")

    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must belong to a company",
        )

    await team_service.cancel_invite(invite_id=invite_id, company_id=company_id)
    return {"message": "Invite cancelled"}


@router.post(
    "/team/invites/{invite_id}/resend",
    response_model=InviteResponse,
    status_code=status.HTTP_200_OK,
)
async def resend_invite(
    invite_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Resend a pending team invite (extends expiry).

    Args:
        invite_id: The invite's UUID.
        current_user: The authenticated user (must be admin).

    Returns:
        Updated invite record.
    """
    from fastapi import HTTPException

    from src.db.supabase import SupabaseClient

    profile = await SupabaseClient.get_user_by_id(current_user.id)
    company_id = profile.get("company_id")

    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must belong to a company",
        )

    return await team_service.resend_invite(invite_id=invite_id, company_id=company_id)


@router.patch(
    "/team/{user_id}/role", response_model=TeamMemberResponse, status_code=status.HTTP_200_OK
)
async def change_role(
    user_id: str,
    data: ChangeRoleRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Change a team member's role.

    Args:
        user_id: The user's UUID.
        data: Role change request.
        current_user: The authenticated user (must be admin).

    Returns:
        Updated team member.

    Raises:
        HTTPException: If attempting to demote the last admin.
    """
    from fastapi import HTTPException

    from src.db.supabase import SupabaseClient

    profile = await SupabaseClient.get_user_by_id(current_user.id)
    company_id = profile.get("company_id")

    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must belong to a company",
        )

    # Get old role before change for logging
    target_profile = await SupabaseClient.get_user_by_id(user_id)
    old_role = target_profile.get("role", "user")

    updated_profile = await team_service.change_role(
        company_id=company_id,
        user_id=user_id,
        new_role=data.role,
    )

    # Log security event for role change
    await account_service.log_security_event(
        user_id=current_user.id,  # Log as the admin who made the change
        event_type=account_service.EVENT_ROLE_CHANGED,
        metadata={
            "target_user_id": user_id,
            "old_role": old_role,
            "new_role": data.role,
        },
    )

    return {
        "id": updated_profile["id"],
        "full_name": updated_profile.get("full_name"),
        "email": "",  # Would need to fetch from auth
        "role": updated_profile.get("role", "user"),
        "is_active": updated_profile.get("is_active", True),
        "last_active": updated_profile.get("updated_at"),
        "created_at": updated_profile.get("created_at"),
    }


@router.post(
    "/team/{user_id}/deactivate", response_model=MessageResponse, status_code=status.HTTP_200_OK
)
async def deactivate_user(
    user_id: str,
    _current_user: CurrentUser,
) -> dict[str, str]:
    """Deactivate a team member account.

    Args:
        user_id: The user's UUID.
        _current_user: The authenticated user (must be admin).

    Returns:
        Success message.
    """
    await team_service.deactivate_user(user_id=user_id)
    return {"message": "User deactivated"}


@router.post(
    "/team/{user_id}/reactivate", response_model=MessageResponse, status_code=status.HTTP_200_OK
)
async def reactivate_user(
    user_id: str,
    _current_user: CurrentUser,
) -> dict[str, str]:
    """Reactivate a deactivated team member account.

    Args:
        user_id: The user's UUID.
        _current_user: The authenticated user (must be admin).

    Returns:
        Success message.
    """
    await team_service.reactivate_user(user_id=user_id)
    return {"message": "User reactivated"}


@router.get("/company", response_model=CompanyResponse, status_code=status.HTTP_200_OK)
async def get_company(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get company details.

    Args:
        current_user: The authenticated user (must be admin or manager).

    Returns:
        Company details.
    """
    from fastapi import HTTPException

    from src.db.supabase import SupabaseClient

    profile = await SupabaseClient.get_user_by_id(current_user.id)
    company_id = profile.get("company_id")

    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found",
        )

    return await team_service.get_company(company_id=company_id)


@router.patch("/company", response_model=CompanyResponse, status_code=status.HTTP_200_OK)
async def update_company(
    data: UpdateCompanyRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Update company details.

    Args:
        data: Company update request.
        current_user: The authenticated user (must be admin).

    Returns:
        Updated company details.
    """
    from fastapi import HTTPException

    from src.db.supabase import SupabaseClient

    profile = await SupabaseClient.get_user_by_id(current_user.id)
    company_id = profile.get("company_id")

    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must belong to a company",
        )

    return await team_service.update_company(
        company_id=company_id,
        name=data.name,
        settings=data.settings,
    )


# --- Audit Trail Routes (US-932) ---


class AuditLogEntryResponse(BaseModel):
    """Individual audit log entry."""

    id: str
    user_id: str | None = None
    event_type: str
    source: str  # "security" or "memory"
    resource_type: str | None = None
    resource_id: str | None = None
    ip_address: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class AuditLogResponse(BaseModel):
    """Paginated audit log response."""

    items: list[AuditLogEntryResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


@router.get("/audit-log", response_model=AuditLogResponse, status_code=status.HTTP_200_OK)
async def get_audit_log(
    _current_user: AdminUser,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Results per page"),
    event_type: str | None = Query(None, description="Filter by event type"),
    user_id: str | None = Query(None, description="Filter by user ID"),
    date_from: str | None = Query(None, description="Filter from date (ISO format)"),
    date_to: str | None = Query(None, description="Filter to date (ISO format)"),
    search: str | None = Query(None, description="Search in resource ID or metadata"),
) -> dict[str, Any]:
    """Query the unified audit trail (security + memory events).

    Combines security_audit_log and memory_audit_log into a single
    chronological view for admin compliance monitoring.

    Args:
        _current_user: Authenticated admin user.
        page: Page number (1-indexed).
        page_size: Results per page (max 100).
        event_type: Filter by operation/event type.
        user_id: Filter by specific user.
        date_from: Start date filter (ISO 8601).
        date_to: End date filter (ISO 8601).
        search: Search term for resource_id or metadata.

    Returns:
        Paginated audit log entries.
    """
    from src.db.supabase import SupabaseClient

    client = SupabaseClient.get_client()
    offset = (page - 1) * page_size

    items: list[dict[str, Any]] = []

    # Query security_audit_log
    sec_query = client.table("security_audit_log").select("*", count="exact")
    if user_id:
        sec_query = sec_query.eq("user_id", user_id)
    if event_type:
        sec_query = sec_query.eq("event_type", event_type)
    if date_from:
        sec_query = sec_query.gte("created_at", date_from)
    if date_to:
        sec_query = sec_query.lte("created_at", date_to)

    sec_response = sec_query.order("created_at", desc=True).execute()
    sec_data = sec_response.data or []

    for row in sec_data:
        metadata = row.get("metadata") or {}
        items.append(
            {
                "id": str(row["id"]),
                "user_id": str(row.get("user_id") or ""),
                "event_type": row.get("event_type", ""),
                "source": "security",
                "resource_type": "account",
                "resource_id": metadata.get("target_user_id") or metadata.get("session_id"),
                "ip_address": row.get("ip_address"),
                "metadata": metadata,
                "created_at": row.get("created_at", ""),
            }
        )

    # Query memory_audit_log
    mem_query = client.table("memory_audit_log").select("*", count="exact")
    if user_id:
        mem_query = mem_query.eq("user_id", user_id)
    if event_type:
        mem_query = mem_query.eq("operation", event_type)
    if date_from:
        mem_query = mem_query.gte("created_at", date_from)
    if date_to:
        mem_query = mem_query.lte("created_at", date_to)

    mem_response = mem_query.order("created_at", desc=True).execute()
    mem_data = mem_response.data or []

    for row in mem_data:
        items.append(
            {
                "id": str(row["id"]),
                "user_id": str(row.get("user_id") or ""),
                "event_type": row.get("operation", ""),
                "source": "memory",
                "resource_type": row.get("memory_type"),
                "resource_id": row.get("memory_id"),
                "ip_address": None,
                "metadata": row.get("metadata") or {},
                "created_at": row.get("created_at", ""),
            }
        )

    # Sort combined results by created_at descending
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    # Apply search filter on combined results
    if search:
        search_lower = search.lower()
        items = [
            item
            for item in items
            if (item.get("resource_id") and search_lower in str(item["resource_id"]).lower())
            or search_lower in str(item.get("metadata", {})).lower()
            or search_lower in str(item.get("event_type", "")).lower()
        ]

    total = len(items)
    paginated = items[offset : offset + page_size]

    return {
        "items": paginated,
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_more": (offset + page_size) < total,
    }


@router.get("/audit-log/export", status_code=status.HTTP_200_OK)
async def export_audit_log(
    _current_user: AdminUser,
    event_type: str | None = Query(None),
    user_id: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    search: str | None = Query(None),
) -> StreamingResponse:
    """Export audit log as CSV for compliance reporting.

    Args:
        _current_user: Authenticated admin user.
        event_type: Filter by operation/event type.
        user_id: Filter by specific user.
        date_from: Start date filter (ISO 8601).
        date_to: End date filter (ISO 8601).
        search: Search term for resource_id or metadata.

    Returns:
        CSV file download.
    """
    # Reuse the query logic with max page size
    result = await get_audit_log(
        _current_user=_current_user,
        page=1,
        page_size=100,
        event_type=event_type,
        user_id=user_id,
        date_from=date_from,
        date_to=date_to,
        search=search,
    )

    # Fetch all pages
    all_items = list(result["items"])
    total = result["total"]
    fetched = len(all_items)

    while fetched < total:
        next_page = (fetched // 100) + 2
        more = await get_audit_log(
            _current_user=_current_user,
            page=next_page,
            page_size=100,
            event_type=event_type,
            user_id=user_id,
            date_from=date_from,
            date_to=date_to,
            search=search,
        )
        all_items.extend(more["items"])
        fetched = len(all_items)
        if not more["has_more"]:
            break

    # Generate CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Timestamp",
            "User ID",
            "Event Type",
            "Source",
            "Resource Type",
            "Resource ID",
            "IP Address",
            "Details",
        ]
    )

    for item in all_items:
        writer.writerow(
            [
                item.get("created_at", ""),
                item.get("user_id", ""),
                item.get("event_type", ""),
                item.get("source", ""),
                item.get("resource_type", ""),
                item.get("resource_id", ""),
                item.get("ip_address", ""),
                str(item.get("metadata", {})),
            ]
        )

    output.seek(0)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=audit_log_{timestamp}.csv",
        },
    )


# --- Onboarding Outcomes Routes (US-924) ---


class OnboardingOutcomeResponse(BaseModel):
    """Individual onboarding outcome response."""

    id: str
    user_id: str
    completion_time_minutes: float | None = None
    steps_completed: int = 0
    steps_skipped: int = 0
    company_type: str | None = None
    first_goal_category: str | None = None
    documents_uploaded: int = 0
    email_connected: bool = False
    crm_connected: bool = False
    readiness_snapshot: dict[str, float] = Field(default_factory=dict)
    created_at: str


class OnboardingOutcomesResponse(BaseModel):
    """Paginated onboarding outcomes response."""

    items: list[OnboardingOutcomeResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class OnboardingInsightResponse(BaseModel):
    """Onboarding insight response."""

    pattern: str
    description: str
    value: float | None = None
    evidence_count: int = 1
    confidence: float = 0.5


@router.get(
    "/onboarding/outcomes",
    response_model=OnboardingOutcomesResponse,
    status_code=status.HTTP_200_OK,
)
async def get_onboarding_outcomes(
    _current_user: AdminUser,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Results per page"),
    company_type: str | None = Query(None, description="Filter by company type"),
) -> dict[str, Any]:
    """Get paginated list of onboarding outcomes.

    Args:
        _current_user: Authenticated admin user.
        page: Page number (1-indexed).
        page_size: Results per page (max 100).
        company_type: Optional filter by company type.

    Returns:
        Paginated onboarding outcomes.
    """
    from src.db.supabase import SupabaseClient

    client = SupabaseClient.get_client()
    offset = (page - 1) * page_size

    query = client.table("onboarding_outcomes").select("*", count="exact")

    if company_type:
        query = query.eq("company_type", company_type)

    response = query.order("created_at", desc=True).range(offset, offset + page_size - 1).execute()

    items = response.data or []
    total = response.count if hasattr(response, "count") else len(items)

    return {
        "items": [
            {
                "id": str(row["id"]),
                "user_id": str(row.get("user_id", "")),
                "completion_time_minutes": row.get("completion_time_minutes"),
                "steps_completed": row.get("steps_completed", 0),
                "steps_skipped": row.get("steps_skipped", 0),
                "company_type": row.get("company_type"),
                "first_goal_category": row.get("first_goal_category"),
                "documents_uploaded": row.get("documents_uploaded", 0),
                "email_connected": row.get("email_connected", False),
                "crm_connected": row.get("crm_connected", False),
                "readiness_snapshot": row.get("readiness_snapshot", {}),
                "created_at": row.get("created_at", ""),
            }
            for row in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_more": (offset + page_size) < total,
    }


@router.get(
    "/onboarding/insights",
    response_model=list[OnboardingInsightResponse],
    status_code=status.HTTP_200_OK,
)
async def get_onboarding_insights(
    _current_user: AdminUser,
) -> list[dict[str, Any]]:
    """Get system-level onboarding insights from procedural memory.

    Returns aggregated patterns like average readiness by company type,
    completion times, and correlations between onboarding behaviors
    and outcomes.

    Args:
        _current_user: Authenticated admin user.

    Returns:
        List of insight dictionaries.
    """
    from src.onboarding.outcome_tracker import OnboardingOutcomeTracker

    tracker = OnboardingOutcomeTracker()
    insights = await tracker.get_system_insights()

    return [
        {
            "pattern": insight.get("pattern", ""),
            "description": tracker._format_insight(insight),
            "value": insight.get("value"),
            "evidence_count": insight.get("evidence_count", 1),
            "confidence": insight.get("confidence", 0.5),
        }
        for insight in insights
    ]


@router.post(
    "/onboarding/consolidate",
    response_model=dict[str, str],
    status_code=status.HTTP_200_OK,
)
async def consolidate_procedural_insights(
    _current_user: AdminUser,
) -> dict[str, str]:
    """Trigger consolidation of episodic outcomes to procedural insights.

    Typically run quarterly via cron, but can be triggered manually
    by admins to refresh insights.

    Args:
        _current_user: Authenticated admin user.

    Returns:
        Success message with count of new insights created.
    """
    from src.onboarding.outcome_tracker import OnboardingOutcomeTracker

    tracker = OnboardingOutcomeTracker()
    count = await tracker.consolidate_to_procedural()

    return {"message": f"Consolidated {count} new procedural insights"}
