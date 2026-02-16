"""Causal Intelligence API routes for ARIA Phase 7.

This module provides endpoints for causal chain traversal and analysis,
enabling ARIA to trace how events propagate through connected entities.
Also provides implication reasoning endpoints for deriving actionable insights.
"""

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.api.deps import CurrentUser
from src.core.llm import LLMClient
from src.db.supabase import get_supabase_client
from src.intelligence.causal import (
    CausalChain,
    CausalChainEngine,
    CausalChainStore,
    CausalTraversalRequest,
    CausalTraversalResponse,
)
from src.intelligence.causal.implication_engine import ImplicationEngine
from src.intelligence.causal.models import (
    ImplicationRequest,
    ImplicationResponse,
    InsightUpdateRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/intelligence", tags=["intelligence", "causal"])


class CausalChainResponse(BaseModel):
    """Response model for a single causal chain."""

    id: str | None
    trigger_event: str
    hops: list[dict[str, Any]]
    final_confidence: float
    time_to_impact: str | None
    source_context: str | None
    created_at: str | None

    @classmethod
    def from_chain(cls, chain: CausalChain) -> "CausalChainResponse":
        """Create response from a CausalChain model."""
        return cls(
            id=str(chain.id) if chain.id else None,
            trigger_event=chain.trigger_event,
            hops=[hop.model_dump() for hop in chain.hops],
            final_confidence=chain.final_confidence,
            time_to_impact=chain.time_to_impact,
            source_context=chain.source_context,
            created_at=chain.created_at.isoformat() if chain.created_at else None,
        )


class CausalChainsListResponse(BaseModel):
    """Response model for listing causal chains."""

    chains: list[CausalChainResponse]
    total: int


@router.post("/causal-chains", response_model=CausalTraversalResponse)
async def traverse_causal_chains(
    current_user: CurrentUser,
    request: CausalTraversalRequest,
    save_results: bool = Query(True, description="Whether to save chains to database"),
    source_context: str = Query("api_request", description="Context for saved chains"),
) -> CausalTraversalResponse:
    """Traverse causal chains from a trigger event.

    Analyzes a trigger event to discover causal relationships and
    downstream impacts. Uses Graphiti graph traversal where possible
    and LLM inference for implicit causality.

    Args:
        current_user: Authenticated user
        request: Traversal request with trigger event and parameters
        save_results: Whether to persist results to database
        source_context: Context label for saved chains

    Returns:
        CausalTraversalResponse with discovered chains and metadata

    Raises:
        HTTPException: If traversal fails
    """
    try:
        db = get_supabase_client()
        llm = LLMClient()

        # Create engine with None for Graphiti (will check internally)
        engine = CausalChainEngine(
            graphiti_client=None,
            llm_client=llm,
            db_client=db,
        )

        # Perform traversal
        response = await engine.traverse_with_metadata(
            user_id=current_user.id,
            request=request,
        )

        # Optionally save chains
        if save_results and response.chains:
            store = CausalChainStore(db_client=db)
            for chain in response.chains:
                try:
                    await store.save_chain(
                        user_id=current_user.id,
                        chain=chain,
                        source_context=source_context,
                    )
                except Exception as e:
                    logger.warning(f"Failed to save causal chain: {e}")

        logger.info(
            "Causal chain traversal completed",
            extra={
                "user_id": current_user.id,
                "chains_found": len(response.chains),
                "processing_time_ms": response.processing_time_ms,
                "entities_found": response.entities_found,
            },
        )

        return response

    except Exception as e:
        logger.exception(
            "Causal chain traversal failed",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail=f"Causal chain analysis failed: {str(e)}",
        ) from e


@router.get("/causal-chains", response_model=CausalChainsListResponse)
async def list_causal_chains(
    current_user: CurrentUser,
    limit: int = Query(20, ge=1, le=100, description="Maximum chains to return"),
    source_context: str | None = Query(None, description="Filter by source context"),
) -> CausalChainsListResponse:
    """List recent causal chains for the current user.

    Returns chains ordered by most recent first. Only returns
    non-invalidated chains.

    Args:
        current_user: Authenticated user
        limit: Maximum number of chains to return
        source_context: Optional filter by source context

    Returns:
        List of causal chains with total count
    """
    try:
        db = get_supabase_client()
        store = CausalChainStore(db_client=db)

        chains = await store.get_chains(
            user_id=current_user.id,
            limit=limit,
            source_context=source_context,
        )

        return CausalChainsListResponse(
            chains=[CausalChainResponse.from_chain(chain) for chain in chains],
            total=len(chains),
        )

    except Exception as e:
        logger.exception(
            "Failed to list causal chains",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve causal chains",
        ) from e


@router.get("/causal-chains/{chain_id}", response_model=CausalChainResponse)
async def get_causal_chain(
    current_user: CurrentUser,
    chain_id: UUID,
) -> CausalChainResponse:
    """Get a specific causal chain by ID.

    Args:
        current_user: Authenticated user
        chain_id: UUID of the chain to retrieve

    Returns:
        The requested causal chain

    Raises:
        HTTPException: If chain not found or access denied
    """
    try:
        db = get_supabase_client()
        store = CausalChainStore(db_client=db)

        chain = await store.get_chain(chain_id)

        if chain is None:
            raise HTTPException(
                status_code=404,
                detail=f"Causal chain {chain_id} not found",
            )

        return CausalChainResponse.from_chain(chain)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Failed to get causal chain",
            extra={"user_id": current_user.id, "chain_id": str(chain_id)},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve causal chain",
        ) from e


@router.delete("/causal-chains/{chain_id}", status_code=204)
async def invalidate_causal_chain(
    current_user: CurrentUser,
    chain_id: UUID,
) -> None:
    """Invalidate a causal chain.

    Marks the chain as invalidated. It will be kept for history
    but excluded from normal queries.

    Args:
        current_user: Authenticated user
        chain_id: UUID of the chain to invalidate

    Raises:
        HTTPException: If chain not found or operation fails
    """
    try:
        db = get_supabase_client()
        store = CausalChainStore(db_client=db)

        # First verify the chain exists and belongs to user
        chain = await store.get_chain(chain_id)
        if chain is None:
            raise HTTPException(
                status_code=404,
                detail=f"Causal chain {chain_id} not found",
            )

        success = await store.invalidate_chain(chain_id)

        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to invalidate causal chain",
            )

        logger.info(
            "Causal chain invalidated",
            extra={"user_id": current_user.id, "chain_id": str(chain_id)},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Failed to invalidate causal chain",
            extra={"user_id": current_user.id, "chain_id": str(chain_id)},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to invalidate causal chain",
        ) from e


@router.get("/causal-chains/entity/{entity_name}", response_model=CausalChainsListResponse)
async def get_chains_by_entity(
    current_user: CurrentUser,
    entity_name: str,
    limit: int = Query(10, ge=1, le=50, description="Maximum chains to return"),
) -> CausalChainsListResponse:
    """Get causal chains involving a specific entity.

    Searches both source and target entities across all hops
    to find chains that involve the specified entity.

    Args:
        current_user: Authenticated user
        entity_name: Name of the entity to search for
        limit: Maximum number of chains to return

    Returns:
        List of causal chains involving the entity
    """
    try:
        db = get_supabase_client()
        store = CausalChainStore(db_client=db)

        chains = await store.get_chains_by_entity(
            user_id=current_user.id,
            entity_name=entity_name,
            limit=limit,
        )

        return CausalChainsListResponse(
            chains=[CausalChainResponse.from_chain(chain) for chain in chains],
            total=len(chains),
        )

    except Exception as e:
        logger.exception(
            "Failed to get chains by entity",
            extra={"user_id": current_user.id, "entity_name": entity_name},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve causal chains by entity",
        ) from e


# ==============================================================================
# IMPLICATION REASONING ENDPOINTS (US-702)
# ==============================================================================


class InsightResponse(BaseModel):
    """Response model for a single insight."""

    id: str
    user_id: str
    insight_type: str
    trigger_event: str
    content: str
    classification: str
    impact_score: float
    confidence: float
    urgency: float
    combined_score: float
    causal_chain: list[dict[str, Any]]
    affected_goals: list[str]
    recommended_actions: list[str]
    status: str
    feedback_text: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_db(cls, data: dict[str, Any]) -> "InsightResponse":
        """Create response from database row."""
        return cls(
            id=str(data["id"]),
            user_id=str(data["user_id"]),
            insight_type=data["insight_type"],
            trigger_event=data["trigger_event"],
            content=data["content"],
            classification=data["classification"],
            impact_score=data["impact_score"],
            confidence=data["confidence"],
            urgency=data["urgency"],
            combined_score=data["combined_score"],
            causal_chain=data["causal_chain"] or [],
            affected_goals=data["affected_goals"] or [],
            recommended_actions=data["recommended_actions"] or [],
            status=data["status"],
            feedback_text=data.get("feedback_text"),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )


class InsightsListResponse(BaseModel):
    """Response model for listing insights."""

    insights: list[InsightResponse]
    total: int


@router.post("/implications", response_model=ImplicationResponse)
async def analyze_implications(
    current_user: CurrentUser,
    request: ImplicationRequest,
    save_insights: bool = Query(True, description="Whether to save insights to database"),
) -> ImplicationResponse:
    """Analyze an event for implications affecting user's goals.

    Traverses causal chains from the event, matches endpoints to the
    user's active goals, classifies as opportunity/threat/neutral,
    and generates LLM-powered explanations and recommendations.

    Args:
        current_user: Authenticated user
        request: Implication request with event and parameters
        save_insights: Whether to persist top insights to database

    Returns:
        ImplicationResponse with implications and processing metadata

    Raises:
        HTTPException: If analysis fails
    """
    try:
        db = get_supabase_client()
        llm = LLMClient()

        # Create engines
        causal_engine = CausalChainEngine(
            graphiti_client=None,
            llm_client=llm,
            db_client=db,
        )
        implication_engine = ImplicationEngine(
            causal_engine=causal_engine,
            db_client=db,
            llm_client=llm,
        )

        # Analyze event for implications
        response = await implication_engine.analyze_with_metadata(
            user_id=current_user.id,
            request=request,
        )

        # Optionally save top insights
        if save_insights and response.implications:
            # Save only top 5 insights by score
            for implication in response.implications[:5]:
                try:
                    await implication_engine.save_insight(
                        user_id=current_user.id,
                        implication=implication,
                    )
                except Exception as e:
                    logger.warning(f"Failed to save insight: {e}")

        logger.info(
            "Implication analysis completed",
            extra={
                "user_id": current_user.id,
                "implications_found": len(response.implications),
                "chains_analyzed": response.chains_analyzed,
                "goals_considered": response.goals_considered,
                "processing_time_ms": response.processing_time_ms,
            },
        )

        return response

    except Exception as e:
        logger.exception(
            "Implication analysis failed",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail=f"Implication analysis failed: {str(e)}",
        ) from e


@router.get("/insights", response_model=InsightsListResponse)
async def list_insights(
    current_user: CurrentUser,
    limit: int = Query(20, ge=1, le=100, description="Maximum insights to return"),
    status: str | None = Query(
        None, description="Filter by status (new, engaged, dismissed, feedback)"
    ),
    classification: str | None = Query(
        None, description="Filter by classification (opportunity, threat, neutral)"
    ),
    insight_type: str | None = Query(None, description="Filter by insight type"),
) -> InsightsListResponse:
    """List insights for the current user.

    Returns insights ordered by combined_score descending, then by
    created_at descending for equal scores.

    Args:
        current_user: Authenticated user
        limit: Maximum number of insights to return
        status: Optional filter by engagement status
        classification: Optional filter by classification type
        insight_type: Optional filter by insight type

    Returns:
        List of insights with total count
    """
    try:
        db = get_supabase_client()

        query = db.table("jarvis_insights").select("*").eq("user_id", current_user.id)

        if status:
            query = query.eq("status", status)
        if classification:
            query = query.eq("classification", classification)
        if insight_type:
            query = query.eq("insight_type", insight_type)

        result = (
            query.order("combined_score", desc=True)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        insights = result.data or []

        return InsightsListResponse(
            insights=[InsightResponse.from_db(insight) for insight in insights],
            total=len(insights),
        )

    except Exception as e:
        logger.exception(
            "Failed to list insights",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve insights",
        ) from e


@router.patch("/insights/{insight_id}", response_model=InsightResponse)
async def update_insight(
    current_user: CurrentUser,
    insight_id: UUID,
    request: InsightUpdateRequest,
) -> InsightResponse:
    """Update an insight's status or add feedback.

    Allows marking insights as engaged, dismissed, or adding feedback.

    Args:
        current_user: Authenticated user
        insight_id: UUID of the insight to update
        request: Update request with new status or feedback

    Returns:
        Updated insight

    Raises:
        HTTPException: If insight not found or update fails
    """
    try:
        db = get_supabase_client()

        # Build update data
        update_data: dict[str, Any] = {"updated_at": datetime.utcnow().isoformat()}

        if request.status:
            valid_statuses = {"new", "engaged", "dismissed", "feedback"}
            if request.status not in valid_statuses:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status. Must be one of: {valid_statuses}",
                )
            update_data["status"] = request.status

        if request.feedback_text is not None:
            update_data["feedback_text"] = request.feedback_text
            if request.status is None:
                update_data["status"] = "feedback"

        # Perform update
        result = (
            db.table("jarvis_insights")
            .update(update_data)
            .eq("id", str(insight_id))
            .eq("user_id", current_user.id)
            .execute()
        )

        if not result.data or len(result.data) == 0:
            raise HTTPException(
                status_code=404,
                detail=f"Insight {insight_id} not found",
            )

        logger.info(
            "Insight updated",
            extra={
                "user_id": current_user.id,
                "insight_id": str(insight_id),
                "status": update_data.get("status"),
            },
        )

        return InsightResponse.from_db(result.data[0])

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Failed to update insight",
            extra={"user_id": current_user.id, "insight_id": str(insight_id)},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to update insight",
        ) from e


@router.get("/insights/{insight_id}", response_model=InsightResponse)
async def get_insight(
    current_user: CurrentUser,
    insight_id: UUID,
) -> InsightResponse:
    """Get a specific insight by ID.

    Args:
        current_user: Authenticated user
        insight_id: UUID of the insight to retrieve

    Returns:
        The requested insight

    Raises:
        HTTPException: If insight not found
    """
    try:
        db = get_supabase_client()

        result = (
            db.table("jarvis_insights")
            .select("*")
            .eq("id", str(insight_id))
            .eq("user_id", current_user.id)
            .single()
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=404,
                detail=f"Insight {insight_id} not found",
            )

        return InsightResponse.from_db(result.data)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Failed to get insight",
            extra={"user_id": current_user.id, "insight_id": str(insight_id)},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve insight",
        ) from e
