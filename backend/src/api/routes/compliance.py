"""Compliance & Data Management API Routes (US-929)."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from src.api.deps import AdminUser, CurrentUser
from src.services.compliance_service import ComplianceError, ComplianceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/compliance", tags=["compliance"])
compliance_service = ComplianceService()


# Request/Response Models
class DataExportResponse(BaseModel):
    """Data export response."""

    export_date: str
    user_id: str
    user_profile: dict[str, Any] | None = None
    user_settings: dict[str, Any] | None = None
    onboarding_state: list[dict[str, Any]] | dict[str, Any] | None = None
    semantic_memory: list[Any] | None = None
    prospective_memory: list[Any] | None = None
    conversations: list[Any] | None = None
    messages: list[Any] | None = None
    documents: list[Any] | None = None
    audit_log: list[Any] | None = None


class DeleteDataRequest(BaseModel):
    """Request to delete user data."""

    confirmation: str = Field(..., min_length=1, max_length=100)


class DeleteDataResponse(BaseModel):
    """Response for data deletion."""

    deleted: bool
    user_id: str
    summary: dict[str, Any]


class DigitalTwinDeleteResponse(BaseModel):
    """Response for digital twin deletion."""

    deleted: bool
    user_id: str
    deleted_at: str


class ConsentStatusResponse(BaseModel):
    """Consent status response."""

    email_analysis: bool
    document_learning: bool
    crm_processing: bool
    writing_style_learning: bool


class UpdateConsentRequest(BaseModel):
    """Request to update consent."""

    category: str = Field(..., min_length=1, max_length=50)
    granted: bool


class UpdateConsentResponse(BaseModel):
    """Response for consent update."""

    category: str
    granted: bool
    updated_at: str


class MarkDontLearnRequest(BaseModel):
    """Request to mark content as don't learn."""

    content_ids: list[str] = Field(..., min_length=1, max_length=100)


class MarkDontLearnResponse(BaseModel):
    """Response for mark don't learn."""

    marked_count: int
    total_requested: int


class RetentionPoliciesResponse(BaseModel):
    """Retention policies response."""

    audit_query_logs: dict[str, Any]
    audit_write_logs: dict[str, Any]
    email_data: dict[str, Any]
    conversation_history: dict[str, Any]
    note: str | None = None


class CompanyDataExportResponse(BaseModel):
    """Company data export response."""

    export_date: str
    company_id: str
    exported_by: str
    company: dict[str, Any] | None = None
    users: list[Any] | None = None
    documents: list[Any] | None = None
    corporate_memory: dict[str, Any] | None = None


# Routes
@router.get(
    "/data/export",
    response_model=DataExportResponse,
    status_code=status.HTTP_200_OK,
)
async def get_data_export(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Export all user data (GDPR right to access).

    Returns a structured JSON export of all user data including:
    - Profile and settings
    - Onboarding state
    - Semantic and prospective memory
    - Conversations and messages
    - Uploaded documents
    - Audit log entries

    Args:
        current_user: Authenticated user.

    Returns:
        Structured export data.
    """
    try:
        return await compliance_service.export_user_data(current_user.id)
    except Exception as e:
        logger.exception("Error exporting user data")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export user data",
        ) from e


@router.post(
    "/data/delete",
    response_model=DeleteDataResponse,
    status_code=status.HTTP_200_OK,
)
async def delete_user_data(
    request_data: DeleteDataRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Delete all user data (GDPR right to erasure).

    Requires explicit confirmation text "DELETE MY DATA".

    Warning: This action is irreversible and will cascade delete:
    - Memories (semantic, prospective)
    - Messages and conversations
    - Documents uploaded by user
    - Onboarding state
    - Settings and profile

    Args:
        request_data: Must contain confirmation: "DELETE MY DATA"
        current_user: Authenticated user.

    Returns:
        Summary of deleted data.
    """
    if request_data.confirmation != "DELETE MY DATA":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Confirmation must be exactly "DELETE MY DATA"',
        )

    try:
        return await compliance_service.delete_user_data(
            current_user.id,
            request_data.confirmation,
        )
    except Exception as e:
        logger.exception("Error deleting user data")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete user data",
        ) from e


@router.delete(
    "/data/digital-twin",
    response_model=DigitalTwinDeleteResponse,
    status_code=status.HTTP_200_OK,
)
async def delete_digital_twin(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Delete Digital Twin data only (writing style, communication patterns).

    This removes ARIA's learned understanding of your writing style and
    communication patterns while preserving other data.

    Args:
        current_user: Authenticated user.

    Returns:
        Deletion confirmation with timestamp.
    """
    try:
        return await compliance_service.delete_digital_twin(current_user.id)
    except Exception as e:
        logger.exception("Error deleting digital twin")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete digital twin",
        ) from e


@router.get(
    "/consent",
    response_model=ConsentStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def get_consent_status(
    current_user: CurrentUser,
) -> dict[str, bool]:
    """Get current consent status for all data processing categories.

    Returns the current granted/revoked status for:
    - Email analysis
    - Document learning
    - CRM processing
    - Writing style learning

    Args:
        current_user: Authenticated user.

    Returns:
        Dictionary of consent categories to boolean status.
    """
    try:
        return await compliance_service.get_consent_status(current_user.id)
    except Exception as e:
        logger.exception("Error getting consent status")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get consent status",
        ) from e


@router.patch(
    "/consent",
    response_model=UpdateConsentResponse,
    status_code=status.HTTP_200_OK,
)
async def update_consent(
    request_data: UpdateConsentRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Update consent for a specific data processing category.

    Args:
        request_data: Category to update and new granted status.
        current_user: Authenticated user.

    Returns:
        Updated consent status with timestamp.
    """
    try:
        return await compliance_service.update_consent(
            current_user.id,
            request_data.category,
            request_data.granted,
        )
    except ComplianceError as e:
        logger.exception("Error updating consent - compliance error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.exception("Error updating consent")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update consent",
        ) from e


@router.post(
    "/data/dont-learn",
    response_model=MarkDontLearnResponse,
    status_code=status.HTTP_200_OK,
)
async def mark_dont_learn(
    request_data: MarkDontLearnRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Mark specific content as off-limits for learning.

    Marks semantic memory entries as excluded so ARIA will not
    learn from or reference this content.

    Args:
        request_data: List of content IDs to mark as excluded.
        current_user: Authenticated user.

    Returns:
        Count of successfully marked entries.
    """
    try:
        return await compliance_service.mark_dont_learn(
            current_user.id,
            request_data.content_ids,
        )
    except Exception as e:
        logger.exception("Error marking don't learn")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark content as don't learn",
        ) from e


@router.get(
    "/retention",
    response_model=RetentionPoliciesResponse,
    status_code=status.HTTP_200_OK,
)
async def get_retention_policies(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get data retention policy definitions.

    Returns information about how long different types of data
    are retained before automatic deletion.

    Args:
        current_user: Authenticated user.

    Returns:
        Dictionary of retention policies.
    """
    try:
        # Get user's company_id for context
        from src.db.supabase import SupabaseClient

        profile = await SupabaseClient.get_user_by_id(current_user.id)
        company_id = profile.get("company_id", "unknown")

        return await compliance_service.get_retention_policies(company_id)
    except Exception as e:
        logger.exception("Error getting retention policies")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get retention policies",
        ) from e


@router.get(
    "/data/export/company",
    response_model=CompanyDataExportResponse,
    status_code=status.HTTP_200_OK,
)
async def export_company_data(
    current_user: AdminUser,
) -> dict[str, Any]:
    """Export all company data (admin only).

    Requires admin role. Exports all data associated with the company
    including all users, documents, and corporate memory.

    Args:
        current_user: Authenticated admin user.

    Returns:
        Structured company data export.

    Raises:
        HTTPException: If user is not an admin.
    """
    try:
        from src.core.exceptions import NotFoundError
        from src.db.supabase import SupabaseClient

        profile = await SupabaseClient.get_user_by_id(current_user.id)
        company_id = profile.get("company_id")

        if not company_id:
            raise NotFoundError("Company", "not found")

        return await compliance_service.export_company_data(
            company_id,
            current_user.id,
        )
    except NotFoundError:
        raise
    except Exception as e:
        logger.exception("Error exporting company data")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export company data",
        ) from e
