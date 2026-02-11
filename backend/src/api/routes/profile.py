"""Profile Page API Routes (US-921).

Multi-section profile page: user details, company details, documents,
integrations. Pre-populated from onboarding data. Saves trigger US-922
Memory Merge Pipeline.
"""

import logging
from enum import Enum
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from src.api.deps import CurrentUser
from src.core.exceptions import ARIAException, NotFoundError, sanitize_error
from src.services.profile_service import ProfileService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profile", tags=["profile"])


def _get_service() -> ProfileService:
    """Get ProfileService instance."""
    return ProfileService()


# --- Pydantic Models ---


class DefaultTone(str, Enum):
    """Allowed tone values."""

    FORMAL = "formal"
    FRIENDLY = "friendly"
    URGENT = "urgent"


class UpdateUserDetailsRequest(BaseModel):
    """Request to update user profile details."""

    full_name: str | None = Field(None, min_length=1, max_length=200)
    title: str | None = Field(None, min_length=1, max_length=200)
    department: str | None = Field(None, min_length=1, max_length=200)
    linkedin_url: str | None = Field(None, max_length=500)
    avatar_url: str | None = Field(None, max_length=500)
    communication_preferences: dict[str, Any] | None = None
    privacy_exclusions: list[str] | None = None
    default_tone: DefaultTone | None = None
    tracked_competitors: list[str] | None = None

    @field_validator("linkedin_url")
    @classmethod
    def validate_linkedin_url(cls, v: str | None) -> str | None:
        """Validate LinkedIn URL format."""
        if v is None:
            return v
        if not v.startswith(("https://linkedin.com/", "https://www.linkedin.com/")):
            raise ValueError(
                "LinkedIn URL must start with https://linkedin.com/ or https://www.linkedin.com/"
            )
        return v


class UpdateCompanyDetailsRequest(BaseModel):
    """Request to update company details (admin only)."""

    name: str | None = Field(None, min_length=1, max_length=200)
    website: str | None = Field(None, max_length=500)
    industry: str | None = Field(None, min_length=1, max_length=200)
    sub_vertical: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    key_products: list[str] | None = None


class UpdatePreferencesRequest(BaseModel):
    """Request to update notification/communication preferences."""

    communication_preferences: dict[str, Any] | None = None
    default_tone: DefaultTone | None = None
    tracked_competitors: list[str] | None = None
    privacy_exclusions: list[str] | None = None


# --- Route Handlers ---


@router.get("")
async def get_profile(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get full profile: user details + company + integrations.

    Returns the full profile if a user_profiles row exists, otherwise returns
    a skeleton profile from the auth token so the frontend can render without
    errors for freshly-created users who haven't completed onboarding.

    Args:
        current_user: The authenticated user.

    Returns:
        Merged profile view.
    """
    try:
        service = _get_service()
        return await service.get_full_profile(current_user.id)
    except Exception as e:
        # If the profile row simply doesn't exist yet, return a skeleton
        # so the frontend can proceed (e.g. redirect to onboarding).
        # The error chain may be: PGRST116 → DatabaseError → ARIAException,
        # so check the full cause chain for the original error.
        err_chain = str(e).lower()
        cause = e.__cause__
        while cause:
            err_chain += " " + str(cause).lower()
            cause = cause.__cause__
        if (
            isinstance(e, NotFoundError)
            or "not found" in err_chain
            or "pgrst116" in err_chain
        ):
            user_meta = getattr(current_user, "user_metadata", {}) or {}
            logger.info(
                "No user_profiles row, returning skeleton profile",
                extra={"user_id": current_user.id},
            )
            return {
                "user": {
                    "id": current_user.id,
                    "full_name": user_meta.get("full_name"),
                    "title": None,
                    "department": None,
                    "linkedin_url": None,
                    "avatar_url": None,
                    "company_id": None,
                    "role": "user",
                    "communication_preferences": {},
                    "privacy_exclusions": [],
                    "default_tone": "friendly",
                    "tracked_competitors": [],
                    "created_at": None,
                    "updated_at": None,
                },
                "company": None,
                "integrations": [],
            }
        logger.exception("Error fetching profile")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch profile",
        ) from e


@router.put("/user")
async def update_user_details(
    data: UpdateUserDetailsRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Update user profile details.

    Args:
        data: User detail fields to update.
        current_user: The authenticated user.

    Returns:
        Updated user profile data.
    """
    try:
        service = _get_service()
        update_dict = data.model_dump(exclude_none=True)
        # Convert enum to string value
        if "default_tone" in update_dict:
            update_dict["default_tone"] = update_dict["default_tone"].value
        return await service.update_user_details(
            user_id=current_user.id,
            data=update_dict,
        )
    except NotFoundError as e:
        logger.exception("User profile not found for update")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=sanitize_error(e),
        ) from e
    except Exception as e:
        logger.exception("Error updating user details")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user details",
        ) from e


@router.put("/company")
async def update_company_details(
    data: UpdateCompanyDetailsRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Update company details (admin only).

    Args:
        data: Company detail fields to update.
        current_user: The authenticated user.

    Returns:
        Updated company data.
    """
    try:
        service = _get_service()
        update_dict = data.model_dump(exclude_none=True)
        return await service.update_company_details(
            user_id=current_user.id,
            data=update_dict,
        )
    except ARIAException as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
        ) from e
    except NotFoundError as e:
        logger.exception("Company not found for update")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=sanitize_error(e),
        ) from e
    except Exception as e:
        logger.exception("Error updating company details")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update company details",
        ) from e


@router.get("/documents")
async def list_documents(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """List all documents (company + user).

    Args:
        current_user: The authenticated user.

    Returns:
        Dict with company_documents and user_documents.
    """
    try:
        service = _get_service()
        return await service.list_documents(current_user.id)
    except Exception as e:
        logger.exception("Error listing documents")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list documents",
        ) from e


@router.put("/preferences")
async def update_preferences(
    data: UpdatePreferencesRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Update notification/communication preferences.

    Args:
        data: Preference fields to update.
        current_user: The authenticated user.

    Returns:
        Updated preference data.
    """
    try:
        service = _get_service()
        update_dict = data.model_dump(exclude_none=True)
        # Convert enum to string value
        if "default_tone" in update_dict:
            update_dict["default_tone"] = update_dict["default_tone"].value
        return await service.update_preferences(
            user_id=current_user.id,
            data=update_dict,
        )
    except NotFoundError as e:
        logger.exception("Preferences not found for update")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=sanitize_error(e),
        ) from e
    except Exception as e:
        logger.exception("Error updating preferences")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update preferences",
        ) from e
