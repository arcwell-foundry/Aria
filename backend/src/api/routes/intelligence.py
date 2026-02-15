"""Causal Intelligence API routes for ARIA Phase 7.

This module provides endpoints for causal chain traversal and analysis,
enabling ARIA to trace how events propagate through connected entities.
"""

import logging
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
