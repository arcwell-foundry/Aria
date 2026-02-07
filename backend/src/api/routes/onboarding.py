"""API routes for onboarding state machine."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, EmailStr

from src.api.deps import CurrentUser
from src.db.supabase import SupabaseClient
from src.memory.episodic import Episode
from src.onboarding.company_discovery import CompanyDiscoveryService
from src.onboarding.document_ingestion import DocumentIngestionService
from src.onboarding.email_integration import (
    EmailIntegrationConfig,
    EmailIntegrationService,
)
from src.onboarding.first_goal import (
    FirstGoalService,
)

if TYPE_CHECKING:
    from src.onboarding.cross_user import CrossUserAccelerationService
    from src.onboarding.personality_calibrator import PersonalityCalibrator
    from src.onboarding.skill_recommender import SkillRecommendationEngine
from src.onboarding.integration_wizard import (
    IntegrationPreferences,
    IntegrationWizardService,
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


# Email bootstrap status endpoint (US-908)


@router.get("/email/bootstrap/status")
async def email_bootstrap_status(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get email bootstrap processing status.

    Returns the current state of the priority email bootstrap,
    including counts of emails processed, contacts discovered,
    active threads, and commitments detected.
    """
    db = SupabaseClient.get_client()

    result = (
        db.table("onboarding_state")
        .select("metadata")
        .eq("user_id", current_user.id)
        .maybe_single()
        .execute()
    )

    if not result or not result.data:
        return {"status": "not_started"}

    metadata: dict[str, Any] = result.data.get("metadata", {})  # type: ignore[union-attr]
    bootstrap_data = metadata.get("email_bootstrap")

    if not bootstrap_data:
        return {"status": "not_started"}

    return bootstrap_data


# Integration Wizard endpoints (US-909)


class IntegrationConnectRequest(BaseModel):
    """Request body for initiating integration OAuth."""

    app_name: str  # "SALESFORCE", "HUBSPOT", "GOOGLECALENDAR", "OUTLOOK365CALENDAR", "SLACK"


class IntegrationDisconnectRequest(BaseModel):
    """Request body for disconnecting an integration."""

    app_name: str  # Same as above


class IntegrationPreferencesRequest(BaseModel):
    """Request body for saving integration preferences."""

    slack_channels: list[str] = []
    notification_enabled: bool = True
    sync_frequency_hours: int = 1


def _get_integration_wizard_service() -> IntegrationWizardService:
    """Get integration wizard service instance."""
    return IntegrationWizardService()


@router.get("/integrations/status")
async def get_integration_status(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get connection status for all integrations.

    Returns status for CRM (Salesforce, HubSpot), Calendar (Google, Outlook),
    and Slack integrations, including connection state, connected timestamp,
    and user preferences.

    Returns:
        Dict with integration statuses grouped by category and preferences.
    """
    service = _get_integration_wizard_service()
    return await service.get_integration_status(current_user.id)


@router.post("/integrations/connect")
async def connect_integration(
    body: IntegrationConnectRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Initiate OAuth flow for an integration.

    Generates an OAuth authorization URL for the user to redirect to.
    Supports Salesforce, HubSpot, Google Calendar, Outlook Calendar, and Slack.

    Returns:
        Dict with auth_url, connection_id, and status.
    """
    service = _get_integration_wizard_service()
    return await service.connect_integration(current_user.id, body.app_name)


@router.post("/integrations/disconnect")
async def disconnect_integration(
    body: IntegrationDisconnectRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Disconnect an integration.

    Revokes the OAuth connection and removes local records.

    Returns:
        Dict with status indicating success or error.
    """
    service = _get_integration_wizard_service()
    return await service.disconnect_integration(current_user.id, body.app_name)


@router.post("/integrations/preferences")
async def save_integration_preferences(
    body: IntegrationPreferencesRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Save integration preferences and update readiness scores.

    Saves notification routing preferences, sync frequency, and
    Slack channel configuration. Updates the integrations readiness score.

    Returns:
        Dict with save status and connected count.
    """
    service = _get_integration_wizard_service()
    preferences = IntegrationPreferences(
        slack_channels=body.slack_channels,
        notification_enabled=body.notification_enabled,
        sync_frequency_hours=body.sync_frequency_hours,
    )
    return await service.save_integration_preferences(current_user.id, preferences)


# First Goal endpoints (US-910)


class FirstGoalSuggestionsResponse(BaseModel):
    """Response model for first goal suggestions."""

    suggestions: list[dict[str, Any]]
    templates: dict[str, list[dict[str, Any]]]
    enrichment_context: dict[str, Any] | None = None


class FirstGoalCreateRequest(BaseModel):
    """Request body for creating first goal."""

    title: str
    description: str | None = None
    goal_type: str | None = None  # "lead_gen", "research", "outreach", "analysis", "custom"


class SmartValidationRequest(BaseModel):
    """Request body for SMART validation."""

    title: str
    description: str | None = None


def _get_first_goal_service() -> FirstGoalService:
    """Get first goal service instance."""
    return FirstGoalService()


@router.get("/first-goal/suggestions", response_model=FirstGoalSuggestionsResponse)
async def get_first_goal_suggestions(
    current_user: CurrentUser,
) -> FirstGoalSuggestionsResponse:
    """Get personalized goal suggestions and templates.

    Analyzes onboarding data (company classification, user role,
    connected integrations) to suggest relevant goals. Also provides
    role-based goal templates.

    Returns:
        Dict with suggestions list, templates by category, and enrichment context.
    """
    service = _get_first_goal_service()

    # Get user profile to determine role for templates
    db = SupabaseClient.get_client()
    profile = (
        db.table("user_profiles")
        .select("role, department")
        .eq("id", current_user.id)
        .maybe_single()
        .execute()
    )

    user_role = profile.data.get("role") if profile and profile.data else None

    # Get suggestions
    suggestions = await service.suggest_goals(current_user.id)

    # Get templates filtered by role
    templates = service.get_goal_templates(user_role)

    # Get enrichment context for UI display
    enrichment_context = await _get_enrichment_context(current_user.id)

    return FirstGoalSuggestionsResponse(
        suggestions=[s.model_dump() for s in suggestions],
        templates={
            category: [t.model_dump() for t in template_list]
            for category, template_list in templates.items()
        },
        enrichment_context=enrichment_context,
    )


@router.post("/first-goal/validate-smart")
async def validate_goal_smart(
    body: SmartValidationRequest,
    current_user: CurrentUser,  # noqa: ARG001
) -> dict[str, Any]:
    """Validate a goal against SMART criteria.

    Uses LLM to assess if goal is Specific, Measurable, Achievable,
    Relevant, and Time-bound. Provides feedback and refined version.

    Returns:
        Dict with SMART validation result, score, and refined version.
    """
    service = _get_first_goal_service()
    validation = await service.validate_smart(body.title, body.description)
    return validation.model_dump()


@router.post("/first-goal/create")
async def create_first_goal(
    body: FirstGoalCreateRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Create the first goal and trigger agent activation.

    Creates the goal using the existing Goal system, assigns appropriate
    agents, updates readiness score, and creates prospective memory
    entries for milestone tracking.

    This is the final step of onboarding and triggers agent activation.

    Returns:
        Dict with created goal and agent assignments.
    """
    from src.models.goal import GoalType

    service = _get_first_goal_service()

    # Parse goal type from string
    goal_type = GoalType.CUSTOM
    if body.goal_type:
        try:
            goal_type = GoalType(body.goal_type)
        except ValueError:
            logger.warning(f"Invalid goal_type '{body.goal_type}', using CUSTOM")

    result = await service.create_first_goal(
        user_id=current_user.id,
        title=body.title,
        description=body.description,
        goal_type=goal_type,
    )

    return result


async def _get_enrichment_context(user_id: str) -> dict[str, Any] | None:
    """Get enrichment context for goal suggestions UI.

    Args:
        user_id: The user's UUID.

    Returns:
        Enrichment context dict with company classification and connected integrations.
    """
    db = SupabaseClient.get_client()

    try:
        # Get company classification
        profile = (
            db.table("user_profiles")
            .select("companies(*)")
            .eq("id", user_id)
            .maybe_single()
            .execute()
        )

        company_data = None
        if profile and profile.data:
            company = profile.data.get("companies")
            if company:
                settings = company.get("settings", {})
                company_data = {
                    "name": company.get("name"),
                    "classification": settings.get("classification"),
                }

        # Get connected integrations
        integrations = (
            db.table("user_integrations")
            .select("provider, status")
            .eq("user_id", user_id)
            .eq("status", "active")
            .execute()
        )

        connected_providers = (
            [i["provider"] for i in integrations.data] if integrations and integrations.data else []
        )

        return {
            "company": company_data,
            "connected_integrations": connected_providers,
        }

    except Exception as e:
        logger.warning(f"Failed to get enrichment context: {e}")
        return None


# Activation endpoint (US-911)


@router.post("/activate")
async def activate_aria(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Complete onboarding and activate ARIA.

    Marks the activation step as complete, fires off background
    memory construction (US-911), and redirects user to dashboard.

    Returns:
        Dict with activation status and dashboard redirect.
    """
    orchestrator = _get_orchestrator()

    try:
        await orchestrator.complete_step(
            current_user.id,
            OnboardingStep.ACTIVATION,
            {},
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # Run personality calibration before agents are spawned (US-919)
    from src.onboarding.personality_calibrator import PersonalityCalibrator

    calibrator = PersonalityCalibrator()
    asyncio.create_task(calibrator.calibrate(current_user.id))

    # Fire memory construction as a background task
    from src.onboarding.memory_constructor import MemoryConstructionOrchestrator

    constructor = MemoryConstructionOrchestrator()
    asyncio.create_task(constructor.run_construction(current_user.id))

    return {"status": "activated", "redirect": "/dashboard"}


# Knowledge Gap Detection endpoint (US-912)


@router.get("/gaps")
async def get_knowledge_gaps(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get current knowledge gaps by domain.

    Runs full gap analysis across Corporate Memory, Digital Twin,
    Competitive Intelligence, and Integration connectivity. Each gap
    generates a Prospective Memory entry for future resolution.

    Returns:
        GapAnalysisResult with gaps, completeness scores, and counts.
    """
    from src.onboarding.gap_detector import KnowledgeGapDetector

    detector = KnowledgeGapDetector()
    result = await detector.detect_gaps(current_user.id)
    return result.model_dump()


# Readiness Score endpoint (US-913)


@router.get("/readiness")
async def get_readiness(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get current readiness scores with overall calculation.

    Returns readiness breakdown across five domains with weighted
    overall score and confidence modifier. The readiness score indicates
    how well-initialized ARIA is for this user.

    Returns:
        ReadinessBreakdown with all sub-scores, overall, and confidence modifier.
    """
    from src.onboarding.readiness import OnboardingReadinessService

    service = OnboardingReadinessService()
    result = await service.get_readiness(current_user.id)
    return result.model_dump()


# First Conversation endpoint (US-914)


@router.get("/first-conversation")
async def get_first_conversation(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get or generate ARIA's first conversation message.

    Returns the intelligence-demonstrating first message that proves
    ARIA has done her homework. If not yet generated, triggers generation.

    Returns:
        FirstConversationMessage with content, memory delta, and metadata.
    """
    from src.onboarding.first_conversation import FirstConversationGenerator

    generator = FirstConversationGenerator()
    message = await generator.generate(current_user.id)
    return message.model_dump()


# Agent Activation Status endpoint (US-915)


@router.get("/activation-status")
async def get_activation_status(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get agent activation status after onboarding completion.

    Returns active goals created by the activation process, each
    with their assigned agent and current status.

    Returns:
        Dict with activations list and overall status.
    """
    db = SupabaseClient.get_client()

    # Query goals created by onboarding activation
    result = (
        db.table("goals")
        .select("id, title, description, status, progress, config, goal_agents(*)")
        .eq("user_id", current_user.id)
        .execute()
    )

    activations: list[dict[str, Any]] = []
    for goal in result.data or []:
        config = goal.get("config", {})
        if config.get("source") != "onboarding_activation":
            continue

        agents = goal.get("goal_agents", [])
        agent_type = config.get("agent", "")
        agent_status = "pending"
        if agents:
            agent_status = agents[0].get("status", "pending")

        activations.append(
            {
                "goal_id": goal["id"],
                "agent": agent_type,
                "goal_title": goal["title"],
                "task": goal["description"],
                "status": agent_status,
                "progress": goal.get("progress", 0),
            }
        )

    overall = "idle"
    if activations:
        statuses = {a["status"] for a in activations}
        if "running" in statuses:
            overall = "running"
        elif statuses == {"complete"}:
            overall = "complete"
        elif "pending" in statuses:
            overall = "pending"

    return {"status": overall, "activations": activations}


# Adaptive OODA Controller endpoints (US-916)


class AssessNextStepRequest(BaseModel):
    """Request model for triggering an OODA assessment."""

    completed_step: str


@router.post("/assess-next-step")
async def assess_next_step(
    request: AssessNextStepRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Trigger an OODA assessment for onboarding adaptation.

    Runs the full Observe → Orient → Decide → Act loop and returns
    the assessment with step reordering, emphasis, injected questions,
    and reasoning.

    Returns:
        OODAAssessment dict with observation, orientation, decision, reasoning.
    """
    from src.onboarding.adaptive_controller import OnboardingOODAController
    from src.onboarding.models import OnboardingStep

    try:
        step = OnboardingStep(request.completed_step)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid step: {request.completed_step}",
        ) from e

    ooda = OnboardingOODAController()
    assessment = await ooda.assess_next_step(current_user.id, step)
    return assessment.model_dump()


@router.get("/steps/{step}/injected-questions")
async def get_injected_questions(
    step: str,
    current_user: CurrentUser,
) -> list[dict[str, Any]]:
    """Get OODA-injected contextual questions for a step.

    Returns any questions ARIA's OODA controller has determined
    should be asked at this step based on what was learned so far.

    Returns:
        List of injected question dicts with question, context, insert_after_step.
    """
    from src.onboarding.adaptive_controller import OnboardingOODAController

    ooda = OnboardingOODAController()
    questions = await ooda.get_injected_questions(current_user.id, step)
    return [q.model_dump() for q in questions]


# Cross-user acceleration endpoints (US-917)


class CrossUserAccelerationResponse(BaseModel):
    """Response model for cross-user acceleration check."""

    exists: bool
    company_id: str | None
    company_name: str | None
    richness_score: int
    recommendation: str  # "skip", "partial", "full"
    facts: list[dict[str, Any]]  # Corporate memory facts


class ConfirmCompanyDataRequest(BaseModel):
    """Request body for confirming company data."""

    company_id: str
    corrections: dict[str, str] = {}


class ConfirmCompanyDataResponse(BaseModel):
    """Response model for confirming company data."""

    user_linked: bool
    steps_skipped: list[str]
    readiness_inherited: int
    corrections_applied: int


def _get_cross_user_service() -> "CrossUserAccelerationService":
    """Get cross-user acceleration service instance."""
    from src.onboarding.cross_user import CrossUserAccelerationService

    db = SupabaseClient.get_client()
    return CrossUserAccelerationService(db=db)


@router.get(
    "/cross-user",
    response_model=CrossUserAccelerationResponse,
)
async def get_cross_user_acceleration(
    domain: str,
    current_user: CurrentUser,
) -> CrossUserAccelerationResponse:
    """Check if company domain exists in Corporate Memory.

    When user #2+ at a company starts onboarding, this endpoint detects
    existing Corporate Memory and recommends step skipping based on data richness.

    Privacy: Only returns corporate facts (excludes personal data from other users).

    Args:
        domain: Company domain to check (e.g., "acme-corp.com").
        current_user: Authenticated user.

    Returns:
        CrossUserAccelerationResponse with existence status, company info,
        richness score, recommendation, and corporate facts.

    Raises:
        HTTPException: 500 if service error occurs.
    """
    try:
        service = _get_cross_user_service()

        # Check if company exists
        check_result = service.check_company_exists(domain)

        # Get company facts if company exists
        facts: list[dict[str, Any]] = []
        if check_result.exists and check_result.company_id:
            memory_delta = service.get_company_memory_delta(
                check_result.company_id,
                current_user.id,
            )
            facts = memory_delta.get("facts", [])

        return CrossUserAccelerationResponse(
            exists=check_result.exists,
            company_id=check_result.company_id,
            company_name=check_result.company_name,
            richness_score=check_result.richness_score,
            recommendation=check_result.recommendation,
            facts=facts,
        )

    except Exception as e:
        logger.exception(f"Error checking cross-user acceleration for domain {domain}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to check company domain",
        ) from e


@router.post(
    "/cross-user/confirm",
    response_model=ConfirmCompanyDataResponse,
)
async def confirm_company_data(
    body: ConfirmCompanyDataRequest,
    current_user: CurrentUser,
) -> ConfirmCompanyDataResponse:
    """Confirm existing company data and link user to company.

    When user #2+ confirms their company data, this endpoint:
    1. Links user to company via user_profiles
    2. Applies any corrections provided by user
    3. Marks company_discovery and document_upload as skipped
    4. Inherits corporate_memory readiness score from company richness

    Args:
        body: Request with company_id and optional corrections.
        current_user: Authenticated user.

    Returns:
        ConfirmCompanyDataResponse with link status, skipped steps,
        inherited readiness score, and corrections applied count.

    Raises:
        HTTPException: 500 if service error occurs.
    """
    try:
        service = _get_cross_user_service()

        result = service.confirm_company_data(
            company_id=body.company_id,
            user_id=current_user.id,
            corrections=body.corrections,
        )

        return ConfirmCompanyDataResponse(
            user_linked=result["user_linked"],
            steps_skipped=result["steps_skipped"],
            readiness_inherited=result["readiness_inherited"],
            corrections_applied=result["corrections_applied"],
        )

    except Exception as e:
        logger.exception(f"Error confirming company data for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to confirm company data",
        ) from e


# Skills Pre-Configuration endpoints (US-918)


class SkillRecommendationsRequest(BaseModel):
    """Request body for getting skill recommendations."""

    company_type: str
    role: str = ""


class SkillRecommendationsResponse(BaseModel):
    """Response model for skill recommendations."""

    recommendations: list[dict[str, Any]]
    message: str | None = None


class SkillInstallRequest(BaseModel):
    """Request body for installing recommended skills."""

    skill_ids: list[str]


class SkillInstallResponse(BaseModel):
    """Response model for skill installation."""

    installed_count: int
    total_count: int
    failed_skills: list[str]


def _get_skill_recommender() -> "SkillRecommendationEngine":
    """Get skill recommendation engine instance."""
    from src.onboarding.skill_recommender import SkillRecommendationEngine

    return SkillRecommendationEngine()


@router.post(
    "/skills/recommendations",
    response_model=SkillRecommendationsResponse,
)
async def get_skill_recommendations(
    body: SkillRecommendationsRequest,
    current_user: CurrentUser,  # noqa: ARG001 - Required for auth but not used in recommendations
) -> SkillRecommendationsResponse:
    """Get skill recommendations based on company type and role.

    Analyzes the user's company classification from enrichment (US-903)
    and returns relevant skills recommended for pre-installation at
    COMMUNITY trust level.

    Args:
        body: Request with company_type and optional role.
        current_user: Authenticated user.

    Returns:
        SkillRecommendationsResponse with recommended skills list and message.

    Raises:
        HTTPException: 500 if service error occurs.
    """
    try:
        engine = _get_skill_recommender()
        recommendations = await engine.recommend(body.company_type, body.role)

        # Generate a personalized message
        message = (
            f"Based on your role in {body.company_type}, I've equipped myself with "
            f"these capabilities. You can add or remove any before confirming."
        )

        return SkillRecommendationsResponse(
            recommendations=recommendations,
            message=message,
        )

    except Exception as e:
        logger.exception(f"Error generating skill recommendations: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to generate skill recommendations",
        ) from e


@router.post(
    "/skills/install",
    response_model=SkillInstallResponse,
)
async def install_recommended_skills(
    body: SkillInstallRequest,
    current_user: CurrentUser,
) -> SkillInstallResponse:
    """Install selected recommended skills at COMMUNITY trust level.

    Pre-installs skills selected by the user from the recommendations.
    Skills are marked as auto_installed=True and start at COMMUNITY
    trust level, earning higher trust through usage (US-530).

    Updates the integrations readiness score and records the event
    in episodic memory.

    Args:
        body: Request with list of skill_ids to install.
        current_user: Authenticated user.

    Returns:
        SkillInstallResponse with installed count and failed skills.

    Raises:
        HTTPException: 500 if service error occurs.
    """
    try:
        engine = _get_skill_recommender()

        # Convert skill_ids to recommendation format
        skills = [{"skill_id": sid, "trust_level": "community"} for sid in body.skill_ids]

        installed_count = await engine.pre_install(current_user.id, skills)

        # Track failed skills
        failed_count = len(body.skill_ids) - installed_count
        failed_skills = []
        if failed_count > 0:
            # Skills that failed would be logged, but we don't track them individually here
            failed_skills = ["Some skills failed to install - see logs for details"]

        # Update readiness score for integrations
        from src.memory.episodic import EpisodicMemory
        from src.onboarding.readiness import OnboardingReadinessService

        readiness_service = OnboardingReadinessService()
        await readiness_service.recalculate(current_user.id)

        # Record episodic memory
        episodic = EpisodicMemory()
        now = datetime.now(UTC)
        episode = Episode(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            event_type="onboarding_skills_preconfigured",
            content=f"Pre-configured {installed_count} skills based on company type",
            participants=[current_user.id],
            occurred_at=now,
            recorded_at=now,
            context={
                "skills_count": installed_count,
                "total_requested": len(body.skill_ids),
            },
        )
        await episodic.store_episode(episode)

        return SkillInstallResponse(
            installed_count=installed_count,
            total_count=len(body.skill_ids),
            failed_skills=failed_skills,
        )

    except Exception as e:
        logger.exception(f"Error installing skills for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to install skills",
        ) from e


# Personality Calibration endpoints (US-919)


class PersonalityCalibrationResponse(BaseModel):
    """Response model for personality calibration."""

    directness: float
    warmth: float
    assertiveness: float
    detail_orientation: float
    formality: float
    tone_guidance: str
    example_adjustments: list[str]


def _get_personality_calibrator() -> "PersonalityCalibrator":
    """Get personality calibrator service instance."""
    from src.onboarding.personality_calibrator import PersonalityCalibrator

    return PersonalityCalibrator()


@router.post(
    "/personality/calibrate",
    response_model=PersonalityCalibrationResponse,
)
async def calibrate_personality(
    current_user: CurrentUser,
) -> PersonalityCalibrationResponse:
    """Calibrate ARIA's personality from user's Digital Twin.

    Reads the writing style fingerprint and generates personality
    trait adjustments. Stores calibration in Digital Twin for use
    by all ARIA features (Scribe drafts, responses, etc.).

    Returns:
        PersonalityCalibrationResponse with trait adjustments and tone guidance.

    Raises:
        HTTPException: 500 if calibration fails.
    """
    try:
        calibrator = _get_personality_calibrator()
        result = await calibrator.calibrate(current_user.id)
        return PersonalityCalibrationResponse(**result.model_dump())
    except Exception as e:
        logger.exception(f"Error calibrating personality for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to calibrate personality",
        ) from e


@router.get("/personality/calibration")
async def get_personality_calibration(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get stored personality calibration.

    Returns the current personality calibration for the user,
    or a status indicator if not yet calibrated.

    Returns:
        PersonalityCalibration dict or {status: "not_calibrated"}.
    """
    calibrator = _get_personality_calibrator()
    cal = await calibrator.get_calibration(current_user.id)
    if cal:
        return cal.model_dump()
    return {"status": "not_calibrated"}
