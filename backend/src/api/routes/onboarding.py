"""API routes for onboarding state machine."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from src.api.deps import CurrentUser
from src.db.supabase import SupabaseClient
from src.onboarding.company_discovery import CompanyDiscoveryService
from src.onboarding.models import (
    OnboardingStateResponse,
    OnboardingStep,
    StepCompletionRequest,
    StepSkipRequest,
)
from src.onboarding.orchestrator import OnboardingOrchestrator

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
