"""Account & Identity Management API Routes (US-926)."""

import logging
from typing import Any

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, EmailStr, Field

from src.api.deps import CurrentUser
from src.core.rate_limiter import RateLimitConfig, rate_limit
from src.services.account_service import AccountService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/account", tags=["account"])
account_service = AccountService()


# Request/Response Models
class ProfileResponse(BaseModel):
    """User profile response."""

    id: str
    full_name: str | None = None
    avatar_url: str | None = None
    company_id: str | None = None
    role: str = "user"
    is_2fa_enabled: bool = False
    created_at: str | None = None
    updated_at: str | None = None


class UpdateProfileRequest(BaseModel):
    """Request to update profile."""

    full_name: str | None = Field(None, min_length=1, max_length=100)
    avatar_url: str | None = Field(None, max_length=500)


class ChangePasswordRequest(BaseModel):
    """Request to change password."""

    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=100)


class PasswordResetRequest(BaseModel):
    """Request to reset password."""

    email: EmailStr


class TwoFactorSetupResponse(BaseModel):
    """Response for 2FA setup."""

    secret: str
    qr_code_uri: str
    provisioning_uri: str


class VerifyTwoFactorRequest(BaseModel):
    """Request to verify 2FA code."""

    code: str = Field(..., pattern=r"^\d{6}$", description="6-digit verification code")
    secret: str = Field(..., description="TOTP secret from setup")


class DisableTwoFactorRequest(BaseModel):
    """Request to disable 2FA."""

    password: str = Field(..., min_length=1)


class SessionInfo(BaseModel):
    """Session information."""

    id: str
    device: str
    ip_address: str
    user_agent: str
    last_active: str | None = None
    is_current: bool = False


class DeleteAccountRequest(BaseModel):
    """Request to delete account."""

    confirmation: str = Field(
        ...,
        description='Must be exactly "DELETE MY ACCOUNT"',
    )
    password: str = Field(..., min_length=1)


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str


class PasswordResetResponse(BaseModel):
    """Password reset response."""

    message: str


def _get_client_ip(request: Request) -> str | None:
    """Extract client IP from request.

    Args:
        request: FastAPI request object.

    Returns:
        Client IP address or None.
    """
    # Check various headers for the real IP
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    return None


# Routes
@router.get("/profile", response_model=ProfileResponse, status_code=status.HTTP_200_OK)
async def get_profile(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get the current user's profile.

    Args:
        current_user: The authenticated user.

    Returns:
        User profile data.
    """
    return await account_service.get_profile(current_user.id)


@router.patch("/profile", response_model=ProfileResponse, status_code=status.HTTP_200_OK)
async def update_profile(
    _request: Request,
    data: UpdateProfileRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Update the current user's profile.

    Args:
        _request: FastAPI request (reserved for future IP logging).
        data: Profile update data.
        current_user: The authenticated user.

    Returns:
        Updated user profile data.
    """
    return await account_service.update_profile(
        user_id=current_user.id,
        full_name=data.full_name,
        avatar_url=data.avatar_url,
    )


@router.post(
    "/password/change",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
async def change_password(
    _request: Request,
    data: ChangePasswordRequest,
    current_user: CurrentUser,
) -> dict[str, str]:
    """Change the current user's password.

    Args:
        _request: FastAPI request (reserved for future IP logging).
        data: Password change data.
        current_user: The authenticated user.

    Returns:
        Success message.
    """
    await account_service.change_password(
        user_id=current_user.id,
        current_password=data.current_password,
        new_password=data.new_password,
    )
    return {"message": "Password changed successfully"}


@router.post(
    "/password/reset-request",
    response_model=PasswordResetResponse,
    status_code=status.HTTP_200_OK,
)
@rate_limit(RateLimitConfig(requests=3, window_seconds=3600))
async def request_password_reset(
    data: PasswordResetRequest,
    _request: Request,
) -> dict[str, str]:
    """Request a password reset email.

    This endpoint does not require authentication.

    Args:
        data: Password reset request with email.
        _request: FastAPI request (reserved for future IP logging).

    Returns:
        Message indicating reset email was sent.
    """
    await account_service.request_password_reset(email=data.email)
    return {
        "message": "If an account exists with this email, a reset link has been sent."
    }


@router.post(
    "/2fa/setup",
    response_model=TwoFactorSetupResponse,
    status_code=status.HTTP_200_OK,
)
async def setup_2fa(
    current_user: CurrentUser,
) -> dict[str, str]:
    """Initiate two-factor authentication setup.

    Returns a TOTP secret and QR code for the user to scan.

    Args:
        current_user: The authenticated user.

    Returns:
        TOTP secret and QR code data URI.
    """
    return await account_service.setup_2fa(user_id=current_user.id)


@router.post("/2fa/verify", response_model=ProfileResponse, status_code=status.HTTP_200_OK)
@rate_limit(RateLimitConfig(requests=5, window_seconds=60))
async def verify_2fa(
    _request: Request,
    data: VerifyTwoFactorRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Verify TOTP code and enable 2FA.

    Args:
        _request: FastAPI request (reserved for future IP logging).
        data: Verification code and secret.
        current_user: The authenticated user.

    Returns:
        Updated profile with 2FA enabled.
    """
    return await account_service.verify_2fa(
        user_id=current_user.id,
        code=data.code,
        secret=data.secret,
    )


@router.post(
    "/2fa/disable",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
async def disable_2fa(
    _request: Request,
    data: DisableTwoFactorRequest,
    current_user: CurrentUser,
) -> dict[str, str]:
    """Disable two-factor authentication.

    Args:
        _request: FastAPI request (reserved for future IP logging).
        data: Password for verification.
        current_user: The authenticated user.

    Returns:
        Success message.
    """
    await account_service.disable_2fa(
        user_id=current_user.id,
        password=data.password,
    )
    return {"message": "Two-factor authentication disabled"}


@router.get(
    "/sessions",
    response_model=list[SessionInfo],
    status_code=status.HTTP_200_OK,
)
async def list_sessions(
    current_user: CurrentUser,
) -> list[dict[str, Any]]:
    """List active sessions for the current user.

    Args:
        current_user: The authenticated user.

    Returns:
        List of active sessions.
    """
    return await account_service.list_sessions(user_id=current_user.id)


@router.delete(
    "/sessions/{session_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
async def revoke_session(
    _request: Request,
    session_id: str,
    current_user: CurrentUser,
) -> dict[str, str]:
    """Revoke a specific session.

    Args:
        _request: FastAPI request (reserved for future IP logging).
        session_id: The session ID to revoke.
        current_user: The authenticated user.

    Returns:
        Success message.
    """
    await account_service.revoke_session(
        user_id=current_user.id,
        session_id=session_id,
    )
    return {"message": "Session revoked"}


@router.post(
    "/delete",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
async def delete_account(
    _request: Request,
    data: DeleteAccountRequest,
    current_user: CurrentUser,
) -> dict[str, str]:
    """Delete the current user's account.

    This will permanently delete all user data. Requires confirmation
    and password verification.

    Args:
        _request: FastAPI request (reserved for future IP logging).
        data: Account deletion confirmation and password.
        current_user: The authenticated user.

    Returns:
        Success message.
    """
    await account_service.delete_account(
        user_id=current_user.id,
        confirmation=data.confirmation,
        password=data.password,
    )
    return {"message": "Account deleted successfully"}
