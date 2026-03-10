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
from typing import Any, List
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

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
from src.intelligence.simulation import (
    MentalSimulationEngine,
    OutcomeClassification,
    QuickSimulationResponse,
    ScenarioType,
    SimulationOutcome,
    SimulationRequest,
    SimulationResponse,
    SimulationResult,
)
from src.intelligence.temporal import (
    ImplicationWithTiming,
    TemporalAnalysis,
    TemporalAnalysisRequest,
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
            detail="Causal chain analysis failed. Please try again.",
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
    trigger_event: str | None = None  # Optional - may not be in all insight types
    engine_source: str | None = None  # Which Jarvis engine generated this
    title: str | None = None  # Optional title for the insight
    content: str
    classification: str
    impact_score: float
    confidence: float
    urgency: float
    combined_score: float
    priority: float | None = None  # Priority score (0-1)
    time_horizon: str | None = None  # When impact expected (immediate, short_term, etc.)
    causal_chain: list[dict[str, Any]]
    affected_goals: list[str]
    recommended_actions: list[str]
    status: str
    feedback_text: str | None = None
    explanation: str | None = None  # Optional explanation of the insight
    created_at: str
    updated_at: str

    @classmethod
    def from_db(cls, data: dict[str, Any]) -> "InsightResponse":
        """Create response from database row."""
        return cls(
            id=str(data["id"]),
            user_id=str(data["user_id"]),
            insight_type=data["insight_type"],
            trigger_event=data.get("trigger_event"),  # Optional field
            engine_source=data.get("engine_source"),
            title=data.get("title"),
            content=data["content"],
            classification=data["classification"],
            impact_score=data["impact_score"],
            confidence=data["confidence"],
            urgency=data["urgency"],
            combined_score=data["combined_score"],
            priority=data.get("priority"),
            time_horizon=data.get("time_horizon"),
            causal_chain=data.get("causal_chain") or [],
            affected_goals=data.get("affected_goals") or [],
            recommended_actions=data.get("recommended_actions") or [],
            status=data["status"],
            feedback_text=data.get("feedback_text"),
            explanation=data.get("explanation"),
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
            detail="Implication analysis failed. Please try again.",
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
            detail="Butterfly detection failed. Please try again.",
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
            detail="Connection scan failed. Please try again.",
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
            detail="Timeline retrieval failed. Please try again.",
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
            detail="Goal impact summary failed. Please try again.",
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
        logger.warning(
            "Goal impact not found",
            extra={"user_id": current_user.id, "goal_id": str(goal_id), "error": str(e)},
        )
        raise HTTPException(
            status_code=404,
            detail="The requested goal impact data was not found.",
        ) from e
    except Exception as e:
        logger.exception(
            "Goal impact retrieval failed",
            extra={"user_id": current_user.id, "goal_id": str(goal_id)},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve goal impact data. Please try again.",
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
            detail="Failed to retrieve predictions. Please try again.",
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
            detail="Failed to retrieve calibration. Please try again.",
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
            detail="Failed to detect prediction errors. Please try again.",
        ) from e


# ==============================================================================
# MENTAL SIMULATION ENDPOINTS (US-708)
# ==============================================================================


class SimulationListResponse(BaseModel):
    """Response model for listing simulations."""

    simulations: list[SimulationResult]
    total: int


@router.post("/simulations", response_model=SimulationResponse)
async def run_simulation(
    current_user: CurrentUser,
    request: SimulationRequest,
    save_results: bool = Query(True, description="Whether to save simulation to database"),
) -> SimulationResponse:
    """Run a mental simulation for a "what if" scenario.

    Analyzes a scenario to generate multiple possible outcomes,
    traverses causal chains to identify downstream effects,
    and provides a recommendation based on expected value.

    Args:
        current_user: Authenticated user
        request: Simulation request with scenario and parameters
        save_results: Whether to persist the simulation result

    Returns:
        SimulationResponse with outcomes and recommendation

    Raises:
        HTTPException: If simulation fails
    """
    try:
        db = get_supabase_client()
        llm = LLMClient()

        # Create causal engine for chain traversal
        causal_engine = CausalChainEngine(
            graphiti_client=None,
            llm_client=llm,
            db_client=db,
        )

        # Create simulation engine
        simulation_engine = MentalSimulationEngine(
            causal_engine=causal_engine,
            llm_client=llm,
            db_client=db,
        )

        # Run simulation
        result = await simulation_engine.simulate(
            user_id=current_user.id,
            request=request,
        )

        # Optionally save
        simulation_id = None
        saved = False
        if save_results:
            try:
                simulation_id = await simulation_engine.save_simulation(
                    user_id=current_user.id,
                    result=result,
                )
                saved = True
            except Exception as e:
                logger.warning(f"Failed to save simulation: {e}")

        logger.info(
            "Simulation completed",
            extra={
                "user_id": current_user.id,
                "outcomes_generated": len(result.outcomes),
                "confidence": result.confidence,
                "saved": saved,
                "processing_time_ms": result.processing_time_ms,
            },
        )

        return SimulationResponse(
            result=result,
            simulation_id=simulation_id,
            saved=saved,
        )

    except Exception as e:
        logger.exception(
            "Simulation failed",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail="Simulation failed. Please try again.",
        ) from e


@router.get("/simulations", response_model=SimulationListResponse)
async def list_simulations(
    current_user: CurrentUser,
    limit: int = Query(20, ge=1, le=100, description="Maximum simulations to return"),
) -> SimulationListResponse:
    """List past simulation results.

    Returns simulations stored in jarvis_insights where
    insight_type='simulation_result', ordered by most recent.

    Args:
        current_user: Authenticated user
        limit: Maximum number of simulations to return

    Returns:
        SimulationListResponse with simulation results

    Raises:
        HTTPException: If retrieval fails
    """
    try:
        db = get_supabase_client()

        result = (
            db.table("jarvis_insights")
            .select("*")
            .eq("user_id", current_user.id)
            .eq("insight_type", "simulation_result")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        insights = result.data or []

        simulations: list[SimulationResult] = []
        for insight in insights:
            # Reconstruct SimulationResult from stored data
            outcomes_data = insight.get("causal_chain") or []

            outcomes = [
                SimulationOutcome(
                    scenario=o.get("scenario", ""),
                    probability=o.get("probability", 0.5),
                    classification=OutcomeClassification(o.get("classification", "mixed")),
                    positive_outcomes=o.get("positive_outcomes", []),
                    negative_outcomes=o.get("negative_outcomes", []),
                    key_uncertainties=o.get("key_uncertainties", []),
                    recommended=o.get("recommended", False),
                    reasoning=o.get("reasoning", ""),
                    causal_chain=o.get("causal_chain", []),
                    time_to_impact=o.get("time_to_impact"),
                    affected_goals=o.get("affected_goals", []),
                )
                for o in outcomes_data
                if isinstance(o, dict)
            ]

            simulations.append(
                SimulationResult(
                    scenario=insight.get("trigger_event", ""),
                    scenario_type=ScenarioType.HYPOTHETICAL,
                    outcomes=outcomes,
                    recommended_path=(insight.get("recommended_actions") or [""])[0],
                    reasoning=insight.get("content", ""),
                    sensitivity={},
                    confidence=insight.get("confidence", 0.5),
                    key_insights=[],
                    processing_time_ms=0,
                )
            )

        return SimulationListResponse(
            simulations=simulations,
            total=len(simulations),
        )

    except Exception as e:
        logger.exception(
            "Failed to list simulations",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve simulations. Please try again.",
        ) from e


@router.get("/simulations/{simulation_id}", response_model=SimulationResponse)
async def get_simulation(
    current_user: CurrentUser,
    simulation_id: UUID,
) -> SimulationResponse:
    """Get a specific simulation result by ID.

    Args:
        current_user: Authenticated user
        simulation_id: UUID of the simulation to retrieve

    Returns:
        SimulationResponse with the simulation result

    Raises:
        HTTPException: If simulation not found
    """
    try:
        db = get_supabase_client()

        result = (
            db.table("jarvis_insights")
            .select("*")
            .eq("id", str(simulation_id))
            .eq("user_id", current_user.id)
            .eq("insight_type", "simulation_result")
            .single()
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=404,
                detail=f"Simulation {simulation_id} not found",
            )

        insight = result.data

        # Reconstruct SimulationResult
        outcomes_data = insight.get("causal_chain") or []

        outcomes = [
            SimulationOutcome(
                scenario=o.get("scenario", ""),
                probability=o.get("probability", 0.5),
                classification=OutcomeClassification(o.get("classification", "mixed")),
                positive_outcomes=o.get("positive_outcomes", []),
                negative_outcomes=o.get("negative_outcomes", []),
                key_uncertainties=o.get("key_uncertainties", []),
                recommended=o.get("recommended", False),
                reasoning=o.get("reasoning", ""),
                causal_chain=o.get("causal_chain", []),
                time_to_impact=o.get("time_to_impact"),
                affected_goals=o.get("affected_goals", []),
            )
            for o in outcomes_data
            if isinstance(o, dict)
        ]

        simulation_result = SimulationResult(
            scenario=insight.get("trigger_event", ""),
            scenario_type=ScenarioType.HYPOTHETICAL,
            outcomes=outcomes,
            recommended_path=(insight.get("recommended_actions") or [""])[0],
            reasoning=insight.get("content", ""),
            sensitivity={},
            confidence=insight.get("confidence", 0.5),
            key_insights=[],
            processing_time_ms=0,
        )

        return SimulationResponse(
            result=simulation_result,
            simulation_id=simulation_id,
            saved=True,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Failed to get simulation",
            extra={"user_id": current_user.id, "simulation_id": str(simulation_id)},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve simulation. Please try again.",
        ) from e


@router.post("/simulations/quick", response_model=QuickSimulationResponse)
async def quick_simulation(
    current_user: CurrentUser,
    question: str = Query(..., min_length=10, max_length=1000, description="The what-if question"),
) -> QuickSimulationResponse:
    """Run a quick simulation for chat integration.

    Lightweight simulation without full causal chain traversal,
    suitable for real-time chat responses to "what if" questions.

    Args:
        current_user: Authenticated user
        question: The "what if" question to answer

    Returns:
        QuickSimulationResponse with natural language answer

    Raises:
        HTTPException: If simulation fails
    """
    try:
        engine = MentalSimulationEngine()

        response = await engine.quick_simulate(
            user_id=current_user.id,
            question=question,
        )

        logger.info(
            "Quick simulation completed",
            extra={
                "user_id": current_user.id,
                "confidence": response.confidence,
                "processing_time_ms": response.processing_time_ms,
            },
        )

        return response

    except Exception as e:
        logger.exception(
            "Quick simulation failed",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail="Quick simulation failed. Please try again.",
        ) from e


# ==============================================================================
# MULTI-SCALE TEMPORAL REASONING ENDPOINTS (US-709)
# ==============================================================================


@router.post("/temporal-analysis", response_model=TemporalAnalysis)
async def analyze_decision_temporal(
    current_user: CurrentUser,
    request: TemporalAnalysisRequest,
) -> TemporalAnalysis:
    """Analyze a decision across all time scales.

    Enables ARIA to reason simultaneously across different time horizons
    (immediate, tactical, strategic, visionary), detect cross-scale conflicts,
    and generate time-appropriate recommendations.

    This is particularly useful for:
    - Decisions with short-term benefits but long-term risks
    - Resource allocation across competing time horizons
    - Strategic planning that needs to balance immediate and future needs

    Args:
        current_user: Authenticated user
        request: Temporal analysis request with decision and parameters

    Returns:
        TemporalAnalysis with cross-scale impacts, conflicts, and recommendations

    Raises:
        HTTPException: If analysis fails
    """
    try:
        from src.intelligence.temporal import MultiScaleTemporalReasoner

        reasoner = MultiScaleTemporalReasoner(
            llm_client=LLMClient(),
            db_client=get_supabase_client(),
        )

        response = await reasoner.analyze_with_metadata(
            user_id=str(current_user.id),
            request=request,
        )

        logger.info(
            "Temporal analysis completed",
            extra={
                "user_id": current_user.id,
                "primary_scale": response.primary_scale.value,
                "conflicts_found": len(response.conflicts),
                "overall_alignment": response.overall_alignment,
                "processing_time_ms": response.processing_time_ms,
            },
        )

        return response

    except Exception as e:
        logger.exception(
            "Temporal analysis failed",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail="Temporal analysis failed. Please try again.",
        ) from e


# ==============================================================================
# JARVIS ORCHESTRATOR ENDPOINTS (US-710)
# ==============================================================================


class BriefingRequest(BaseModel):
    """Request model for intelligence briefing generation."""

    context: dict[str, Any] | None = None
    budget_ms: int = Field(default=5000, ge=1000, le=15000)


class ProcessEventRequest(BaseModel):
    """Request model for event processing through intelligence pipeline."""

    event: str = Field(..., min_length=10, max_length=2000)
    source_context: str = Field(default="api_request")
    source_id: str | None = None


class InsightFeedbackRequest(BaseModel):
    """Request model for recording feedback on an insight."""

    feedback: str = Field(
        ..., description="Feedback value: helpful, not_helpful, or wrong"
    )


class IntelligenceMetrics(BaseModel):
    """Response model for intelligence system metrics."""

    total_insights: int
    by_type: dict[str, int]
    by_classification: dict[str, int]
    by_status: dict[str, int]
    average_score: float
    last_7_days: int
    last_30_days: int


@router.post("/briefing", response_model=InsightsListResponse)
async def generate_intelligence_briefing(
    current_user: CurrentUser,
    request: BriefingRequest,
) -> InsightsListResponse:
    """Generate intelligence insights for a briefing.

    Runs all engines in priority order with time-budgeted execution.
    Returns up to 10 deduplicated insights sorted by combined score.
    """
    try:
        from src.intelligence.orchestrator import create_orchestrator

        orchestrator = create_orchestrator()
        insights = await orchestrator.generate_briefing(
            user_id=str(current_user.id),
            context=request.context,
            budget_ms=request.budget_ms,
        )

        insight_responses = []
        for i in insights:
            insight_responses.append(
                InsightResponse(
                    id=str(i.id),
                    user_id=str(i.user_id),
                    insight_type=i.insight_type,
                    trigger_event=i.trigger_event,
                    content=i.content,
                    classification=i.classification,
                    impact_score=i.impact_score,
                    confidence=i.confidence,
                    urgency=i.urgency,
                    combined_score=i.combined_score,
                    causal_chain=i.causal_chain,
                    affected_goals=i.affected_goals,
                    recommended_actions=i.recommended_actions,
                    status=i.status,
                    feedback_text=i.feedback_text,
                    created_at=i.created_at.isoformat() if hasattr(i.created_at, "isoformat") else str(i.created_at),
                    updated_at=i.updated_at.isoformat() if hasattr(i.updated_at, "isoformat") else str(i.updated_at),
                )
            )

        return InsightsListResponse(
            insights=insight_responses,
            total=len(insight_responses),
        )

    except Exception as e:
        logger.exception(
            "Intelligence briefing generation failed",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail="Intelligence briefing failed. Please try again.",
        ) from e


@router.post("/process-event", response_model=InsightsListResponse)
async def process_intelligence_event(
    current_user: CurrentUser,
    request: ProcessEventRequest,
) -> InsightsListResponse:
    """Process an event through the full intelligence pipeline.

    Runs causal traversal, implications, butterfly detection,
    goal impact, and time horizon categorization.
    """
    try:
        from src.intelligence.orchestrator import create_orchestrator

        orchestrator = create_orchestrator()
        insights = await orchestrator.process_event(
            user_id=str(current_user.id),
            event=request.event,
            source_context=request.source_context,
            source_id=request.source_id,
        )

        insight_responses = []
        for i in insights:
            insight_responses.append(
                InsightResponse(
                    id=str(i.id),
                    user_id=str(i.user_id),
                    insight_type=i.insight_type,
                    trigger_event=i.trigger_event,
                    content=i.content,
                    classification=i.classification,
                    impact_score=i.impact_score,
                    confidence=i.confidence,
                    urgency=i.urgency,
                    combined_score=i.combined_score,
                    causal_chain=i.causal_chain,
                    affected_goals=i.affected_goals,
                    recommended_actions=i.recommended_actions,
                    status=i.status,
                    feedback_text=i.feedback_text,
                    created_at=i.created_at.isoformat() if hasattr(i.created_at, "isoformat") else str(i.created_at),
                    updated_at=i.updated_at.isoformat() if hasattr(i.updated_at, "isoformat") else str(i.updated_at),
                )
            )

        return InsightsListResponse(
            insights=insight_responses,
            total=len(insight_responses),
        )

    except Exception as e:
        logger.exception(
            "Intelligence event processing failed",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail="Event processing failed. Please try again.",
        ) from e


@router.patch("/insights/{insight_id}/feedback", response_model=InsightResponse)
async def record_insight_feedback(
    current_user: CurrentUser,
    insight_id: str,
    request: InsightFeedbackRequest,
) -> InsightResponse:
    """Record user feedback on an intelligence insight."""
    try:
        from src.intelligence.orchestrator import create_orchestrator

        orchestrator = create_orchestrator()
        await orchestrator.record_feedback(
            insight_id=insight_id,
            feedback=request.feedback,
            user_id=str(current_user.id),
        )

        # Fetch and return the updated insight
        db = get_supabase_client()
        response = (
            db.table("jarvis_insights")
            .select("*")
            .eq("id", insight_id)
            .eq("user_id", str(current_user.id))
            .single()
            .execute()
        )

        if not response.data:
            raise HTTPException(status_code=404, detail="Insight not found")

        return InsightResponse.from_db(response.data)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Insight feedback recording failed",
            extra={"user_id": current_user.id, "insight_id": insight_id},
        )
        raise HTTPException(
            status_code=500,
            detail="Feedback recording failed. Please try again.",
        ) from e


@router.get("/metrics", response_model=IntelligenceMetrics)
async def get_intelligence_metrics(
    current_user: CurrentUser,
) -> IntelligenceMetrics:
    """Get aggregated metrics for the intelligence system."""
    try:
        from src.intelligence.orchestrator import create_orchestrator

        orchestrator = create_orchestrator()
        metrics = await orchestrator.get_engine_metrics(
            user_id=str(current_user.id),
        )

        return IntelligenceMetrics(**metrics)

    except Exception as e:
        logger.exception(
            "Intelligence metrics retrieval failed",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail="Metrics retrieval failed. Please try again.",
        ) from e


# ==============================================================================
# METACOGNITION ENDPOINTS (US-803)
# ==============================================================================


class MetacognitionResponse(BaseModel):
    """Response model for metacognition assessment."""

    topic: str
    confidence: float
    knowledge_source: str
    last_updated: str
    reliability_notes: str
    should_research: bool
    fact_count: int
    uncertainty_acknowledgment: str | None


@router.get("/metacognition", response_model=MetacognitionResponse)
async def get_metacognition(
    current_user: CurrentUser,
    topic: str = Query(..., min_length=1, max_length=500, description="Topic to assess"),
    use_cache: bool = Query(True, description="Use cached assessment if available"),
) -> MetacognitionResponse:
    """Assess ARIA's knowledge confidence on a specific topic.

    This endpoint enables ARIA to understand what she knows and doesn't know,
    acknowledge uncertainty appropriately, and calibrate confidence based on
    her track record.

    Args:
        current_user: Authenticated user
        topic: Topic to assess knowledge confidence for
        use_cache: Whether to use cached assessment if available

    Returns:
        MetacognitionResponse with confidence, source, and uncertainty acknowledgment

    Raises:
        HTTPException: If assessment fails
    """
    try:
        from src.companion.metacognition import MetacognitionService

        service = MetacognitionService()

        # Check cache first if enabled
        if use_cache:
            cached = await service.get_cached_assessment(str(current_user.id), topic)
            if cached:
                acknowledgment = service.acknowledge_uncertainty(cached)
                return MetacognitionResponse(
                    topic=cached.topic,
                    confidence=cached.confidence,
                    knowledge_source=cached.knowledge_source.value,
                    last_updated=cached.last_updated.isoformat(),
                    reliability_notes=cached.reliability_notes,
                    should_research=cached.should_research,
                    fact_count=cached.fact_count,
                    uncertainty_acknowledgment=acknowledgment,
                )

        # Perform fresh assessment
        assessment = await service.assess_knowledge(str(current_user.id), topic)
        acknowledgment = service.acknowledge_uncertainty(assessment)

        logger.info(
            "Metacognition assessment completed",
            extra={
                "user_id": current_user.id,
                "topic": topic,
                "confidence": assessment.confidence,
                "knowledge_source": assessment.knowledge_source.value,
                "fact_count": assessment.fact_count,
            },
        )

        return MetacognitionResponse(
            topic=assessment.topic,
            confidence=assessment.confidence,
            knowledge_source=assessment.knowledge_source.value,
            last_updated=assessment.last_updated.isoformat(),
            reliability_notes=assessment.reliability_notes,
            should_research=assessment.should_research,
            fact_count=assessment.fact_count,
            uncertainty_acknowledgment=acknowledgment,
        )

    except Exception as e:
        logger.exception(
            "Metacognition assessment failed",
            extra={"user_id": current_user.id, "topic": topic},
        )
        raise HTTPException(
            status_code=500,
            detail="Metacognition assessment failed. Please try again.",
        ) from e


# ==============================================================================
# RETURN BRIEFING ENDPOINTS (E7)
# ==============================================================================


@router.get("/return-briefing")
async def get_return_briefing(
    current_user: CurrentUser,
) -> dict:
    """Get a 'what changed while you were away' briefing.

    Generates a prioritized briefing of changes since the user was last active.
    Returns a summary only if the user has been away for 4+ hours.

    Args:
        current_user: Authenticated user

    Returns:
        Briefing with changes, summary, and priority items, or a no-briefing-needed message

    Raises:
        HTTPException: If briefing generation fails
    """
    try:
        from src.intelligence.return_briefing import ReturnBriefingGenerator

        generator = ReturnBriefingGenerator(get_supabase_client())
        briefing = await generator.generate_return_briefing(str(current_user.id))

        if not briefing:
            return {"status": "no_briefing_needed", "message": "You're all caught up."}

        return briefing

    except Exception as e:
        logger.exception(
            "Return briefing generation failed",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail="Return briefing generation failed. Please try again.",
        ) from e


# ==============================================================================
# THERAPEUTIC AREA TREND ENDPOINTS (E8)
# ==============================================================================


class TherapeuticTrendResponse(BaseModel):
    """Response model for a single therapeutic trend."""

    trend_type: str
    name: str
    signal_count: int
    companies_involved: list[str]
    company_count: int
    description: str
    narrative: str = ""


class TherapeuticTrendsListResponse(BaseModel):
    """Response model for listing therapeutic trends."""

    trends: list[TherapeuticTrendResponse]
    count: int


@router.get("/therapeutic-trends", response_model=TherapeuticTrendsListResponse)
async def get_therapeutic_trends(
    current_user: CurrentUser,
    days: int = Query(30, ge=1, le=90, description="Days to look back for trends"),
    min_signals: int = Query(3, ge=2, le=10, description="Minimum signals to form a trend"),
) -> TherapeuticTrendsListResponse:
    """Get therapeutic area and manufacturing modality trends across recent signals.

    Analyzes market signals to detect patterns where multiple signals point
    to the same therapeutic area or manufacturing modality across different
    companies. Returns sector-level insights useful for strategic planning.

    Args:
        current_user: Authenticated user
        days: Number of days to look back for signal analysis
        min_signals: Minimum number of signals required to form a trend

    Returns:
        TherapeuticTrendsListResponse with detected trends and count

    Raises:
        HTTPException: If trend detection fails
    """
    try:
        from src.intelligence.therapeutic_area_intelligence import detect_therapeutic_trends

        db = get_supabase_client()
        trends = await detect_therapeutic_trends(
            supabase_client=db,
            user_id=str(current_user.id),
            days=days,
            min_signals=min_signals,
        )

        logger.info(
            "Therapeutic trends retrieved",
            extra={
                "user_id": current_user.id,
                "trend_count": len(trends),
                "days": days,
            },
        )

        return TherapeuticTrendsListResponse(
            trends=[
                TherapeuticTrendResponse(
                    trend_type=t["trend_type"],
                    name=t["name"],
                    signal_count=t["signal_count"],
                    companies_involved=t["companies_involved"],
                    company_count=t["company_count"],
                    description=t["description"],
                    narrative=t.get("narrative", ""),
                )
                for t in trends
            ],
            count=len(trends),
        )

    except Exception as e:
        logger.exception(
            "Therapeutic trends retrieval failed",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve therapeutic trends. Please try again.",
        ) from e


@router.get("/conferences/upcoming")
async def get_upcoming_conferences(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get upcoming conferences with relevance recommendations for the user."""
    try:
        from src.intelligence.conference_intelligence import (
            ConferenceIntelligenceEngine,
        )

        db = get_supabase_client()
        engine = ConferenceIntelligenceEngine(db)
        recommendations = await engine.generate_recommendations(
            str(current_user.id)
        )

        logger.info(
            "Conference recommendations retrieved",
            extra={
                "user_id": current_user.id,
                "count": len(recommendations),
            },
        )

        return {"conferences": recommendations, "count": len(recommendations)}

    except Exception as e:
        logger.exception(
            "Conference recommendations failed",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve conference recommendations.",
        ) from e


@router.get("/conferences/{conference_id}")
async def get_conference_detail(
    conference_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get detailed conference info with participants and insights."""
    try:
        db = get_supabase_client()

        conf = (
            db.table("conferences")
            .select("*")
            .eq("id", conference_id)
            .limit(1)
            .execute()
        )
        if not conf.data:
            raise HTTPException(
                status_code=404, detail="Conference not found"
            )

        participants = (
            db.table("conference_participants")
            .select("*")
            .eq("conference_id", conference_id)
            .order("participation_type")
            .execute()
        )

        insights = (
            db.table("conference_insights")
            .select("*")
            .eq("conference_id", conference_id)
            .eq("user_id", str(current_user.id))
            .order("created_at", desc=True)
            .limit(10)
            .execute()
        )

        return {
            "conference": conf.data[0],
            "participants": participants.data or [],
            "insights": insights.data or [],
            "competitor_count": sum(
                1
                for p in (participants.data or [])
                if p.get("is_competitor")
            ),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Conference detail retrieval failed",
            extra={
                "user_id": current_user.id,
                "conference_id": conference_id,
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve conference details.",
        ) from e


# ==============================================================================
# INTELLIGENCE PAGE V2 ENDPOINTS
# ==============================================================================


class WatchTopicRequest(BaseModel):
    """Request model for adding a watch topic."""

    topic_type: str = Field(default="keyword", description="Type: keyword, company, or therapeutic_area")
    topic_value: str = Field(..., min_length=1, max_length=500, description="The topic to watch")
    description: str | None = Field(default=None, description="Optional description")


class WatchTopicResponse(BaseModel):
    """Response model for a watch topic."""

    id: str
    topic_type: str
    topic_value: str
    description: str | None
    signal_count: int
    is_active: bool
    created_at: str
    last_matched_at: str | None


class WatchTopicsListResponse(BaseModel):
    """Response model for listing watch topics."""

    topics: list[WatchTopicResponse]
    count: int


class CompetitorActivityItem(BaseModel):
    """Model for a single competitor's activity."""

    competitor: str
    signal_count: int
    signals: list[dict[str, Any]]


class CompetitorActivityResponse(BaseModel):
    """Response model for competitor activity timeline."""

    activity: list[CompetitorActivityItem]
    days: int


class CRMStatusResponse(BaseModel):
    """Response model for CRM connection status."""

    connected: bool
    type: str | None = None


class PrioritySignalResponse(BaseModel):
    """Response model for priority signals."""

    id: str
    headline: str
    company_name: str
    signal_type: str
    relevance_score: float
    detected_at: str
    linked_insight_id: str | None
    linked_action_summary: str | None


class PrioritySignalsResponse(BaseModel):
    """Response model for priority signals list."""

    signals: list[PrioritySignalResponse]
    hours: int


# --- Watch Topics ---


@router.post("/watch-topics", response_model=WatchTopicResponse)
async def add_watch_topic(
    current_user: CurrentUser,
    request: WatchTopicRequest,
) -> WatchTopicResponse:
    """Add a custom watch topic for the user."""
    try:
        from src.intelligence.watch_topics_service import WatchTopicsService

        db = get_supabase_client()
        service = WatchTopicsService(db)
        result = await service.add_topic(
            user_id=str(current_user.id),
            topic_type=request.topic_type,
            topic_value=request.topic_value,
            description=request.description,
        )

        topic = result.get("topic", {})
        return WatchTopicResponse(
            id=str(topic.get("id", "")),
            topic_type=topic.get("topic_type", "keyword"),
            topic_value=topic.get("topic_value", ""),
            description=topic.get("description"),
            signal_count=topic.get("signal_count", 0),
            is_active=topic.get("is_active", True),
            created_at=topic.get("created_at", ""),
            last_matched_at=topic.get("last_matched_at"),
        )

    except Exception as e:
        logger.exception(
            "Failed to add watch topic",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to add watch topic.",
        ) from e


@router.get("/watch-topics", response_model=WatchTopicsListResponse)
async def get_watch_topics(
    current_user: CurrentUser,
) -> WatchTopicsListResponse:
    """Get user's watch topics."""
    try:
        db = get_supabase_client()
        result = (
            db.table("watch_topics")
            .select("*")
            .eq("user_id", str(current_user.id))
            .eq("is_active", True)
            .order("created_at", desc=True)
            .execute()
        )

        topics = [
            WatchTopicResponse(
                id=str(t["id"]),
                topic_type=t.get("topic_type", "keyword"),
                topic_value=t.get("topic_value", ""),
                description=t.get("description"),
                signal_count=t.get("signal_count", 0),
                is_active=t.get("is_active", True),
                created_at=t.get("created_at", ""),
                last_matched_at=t.get("last_matched_at"),
            )
            for t in (result.data or [])
        ]

        return WatchTopicsListResponse(topics=topics, count=len(topics))

    except Exception as e:
        logger.exception(
            "Failed to get watch topics",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve watch topics.",
        ) from e


@router.delete("/watch-topics/{topic_id}", status_code=204)
async def delete_watch_topic(
    topic_id: str,
    current_user: CurrentUser,
) -> None:
    """Remove a watch topic (soft delete)."""
    try:
        db = get_supabase_client()
        db.table("watch_topics").update({"is_active": False}).eq(
            "id", topic_id
        ).eq("user_id", str(current_user.id)).execute()

    except Exception as e:
        logger.exception(
            "Failed to delete watch topic",
            extra={"user_id": current_user.id, "topic_id": topic_id},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to delete watch topic.",
        ) from e


# --- Competitor Activity Timeline ---


@router.get("/competitor-activity", response_model=CompetitorActivityResponse)
async def get_competitor_activity(
    current_user: CurrentUser,
    days: int = Query(30, ge=1, le=90, description="Days to look back"),
) -> CompetitorActivityResponse:
    """Get competitor signal activity timeline."""
    try:
        from datetime import datetime, timedelta, timezone

        db = get_supabase_client()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        # Get competitor names from battle cards
        cards = db.table("battle_cards").select("competitor_name").execute()
        competitors = [c["competitor_name"] for c in (cards.data or [])]

        activity: list[CompetitorActivityItem] = []
        for comp in competitors:
            signals = (
                db.table("market_signals")
                .select("id, headline, signal_type, detected_at, is_cluster_primary")
                .ilike("company_name", f"%{comp}%")
                .gte("detected_at", cutoff)
                .order("detected_at", desc=True)
                .execute()
            )

            # Only primary signals (deduped)
            primary_signals = [
                s for s in (signals.data or []) if s.get("is_cluster_primary", True)
            ]

            activity.append(
                CompetitorActivityItem(
                    competitor=comp,
                    signal_count=len(primary_signals),
                    signals=[
                        {
                            "headline": s["headline"][:120],
                            "signal_type": s["signal_type"],
                            "detected_at": s["detected_at"],
                        }
                        for s in primary_signals[:5]  # Top 5 most recent
                    ],
                )
            )

        # Sort by signal count descending
        activity.sort(key=lambda x: x.signal_count, reverse=True)

        return CompetitorActivityResponse(activity=activity, days=days)

    except Exception as e:
        logger.exception(
            "Failed to get competitor activity",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve competitor activity.",
        ) from e


# --- CRM Status ---


@router.get("/crm-status", response_model=CRMStatusResponse)
async def get_crm_status(
    current_user: CurrentUser,
) -> CRMStatusResponse:
    """Check if user has CRM connected."""
    try:
        db = get_supabase_client()
        integration = (
            db.table("user_integrations")
            .select("integration_type, status")
            .eq("user_id", str(current_user.id))
            .in_("integration_type", ["salesforce", "hubspot", "dynamics"])
            .eq("status", "active")
            .limit(1)
            .execute()
        )

        return CRMStatusResponse(
            connected=bool(integration.data),
            type=integration.data[0]["integration_type"] if integration.data else None,
        )

    except Exception as e:
        logger.exception(
            "Failed to get CRM status",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve CRM status.",
        ) from e


# --- Battle Card Detail (V2) ---


@router.get("/battle-cards/{card_id}")
async def get_battle_card_detail_v2(
    card_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get full battle card with recent signals and insights."""
    try:
        db = get_supabase_client()

        card = (
            db.table("battle_cards")
            .select("*")
            .eq("id", card_id)
            .limit(1)
            .execute()
        )
        if not card.data:
            raise HTTPException(status_code=404, detail="Battle card not found")

        competitor_name = card.data[0]["competitor_name"]

        # Recent signals for this competitor
        signals = (
            db.table("market_signals")
            .select("id, headline, signal_type, detected_at")
            .ilike("company_name", f"%{competitor_name}%")
            .order("detected_at", desc=True)
            .limit(10)
            .execute()
        )

        # Insights about this competitor
        insights = (
            db.table("jarvis_insights")
            .select("id, classification, content, confidence, priority_label")
            .eq("user_id", str(current_user.id))
            .ilike("content", f"%{competitor_name}%")
            .order("created_at", desc=True)
            .limit(5)
            .execute()
        )

        return {
            "card": card.data[0],
            "signals": signals.data or [],
            "insights": insights.data or [],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Failed to get battle card detail",
            extra={"user_id": current_user.id, "card_id": card_id},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve battle card details.",
        ) from e


# --- Priority Signals ---


@router.get("/signals/priority", response_model=PrioritySignalsResponse)
async def get_priority_signals(
    current_user: CurrentUser,
    hours: int = Query(48, ge=1, le=168, description="Hours to look back"),
    limit: int = Query(3, ge=1, le=10, description="Maximum signals to return"),
) -> PrioritySignalsResponse:
    """Get top priority signals from the last N hours."""
    try:
        from datetime import datetime, timedelta, timezone

        db = get_supabase_client()
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

        result = (
            db.table("market_signals")
            .select(
                "id, headline, company_name, signal_type, relevance_score, detected_at, "
                "linked_insight_id, linked_action_summary, is_cluster_primary"
            )
            .eq("user_id", str(current_user.id))
            .gte("detected_at", cutoff)
            .eq("is_cluster_primary", True)
            .order("relevance_score", desc=True)
            .limit(limit)
            .execute()
        )

        signals = [
            PrioritySignalResponse(
                id=str(s["id"]),
                headline=s["headline"],
                company_name=s.get("company_name", ""),
                signal_type=s.get("signal_type", "news"),
                relevance_score=s.get("relevance_score", 0.5),
                detected_at=s["detected_at"],
                linked_insight_id=s.get("linked_insight_id"),
                linked_action_summary=s.get("linked_action_summary"),
            )
            for s in (result.data or [])
        ]

        return PrioritySignalsResponse(signals=signals, hours=hours)

    except Exception as e:
        logger.exception(
            "Failed to get priority signals",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve priority signals.",
        ) from e


# --- Therapeutic Trends with Narratives (V2) ---


@router.get("/therapeutic-trends-v2")
async def get_therapeutic_trends_with_narratives(
    current_user: CurrentUser,
    days: int = Query(30, ge=1, le=90, description="Days to look back"),
) -> dict[str, Any]:
    """Get therapeutic/manufacturing trends with strategic narratives and goal alignment."""
    try:
        db = get_supabase_client()

        # Get user's active goals for context
        goals_result = (
            db.table("goals")
            .select("id, title")
            .eq("user_id", str(current_user.id))
            .in_("status", ["active", "in_progress"])
            .execute()
        )
        goals = goals_result.data or []

        # Get therapeutic trends
        from src.intelligence.therapeutic_area_intelligence import (
            detect_therapeutic_trends,
            generate_trend_narrative,
        )

        trends = await detect_therapeutic_trends(
            supabase_client=db,
            user_id=str(current_user.id),
            days=days,
            min_signals=3,
        )

        # Generate narratives for top trends and check goal alignment
        for trend in trends[:7]:  # Top 7
            try:
                narrative = await generate_trend_narrative(trend, goals)
                trend["narrative"] = narrative
            except Exception:
                trend["narrative"] = ""

            # Check goal alignment
            if goals:
                for goal in goals:
                    goal_words = set(goal.get("title", "").lower().split())
                    trend_words = set(
                        trend.get("name", "").lower().replace("_", " ").split()
                    )
                    if len(goal_words & trend_words) >= 1:
                        trend["aligned_goal"] = goal["title"]
                        break

        return {"trends": trends, "goals_count": len(goals)}

    except Exception as e:
        logger.exception(
            "Failed to get therapeutic trends with narratives",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve therapeutic trends.",
        ) from e


# --- Real-Time Web Intelligence Research (Exa + Perplexity) ---


class ResearchRequest(BaseModel):
    """Request for parallel web intelligence research."""

    query: str = Field(..., description="Research query string")
    entity_name: str | None = Field(None, description="Optional entity name for signal linking")
    deep: bool = Field(False, description="Use deep research (sonar-pro)")


class ResearchSourceResult(BaseModel):
    """Result from a single intelligence source."""

    source: str
    answer: str
    citations: List[str] = Field(default_factory=list)
    model: str = ""
    error: str | None = None


class ResearchResponse(BaseModel):
    """Combined response from Exa and Perplexity."""

    exa: ResearchSourceResult | None = None
    perplexity: ResearchSourceResult | None = None
    saved_to_memory: bool = False


@router.post("/research", response_model=ResearchResponse)
async def web_intelligence_research(
    current_user: CurrentUser,
    request: ResearchRequest,
) -> ResearchResponse:
    """Execute parallel web intelligence research using Exa and Perplexity.

    Queries both Exa and Perplexity in parallel for comprehensive market intelligence,
    then combines and results. Writes the combined insight to semantic memory
    for persistence.

    Args:
        current_user: Authenticated user.
        request: Research request with query and optional entity_name, and deep flag.

    Returns:
        ResearchResponse with results from both sources.
    """
    import asyncio

    from src.agents.capabilities.enrichment_providers.exa_provider import ExaEnrichmentProvider
    from src.integrations.perplexity.client import get_perplexity_client

    exa_result: ResearchSourceResult | None = None
    perplexity_result: ResearchSourceResult | None = None

    # Run both searches in parallel
    exa_provider = ExaEnrichmentProvider()
    perplexity_client = get_perplexity_client()

    async def fetch_exa() -> list[dict[str, Any]]:
        """Fetch Exa results."""
        try:
                results = await exa_provider.search_fast(
                    query=request.query,
                    num_results=10,
                )
                return [
                    {
                        "title": r.title,
                        "url": r.url,
                        "snippet": (r.text or "")[:500],
                        "score": r.score,
                    }
                    for r in results
                ]
        except Exception as e:
            logger.warning("Exa search failed: %s", e)
            return []

    async def fetch_perplexity() -> dict[str, Any]:
        """Fetch Perplexity results."""
        if not perplexity_client.is_configured:
            return {}
        try:
                if request.deep:
                    result = await perplexity_client.research(request.query)
                else:
                    result = await perplexity_client.search(request.query)
                return {
                    "answer": result.get("answer", ""),
                    "citations": result.get("citations", []),
                    "model": result.get("model", "sonar"),
                }
        except Exception as e:
            logger.warning("Perplexity search failed: %s", e)
            return {}

    try:
        exa_results, perplexity_results = await asyncio.gather(
            fetch_exa(),
            fetch_perplexity(),
            return_exceptions=True,  # Never let one failure break the whole request
        )

        # Build response objects
        exa_response: ResearchSourceResult | None = None
        perplexity_response: ResearchSourceResult | None = None

        if exa_results:
            first_snippet = exa_results[0].get("snippet", "") if exa_results else ""
            exa_response = ResearchSourceResult(
                source="exa",
                answer=first_snippet,
                citations=[r.get("url", "") for r in exa_results if r.get("url")],
                model="search_fast",
            )
        else:
            exa_response = ResearchSourceResult(
                source="exa",
                answer="",
                citations=[],
                error="Exa search returned no results or API not configured",
            )

        if perplexity_results and perplexity_results.get("answer"):
            perplexity_response = ResearchSourceResult(
                source="perplexity",
                answer=perplexity_results.get("answer", ""),
                citations=perplexity_results.get("citations", []),
                model=perplexity_results.get("model", "sonar"),
            )
        else:
            perplexity_response = ResearchSourceResult(
                source="perplexity",
                answer="",
                citations=[],
                error="Perplexity not configured or returned no results",
            )

        # Write combined result to semantic memory
        saved_to_memory = False
        combined_answer = ""
        if exa_response and exa_response.answer:
            combined_answer += f"[Exa] {exa_response.answer}\n"
        if perplexity_response and perplexity_response.answer:
            combined_answer += f"[Perplexity] {perplexity_response.answer}\n"

        if combined_answer and request.entity_name:
            try:
                db = get_supabase_client()
                db.table("memory_semantic").insert(
                    {
                        "user_id": str(current_user.id),
                        "fact": f"Research on {request.entity_name}: {combined_answer[:500]}",
                        "confidence": 0.7,
                        "source": "scout_agent",
                        "metadata": {
                            "query": request.query,
                            "entity_name": request.entity_name,
                            "sources_used": [
                                s for s in [exa_response, perplexity_response] if s
                            ],
                        },
                    }
                ).execute()
                saved_to_memory = True
                logger.info("Research result saved to memory_semantic")
            except Exception as e:
                logger.warning("Failed to save research to memory: %s", e)

        logger.info(
            "Web intelligence research completed",
            extra={
                "user_id": current_user.id,
                "query": request.query[:100],
                "exa_results": len(exa_results) if exa_results else 0,
                "perplexity_configured": perplexity_client.is_configured,
                "saved_to_memory": saved_to_memory,
            },
        )

        return ResearchResponse(
            exa=exa_response,
            perplexity=perplexity_response,
            saved_to_memory=saved_to_memory,
        )

    except Exception as e:
        logger.exception(
            "Web intelligence research failed",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=500,
            detail="Research request failed. Please try again.",
        ) from e
