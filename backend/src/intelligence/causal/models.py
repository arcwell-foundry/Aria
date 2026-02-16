"""Pydantic models for the Causal Chain Traversal Engine and Implication Reasoning.

This module defines the data structures for representing and traversing
causal relationships between entities in ARIA's knowledge system, as well
as deriving actionable implications from causal analysis.
"""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class CausalHop(BaseModel):
    """Single hop in a causal chain.

    Represents one causal link from a source entity to a target entity,
    including the relationship type, confidence, and explanation.
    """

    source_entity: str = Field(..., description="Name of the source entity")
    target_entity: str = Field(..., description="Name of the target entity")
    relationship: str = Field(
        ...,
        description="Type of causal relationship (causes, enables, threatens, accelerates)",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in this causal link (0-1)",
    )
    explanation: str = Field(
        ...,
        description="Explanation of why this causal link exists",
    )


class CausalChain(BaseModel):
    """Complete causal chain from trigger event to final impact.

    A chain represents the full path of causality from an initial
    trigger event through multiple hops to a final impacted entity.
    """

    id: UUID | None = Field(None, description="Unique identifier for this chain")
    trigger_event: str = Field(..., description="The original event that started this chain")
    hops: list[CausalHop] = Field(
        default_factory=list,
        description="Ordered list of causal hops from trigger to impact",
    )
    final_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Cumulative confidence after decay through all hops",
    )
    time_to_impact: str | None = Field(
        None,
        description="Estimated time until final impact (e.g., '2-4 weeks')",
    )
    source_context: str | None = Field(
        None,
        description="Context where this chain was discovered",
    )
    source_id: UUID | None = Field(
        None,
        description="ID of the source that triggered this chain analysis",
    )
    created_at: datetime | None = Field(None, description="When this chain was created")


class CausalTraversalRequest(BaseModel):
    """Request to traverse causal chains from a trigger event.

    Specifies the trigger event and parameters for how deep and
    with what confidence threshold to traverse.
    """

    trigger_event: str = Field(
        ...,
        description="Description of the event to analyze for causal impacts",
        min_length=10,
        max_length=2000,
    )
    max_hops: int = Field(
        default=4,
        ge=1,
        le=6,
        description="Maximum number of causal hops to traverse",
    )
    min_confidence: float = Field(
        default=0.3,
        ge=0.1,
        le=1.0,
        description="Minimum confidence threshold for including chains",
    )


class CausalTraversalResponse(BaseModel):
    """Response containing discovered causal chains.

    Includes all chains found from the trigger event that meet
    the confidence threshold, plus processing metadata.
    """

    chains: list[CausalChain] = Field(
        default_factory=list,
        description="All causal chains discovered from the trigger",
    )
    processing_time_ms: float = Field(
        ...,
        description="Time taken to process the traversal in milliseconds",
    )
    entities_found: int = Field(
        ...,
        ge=0,
        description="Number of unique entities extracted from trigger",
    )
    trigger_event: str = Field(
        ...,
        description="The original trigger event that was analyzed",
    )


class EntityExtraction(BaseModel):
    """Extracted entity from a trigger event.

    Represents a named entity (company, person, product, etc.)
    extracted from the trigger event text.
    """

    name: str = Field(..., description="Name of the entity")
    entity_type: str = Field(
        ...,
        description="Type of entity (company, person, product, event, etc.)",
    )
    relevance: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Relevance of this entity to the trigger event",
    )
    context: str | None = Field(
        None,
        description="Additional context about the entity's role",
    )


class InferredRelationship(BaseModel):
    """Causal relationship inferred by the LLM.

    When Graphiti doesn't have explicit causal edges, the LLM
    infers relationships based on domain knowledge and context.
    """

    target_entity: str = Field(..., description="Name of the target entity")
    relationship_type: str = Field(
        ...,
        description="Type of causal relationship (causes, enables, threatens, accelerates)",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in the inferred relationship",
    )
    explanation: str = Field(
        ...,
        description="Why this causal relationship is likely to exist",
    )


# ==============================================================================
# IMPLICATION REASONING ENGINE MODELS (US-702)
# ==============================================================================


class ImplicationType(str, Enum):
    """Classification of implication impact on user's goals.

    An implication represents how a causal chain outcome affects
    the user's objectives, deals, or strategic interests.
    """

    OPPORTUNITY = "opportunity"  # Helps achieve goals
    THREAT = "threat"  # Hinders or endangers goals
    NEUTRAL = "neutral"  # No significant impact on goals


class Implication(BaseModel):
    """An implication derived from causal chain analysis.

    Represents an actionable insight derived by connecting causal
    chain endpoints to the user's active goals and deals.
    """

    id: UUID | None = Field(None, description="Unique identifier for this implication")
    trigger_event: str = Field(..., description="Original event that triggered analysis")
    content: str = Field(
        ...,
        description="Natural language explanation of the implication",
    )
    type: ImplicationType = Field(
        ...,
        description="Classification: opportunity, threat, or neutral",
    )
    impact_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Impact on affected goals (0-1)",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in this implication (0-1)",
    )
    urgency: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Time urgency of this implication (0-1)",
    )
    combined_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Composite score: impact*0.4 + confidence*0.35 + urgency*0.25",
    )
    causal_chain: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Serialized causal chain hops leading to this implication",
    )
    affected_goals: list[str] = Field(
        default_factory=list,
        description="IDs of goals affected by this implication",
    )
    recommended_actions: list[str] = Field(
        default_factory=list,
        description="1-3 actionable recommendations",
    )
    time_horizon: str | None = Field(
        None,
        description="Time horizon category: immediate, short_term, medium_term, long_term",
    )
    time_to_impact: str | None = Field(
        None,
        description="Estimated time until impact (e.g., '2-4 weeks')",
    )
    created_at: datetime | None = Field(None, description="When this implication was created")


class ImplicationRequest(BaseModel):
    """Request to analyze an event for implications.

    Specifies the event to analyze and parameters for filtering
    and controlling the implication discovery process.
    """

    event: str = Field(
        ...,
        description="Description of the event to analyze for implications",
        min_length=10,
        max_length=2000,
    )
    max_hops: int = Field(
        default=4,
        ge=1,
        le=6,
        description="Maximum causal hops to traverse",
    )
    include_neutral: bool = Field(
        default=False,
        description="Include implications with neutral impact",
    )
    min_score: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Minimum combined score threshold",
    )


class ImplicationResponse(BaseModel):
    """Response containing discovered implications.

    Includes all implications found from the event analysis,
    ranked by combined score, plus processing metadata.
    """

    implications: list[Implication] = Field(
        default_factory=list,
        description="All implications discovered, sorted by score",
    )
    processing_time_ms: float = Field(
        ...,
        description="Time taken to process the analysis in milliseconds",
    )
    chains_analyzed: int = Field(
        ...,
        ge=0,
        description="Number of causal chains analyzed",
    )
    goals_considered: int = Field(
        ...,
        ge=0,
        description="Number of active goals considered",
    )


class JarvisInsight(BaseModel):
    """Persisted insight in the jarvis_insights table.

    Represents an implication that has been saved for later
    retrieval and user engagement tracking.
    """

    id: UUID
    user_id: UUID
    insight_type: str = Field(default="implication")
    trigger_event: str
    content: str
    classification: str  # opportunity, threat, neutral
    impact_score: float
    confidence: float
    urgency: float
    combined_score: float
    causal_chain: list[dict[str, Any]]
    affected_goals: list[str]
    recommended_actions: list[str]
    time_horizon: str | None = None  # immediate, short_term, medium_term, long_term
    time_to_impact: str | None = None
    status: str = Field(default="new")  # new, engaged, dismissed, feedback
    feedback_text: str | None = None
    created_at: datetime
    updated_at: datetime


class InsightUpdateRequest(BaseModel):
    """Request to update an insight's status or add feedback."""

    status: str | None = Field(
        None,
        description="New status: engaged, dismissed, feedback",
    )
    feedback_text: str | None = Field(
        None,
        description="User feedback on the insight",
    )


# ==============================================================================
# BUTTERFLY EFFECT DETECTION MODELS (US-703)
# ==============================================================================


class WarningLevel(str, Enum):
    """Warning level for butterfly effects based on amplification factor.

    The warning level indicates the severity of a detected butterfly effect,
    determined by how much the cascade amplifies beyond the initial event.
    """

    LOW = "low"  # 3-5x amplification
    MEDIUM = "medium"  # 5-7x amplification
    HIGH = "high"  # 7-10x amplification
    CRITICAL = "critical"  # >10x amplification


class ButterflyEffect(BaseModel):
    """Detected butterfly effect with cascade analysis.

    A butterfly effect occurs when a small event triggers a cascade of
    implications that amplify significantly beyond the initial trigger.
    The amplification factor is the sum of all implication impact scores.
    """

    trigger_event: str = Field(..., description="The original event that triggered the cascade")
    amplification_factor: float = Field(
        ...,
        ge=0.0,
        description="Sum of implication impact scores (amplification ratio)",
    )
    cascade_depth: int = Field(
        ...,
        ge=0,
        description="Maximum hop depth across all causal chains",
    )
    time_to_full_impact: str = Field(
        ...,
        description="Estimated time until cascade completes (e.g., '2-4 weeks')",
    )
    final_implications: list[str] = Field(
        default_factory=list,
        description="Top 5 implication descriptions from the cascade",
    )
    warning_level: WarningLevel = Field(
        ...,
        description="Warning level based on amplification factor",
    )
    affected_goal_count: int = Field(
        ...,
        ge=0,
        description="Number of unique goals affected by the cascade",
    )
    combined_impact_score: float = Field(
        ...,
        ge=0.0,
        description="Sum of all implication combined scores",
    )


class ButterflyDetectionRequest(BaseModel):
    """Request to check an event for butterfly effects.

    Specifies the event to analyze and how deep to traverse causal chains
    when detecting cascade amplification.
    """

    event: str = Field(
        ...,
        description="Description of the event to analyze for butterfly effects",
        min_length=10,
        max_length=2000,
    )
    max_hops: int = Field(
        default=4,
        ge=1,
        le=6,
        description="Maximum causal hops to traverse for cascade detection",
    )


class ButterflyDetectionResponse(BaseModel):
    """Response from butterfly effect detection.

    Contains the detected butterfly effect if amplification exceeds threshold,
    along with metadata about the analysis performed.
    """

    butterfly_effect: ButterflyEffect | None = Field(
        None,
        description="Detected butterfly effect, or None if below threshold",
    )
    implications_analyzed: int = Field(
        ...,
        ge=0,
        description="Number of implications analyzed for cascade detection",
    )
    processing_time_ms: float = Field(
        ...,
        description="Time taken to perform detection in milliseconds",
    )


# ==============================================================================
# CROSS-DOMAIN CONNECTION ENGINE MODELS (US-704)
# ==============================================================================


class ConnectionType(str, Enum):
    """Type of cross-domain connection discovered."""

    ENTITY_OVERLAP = "entity_overlap"  # Direct entity match
    GRAPHITI_PATH = "graphiti_path"  # Graph path between entities
    LLM_INFERRED = "llm_inferred"  # LLM-identified relationship


class ConnectionInsight(BaseModel):
    """A discovered connection between seemingly unrelated events.

    Cross-domain connections reveal non-obvious relationships between
    events from different sources (market signals, leads, memories).
    """

    id: UUID | None = Field(None, description="Unique identifier")
    source_events: list[str] = Field(
        ...,
        min_length=2,
        description="Events that are connected",
    )
    source_domains: list[str] = Field(
        ...,
        description="Domains the events came from (market_signal, lead_memory, episodic)",
    )
    connection_type: ConnectionType = Field(
        ...,
        description="How the connection was discovered",
    )
    entities: list[str] = Field(
        default_factory=list,
        description="Entities involved in the connection",
    )
    novelty_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="How surprising/non-obvious the connection is (0-1)",
    )
    actionability_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Whether user can take action on this (0-1)",
    )
    relevance_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Relevance to user's goals (0-1)",
    )
    explanation: str = Field(
        ...,
        description="Natural language explanation of the connection",
    )
    recommended_action: str | None = Field(
        None,
        description="Suggested action based on this connection",
    )
    created_at: datetime | None = Field(None, description="When discovered")


class ConnectionScanRequest(BaseModel):
    """Request to scan for cross-domain connections."""

    events: list[str] | None = Field(
        None,
        description="Specific events to analyze (if None, scans recent events)",
    )
    days_back: int = Field(
        default=7,
        ge=1,
        le=30,
        description="Days to look back for events",
    )
    min_novelty: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Minimum novelty score threshold",
    )


class ConnectionScanResponse(BaseModel):
    """Response from connection scan."""

    connections: list[ConnectionInsight] = Field(
        default_factory=list,
        description="Discovered connections sorted by novelty",
    )
    events_scanned: int = Field(..., ge=0, description="Number of events analyzed")
    processing_time_ms: float = Field(..., description="Processing time in ms")
