"""Team & Company Administration API Routes (US-927).

All routes require admin or manager role for access.
Admins have full access. Managers can view team and invite members.
"""

import logging
from typing import Any

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, EmailStr, Field

from src.api.deps import CurrentUser
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
