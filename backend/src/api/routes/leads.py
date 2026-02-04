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
from src.core.exceptions import LeadMemoryError, LeadNotFoundError
from src.memory.lead_memory import (
    LeadMemory,
    LeadMemoryService,
    LeadStatus,
    LifecycleStage,
)
from src.models.lead_memory import (
    LeadEventCreate,
    LeadEventResponse,
    LeadMemoryCreate,
    LeadMemoryResponse,
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
            detail=str(e),
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
            detail=str(e),
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
            detail=str(e),
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
            detail=str(e),
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
            detail=str(e),
        ) from e
