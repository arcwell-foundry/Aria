"""Causal Chain Traversal Engine for ARIA Phase 7 Jarvis Intelligence.

This module provides causal chain analysis capabilities, tracing how events
propagate through connected entities using a hybrid approach of graph
traversal and LLM inference.

Key components:
- CausalChainEngine: Main engine for traversing causal chains
- CausalChainStore: Database persistence for causal chains
- ImplicationEngine: Derives actionable insights from causal chains
- ButterflyDetector: Detects cascade amplification (butterfly effects)
- Models: Pydantic models for causal chains, hops, implications, and butterfly effects
"""

from src.intelligence.causal.butterfly_detector import ButterflyDetector
from src.intelligence.causal.engine import CausalChainEngine
from src.intelligence.causal.models import (
    ButterflyDetectionRequest,
    ButterflyDetectionResponse,
    ButterflyEffect,
    CausalChain,
    CausalHop,
    CausalTraversalRequest,
    CausalTraversalResponse,
    EntityExtraction,
    InferredRelationship,
    WarningLevel,
)
from src.intelligence.causal.store import CausalChainStore

__all__ = [
    # Causal chain traversal
    "CausalChainEngine",
    "CausalChainStore",
    "CausalChain",
    "CausalHop",
    "CausalTraversalRequest",
    "CausalTraversalResponse",
    "EntityExtraction",
    "InferredRelationship",
    # Butterfly effect detection (US-703)
    "ButterflyDetector",
    "ButterflyDetectionRequest",
    "ButterflyDetectionResponse",
    "ButterflyEffect",
    "WarningLevel",
]
