"""Causal Intelligence API routes for ARIA Phase 7.

This module provides endpoints for causal chain traversal and analysis,
enabling ARIA to trace how events propagate through connected entities.
Also provides implication reasoning, butterfly effect detection, and
time horizon analysis endpoints.
"""

import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.api.deps import CurrentUser
from src.core.llm import LLMClient
from src.db.supabase import get_supabase_client
from src.intelligence.causal import (
    ButterflyDetectionRequest,
    ButterflyDetectionResponse,
    ButterflyDetector,
    CausalChain,
    CausalChainEngine,
    CausalChainStore,
    CausalTraversalRequest,
    CausalTraversalResponse,
    ConnectionInsight,
    ConnectionScanRequest,
    ConnectionScanResponse,
    ConnectionType,
    GoalImpactMapper,
    GoalImpactSummary,
    GoalWithInsights,
    WarningLevel,
)
from src.intelligence.causal.connection_engine import CrossDomainConnectionEngine
from src.intelligence.causal.implication_engine import ImplicationEngine
from src.intelligence.causal.models import (
    ButterflyEffect,
    ImplicationRequest,
    ImplicationResponse,
    InsightUpdateRequest,
)
from src.intelligence.predictive import (
    ActivePredictionsResponse,
    CalibrationResponse,
    PredictionCategory,
    PredictionErrorDetectionResponse,
    PredictiveEngine,
)
from src.intelligence.temporal import (
    ImplicationWithTiming,
    TimeHorizon,
    TimelineView,
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


# ==============================================================================
# BUTTERFLY EFFECT DETECTION ENDPOINTS (US-703)
# ==============================================================================


@router.post("/detect-butterfly", response_model=ButterflyDetectionResponse)
async def detect_butterfly_effect(
    current_user: CurrentUser,
    request: ButterflyDetectionRequest,
    save_insight: bool = Query(True, description="Whether to save butterfly insight"),
    create_notification: bool = Query(
        True, description="Create notification for high/critical warnings"
    ),
) -> ButterflyDetectionResponse:
    """Detect if an event has butterfly effect potential.

    Analyzes an event through causal chain traversal and implication
    reasoning to identify cascade amplification. Events with total
    implication impact >3x the base event are flagged as butterfly effects.

    Args:
        current_user: Authenticated user
        request: Detection request with event description
        save_insight: Whether to persist the butterfly effect insight
        create_notification: Whether to create notifications for high warnings

    Returns:
        ButterflyDetectionResponse with detected butterfly effect or None

    Raises:
        HTTPException: If detection fails
    """
    start_time = time.monotonic()

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
        butterfly_detector = ButterflyDetector(
            implication_engine=implication_engine,
            db_client=db,
            llm_client=llm,
        )

        # Detect butterfly effect
        butterfly = await butterfly_detector.detect(
            user_id=current_user.id,
            event=request.event,
            max_hops=request.max_hops,
        )

        # Count implications analyzed
        implications = await implication_engine.analyze_event(
            user_id=current_user.id,
            event=request.event,
            max_hops=request.max_hops,
        )

        # Save insight and create notification if applicable
        if butterfly and save_insight:
            await butterfly_detector.save_butterfly_insight(
                user_id=current_user.id,
                butterfly=butterfly,
            )

            # Create notification for high/critical warnings
            if create_notification and butterfly.warning_level in [
                WarningLevel.HIGH,
                WarningLevel.CRITICAL,
            ]:
                await _create_butterfly_notification(
                    db=db,
                    user_id=current_user.id,
                    butterfly=butterfly,
                )

        elapsed_ms = (time.monotonic() - start_time) * 1000

        logger.info(
            "Butterfly detection completed",
            extra={
                "user_id": current_user.id,
                "butterfly_detected": butterfly is not None,
                "warning_level": butterfly.warning_level.value if butterfly else None,
                "amplification": butterfly.amplification_factor if butterfly else None,
                "processing_time_ms": elapsed_ms,
            },
        )

        return ButterflyDetectionResponse(
            butterfly_effect=butterfly,
            implications_analyzed=len(implications),
            processing_time_ms=elapsed_ms,
        )

    except Exception as e:
        logger.exception(
            "Butterfly detection failed",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail=f"Butterfly detection failed: {str(e)}",
        ) from e


async def _create_butterfly_notification(
    db: Any,
    user_id: str,
    butterfly: ButterflyEffect,
) -> None:
    """Create a notification for high/critical butterfly effects.

    Args:
        db: Supabase client
        user_id: User ID
        butterfly: Detected butterfly effect
    """
    try:
        db.table("notifications").insert(
            {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "type": "butterfly_effect",
                "title": f"⚠️ {butterfly.warning_level.value.upper()}: Cascade Effect Detected",
                "message": (
                    f"Event '{butterfly.trigger_event[:100]}...' shows {butterfly.amplification_factor:.1f}x "
                    f"amplification across {butterfly.cascade_depth} cascade levels. "
                    f"Full impact expected in {butterfly.time_to_full_impact}."
                ),
                "metadata": {
                    "amplification_factor": butterfly.amplification_factor,
                    "cascade_depth": butterfly.cascade_depth,
                    "warning_level": butterfly.warning_level.value,
                    "affected_goal_count": butterfly.affected_goal_count,
                },
                "created_at": datetime.now(UTC).isoformat(),
            }
        ).execute()
    except Exception as e:
        logger.warning("Failed to create butterfly notification: %s", e)


# ==============================================================================
# CROSS-DOMAIN CONNECTION ENDPOINTS (US-704)
# ==============================================================================


@router.get("/connections", response_model=ConnectionScanResponse)
async def list_connection_insights(
    current_user: CurrentUser,
    limit: int = Query(20, ge=1, le=100, description="Maximum insights to return"),
) -> ConnectionScanResponse:
    """List recent cross-domain connection insights.

    Returns connections from jarvis_insights where insight_type='cross_domain_connection'.

    Args:
        current_user: Authenticated user
        limit: Maximum number of connections to return

    Returns:
        ConnectionScanResponse with stored connection insights
    """
    try:
        db = get_supabase_client()

        result = (
            db.table("jarvis_insights")
            .select("*")
            .eq("user_id", current_user.id)
            .eq("insight_type", "cross_domain_connection")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        insights = result.data or []

        connections: list[ConnectionInsight] = []
        for data in insights:
            events = [hop.get("event", "") for hop in (data.get("causal_chain") or [])]
            connections.append(
                ConnectionInsight(
                    id=data["id"],
                    source_events=events,
                    source_domains=["stored"],
                    connection_type=ConnectionType.LLM_INFERRED,
                    entities=[],
                    novelty_score=data.get("impact_score", 0.5),
                    actionability_score=data.get("confidence", 0.5),
                    relevance_score=data.get("urgency", 0.5),
                    explanation=data.get("content", ""),
                    recommended_action=(
                        (data.get("recommended_actions") or [""])[0]
                        if data.get("recommended_actions")
                        else None
                    ),
                    created_at=data.get("created_at"),
                )
            )

        return ConnectionScanResponse(
            connections=connections,
            events_scanned=len(connections),
            processing_time_ms=0,
        )

    except Exception as e:
        logger.exception(
            "Failed to list connection insights",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve connection insights",
        ) from e


@router.post("/connections/scan", response_model=ConnectionScanResponse)
async def scan_for_connections(
    current_user: CurrentUser,
    request: ConnectionScanRequest,
    save_insights: bool = Query(True, description="Save discovered connections"),
) -> ConnectionScanResponse:
    """Scan for cross-domain connections between events.

    Analyzes recent events from market signals, lead memories, and
    episodic memories to find non-obvious connections.

    Args:
        current_user: Authenticated user
        request: Scan request with optional events and parameters
        save_insights: Whether to persist discovered connections

    Returns:
        ConnectionScanResponse with discovered connections

    Raises:
        HTTPException: If scan fails
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
        connection_engine = CrossDomainConnectionEngine(
            graphiti_client=None,
            llm_client=llm,
            db_client=db,
            causal_engine=causal_engine,
        )

        # Run scan
        response = await connection_engine.scan_with_metadata(
            user_id=current_user.id,
            request=request,
        )

        # Save insights
        if save_insights and response.connections:
            for connection in response.connections[:5]:
                try:
                    await connection_engine.save_connection_insight(
                        user_id=current_user.id,
                        connection=connection,
                    )
                except Exception as e:
                    logger.warning(f"Failed to save connection insight: {e}")

        logger.info(
            "Cross-domain connection scan completed",
            extra={
                "user_id": current_user.id,
                "connections_found": len(response.connections),
                "events_scanned": response.events_scanned,
                "processing_time_ms": response.processing_time_ms,
            },
        )

        return response

    except Exception as e:
        logger.exception(
            "Connection scan failed",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail=f"Connection scan failed: {str(e)}",
        ) from e


# ==============================================================================
# TIME HORIZON ANALYSIS ENDPOINTS (US-705)
# ==============================================================================


@router.get("/timeline", response_model=TimelineView)
async def get_timeline(
    current_user: CurrentUser,
    limit: int = Query(20, ge=1, le=100, description="Maximum implications per horizon"),
    horizon_filter: TimeHorizon | None = Query(None, description="Filter to specific time horizon"),
    include_closing_windows: bool = Query(
        True, description="Include implications with closing action windows"
    ),
    classification: str | None = Query(
        None, description="Filter by classification (opportunity, threat, neutral)"
    ),
    min_score: float = Query(0.3, ge=0.0, le=1.0, description="Minimum combined score"),
) -> TimelineView:
    """Get timeline view of implications organized by time horizon.

    Returns implications categorized by when they'll materialize:
    - immediate: 1-7 days
    - short_term: 1-4 weeks
    - medium_term: 1-6 months
    - long_term: 6+ months

    Also includes a closing_windows list for time-sensitive actions.

    Args:
        current_user: Authenticated user
        limit: Maximum implications to return per horizon
        horizon_filter: Optional filter to specific time horizon
        include_closing_windows: Whether to include closing window implications
        classification: Optional filter by classification type
        min_score: Minimum combined score threshold

    Returns:
        TimelineView with implications organized by time horizon

    Raises:
        HTTPException: If retrieval fails
    """
    start_time = time.monotonic()

    try:
        db = get_supabase_client()

        # Build query for jarvis_insights
        query = (
            db.table("jarvis_insights")
            .select("*")
            .eq("user_id", current_user.id)
            .eq("insight_type", "implication")
            .gte("combined_score", min_score)
        )

        if classification:
            query = query.eq("classification", classification)

        # Get all matching insights
        result = query.order("combined_score", desc=True).limit(limit * 4).execute()

        insights = result.data or []

        # Categorize by time horizon
        immediate: list[ImplicationWithTiming] = []
        short_term: list[ImplicationWithTiming] = []
        medium_term: list[ImplicationWithTiming] = []
        long_term: list[ImplicationWithTiming] = []
        closing_windows: list[ImplicationWithTiming] = []

        for insight in insights:
            # Parse time horizon from insight
            horizon_str = insight.get("time_horizon")
            if horizon_str:
                try:
                    horizon = TimeHorizon(horizon_str)
                except ValueError:
                    horizon = TimeHorizon.MEDIUM_TERM
            else:
                # Default based on urgency
                urgency = insight.get("urgency", 0.5)
                if urgency >= 0.8:
                    horizon = TimeHorizon.IMMEDIATE
                elif urgency >= 0.6:
                    horizon = TimeHorizon.SHORT_TERM
                elif urgency >= 0.4:
                    horizon = TimeHorizon.MEDIUM_TERM
                else:
                    horizon = TimeHorizon.LONG_TERM

            # Skip if horizon filter is set and doesn't match
            if horizon_filter and horizon != horizon_filter:
                continue

            # Build ImplicationWithTiming
            impl_with_timing = ImplicationWithTiming(
                id=insight.get("id"),
                trigger_event=insight.get("trigger_event", ""),
                content=insight.get("content", ""),
                classification=insight.get("classification", "neutral"),
                impact_score=insight.get("impact_score", 0.5),
                confidence=insight.get("confidence", 0.5),
                urgency=insight.get("urgency", 0.5),
                combined_score=insight.get("combined_score", 0.5),
                time_horizon=horizon,
                time_to_impact=insight.get("time_to_impact"),
                affected_goals=insight.get("affected_goals") or [],
                recommended_actions=insight.get("recommended_actions") or [],
                is_closing_window=urgency >= 0.7
                and horizon
                in [
                    TimeHorizon.IMMEDIATE,
                    TimeHorizon.SHORT_TERM,
                ],
                created_at=insight.get("created_at"),
            )

            # Add to appropriate horizon list
            if horizon == TimeHorizon.IMMEDIATE:
                if len(immediate) < limit:
                    immediate.append(impl_with_timing)
            elif horizon == TimeHorizon.SHORT_TERM:
                if len(short_term) < limit:
                    short_term.append(impl_with_timing)
            elif horizon == TimeHorizon.MEDIUM_TERM:
                if len(medium_term) < limit:
                    medium_term.append(impl_with_timing)
            else:  # LONG_TERM
                if len(long_term) < limit:
                    long_term.append(impl_with_timing)

            # Add to closing windows if applicable
            if (
                include_closing_windows
                and impl_with_timing.is_closing_window
                and len(closing_windows) < limit
            ):
                closing_windows.append(impl_with_timing)

        elapsed_ms = (time.monotonic() - start_time) * 1000
        total_count = len(immediate) + len(short_term) + len(medium_term) + len(long_term)

        logger.info(
            "Timeline view generated",
            extra={
                "user_id": current_user.id,
                "immediate": len(immediate),
                "short_term": len(short_term),
                "medium_term": len(medium_term),
                "long_term": len(long_term),
                "closing_windows": len(closing_windows),
                "total_count": total_count,
                "processing_time_ms": elapsed_ms,
            },
        )

        return TimelineView(
            immediate=immediate,
            short_term=short_term,
            medium_term=medium_term,
            long_term=long_term,
            closing_windows=closing_windows,
            total_count=total_count,
            processing_time_ms=elapsed_ms,
        )

    except Exception as e:
        logger.exception(
            "Timeline retrieval failed",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail=f"Timeline retrieval failed: {str(e)}",
        ) from e


# ==============================================================================
# GOAL IMPACT MAPPING ENDPOINTS (US-706)
# ==============================================================================


@router.get("/goal-impact", response_model=GoalImpactSummary)
async def get_goal_impact_summary(
    current_user: CurrentUser,
    include_draft_goals: bool = Query(True, description="Include draft goals in analysis"),
    days_back: int = Query(30, ge=1, le=90, description="Days to look back for insights"),
) -> GoalImpactSummary:
    """Get goal impact summary showing insights affecting each goal.

    Returns a summary of all goals with their associated insights,
    including net pressure (opportunities vs threats) and counts.

    Args:
        current_user: Authenticated user
        include_draft_goals: Whether to include draft goals
        days_back: Number of days to look back for insights

    Returns:
        GoalImpactSummary with goals and their associated insights

    Raises:
        HTTPException: If summary generation fails
    """
    try:
        db = get_supabase_client()
        llm = LLMClient()

        mapper = GoalImpactMapper(
            db_client=db,
            llm_client=llm,
        )

        summary = await mapper.get_goal_impact_summary(
            user_id=str(current_user.id),
            include_draft_goals=include_draft_goals,
            days_back=days_back,
        )

        logger.info(
            "Goal impact summary generated",
            extra={
                "user_id": current_user.id,
                "goal_count": len(summary.goals),
                "total_insights": summary.total_insights_analyzed,
                "multi_goal_implications": summary.multi_goal_implications,
                "processing_time_ms": summary.processing_time_ms,
            },
        )

        return summary

    except Exception as e:
        logger.exception(
            "Goal impact summary failed",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail=f"Goal impact summary failed: {str(e)}",
        ) from e


@router.get("/goal-impact/{goal_id}", response_model=GoalWithInsights)
async def get_goal_impact(
    current_user: CurrentUser,
    goal_id: UUID,
    limit: int = Query(20, ge=1, le=100, description="Maximum insights to return"),
) -> GoalWithInsights:
    """Get insights affecting a specific goal.

    Returns all insights that affect the specified goal,
    including their classification and impact scores.

    Args:
        current_user: Authenticated user
        goal_id: UUID of the goal to get insights for
        limit: Maximum number of insights to return

    Returns:
        GoalWithInsights for the specified goal

    Raises:
        HTTPException: If goal not found or retrieval fails
    """
    try:
        db = get_supabase_client()
        llm = LLMClient()

        mapper = GoalImpactMapper(
            db_client=db,
            llm_client=llm,
        )

        result = await mapper.get_goal_insights(
            user_id=str(current_user.id),
            goal_id=str(goal_id),
            limit=limit,
        )

        logger.info(
            "Goal impact retrieved",
            extra={
                "user_id": current_user.id,
                "goal_id": str(goal_id),
                "insight_count": len(result.insights),
                "net_pressure": result.net_pressure,
            },
        )

        return result

    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.exception(
            "Goal impact retrieval failed",
            extra={"user_id": current_user.id, "goal_id": str(goal_id)},
        )
        raise HTTPException(
            status_code=500,
            detail=f"Goal impact retrieval failed: {str(e)}",
        ) from e


# ==============================================================================
# PREDICTIVE PROCESSING ENDPOINTS (US-707)
# ==============================================================================


@router.get("/predictions/active", response_model=ActivePredictionsResponse)
async def get_active_predictions(
    current_user: CurrentUser,
    limit: int = Query(20, ge=1, le=100, description="Maximum predictions to return"),
) -> ActivePredictionsResponse:
    """Get active predictions for the current user.

    Returns all pending predictions that have not yet been validated
    or expired, ordered by expected resolution date.

    Args:
        current_user: Authenticated user
        limit: Maximum number of predictions to return

    Returns:
        ActivePredictionsResponse with predictions and metadata

    Raises:
        HTTPException: If retrieval fails
    """
    try:
        engine = PredictiveEngine()

        response = await engine.get_active_predictions(
            user_id=str(current_user.id),
            limit=limit,
        )

        logger.info(
            "Active predictions retrieved",
            extra={
                "user_id": current_user.id,
                "prediction_count": response.total_count,
                "processing_time_ms": response.processing_time_ms,
            },
        )

        return response

    except Exception as e:
        logger.exception(
            "Failed to get active predictions",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve predictions: {str(e)}",
        ) from e


@router.get("/predictions/calibration", response_model=CalibrationResponse)
async def get_prediction_calibration(
    current_user: CurrentUser,
    prediction_type: PredictionCategory | None = Query(
        None, description="Filter by prediction type"
    ),
) -> CalibrationResponse:
    """Get calibration statistics for predictions.

    Returns calibration data showing how well ARIA's confidence
    matches actual accuracy. Well-calibrated predictions have
    accuracy within 10% of confidence.

    Args:
        current_user: Authenticated user
        prediction_type: Optional filter by prediction type

    Returns:
        CalibrationResponse with calibration data and overall metrics

    Raises:
        HTTPException: If retrieval fails
    """
    try:
        engine = PredictiveEngine()

        response = await engine.get_calibration_response(
            user_id=str(current_user.id),
            prediction_type=prediction_type,
        )

        logger.info(
            "Prediction calibration retrieved",
            extra={
                "user_id": current_user.id,
                "total_predictions": response.total_predictions,
                "overall_accuracy": response.overall_accuracy,
                "processing_time_ms": response.processing_time_ms,
            },
        )

        return response

    except Exception as e:
        logger.exception(
            "Failed to get prediction calibration",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve calibration: {str(e)}",
        ) from e


@router.post("/predictions/detect-errors", response_model=PredictionErrorDetectionResponse)
async def detect_prediction_errors(
    current_user: CurrentUser,
    boost_salience: bool = Query(
        True, description="Boost salience for surprising prediction errors"
    ),
) -> PredictionErrorDetectionResponse:
    """Detect prediction errors (surprises) for the current user.

    Compares pending predictions against actual events to identify
    prediction errors. High-surprise errors boost entity salience
    to direct ARIA's attention.

    This implements predictive processing theory where prediction
    errors drive learning and attention allocation.

    Args:
        current_user: Authenticated user
        boost_salience: Whether to boost salience for high-surprise errors

    Returns:
        PredictionErrorDetectionResponse with detected errors and metadata

    Raises:
        HTTPException: If detection fails
    """
    try:
        engine = PredictiveEngine()

        response = await engine.detect_errors_with_metadata(
            user_id=str(current_user.id),
            boost_salience=boost_salience,
        )

        logger.info(
            "Prediction errors detected",
            extra={
                "user_id": current_user.id,
                "errors_detected": len(response.errors_detected),
                "predictions_validated": response.predictions_validated,
                "predictions_expired": response.predictions_expired,
                "salience_boosted": len(response.salience_boosted_entities),
                "processing_time_ms": response.processing_time_ms,
            },
        )

        return response

    except Exception as e:
        logger.exception(
            "Failed to detect prediction errors",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to detect prediction errors: {str(e)}",
        ) from e
