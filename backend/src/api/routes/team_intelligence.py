"""API routes for team intelligence sharing.

Provides endpoints for:
- Getting/setting user opt-in status
- Viewing shared intelligence for the company
- Searching shared intelligence
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.deps import get_current_user
from src.memory.shared_intelligence import get_shared_intelligence_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/team-intelligence", tags=["Team Intelligence"])


class OptInRequest(BaseModel):
    """Request to update team intelligence opt-in status."""

    opted_in: bool


class OptInResponse(BaseModel):
    """Response for opt-in status."""

    user_id: str
    company_id: str | None
    opted_in: bool
    opted_in_at: str | None


class SharedFactResponse(BaseModel):
    """Response for a shared intelligence fact."""

    id: str
    subject: str
    predicate: str
    object: str
    confidence: float
    source_type: str
    contribution_count: int
    related_account_name: str | None
    is_active: bool
    created_at: str


class SharedIntelligenceListResponse(BaseModel):
    """Response for listing shared intelligence."""

    facts: list[SharedFactResponse]
    total: int
    opted_in: bool


class SearchRequest(BaseModel):
    """Request for searching shared intelligence."""

    query: str
    min_confidence: float = 0.5
    limit: int = 20


@router.get("/opt-in", response_model=OptInResponse)
async def get_opt_in_status(
    user: dict[str, Any] = Depends(get_current_user),
) -> OptInResponse:
    """Get the current user's team intelligence sharing preference.

    Requires authentication.
    """
    user_id = user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    service = get_shared_intelligence_service()
    status = await service.get_opt_in_status(user_id)

    if not status:
        # Return default status
        return OptInResponse(
            user_id=user_id,
            company_id=None,
            opted_in=False,
            opted_in_at=None,
        )

    return OptInResponse(
        user_id=status.user_id,
        company_id=status.company_id,
        opted_in=status.opted_in,
        opted_in_at=status.opted_in_at.isoformat() if status.opted_in_at else None,
    )


@router.put("/opt-in", response_model=OptInResponse)
async def set_opt_in_status(
    request: OptInRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> OptInResponse:
    """Update the user's team intelligence sharing preference.

    When opted in:
    - Your insights about shared accounts will be contributed to team intelligence
    - You will be able to see team intelligence from other members

    Requires authentication.
    """
    user_id = user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    service = get_shared_intelligence_service()
    status = await service.set_opt_in(user_id, request.opted_in)

    if not status:
        raise HTTPException(
            status_code=500,
            detail="Failed to update opt-in status",
        )

    logger.info(
        "Team intelligence opt-in updated",
        extra={"user_id": user_id, "opted_in": request.opted_in},
    )

    return OptInResponse(
        user_id=status.user_id,
        company_id=status.company_id,
        opted_in=status.opted_in,
        opted_in_at=status.opted_in_at.isoformat() if status.opted_in_at else None,
    )


@router.get("", response_model=SharedIntelligenceListResponse)
async def list_shared_intelligence(
    account_name: str | None = None,
    limit: int = 50,
    user: dict[str, Any] = Depends(get_current_user),
) -> SharedIntelligenceListResponse:
    """List shared intelligence for the user's company.

    Results are filtered by:
    - User must have opted in to team intelligence
    - Only facts from the user's company are returned

    Args:
        account_name: Optional filter by account name.
        limit: Maximum number of facts to return (default 50, max 100).

    Requires authentication.
    """
    user_id = user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    service = get_shared_intelligence_service()

    # Check opt-in status
    status = await service.get_opt_in_status(user_id)
    if not status or not status.company_id:
        return SharedIntelligenceListResponse(
            facts=[],
            total=0,
            opted_in=False,
        )

    if not status.opted_in:
        return SharedIntelligenceListResponse(
            facts=[],
            total=0,
            opted_in=False,
        )

    # Get facts
    limit = min(limit, 100)
    if account_name:
        facts = await service.get_facts_for_account(
            company_id=status.company_id,
            account_name=account_name,
            user_id=user_id,
            limit=limit,
        )
    else:
        facts = await service.get_all_company_facts(
            company_id=status.company_id,
            user_id=user_id,
            limit=limit,
        )

    return SharedIntelligenceListResponse(
        facts=[
            SharedFactResponse(
                id=fact.id,
                subject=fact.subject,
                predicate=fact.predicate,
                object=fact.object,
                confidence=fact.confidence,
                source_type=fact.source_type.value,
                contribution_count=fact.contribution_count,
                related_account_name=fact.related_account_name,
                is_active=fact.is_active,
                created_at=fact.created_at.isoformat(),
            )
            for fact in facts
        ],
        total=len(facts),
        opted_in=True,
    )


@router.post("/search", response_model=SharedIntelligenceListResponse)
async def search_shared_intelligence(
    request: SearchRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> SharedIntelligenceListResponse:
    """Search shared intelligence by text query.

    Searches across subject, predicate, object, and account name fields.

    Requires:
    - User must be authenticated
    - User must have opted in to team intelligence
    """
    user_id = user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    service = get_shared_intelligence_service()

    # Check opt-in status
    status = await service.get_opt_in_status(user_id)
    if not status or not status.company_id or not status.opted_in:
        return SharedIntelligenceListResponse(
            facts=[],
            total=0,
            opted_in=status.opted_in if status else False,
        )

    # Search facts
    facts = await service.search_facts(
        company_id=status.company_id,
        query=request.query,
        user_id=user_id,
        min_confidence=request.min_confidence,
        limit=min(request.limit, 100),
    )

    return SharedIntelligenceListResponse(
        facts=[
            SharedFactResponse(
                id=fact.id,
                subject=fact.subject,
                predicate=fact.predicate,
                object=fact.object,
                confidence=fact.confidence,
                source_type=fact.source_type.value,
                contribution_count=fact.contribution_count,
                related_account_name=fact.related_account_name,
                is_active=fact.is_active,
                created_at=fact.created_at.isoformat(),
            )
            for fact in facts
        ],
        total=len(facts),
        opted_in=True,
    )


@router.get("/account/{account_name}", response_model=SharedIntelligenceListResponse)
async def get_account_intelligence(
    account_name: str,
    limit: int = 20,
    user: dict[str, Any] = Depends(get_current_user),
) -> SharedIntelligenceListResponse:
    """Get shared intelligence for a specific account.

    Args:
        account_name: Name of the account to get intelligence for.
        limit: Maximum number of facts to return.

    Requires:
    - User must be authenticated
    - User must have opted in to team intelligence
    """
    user_id = user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    service = get_shared_intelligence_service()

    # Check opt-in status
    status = await service.get_opt_in_status(user_id)
    if not status or not status.company_id or not status.opted_in:
        return SharedIntelligenceListResponse(
            facts=[],
            total=0,
            opted_in=status.opted_in if status else False,
        )

    # Get facts for account
    facts = await service.get_facts_for_account(
        company_id=status.company_id,
        account_name=account_name,
        user_id=user_id,
        limit=min(limit, 100),
    )

    return SharedIntelligenceListResponse(
        facts=[
            SharedFactResponse(
                id=fact.id,
                subject=fact.subject,
                predicate=fact.predicate,
                object=fact.object,
                confidence=fact.confidence,
                source_type=fact.source_type.value,
                contribution_count=fact.contribution_count,
                related_account_name=fact.related_account_name,
                is_active=fact.is_active,
                created_at=fact.created_at.isoformat(),
            )
            for fact in facts
        ],
        total=len(facts),
        opted_in=True,
    )
