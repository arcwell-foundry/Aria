"""Pydantic models for the Mental Simulation Engine (US-708).

This module defines data structures for ARIA's mental simulation system,
enabling "what if" scenario analysis through causal chain traversal,
outcome prediction, and recommendation generation.
"""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ScenarioType(str, Enum):
    """Type of simulation scenario.

    Different types of scenarios require different analysis approaches.
    """

    DECISION = "decision"  # Choosing between options
    HYPOTHETICAL = "hypothetical"  # "What if X happens"
    STRATEGIC = "strategic"  # Long-term strategic planning
    TACTICAL = "tactical"  # Short-term action planning
    RISK = "risk"  # Risk assessment scenario


class OutcomeClassification(str, Enum):
    """Classification of a simulation outcome.

    Indicates whether the outcome is positive, negative, or mixed.
    """

    POSITIVE = "positive"  # Net positive outcome
    NEGATIVE = "negative"  # Net negative outcome
    MIXED = "mixed"  # Mixed outcomes, depends on priorities
    NEUTRAL = "neutral"  # No significant impact


# ==============================================================================
# CORE SIMULATION MODELS
# ==============================================================================


class SimulationScenario(BaseModel):
    """A scenario to simulate.

    Represents a specific variation of the base scenario with
    different variable values.
    """

    description: str = Field(
        ...,
        description="Human-readable description of this scenario variation",
    )
    probability: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Probability of this scenario occurring (0-1)",
    )
    variables: dict[str, Any] = Field(
        default_factory=dict,
        description="Key variables and their values for this scenario",
    )
    expected_outcome: str | None = Field(
        None,
        description="Expected outcome if this scenario plays out",
    )


class SimulationOutcome(BaseModel):
    """Outcome from simulating a scenario.

    Contains the analysis of what would happen if the scenario
    occurs, including positive/negative effects and recommendations.
    """

    scenario: str = Field(
        ...,
        description="Description of the scenario that was simulated",
    )
    probability: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Probability of this outcome (0-1)",
    )
    classification: OutcomeClassification = Field(
        ...,
        description="Whether outcome is positive, negative, or mixed",
    )
    positive_outcomes: list[str] = Field(
        default_factory=list,
        description="Positive effects of this outcome",
    )
    negative_outcomes: list[str] = Field(
        default_factory=list,
        description="Negative effects of this outcome",
    )
    key_uncertainties: list[str] = Field(
        default_factory=list,
        description="Key factors that could change the outcome",
    )
    recommended: bool = Field(
        ...,
        description="Whether ARIA recommends this path",
    )
    reasoning: str = Field(
        ...,
        description="LLM-generated reasoning for the recommendation",
    )
    causal_chain: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Causal chain hops from the causal engine",
    )
    time_to_impact: str | None = Field(
        None,
        description="Estimated time until impact (e.g., '2-4 weeks')",
    )
    affected_goals: list[str] = Field(
        default_factory=list,
        description="IDs of goals affected by this outcome",
    )


# ==============================================================================
# REQUEST/RESPONSE MODELS
# ==============================================================================


class SimulationRequest(BaseModel):
    """Request to run a mental simulation.

    Specifies the scenario to simulate and parameters for
    controlling the simulation depth and output.
    """

    scenario: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="The 'what if' scenario to simulate",
    )
    scenario_type: ScenarioType = Field(
        default=ScenarioType.HYPOTHETICAL,
        description="Type of simulation scenario",
    )
    variables: list[str] | None = Field(
        None,
        description="Key variables to vary in simulation (auto-detected if None)",
    )
    related_goal_id: UUID | None = Field(
        None,
        description="Related goal for context",
    )
    related_lead_id: UUID | None = Field(
        None,
        description="Related lead for context",
    )
    max_outcomes: int = Field(
        default=3,
        ge=1,
        le=5,
        description="Maximum number of outcomes to generate (1-5)",
    )
    max_hops: int = Field(
        default=3,
        ge=1,
        le=5,
        description="Maximum causal chain hops to traverse (1-5)",
    )


class SimulationResult(BaseModel):
    """Result of a mental simulation.

    Contains all outcomes, the recommended path, and analysis metadata.
    """

    scenario: str = Field(
        ...,
        description="The original scenario that was simulated",
    )
    scenario_type: ScenarioType = Field(
        ...,
        description="Type of simulation that was run",
    )
    outcomes: list[SimulationOutcome] = Field(
        default_factory=list,
        description="All possible outcomes analyzed",
    )
    recommended_path: str = Field(
        ...,
        description="Description of the recommended course of action",
    )
    reasoning: str = Field(
        ...,
        description="Overall reasoning for the recommendation",
    )
    sensitivity: dict[str, float] = Field(
        default_factory=dict,
        description="Variable -> impact score (how much each variable matters)",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Overall confidence in the simulation (0-1)",
    )
    key_insights: list[str] = Field(
        default_factory=list,
        description="Key insights from the simulation",
    )
    processing_time_ms: float = Field(
        ...,
        description="Time taken to run the simulation in milliseconds",
    )


class SimulationResponse(BaseModel):
    """API response with simulation result.

    Wraps the simulation result with metadata about persistence.
    """

    result: SimulationResult = Field(
        ...,
        description="The simulation result",
    )
    simulation_id: UUID | None = Field(
        None,
        description="ID of the saved simulation (if saved)",
    )
    saved: bool = Field(
        default=False,
        description="Whether the simulation was saved to the database",
    )


class SimulationsListResponse(BaseModel):
    """Response for listing past simulations.

    Returns a paginated list of saved simulations.
    """

    simulations: list[SimulationResult] = Field(
        default_factory=list,
        description="List of simulation results",
    )
    total: int = Field(
        ...,
        ge=0,
        description="Total number of simulations",
    )


class QuickSimulationResponse(BaseModel):
    """Response for quick simulation (chat integration).

    Lightweight response for chat "what if" questions without
    full causal chain traversal.
    """

    answer: str = Field(
        ...,
        description="Natural language answer to the what-if question",
    )
    key_points: list[str] = Field(
        default_factory=list,
        description="Key points from the analysis",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in the answer (0-1)",
    )
    processing_time_ms: float = Field(
        ...,
        description="Time taken to generate the answer in milliseconds",
    )


# ==============================================================================
# CONTEXT MODELS
# ==============================================================================


class SimulationContext(BaseModel):
    """Context gathered for simulation analysis.

    Aggregates relevant user data to inform the simulation.
    """

    active_goals: list[dict[str, Any]] = Field(
        default_factory=list,
        description="User's active goals",
    )
    recent_events: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Recent events from memory and signals",
    )
    related_leads: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Leads related to the scenario",
    )
    relevant_memories: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Relevant episodic memories",
    )
    user_preferences: dict[str, Any] = Field(
        default_factory=dict,
        description="User preferences from profile",
    )


# ==============================================================================
# DATABASE MODELS
# ==============================================================================


class SimulationInsight(BaseModel):
    """Persisted simulation in the jarvis_insights table.

    Represents a simulation that has been saved for later retrieval.
    """

    id: UUID
    user_id: UUID
    insight_type: str = Field(default="simulation_result")
    trigger_event: str  # The scenario text
    content: str  # The recommended path + reasoning
    classification: str  # Based on recommended outcome classification
    impact_score: float  # Average outcome probability
    confidence: float  # Simulation confidence
    urgency: float = Field(default=0.5)  # Default urgency
    combined_score: float  # Confidence-based score
    causal_chain: list[dict[str, Any]]  # Outcomes list as JSONB
    affected_goals: list[str]  # Related goal IDs
    recommended_actions: list[str]  # From recommended path
    time_horizon: str | None = None
    time_to_impact: str | None = None
    status: str = Field(default="new")
    feedback_text: str | None = None
    created_at: datetime
    updated_at: datetime
