"""Authentication API routes."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

from src.api.deps import CurrentUser
from src.core.rate_limiter import RateLimitConfig, rate_limit
from src.db.supabase import SupabaseClient
from src.services.account_service import AccountService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])
account_service = AccountService()


# Request/Response Models
class SignupRequest(BaseModel):
    """Request model for user signup."""

    email: EmailStr
    password: str = Field(..., min_length=8, description="Password (min 8 chars)")
    full_name: str = Field(..., min_length=1, max_length=100)
    company_name: str | None = Field(None, max_length=100)


class LoginRequest(BaseModel):
    """Request model for user login."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Response model with authentication tokens."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshTokenRequest(BaseModel):
    """Request model for token refresh."""

    refresh_token: str


class UserResponse(BaseModel):
    """Response model for user data."""

    id: str
    email: str
    full_name: str | None = None
    company_id: str | None = None
    role: str = "user"
    avatar_url: str | None = None


class MessageResponse(BaseModel):
    """Generic message response."""

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


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@rate_limit(RateLimitConfig(requests=5, window_seconds=60))
async def signup(request: Request, signup_request: SignupRequest) -> TokenResponse:  # noqa: ARG001
    """Create a new user account.

    Args:
        request: Signup request with email, password, and profile info.

    Returns:
        Authentication tokens for the new user.

    Raises:
        HTTPException: If signup fails.
    """
    try:
        client = SupabaseClient.get_client()

        # Create auth user
        auth_response = client.auth.sign_up(
            {
                "email": signup_request.email,
                "password": signup_request.password,
            }
        )

        if auth_response.user is None or auth_response.session is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create account. Please check your email for verification.",
            )

        user_id = auth_response.user.id

        # Create company if provided
        company_id: str | None = None
        if signup_request.company_name:
            company = await SupabaseClient.create_company(name=signup_request.company_name)
            company_id = company["id"]

        # Create user profile
        await SupabaseClient.create_user_profile(
            user_id=user_id,
            full_name=signup_request.full_name,
            company_id=company_id,
        )

        # Create default user settings
        await SupabaseClient.create_user_settings(user_id=user_id)

        logger.info("User signed up successfully", extra={"user_id": user_id})

        return TokenResponse(
            access_token=auth_response.session.access_token,
            refresh_token=auth_response.session.refresh_token,
            expires_in=auth_response.session.expires_in or 3600,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error during signup")
        error_msg = str(e) if str(e) else "Signup failed"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg,
        ) from e


@router.post("/login", response_model=TokenResponse)
@rate_limit(RateLimitConfig(requests=5, window_seconds=60))
async def login(request: Request, login_request: LoginRequest) -> TokenResponse:
    """Authenticate user with email and password.

    Args:
        request: Login request with email and password.

    Returns:
        Authentication tokens.

    Raises:
        HTTPException: If login fails.
    """
    client_ip = _get_client_ip(request)
    user_agent = request.headers.get("User-Agent")

    try:
        client = SupabaseClient.get_client()

        auth_response = client.auth.sign_in_with_password(
            {
                "email": login_request.email,
                "password": login_request.password,
            }
        )

        if auth_response.session is None or auth_response.user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        # Log successful login
        await account_service.log_security_event(
            user_id=auth_response.user.id,
            event_type=account_service.EVENT_LOGIN,
            ip_address=client_ip,
            user_agent=user_agent,
        )

        logger.info("User logged in successfully", extra={"user_id": auth_response.user.id})

        return TokenResponse(
            access_token=auth_response.session.access_token,
            refresh_token=auth_response.session.refresh_token,
            expires_in=auth_response.session.expires_in or 3600,
        )

    except HTTPException:
        # For login failures, try to get user_id for logging
        # We need to look up the user by email to log the failed attempt
        try:
            admin_client = client.auth.admin
            # List users to find by email (Supabase limitation)
            users_response = admin_client.list_users()
            user_id = None
            # users_response is actually a list of User objects
            for user in users_response:
                if user.email == login_request.email:
                    user_id = user.id
                    break

            if user_id:
                await account_service.log_security_event(
                    user_id=user_id,
                    event_type=account_service.EVENT_LOGIN_FAILED,
                    ip_address=client_ip,
                    user_agent=user_agent,
                )
        except Exception:
            # Don't let logging failures prevent the error response
            pass
        raise
    except Exception as e:
        # Log failed login attempt
        try:
            admin_client = client.auth.admin
            users_response = admin_client.list_users()
            user_id = None
            # users_response is actually a list of User objects
            for user in users_response:
                if user.email == login_request.email:
                    user_id = user.id
                    break

            if user_id:
                await account_service.log_security_event(
                    user_id=user_id,
                    event_type=account_service.EVENT_LOGIN_FAILED,
                    ip_address=client_ip,
                    user_agent=user_agent,
                )
        except Exception:
            pass
        logger.exception("Error during login")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        ) from e


@router.post("/logout", response_model=MessageResponse)
async def logout(request: Request, current_user: CurrentUser) -> MessageResponse:
    """Invalidate the current user's session.

    Args:
        request: FastAPI request.
        current_user: The authenticated user.

    Returns:
        Success message.
    """
    client_ip = _get_client_ip(request)
    user_agent = request.headers.get("User-Agent")

    try:
        client = SupabaseClient.get_client()
        client.auth.sign_out()

        # Log logout event
        await account_service.log_security_event(
            user_id=current_user.id,
            event_type=account_service.EVENT_LOGOUT,
            ip_address=client_ip,
            user_agent=user_agent,
        )

        logger.info("User logged out successfully", extra={"user_id": current_user.id})

        return MessageResponse(message="Successfully logged out")

    except Exception as e:
        logger.exception("Error during logout")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed",
        ) from e


@router.post("/refresh", response_model=TokenResponse)
@rate_limit(RateLimitConfig(requests=10, window_seconds=60))
async def refresh_token(http_request: Request, refresh_request: RefreshTokenRequest) -> TokenResponse:  # noqa: ARG001
    """Refresh the access token using a refresh token.

    Args:
        request: Request with refresh token.

    Returns:
        New authentication tokens.

    Raises:
        HTTPException: If refresh fails.
    """
    try:
        client = SupabaseClient.get_client()

        auth_response = client.auth.refresh_session(refresh_request.refresh_token)

        if auth_response.session is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
            )

        return TokenResponse(
            access_token=auth_response.session.access_token,
            refresh_token=auth_response.session.refresh_token,
            expires_in=auth_response.session.expires_in or 3600,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error during token refresh")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        ) from e


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(current_user: CurrentUser) -> dict[str, Any]:
    """Get the current user's profile.

    Args:
        current_user: The authenticated user.

    Returns:
        User profile data.

    Raises:
        HTTPException: If profile fetch fails.
    """
    try:
        profile = await SupabaseClient.get_user_by_id(current_user.id)

        return {
            "id": current_user.id,
            "email": current_user.email or "",
            "full_name": profile.get("full_name"),
            "company_id": profile.get("company_id"),
            "role": profile.get("role", "user"),
            "avatar_url": profile.get("avatar_url"),
        }

    except Exception as e:
        logger.exception("Error fetching user profile")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch user profile",
        ) from e
