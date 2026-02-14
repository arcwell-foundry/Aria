"""FastAPI dependencies for authentication and common operations."""

import logging
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.core.exceptions import AuthenticationError, AuthorizationError
from src.db.supabase import SupabaseClient

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# HTTP Bearer token security scheme
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> Any:
    """Extract and validate the current user from JWT token.

    Args:
        credentials: HTTP Bearer token credentials.

    Returns:
        Validated user object from Supabase.

    Raises:
        HTTPException: If authentication fails.
    """
    if credentials is None:
        logger.warning("AUTH: No credentials provided in request")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    # Log token prefix for debugging (don't log full token)
    token_preview = f"{token[:20]}...{token[-10:]}" if len(token) > 30 else f"{token[:10]}..."
    logger.info("AUTH: Validating token: %s (length=%d)", token_preview, len(token))

    try:
        client = SupabaseClient.get_client()
        response = client.auth.get_user(token)

        if response is None or response.user is None:
            logger.warning("AUTH: Token validation returned no user")
            raise AuthenticationError("Invalid authentication token")

        logger.info(
            "AUTH: Token validated successfully for user_id=%s email=%s",
            response.user.id,
            response.user.email,
        )
        return response.user

    except AuthenticationError as e:
        logger.warning("AUTH: AuthenticationError - %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    except Exception as e:
        logger.exception("AUTH: Unexpected error during token validation: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


async def get_current_user_optional(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> Any | None:
    """Get current user if authenticated, None otherwise.

    Args:
        credentials: HTTP Bearer token credentials.

    Returns:
        User object if authenticated, None otherwise.
    """
    if credentials is None:
        return None

    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


def require_role(required_roles: list[str]) -> Any:
    """Create a dependency that requires specific user roles.

    Args:
        required_roles: List of allowed role names.

    Returns:
        Dependency function that validates user roles.
    """

    async def role_checker(
        current_user: Annotated[Any, Depends(get_current_user)],
    ) -> Any:
        """Check if user has required role.

        Args:
            current_user: The authenticated user.

        Returns:
            User if role check passes.

        Raises:
            HTTPException: If user lacks required role.
        """
        try:
            # Get user profile to check role
            profile = await SupabaseClient.get_user_by_id(current_user.id)
            user_role = profile.get("role", "user")

            if user_role not in required_roles:
                raise AuthorizationError("Insufficient permissions for this action")

            return current_user

        except AuthorizationError as e:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this action",
            ) from e
        except Exception as e:
            logger.exception("Role check error")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error checking permissions",
            ) from e

    return role_checker


# Type aliases for common dependency patterns
CurrentUser = Annotated[Any, Depends(get_current_user)]
OptionalUser = Annotated[Any | None, Depends(get_current_user_optional)]
AdminUser = Annotated[Any, Depends(require_role(["admin"]))]
