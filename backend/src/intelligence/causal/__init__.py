"""Causal Chain Traversal Engine for ARIA Phase 7 Jarvis Intelligence.

This module provides causal chain analysis capabilities, tracing how events
propagate through connected entities using a hybrid approach of graph
traversal and LLM inference.

Key components:
- CausalChainEngine: Main engine for traversing causal chains
- CausalChainStore: Database persistence for causal chains
- Models: Pydantic models for causal chains, hops, and requests
"""

from src.intelligence.causal.engine import CausalChainEngine
from src.intelligence.causal.models import (
    CausalChain,
    CausalHop,
    CausalTraversalRequest,
    CausalTraversalResponse,
    EntityExtraction,
    InferredRelationship,
)
from src.intelligence.causal.store import CausalChainStore

__all__ = [
    "CausalChainEngine",
    "CausalChainStore",
    "CausalChain",
    "CausalHop",
    "CausalTraversalRequest",
    "CausalTraversalResponse",
    "EntityExtraction",
    "InferredRelationship",
]
