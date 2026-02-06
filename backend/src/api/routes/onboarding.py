"""API routes for onboarding state machine."""

import logging
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, EmailStr

from src.api.deps import CurrentUser
from src.db.supabase import SupabaseClient
from src.onboarding.company_discovery import CompanyDiscoveryService
from src.onboarding.document_ingestion import DocumentIngestionService
from src.onboarding.email_integration import (
    EmailIntegrationConfig,
    EmailIntegrationService,
)
from src.onboarding.models import (
    OnboardingStateResponse,
    OnboardingStep,
    StepCompletionRequest,
    StepSkipRequest,
)
from src.onboarding.orchestrator import OnboardingOrchestrator
from src.onboarding.stakeholder_step import StakeholderStepService
from src.onboarding.writing_analysis import WritingAnalysisService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


def _get_orchestrator() -> OnboardingOrchestrator:
    return OnboardingOrchestrator()


@router.get("/state", response_model=OnboardingStateResponse)
async def get_onboarding_state(
    current_user: CurrentUser,
) -> OnboardingStateResponse:
    """Get current onboarding state for authenticated user."""
    orchestrator = _get_orchestrator()
    return await orchestrator.get_or_create_state(current_user.id)


@router.post("/steps/{step}/complete", response_model=OnboardingStateResponse)
async def complete_step(
    step: OnboardingStep,
    body: StepCompletionRequest,
    current_user: CurrentUser,
) -> OnboardingStateResponse:
    """Complete a step and advance to the next."""
    orchestrator = _get_orchestrator()
    try:
        return await orchestrator.complete_step(current_user.id, step, body.step_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/steps/{step}/skip", response_model=OnboardingStateResponse)
async def skip_step(
    step: OnboardingStep,
    current_user: CurrentUser,
    body: StepSkipRequest = StepSkipRequest(),
) -> OnboardingStateResponse:
    """Skip a non-critical step."""
    orchestrator = _get_orchestrator()
    try:
        return await orchestrator.skip_step(current_user.id, step, body.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/routing")
async def get_routing(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Determine post-auth routing for user."""
    orchestrator = _get_orchestrator()
    destination = await orchestrator.get_routing_decision(current_user.id)
    return {"route": destination}


# Company discovery endpoints (US-902)


class EmailValidationRequest(BaseModel):
    """Request body for email validation."""

    email: EmailStr


class CompanyDiscoveryRequest(BaseModel):
    """Request body for company discovery submission."""

    company_name: str
    website: str
    email: EmailStr


def _get_company_service() -> CompanyDiscoveryService:
    """Get company discovery service instance."""
    return CompanyDiscoveryService()


@router.post("/company-discovery/validate-email")
async def validate_email(
    body: EmailValidationRequest,
) -> dict[str, Any]:
    """Check if email domain is corporate (not personal).

    Returns validation result with reason if rejected.
    """
    service = _get_company_service()
    return await service.validate_email_domain(body.email)


@router.get("/enrichment/status")
async def get_enrichment_status(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get current enrichment status for user's company.

    Returns enrichment completion status, quality score,
    and classification if available.
    """
    db = SupabaseClient.get_client()

    # Get user's company
    profile = (
        db.table("user_profiles")
        .select("company_id")
        .eq("id", current_user.id)
        .maybe_single()
        .execute()
    )
    if not profile.data or not profile.data.get("company_id"):
        return {"status": "no_company"}

    company = (
        db.table("companies")
        .select("settings")
        .eq("id", profile.data["company_id"])
        .maybe_single()
        .execute()
    )
    if not company.data:
        return {"status": "not_found"}

    company_settings = company.data.get("settings", {})
    if "enrichment_quality_score" in company_settings:
        return {
            "status": "complete",
            "quality_score": company_settings["enrichment_quality_score"],
            "classification": company_settings.get("classification", {}),
            "enriched_at": company_settings.get("enriched_at"),
        }

    return {"status": "in_progress"}


@router.post("/company-discovery/submit")
async def submit_company_discovery(
    body: CompanyDiscoveryRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Submit company discovery and run life sciences gate check.

    Validates email domain, checks if company is in life sciences vertical,
    creates/links company profile, and triggers enrichment.

    For non-life-sciences companies, adds to waitlist and returns
    a graceful message (not an error).
    """
    service = _get_company_service()
    result = await service.submit_company_discovery(
        user_id=current_user.id,
        company_name=body.company_name,
        website=body.website,
        email=body.email,
    )

    # Email validation errors are 400
    if not result["success"] and result.get("type") == "email_validation":
        raise HTTPException(status_code=400, detail=result["error"])

    # Other results (including vertical mismatch) return 200
    # with the full result for frontend handling
    return result


# Document upload endpoints (US-904)


def _get_doc_service() -> DocumentIngestionService:
    """Get document ingestion service instance."""
    return DocumentIngestionService()


@router.post("/documents/upload")
async def upload_document(
    current_user: CurrentUser,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """Upload and process a company document.

    Validates file type and size, uploads to Supabase Storage,
    and triggers the asynchronous processing pipeline.
    """
    db = SupabaseClient.get_client()

    # Get user's company
    profile = (
        db.table("user_profiles")
        .select("company_id")
        .eq("id", current_user.id)
        .maybe_single()
        .execute()
    )
    if not profile.data or not profile.data.get("company_id"):
        raise HTTPException(status_code=400, detail="No company associated with user")

    company_id = profile.data["company_id"]
    content = await file.read()
    doc_service = _get_doc_service()

    # Validate
    validation = await doc_service.validate_upload(
        company_id, file.filename or "unknown", len(content), file.content_type or ""
    )
    if not validation["valid"]:
        raise HTTPException(status_code=400, detail=validation["reason"])

    # Upload and process
    doc = await doc_service.upload_and_process(
        company_id=company_id,
        user_id=current_user.id,
        filename=file.filename or "unknown",
        file_content=content,
        content_type=file.content_type or "",
    )
    return doc


@router.get("/documents")
async def get_documents(
    current_user: CurrentUser,
) -> list[dict[str, Any]]:
    """Get all documents for the user's company."""
    db = SupabaseClient.get_client()

    profile = (
        db.table("user_profiles")
        .select("company_id")
        .eq("id", current_user.id)
        .maybe_single()
        .execute()
    )
    if not profile.data or not profile.data.get("company_id"):
        return []

    doc_service = _get_doc_service()
    return await doc_service.get_company_documents(profile.data["company_id"])


@router.get("/documents/{doc_id}/status")
async def get_document_status(
    doc_id: str,
    current_user: CurrentUser,  # noqa: ARG001
) -> dict[str, Any]:
    """Get processing status for a specific document."""
    db = SupabaseClient.get_client()

    result = (
        db.table("company_documents")
        .select("processing_status, processing_progress, chunk_count, entity_count, quality_score")
        .eq("id", doc_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found")
    return result.data


# Stakeholder mapping endpoints (US-905)


class StakeholderInput(BaseModel):
    """Individual stakeholder data."""

    name: str
    title: str | None = None
    company: str | None = None
    email: str | None = None
    relationship_type: str = (
        "other"  # champion, decision_maker, influencer, end_user, blocker, other
    )
    notes: str | None = None


class StakeholderStepRequest(BaseModel):
    """Request body for saving stakeholders."""

    stakeholders: list[StakeholderInput] = []


def _get_stakeholder_service() -> StakeholderStepService:
    """Get stakeholder step service instance."""
    db = SupabaseClient.get_client()
    return StakeholderStepService(db)


@router.post("/stakeholders/save")
async def save_stakeholders(
    body: StakeholderStepRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Save stakeholders from onboarding step.

    Stores stakeholders in onboarding step_data, records episodic memory,
    and updates readiness score for relationship_graph.

    Returns:
        Dictionary with count and stakeholder IDs.
    """
    service = _get_stakeholder_service()

    # Convert Pydantic models to dicts
    stakeholders_data = [s.model_dump() for s in body.stakeholders]

    result = await service.save_stakeholders(current_user.id, stakeholders_data)
    return result


@router.get("/stakeholders")
async def get_stakeholders(
    current_user: CurrentUser,
) -> list[dict[str, Any]]:
    """Get user's stakeholders from onboarding.

    Returns list of stakeholders mapped during onboarding.
    """
    service = _get_stakeholder_service()
    stakeholders = await service.get_stakeholders(current_user.id)
    return [s.to_dict() for s in stakeholders]


# Writing sample analysis endpoints (US-906)


class WritingSamplesRequest(BaseModel):
    """Request body for writing sample analysis."""

    samples: list[str]  # Raw text samples


def _get_writing_service() -> WritingAnalysisService:
    """Get writing analysis service instance."""
    return WritingAnalysisService()


@router.post("/writing-analysis/analyze")
async def analyze_writing(
    body: WritingSamplesRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Analyze writing samples and generate style fingerprint.

    Accepts raw text samples (emails, documents, reports) and returns
    a comprehensive WritingStyleFingerprint stored in the Digital Twin.
    """
    service = _get_writing_service()
    fingerprint = await service.analyze_samples(current_user.id, body.samples)
    return fingerprint.model_dump()


@router.get("/writing-analysis/fingerprint")
async def get_writing_fingerprint(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get stored writing style fingerprint.

    Returns the user's current WritingStyleFingerprint from the Digital Twin,
    or a status indicator if not yet analyzed.
    """
    service = _get_writing_service()
    fp = await service.get_fingerprint(current_user.id)
    if not fp:
        return {"status": "not_analyzed"}
    return fp.model_dump()


# Email integration endpoints (US-907)


class EmailConnectRequest(BaseModel):
    """Request body for initiating email OAuth."""

    provider: str  # "google" or "microsoft"


def _get_email_service() -> EmailIntegrationService:
    """Get email integration service instance."""
    return EmailIntegrationService()


@router.post("/email/connect")
async def connect_email(
    body: EmailConnectRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Initiate OAuth flow for email provider.

    Generates an OAuth authorization URL for the user to redirect to.
    Supports Google Workspace (Gmail) and Microsoft 365 (Outlook).

    Returns:
        Dict with auth_url, connection_id, and status.
    """
    if body.provider not in ("google", "microsoft"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid provider '{body.provider}'. Must be 'google' or 'microsoft'.",
        )

    service = _get_email_service()
    return await service.initiate_oauth(current_user.id, body.provider)


@router.get("/email/status")
async def email_status(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Check email connection status for both providers.

    Returns connection status for Gmail and Outlook, including
    whether connected and when the connection was established.
    """
    service = _get_email_service()
    google = await service.check_connection_status(current_user.id, "google")
    microsoft = await service.check_connection_status(current_user.id, "microsoft")
    return {"google": google, "microsoft": microsoft}


@router.post("/email/privacy")
async def save_email_privacy(
    body: EmailIntegrationConfig,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Save email privacy exclusions and ingestion preferences.

    Saves the user's privacy configuration before email ingestion begins,
    including excluded senders/domains/categories, ingestion scope,
    and attachment preferences.

    Updates readiness scores and records the event in episodic memory.

    Returns:
        Dict with save status and exclusion count.
    """
    if body.provider not in ("google", "microsoft"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid provider '{body.provider}'. Must be 'google' or 'microsoft'.",
        )

    service = _get_email_service()
    return await service.save_privacy_config(current_user.id, body)
