"""Lead memory API routes.

Provides REST endpoints for managing sales pursuit leads including:
- List leads with filtering and sorting
- Get single lead details
- Create new leads
- Add notes to leads
- Export leads
"""

import csv
import io
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status

from src.api.deps import CurrentUser
from src.core.exceptions import (
    InvalidStageTransitionError,
    LeadMemoryError,
    LeadNotFoundError,
    ValidationError,
    sanitize_error,
)
from src.core.lead_generation import LeadGenerationService
from src.memory.lead_memory import (
    LeadMemory,
    LeadMemoryService,
    LeadStatus,
    LifecycleStage,
)
from src.models.lead_generation import (
    DiscoveredLeadResponse,
    DiscoverLeadsRequest,
    ICPDefinition,
    ICPResponse,
    LeadReviewRequest,
    LeadScoreBreakdown,
    OutreachRequest,
    OutreachResponse,
    PipelineSummary,
    ReviewStatus,
)
from src.models.lead_memory import (
    ContributionCreate,
    ContributionResponse,
    ContributionReviewRequest,
    ContributorCreate,
    ContributorResponse,
    InsightResponse,
    InsightType,
    LeadEventCreate,
    LeadEventResponse,
    LeadMemoryCreate,
    LeadMemoryResponse,
    LeadMemoryUpdate,
    StageTransitionRequest,
    StakeholderCreate,
    StakeholderResponse,
    StakeholderUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/leads", tags=["leads"])


def _lead_to_response(lead: LeadMemory) -> LeadMemoryResponse:
    """Convert LeadMemory dataclass to response model.

    Args:
        lead: LeadMemory dataclass instance.

    Returns:
        LeadMemoryResponse Pydantic model.
    """
    from src.models.lead_memory import LeadStatus as ResponseLeadStatus
    from src.models.lead_memory import LifecycleStage as ResponseLifecycleStage

    return LeadMemoryResponse(
        id=lead.id,
        user_id=lead.user_id,
        company_name=lead.company_name,
        company_id=lead.company_id,
        lifecycle_stage=ResponseLifecycleStage(lead.lifecycle_stage.value),
        status=ResponseLeadStatus(lead.status.value),
        health_score=lead.health_score,
        crm_id=lead.crm_id,
        crm_provider=lead.crm_provider,
        first_touch_at=lead.first_touch_at,
        last_activity_at=lead.last_activity_at,
        expected_close_date=lead.expected_close_date,
        expected_value=float(lead.expected_value) if lead.expected_value else None,
        tags=lead.tags,
        created_at=lead.created_at,
        updated_at=lead.updated_at,
    )


@router.get("", response_model=list[LeadMemoryResponse])
async def list_leads(
    current_user: CurrentUser,
    lead_status: str | None = Query(None, alias="status", description="Filter by status"),
    stage: str | None = Query(None, description="Filter by lifecycle stage"),
    min_health: int | None = Query(None, ge=0, le=100, description="Minimum health score"),
    max_health: int | None = Query(None, ge=0, le=100, description="Maximum health score"),
    search: str | None = Query(None, description="Search by company name"),
    sort_by: str = Query("last_activity", description="Sort field"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
) -> list[LeadMemoryResponse]:
    """List all leads for the current user with optional filters.

    Args:
        current_user: Current authenticated user.
        lead_status: Optional filter by lead status (active, won, lost, dormant).
        stage: Optional filter by lifecycle stage (lead, opportunity, account).
        min_health: Optional minimum health score filter.
        max_health: Optional maximum health score filter.
        search: Optional company name search.
        sort_by: Field to sort by (health, last_activity, name, value).
        sort_order: Sort direction (asc, desc).
        limit: Maximum number of results.

    Returns:
        List of leads matching the filters.
    """
    try:
        service = LeadMemoryService()

        # Parse status filter
        status_filter = None
        if lead_status:
            try:
                status_filter = LeadStatus(lead_status)
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status: {lead_status}",
                ) from e

        # Parse stage filter
        stage_filter = None
        if stage:
            try:
                stage_filter = LifecycleStage(stage)
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid stage: {stage}",
                ) from e

        # Get leads from service
        leads = await service.list_by_user(
            user_id=current_user.id,
            status=status_filter,
            lifecycle_stage=stage_filter,
            min_health_score=min_health,
            max_health_score=max_health,
            limit=limit,
        )

        # Filter by search term if provided
        if search:
            search_lower = search.lower()
            leads = [lead for lead in leads if search_lower in lead.company_name.lower()]

        # Sort results
        sort_key_map = {
            "health": lambda lead: lead.health_score,
            "last_activity": lambda lead: lead.last_activity_at,
            "name": lambda lead: lead.company_name.lower(),
            "value": lambda lead: float(lead.expected_value) if lead.expected_value else 0,
        }

        if sort_by in sort_key_map:
            leads.sort(key=sort_key_map[sort_by], reverse=(sort_order == "desc"))

        return [_lead_to_response(lead) for lead in leads]

    except HTTPException:
        raise
    except LeadMemoryError as e:
        logger.exception("Failed to list leads")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=sanitize_error(e),
        ) from e


# --- Lead Generation Workflow (US-939) ---


@router.post("/icp", response_model=ICPResponse)
async def save_icp(
    current_user: CurrentUser,
    icp: ICPDefinition,
) -> ICPResponse:
    """Save or update the user's Ideal Customer Profile.

    Args:
        current_user: Current authenticated user.
        icp: ICP definition data.

    Returns:
        Saved ICP with version and timestamps.
    """
    try:
        service = LeadGenerationService()
        return await service.save_icp(current_user.id, icp)
    except Exception as e:
        logger.error(f"Failed to save ICP: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save ICP",
        ) from e


@router.get("/icp", response_model=ICPResponse | None)
async def get_icp(current_user: CurrentUser) -> ICPResponse | None:
    """Get the current user's Ideal Customer Profile.

    Args:
        current_user: Current authenticated user.

    Returns:
        Current ICP or None if not defined.
    """
    try:
        service = LeadGenerationService()
        return await service.get_icp(current_user.id)
    except Exception as e:
        logger.error(f"Failed to get ICP: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get ICP",
        ) from e


@router.post("/discovered", response_model=list[DiscoveredLeadResponse])
async def discover_leads(
    current_user: CurrentUser,
    request: DiscoverLeadsRequest,
) -> list[DiscoveredLeadResponse]:
    """Trigger Hunter agent to discover leads matching the user's ICP.

    Args:
        current_user: Current authenticated user.
        request: Discovery parameters including target count.

    Returns:
        List of discovered leads with scores.
    """
    try:
        service = LeadGenerationService()
        icp = await service.get_icp(current_user.id)
        if not icp:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No ICP defined. Create an ICP first.",
            )
        return await service.discover_leads(current_user.id, icp.id, request.target_count)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to discover leads: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to discover leads",
        ) from e


@router.get("/discovered", response_model=list[DiscoveredLeadResponse])
async def list_discovered_leads(
    current_user: CurrentUser,
    review_status: str | None = Query(None, description="Filter by review status"),
) -> list[DiscoveredLeadResponse]:
    """List discovered leads, optionally filtered by review status.

    Args:
        current_user: Current authenticated user.
        review_status: Optional filter by review status.

    Returns:
        List of discovered leads.
    """
    try:
        status_filter = None
        if review_status:
            try:
                status_filter = ReviewStatus(review_status)
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid review status: {review_status}",
                ) from e
        service = LeadGenerationService()
        return await service.list_discovered(current_user.id, status_filter)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list discovered leads: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list discovered leads",
        ) from e


@router.get("/pipeline", response_model=PipelineSummary)
async def get_pipeline(current_user: CurrentUser) -> PipelineSummary:
    """Get pipeline funnel view with stage counts and values.

    Args:
        current_user: Current authenticated user.

    Returns:
        Pipeline summary with stage breakdown.
    """
    try:
        service = LeadGenerationService()
        return await service.get_pipeline(current_user.id)
    except Exception as e:
        logger.error(f"Failed to get pipeline: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get pipeline",
        ) from e


@router.get("/{lead_id}/timeline", response_model=list[LeadEventResponse])
async def get_lead_timeline(
    lead_id: str,
    current_user: CurrentUser,
) -> list[LeadEventResponse]:
    """Get the event timeline for a lead.

    Args:
        lead_id: The lead ID to get timeline for.
        current_user: Current authenticated user.

    Returns:
        List of events for the lead, ordered by time.

    Raises:
        HTTPException: 404 if lead not found.
    """
    from src.db.supabase import SupabaseClient
    from src.memory.lead_memory_events import LeadEventService

    try:
        service = LeadMemoryService()
        await service.get_by_id(user_id=current_user.id, lead_id=lead_id)

        client = SupabaseClient.get_client()
        event_service = LeadEventService(db_client=client)

        events = await event_service.get_timeline(
            user_id=current_user.id,
            lead_memory_id=lead_id,
        )

        return [
            LeadEventResponse(
                id=event.id,
                lead_memory_id=event.lead_memory_id,
                event_type=event.event_type,
                direction=event.direction,
                subject=event.subject,
                content=event.content,
                participants=event.participants,
                occurred_at=event.occurred_at,
                source=event.source,
                created_at=event.created_at,
            )
            for event in events
        ]

    except LeadNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead {lead_id} not found",
        ) from e
    except LeadMemoryError as e:
        logger.exception("Failed to get lead timeline")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=sanitize_error(e),
        ) from e


@router.post("/{lead_id}/events", response_model=LeadEventResponse)
async def add_event(
    lead_id: str,
    event_data: LeadEventCreate,
    current_user: CurrentUser,
) -> LeadEventResponse:
    """Add an event to a lead's timeline.

    Args:
        lead_id: The lead ID to add event to.
        event_data: The event data.
        current_user: Current authenticated user.

    Returns:
        The created event.

    Raises:
        HTTPException: 404 if lead not found.
    """
    from src.db.supabase import SupabaseClient
    from src.memory.lead_memory_events import LeadEventService

    try:
        service = LeadMemoryService()
        await service.get_by_id(user_id=current_user.id, lead_id=lead_id)

        client = SupabaseClient.get_client()
        event_service = LeadEventService(db_client=client)

        event_id = await event_service.add_event(
            user_id=current_user.id,
            lead_memory_id=lead_id,
            event_data=event_data,
        )

        events = await event_service.get_timeline(
            user_id=current_user.id,
            lead_memory_id=lead_id,
        )

        created_event = next((e for e in events if e.id == event_id), None)

        if created_event is None:
            raise LeadMemoryError("Failed to retrieve created event")

        return LeadEventResponse(
            id=created_event.id,
            lead_memory_id=created_event.lead_memory_id,
            event_type=created_event.event_type,
            direction=created_event.direction,
            subject=created_event.subject,
            content=created_event.content,
            participants=created_event.participants,
            occurred_at=created_event.occurred_at,
            source=created_event.source,
            created_at=created_event.created_at,
        )

    except LeadNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead {lead_id} not found",
        ) from e
    except LeadMemoryError as e:
        logger.exception("Failed to add event")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=sanitize_error(e),
        ) from e


@router.get("/{lead_id}", response_model=LeadMemoryResponse)
async def get_lead(
    lead_id: str,
    current_user: CurrentUser,
) -> LeadMemoryResponse:
    """Get a specific lead by ID.

    Args:
        lead_id: The lead ID to retrieve.
        current_user: Current authenticated user.

    Returns:
        The requested lead.

    Raises:
        HTTPException: 404 if lead not found.
    """
    try:
        service = LeadMemoryService()
        lead = await service.get_by_id(user_id=current_user.id, lead_id=lead_id)
        return _lead_to_response(lead)

    except LeadNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead {lead_id} not found",
        ) from e
    except LeadMemoryError as e:
        logger.exception("Failed to get lead")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=sanitize_error(e),
        ) from e


@router.post("", response_model=LeadMemoryResponse, status_code=status.HTTP_201_CREATED)
async def create_lead(
    lead_data: LeadMemoryCreate,
    current_user: CurrentUser,
) -> LeadMemoryResponse:
    """Create a new lead.

    Args:
        lead_data: The lead data to create.
        current_user: Current authenticated user.

    Returns:
        The created lead.

    Raises:
        HTTPException: 500 if creation fails.
    """
    from decimal import Decimal

    from src.memory.lead_memory import TriggerType

    try:
        service = LeadMemoryService()

        # Convert expected_value to Decimal if provided
        expected_value = (
            Decimal(str(lead_data.expected_value)) if lead_data.expected_value else None
        )

        lead = await service.create(
            user_id=current_user.id,
            company_name=lead_data.company_name,
            trigger=TriggerType.MANUAL,
            company_id=lead_data.company_id,
            expected_close_date=lead_data.expected_close_date,
            expected_value=expected_value,
            tags=lead_data.tags,
            metadata=lead_data.metadata,
        )

        return _lead_to_response(lead)

    except LeadMemoryError as e:
        logger.exception("Failed to create lead")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=sanitize_error(e),
        ) from e


@router.patch("/{lead_id}", response_model=LeadMemoryResponse)
async def update_lead(
    lead_id: str,
    lead_data: LeadMemoryUpdate,
    current_user: CurrentUser,
) -> LeadMemoryResponse:
    """Update an existing lead.

    Only provided fields will be updated. None values are ignored.

    Args:
        lead_id: The lead ID to update.
        lead_data: The fields to update.
        current_user: Current authenticated user.

    Returns:
        The updated lead.

    Raises:
        HTTPException: 404 if lead not found, 500 if update fails.
    """
    from decimal import Decimal

    try:
        service = LeadMemoryService()

        # Verify lead exists
        await service.get_by_id(user_id=current_user.id, lead_id=lead_id)

        # Convert expected_value to Decimal if provided
        expected_value = (
            Decimal(str(lead_data.expected_value)) if lead_data.expected_value else None
        )

        # Convert enum types if provided
        lifecycle_stage = (
            LifecycleStage(lead_data.lifecycle_stage.value) if lead_data.lifecycle_stage else None
        )
        lead_status = LeadStatus(lead_data.status.value) if lead_data.status else None

        # Perform update
        await service.update(
            user_id=current_user.id,
            lead_id=lead_id,
            company_name=lead_data.company_name,
            lifecycle_stage=lifecycle_stage,
            status=lead_status,
            health_score=lead_data.health_score,
            expected_close_date=lead_data.expected_close_date,
            expected_value=expected_value,
            tags=lead_data.tags,
        )

        # Fetch and return updated lead
        updated_lead = await service.get_by_id(user_id=current_user.id, lead_id=lead_id)
        return _lead_to_response(updated_lead)

    except LeadNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead {lead_id} not found",
        ) from e
    except LeadMemoryError as e:
        logger.exception("Failed to update lead")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=sanitize_error(e),
        ) from e


@router.post("/{lead_id}/notes", response_model=LeadEventResponse)
async def add_note(
    lead_id: str,
    note: LeadEventCreate,
    current_user: CurrentUser,
) -> LeadEventResponse:
    """Add a note to a lead.

    Args:
        lead_id: The lead ID to add note to.
        note: The note content.
        current_user: Current authenticated user.

    Returns:
        The created note event.

    Raises:
        HTTPException: 404 if lead not found.
    """
    from src.db.supabase import SupabaseClient
    from src.memory.lead_memory_events import LeadEventService

    try:
        # Verify lead exists
        service = LeadMemoryService()
        await service.get_by_id(user_id=current_user.id, lead_id=lead_id)

        # Create note event
        client = SupabaseClient.get_client()
        event_service = LeadEventService(db_client=client)

        event_id = await event_service.add_event(
            user_id=current_user.id,
            lead_memory_id=lead_id,
            event_data=note,
        )

        # Retrieve the created event to return it
        events = await event_service.get_timeline(
            user_id=current_user.id,
            lead_memory_id=lead_id,
        )

        # Find the event we just created
        created_event = next((e for e in events if e.id == event_id), None)

        if created_event is None:
            raise LeadMemoryError("Failed to retrieve created event")

        return LeadEventResponse(
            id=created_event.id,
            lead_memory_id=created_event.lead_memory_id,
            event_type=created_event.event_type,
            direction=created_event.direction,
            subject=created_event.subject,
            content=created_event.content,
            participants=created_event.participants,
            occurred_at=created_event.occurred_at,
            source=created_event.source,
            created_at=created_event.created_at,
        )

    except LeadNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead {lead_id} not found",
        ) from e
    except LeadMemoryError as e:
        logger.exception("Failed to add note")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=sanitize_error(e),
        ) from e


@router.post(
    "/{lead_id}/stakeholders",
    response_model=StakeholderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_stakeholder(
    lead_id: str,
    stakeholder_data: StakeholderCreate,
    current_user: CurrentUser,
) -> StakeholderResponse:
    """Add a stakeholder to a lead.

    Args:
        lead_id: The lead ID to add stakeholder to.
        stakeholder_data: The stakeholder data.
        current_user: Current authenticated user.

    Returns:
        The created stakeholder.

    Raises:
        HTTPException: 404 if lead not found, 500 if creation fails.
    """
    from src.db.supabase import SupabaseClient
    from src.memory.lead_stakeholders import LeadStakeholderService

    try:
        # Verify lead exists
        service = LeadMemoryService()
        await service.get_by_id(user_id=current_user.id, lead_id=lead_id)

        # Create stakeholder
        client = SupabaseClient.get_client()
        stakeholder_service = LeadStakeholderService(db_client=client)

        stakeholder_id = await stakeholder_service.add_stakeholder(
            user_id=current_user.id,
            lead_memory_id=lead_id,
            contact_email=stakeholder_data.contact_email,
            contact_name=stakeholder_data.contact_name,
            title=stakeholder_data.title,
            role=stakeholder_data.role,
            influence_level=stakeholder_data.influence_level,
            sentiment=stakeholder_data.sentiment,
            notes=stakeholder_data.notes,
        )

        # Retrieve the created stakeholder
        stakeholders = await stakeholder_service.list_by_lead(
            user_id=current_user.id,
            lead_memory_id=lead_id,
        )

        # Find the stakeholder we just created
        created_stakeholder = next((s for s in stakeholders if s.id == stakeholder_id), None)

        if created_stakeholder is None:
            raise LeadMemoryError("Failed to retrieve created stakeholder")

        return StakeholderResponse(
            id=created_stakeholder.id,
            lead_memory_id=created_stakeholder.lead_memory_id,
            contact_email=created_stakeholder.contact_email,
            contact_name=created_stakeholder.contact_name,
            title=created_stakeholder.title,
            role=created_stakeholder.role,
            influence_level=created_stakeholder.influence_level,
            sentiment=created_stakeholder.sentiment,
            last_contacted_at=created_stakeholder.last_contacted_at,
            notes=created_stakeholder.notes,
            created_at=created_stakeholder.created_at,
        )

    except LeadNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead {lead_id} not found",
        ) from e
    except LeadMemoryError as e:
        logger.exception("Failed to add stakeholder")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=sanitize_error(e),
        ) from e


@router.get("/{lead_id}/stakeholders", response_model=list[StakeholderResponse])
async def list_stakeholders(
    lead_id: str,
    current_user: CurrentUser,
) -> list[StakeholderResponse]:
    """List all stakeholders for a lead.

    Args:
        lead_id: The lead ID to list stakeholders for.
        current_user: Current authenticated user.

    Returns:
        List of stakeholders for the lead.

    Raises:
        HTTPException: 404 if lead not found, 500 if retrieval fails.
    """
    from src.db.supabase import SupabaseClient
    from src.memory.lead_stakeholders import LeadStakeholderService

    try:
        # Verify lead exists
        service = LeadMemoryService()
        await service.get_by_id(user_id=current_user.id, lead_id=lead_id)

        # Get stakeholders
        client = SupabaseClient.get_client()
        stakeholder_service = LeadStakeholderService(db_client=client)

        stakeholders = await stakeholder_service.list_by_lead(
            user_id=current_user.id,
            lead_memory_id=lead_id,
        )

        return [
            StakeholderResponse(
                id=stakeholder.id,
                lead_memory_id=stakeholder.lead_memory_id,
                contact_email=stakeholder.contact_email,
                contact_name=stakeholder.contact_name,
                title=stakeholder.title,
                role=stakeholder.role,
                influence_level=stakeholder.influence_level,
                sentiment=stakeholder.sentiment,
                last_contacted_at=stakeholder.last_contacted_at,
                notes=stakeholder.notes,
                created_at=stakeholder.created_at,
            )
            for stakeholder in stakeholders
        ]

    except LeadNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead {lead_id} not found",
        ) from e
    except LeadMemoryError as e:
        logger.exception("Failed to list stakeholders")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=sanitize_error(e),
        ) from e


@router.patch("/{lead_id}/stakeholders/{stakeholder_id}", response_model=StakeholderResponse)
async def update_stakeholder(
    lead_id: str,
    stakeholder_id: str,
    stakeholder_data: StakeholderUpdate,
    current_user: CurrentUser,
) -> StakeholderResponse:
    """Update a stakeholder.

    Only provided fields will be updated. None values are ignored.

    Args:
        lead_id: The lead ID the stakeholder belongs to.
        stakeholder_id: The stakeholder ID to update.
        stakeholder_data: The fields to update.
        current_user: Current authenticated user.

    Returns:
        The updated stakeholder.

    Raises:
        HTTPException: 404 if lead or stakeholder not found, 500 if update fails.
    """
    from src.db.supabase import SupabaseClient
    from src.memory.lead_stakeholders import LeadStakeholderService

    try:
        # Verify lead exists
        service = LeadMemoryService()
        await service.get_by_id(user_id=current_user.id, lead_id=lead_id)

        # Update stakeholder
        client = SupabaseClient.get_client()
        stakeholder_service = LeadStakeholderService(db_client=client)

        await stakeholder_service.update_stakeholder(
            user_id=current_user.id,
            stakeholder_id=stakeholder_id,
            contact_name=stakeholder_data.contact_name,
            title=stakeholder_data.title,
            role=stakeholder_data.role,
            influence_level=stakeholder_data.influence_level,
            sentiment=stakeholder_data.sentiment,
            notes=stakeholder_data.notes,
        )

        # Retrieve the updated stakeholder
        stakeholders = await stakeholder_service.list_by_lead(
            user_id=current_user.id,
            lead_memory_id=lead_id,
        )

        # Find the updated stakeholder
        updated_stakeholder = next((s for s in stakeholders if s.id == stakeholder_id), None)

        if updated_stakeholder is None:
            raise LeadMemoryError("Failed to retrieve updated stakeholder")

        return StakeholderResponse(
            id=updated_stakeholder.id,
            lead_memory_id=updated_stakeholder.lead_memory_id,
            contact_email=updated_stakeholder.contact_email,
            contact_name=updated_stakeholder.contact_name,
            title=updated_stakeholder.title,
            role=updated_stakeholder.role,
            influence_level=updated_stakeholder.influence_level,
            sentiment=updated_stakeholder.sentiment,
            last_contacted_at=updated_stakeholder.last_contacted_at,
            notes=updated_stakeholder.notes,
            created_at=updated_stakeholder.created_at,
        )

    except LeadNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead {lead_id} not found",
        ) from e
    except LeadMemoryError as e:
        logger.exception("Failed to update stakeholder")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=sanitize_error(e),
        ) from e


@router.delete("/{lead_id}/stakeholders/{stakeholder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_stakeholder(
    lead_id: str,
    stakeholder_id: str,
    current_user: CurrentUser,
) -> None:
    """Remove a stakeholder from a lead.

    Args:
        lead_id: The lead ID the stakeholder belongs to.
        stakeholder_id: The stakeholder ID to remove.
        current_user: Current authenticated user.

    Raises:
        HTTPException: 404 if lead not found, 500 if deletion fails.
    """
    from src.db.supabase import SupabaseClient
    from src.memory.lead_stakeholders import LeadStakeholderService

    try:
        # Verify lead exists
        service = LeadMemoryService()
        await service.get_by_id(user_id=current_user.id, lead_id=lead_id)

        # Remove stakeholder
        client = SupabaseClient.get_client()
        stakeholder_service = LeadStakeholderService(db_client=client)

        await stakeholder_service.remove_stakeholder(
            user_id=current_user.id,
            stakeholder_id=stakeholder_id,
        )

        return None

    except LeadNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead {lead_id} not found",
        ) from e
    except LeadMemoryError as e:
        logger.exception("Failed to remove stakeholder")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=sanitize_error(e),
        ) from e


@router.get("/{lead_id}/insights", response_model=list[InsightResponse])
async def get_insights(
    lead_id: str,
    current_user: CurrentUser,
    insight_type: str | None = Query(None, description="Filter by insight type"),
    include_addressed: bool = Query(False, description="Include addressed insights"),
) -> list[InsightResponse]:
    """Get AI insights for a lead.

    Args:
        lead_id: The lead ID to get insights for.
        current_user: Current authenticated user.
        insight_type: Optional filter by insight type.
        include_addressed: Whether to include addressed insights (default False).

    Returns:
        List of insights for the lead.

    Raises:
        HTTPException: 404 if lead not found, 400 if invalid insight type, 500 if retrieval fails.
    """
    from src.db.supabase import SupabaseClient
    from src.memory.lead_insights import LeadInsightsService

    try:
        service = LeadMemoryService()
        await service.get_by_id(user_id=current_user.id, lead_id=lead_id)

        insight_type_filter = None
        if insight_type:
            try:
                insight_type_filter = InsightType(insight_type)
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid insight type: {insight_type}",
                ) from e

        client = SupabaseClient.get_client()
        insights_service = LeadInsightsService(db_client=client)

        insights = await insights_service.get_insights(
            user_id=current_user.id,
            lead_memory_id=lead_id,
            insight_type=insight_type_filter,
            include_addressed=include_addressed,
        )

        return [
            InsightResponse(
                id=insight.id,
                lead_memory_id=insight.lead_memory_id,
                insight_type=insight.insight_type,
                content=insight.content,
                confidence=insight.confidence,
                source_event_id=insight.source_event_id,
                detected_at=insight.detected_at,
                addressed_at=insight.addressed_at,
            )
            for insight in insights
        ]

    except HTTPException:
        raise
    except LeadNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Lead {lead_id} not found"
        ) from e
    except LeadMemoryError as e:
        logger.exception("Failed to get insights")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=sanitize_error(e)
        ) from e


@router.post("/{lead_id}/transition", response_model=LeadMemoryResponse)
async def transition_stage(
    lead_id: str,
    transition: StageTransitionRequest,
    current_user: CurrentUser,
) -> LeadMemoryResponse:
    """Transition a lead to a new lifecycle stage.

    Stages can only progress forward: lead -> opportunity -> account.

    Args:
        lead_id: The lead ID to transition.
        transition: The transition request with target stage.
        current_user: Current authenticated user.

    Returns:
        The updated lead.

    Raises:
        HTTPException: 400 if invalid transition, 404 if lead not found,
                      500 if transition fails.
    """
    try:
        service = LeadMemoryService()

        # Convert model LifecycleStage (string value) to memory LifecycleStage
        memory_stage = LifecycleStage(transition.stage.value)

        await service.transition_stage(
            user_id=current_user.id,
            lead_id=lead_id,
            new_stage=memory_stage,
        )

        updated_lead = await service.get_by_id(user_id=current_user.id, lead_id=lead_id)
        return _lead_to_response(updated_lead)

    except InvalidStageTransitionError as e:
        logger.exception("Invalid stage transition")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=sanitize_error(e),
        ) from e
    except LeadNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead {lead_id} not found",
        ) from e
    except LeadMemoryError as e:
        logger.exception("Failed to transition stage")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=sanitize_error(e),
        ) from e


@router.post(
    "/{lead_id}/contributors",
    response_model=dict[str, str],
    status_code=status.HTTP_201_CREATED,
)
async def add_contributor(
    lead_id: str,
    contributor_data: ContributorCreate,
    current_user: CurrentUser,
) -> dict[str, str]:
    """Add a contributor to a lead.

    Args:
        lead_id: The lead ID to add contributor to.
        contributor_data: The contributor data.
        current_user: Current authenticated user.

    Returns:
        The contributor_id that was added.

    Raises:
        HTTPException: 404 if lead not found, 500 if operation fails.
    """
    from src.db.supabase import SupabaseClient
    from src.services.lead_collaboration import LeadCollaborationService

    try:
        # Verify lead exists and user owns it
        service = LeadMemoryService()
        await service.get_by_id(user_id=current_user.id, lead_id=lead_id)

        # Add contributor
        client = SupabaseClient.get_client()
        collab_service = LeadCollaborationService(db_client=client)

        contributor_id = await collab_service.add_contributor(
            user_id=current_user.id,
            lead_memory_id=lead_id,
            contributor_id=contributor_data.contributor_id,
        )

        return {"contributor_id": contributor_id}

    except LeadNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead {lead_id} not found",
        ) from e
    except LeadMemoryError as e:
        logger.exception("Failed to add contributor")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=sanitize_error(e),
        ) from e


@router.get("/{lead_id}/contributors", response_model=list[ContributorResponse])
async def list_contributors(
    lead_id: str,
    current_user: CurrentUser,
) -> list[ContributorResponse]:
    """List all contributors for a lead.

    Args:
        lead_id: The lead ID to list contributors for.
        current_user: Current authenticated user.

    Returns:
        List of contributors for the lead.

    Raises:
        HTTPException: 404 if lead not found, 500 if retrieval fails.
    """
    from src.db.supabase import SupabaseClient
    from src.services.lead_collaboration import LeadCollaborationService

    try:
        # Verify lead exists
        service = LeadMemoryService()
        await service.get_by_id(user_id=current_user.id, lead_id=lead_id)

        # Get contributors
        client = SupabaseClient.get_client()
        collab_service = LeadCollaborationService(db_client=client)

        contributors = await collab_service.get_contributors(
            user_id=current_user.id,
            lead_memory_id=lead_id,
        )

        return [ContributorResponse(**c.to_dict()) for c in contributors]

    except LeadNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead {lead_id} not found",
        ) from e
    except LeadMemoryError as e:
        logger.exception("Failed to list contributors")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=sanitize_error(e),
        ) from e


@router.post(
    "/{lead_id}/contributions",
    response_model=dict[str, str],
    status_code=status.HTTP_201_CREATED,
)
async def submit_contribution(
    lead_id: str,
    contribution_data: ContributionCreate,
    current_user: CurrentUser,
) -> dict[str, str]:
    """Submit a contribution to a lead for owner review.

    Args:
        lead_id: The lead ID to submit contribution to.
        contribution_data: The contribution data.
        current_user: Current authenticated user.

    Returns:
        The ID of the created contribution.

    Raises:
        HTTPException: 500 if submission fails.
    """
    from src.db.supabase import SupabaseClient
    from src.services.lead_collaboration import ContributionType as ServiceContributionType
    from src.services.lead_collaboration import LeadCollaborationService

    try:
        client = SupabaseClient.get_client()
        collab_service = LeadCollaborationService(db_client=client)

        # Convert model enum to service enum
        service_contribution_type = ServiceContributionType(
            contribution_data.contribution_type.value
        )

        contribution_id = await collab_service.submit_contribution(
            user_id=current_user.id,
            lead_memory_id=lead_id,
            contribution_type=service_contribution_type,
            contribution_id=contribution_data.contribution_id,
            content=contribution_data.content,
        )
        return {"id": contribution_id}

    except LeadMemoryError as e:
        logger.exception("Failed to submit contribution")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=sanitize_error(e),
        ) from e


@router.get("/{lead_id}/contributions", response_model=list[ContributionResponse])
async def list_contributions(
    lead_id: str,
    current_user: CurrentUser,
    status_filter: str | None = Query(  # noqa: ARG001
        None, alias="status", description="Filter by contribution status"
    ),
) -> list[ContributionResponse]:
    """List contributions for a lead.

    Args:
        lead_id: The lead ID to list contributions for.
        current_user: Current authenticated user.
        status_filter: Optional filter by contribution status.

    Returns:
        List of contributions for the lead.

    Raises:
        HTTPException: 404 if lead not found, 500 if retrieval fails.
    """
    from src.db.supabase import SupabaseClient
    from src.models.lead_memory import (
        ContributionStatus as ModelContributionStatus,
    )
    from src.models.lead_memory import (
        ContributionType as ModelContributionType,
    )
    from src.services.lead_collaboration import LeadCollaborationService

    try:
        service = LeadMemoryService()
        await service.get_by_id(user_id=current_user.id, lead_id=lead_id)

        client = SupabaseClient.get_client()
        collab_service = LeadCollaborationService(db_client=client)
        contributions = await collab_service.get_pending_contributions(
            user_id=current_user.id, lead_memory_id=lead_id
        )

        return [
            ContributionResponse(
                id=c.id,
                lead_memory_id=c.lead_memory_id,
                contributor_id=c.contributor_id,
                contributor_name="",
                contribution_type=ModelContributionType(c.contribution_type.value),
                contribution_id=c.contribution_id,
                content=None,
                status=ModelContributionStatus(c.status.value),
                created_at=c.created_at,
                reviewed_at=c.reviewed_at,
                reviewed_by=c.reviewed_by,
            )
            for c in contributions
        ]

    except HTTPException:
        raise
    except LeadNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Lead {lead_id} not found"
        ) from e
    except LeadMemoryError as e:
        logger.exception("Failed to list contributions")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=sanitize_error(e)
        ) from e


@router.post(
    "/{lead_id}/contributions/{contribution_id}/review",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def review_contribution(
    lead_id: str,
    contribution_id: str,
    review_data: ContributionReviewRequest,
    current_user: CurrentUser,
) -> None:
    """Review a contribution (merge or reject).

    Args:
        lead_id: The lead ID the contribution belongs to.
        contribution_id: The contribution ID to review.
        review_data: The review action (merge or reject).
        current_user: Current authenticated user.

    Raises:
        HTTPException: 400 if invalid action, 404 if lead not found, 500 if review fails.
    """
    from src.db.supabase import SupabaseClient
    from src.services.lead_collaboration import LeadCollaborationService

    try:
        service = LeadMemoryService()
        await service.get_by_id(user_id=current_user.id, lead_id=lead_id)

        client = SupabaseClient.get_client()
        collab_service = LeadCollaborationService(db_client=client)
        await collab_service.review_contribution(
            user_id=current_user.id, contribution_id=contribution_id, action=review_data.action
        )
        return None

    except ValidationError as e:
        logger.exception("Validation error reviewing contribution")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=sanitize_error(e)
        ) from e
    except LeadNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Lead {lead_id} not found"
        ) from e
    except LeadMemoryError as e:
        logger.exception("Failed to review contribution")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=sanitize_error(e)
        ) from e


@router.post("/export")
async def export_leads(
    lead_ids: list[str],
    current_user: CurrentUser,
) -> dict[str, str]:
    """Export leads to CSV format.

    Args:
        lead_ids: List of lead IDs to export.
        current_user: Current authenticated user.

    Returns:
        CSV content as string with filename.
    """
    try:
        service = LeadMemoryService()
        leads = []

        for lead_id in lead_ids:
            try:
                lead = await service.get_by_id(user_id=current_user.id, lead_id=lead_id)
                leads.append(lead)
            except LeadNotFoundError:
                continue

        # Generate CSV
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow(
            [
                "Company Name",
                "Stage",
                "Status",
                "Health Score",
                "Expected Value",
                "Expected Close Date",
                "Last Activity",
                "Tags",
            ]
        )

        # Data rows
        for lead in leads:
            writer.writerow(
                [
                    lead.company_name,
                    lead.lifecycle_stage.value,
                    lead.status.value,
                    lead.health_score,
                    str(lead.expected_value) if lead.expected_value else "",
                    lead.expected_close_date.isoformat() if lead.expected_close_date else "",
                    lead.last_activity_at.isoformat(),
                    ", ".join(lead.tags),
                ]
            )

        return {
            "filename": f"leads_export_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.csv",
            "content": output.getvalue(),
            "content_type": "text/csv",
        }

    except LeadMemoryError as e:
        logger.exception("Failed to export leads")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=sanitize_error(e),
        ) from e


# --- Lead Generation Workflow (US-939) - Parametric Routes ---


@router.post("/{lead_id}/review", response_model=DiscoveredLeadResponse)
async def review_lead(
    lead_id: str,
    current_user: CurrentUser,
    request: LeadReviewRequest,
) -> DiscoveredLeadResponse:
    """Review a discovered lead: approve, reject, or save for later.

    Args:
        lead_id: ID of the discovered lead.
        current_user: Current authenticated user.
        request: Review action.

    Returns:
        Updated discovered lead.
    """
    try:
        service = LeadGenerationService()
        result = await service.review_lead(current_user.id, lead_id, request.action)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Discovered lead not found",
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to review lead: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to review lead",
        ) from e


@router.get("/{lead_id}/score-explanation", response_model=LeadScoreBreakdown)
async def get_score_explanation(
    lead_id: str,
    current_user: CurrentUser,
) -> LeadScoreBreakdown:
    """Get a detailed score breakdown for a discovered lead.

    Args:
        lead_id: ID of the discovered lead.
        current_user: Current authenticated user.

    Returns:
        Score breakdown with factors and explanations.
    """
    try:
        service = LeadGenerationService()
        result = await service.get_score_explanation(current_user.id, lead_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Discovered lead not found",
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get score explanation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get score explanation",
        ) from e


@router.post("/outreach/{lead_id}", response_model=OutreachResponse)
async def initiate_outreach(
    lead_id: str,
    current_user: CurrentUser,
    request: OutreachRequest,
) -> OutreachResponse:
    """Initiate outreach for a lead, creating a draft via Scribe agent.

    Args:
        lead_id: ID of the lead.
        current_user: Current authenticated user.
        request: Outreach content.

    Returns:
        Outreach draft.
    """
    try:
        service = LeadGenerationService()
        result = await service.initiate_outreach(current_user.id, lead_id, request)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found",
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to initiate outreach: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate outreach",
        ) from e
