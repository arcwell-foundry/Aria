"""ARIA custom component schemas for Thesys C1 generative UI.

Defines Pydantic models for component schemas that C1 uses to determine
what props to pass to custom React components. These must stay in sync
with the frontend Zod schemas in frontend/src/components/c1/schemas.ts.
"""

from pydantic import BaseModel, Field
from typing import Literal, Optional


# -----------------------------------------------------------------------------
# GoalPlanCard
# -----------------------------------------------------------------------------

class StepModel(BaseModel):
    """A single step in a goal execution plan."""

    step_number: int
    description: str
    assigned_agent: Optional[str] = Field(
        default=None,
        description="Which ARIA agent handles this step",
    )
    status: Literal["pending", "in_progress", "complete", "failed"] = "pending"


class GoalPlanCardSchema(BaseModel):
    """Schema for GoalPlanCard component."""

    goal_name: str = Field(description="Name of the goal or plan")
    goal_id: str = Field(description="Unique identifier for the goal")
    description: str = Field(description="Brief description of what will be accomplished")
    steps: list[StepModel] = Field(
        default_factory=list,
        description="Ordered list of execution steps",
    )
    estimated_duration: Optional[str] = Field(
        default=None,
        description="How long the plan will take",
    )
    ooda_phase: Optional[Literal["observe", "orient", "decide", "act"]] = None

    class Config:
        json_schema_extra = {
            "description": (
                "Renders an execution plan card for a goal that ARIA has proposed. "
                "Shows numbered steps with agent assignments, progress indicators, "
                "and Approve/Modify action buttons. Use this whenever ARIA proposes "
                "a multi-step plan for the user to review."
            )
        }


# -----------------------------------------------------------------------------
# EmailDraftCard
# -----------------------------------------------------------------------------

class EmailDraftCardSchema(BaseModel):
    """Schema for EmailDraftCard component."""

    email_draft_id: str = Field(description="Unique identifier for this draft")
    to: str = Field(description="Recipient email or name")
    subject: str = Field(description="Email subject line")
    body: str = Field(description="Email body text")
    tone: Literal["formal", "friendly", "urgent", "neutral"] = Field(
        default="neutral",
        description="Detected tone of the draft",
    )
    context: Optional[str] = Field(
        default=None,
        description="Why ARIA drafted this email",
    )

    class Config:
        json_schema_extra = {
            "description": (
                "Renders an email draft card showing recipient, subject, body preview, "
                "and tone indicator. Includes Approve (send), Edit, and Dismiss action "
                "buttons. Use this whenever ARIA has drafted an email for the user to "
                "review before sending."
            )
        }


# -----------------------------------------------------------------------------
# AgentStatusCard
# -----------------------------------------------------------------------------

class AgentInfoModel(BaseModel):
    """Information about a single agent's status."""

    name: str = Field(
        description="Agent name: Hunter, Analyst, Strategist, Scribe, Operator, or Scout"
    )
    status: Literal["idle", "working", "complete", "error"]
    current_task: Optional[str] = Field(
        default=None,
        description="What the agent is currently doing",
    )
    ooda_phase: Optional[Literal["observe", "orient", "decide", "act"]] = None
    progress: Optional[int] = Field(
        default=None,
        ge=0,
        le=100,
    )


class AgentStatusCardSchema(BaseModel):
    """Schema for AgentStatusCard component."""

    agents: list[AgentInfoModel] = Field(
        default_factory=list,
        description="List of active ARIA agents and their status",
    )

    class Config:
        json_schema_extra = {
            "description": (
                "Renders a status dashboard showing ARIA's active agents with progress "
                "indicators and current OODA phase. Use this when reporting on multi-agent "
                "execution progress or when the user asks about what ARIA is working on."
            )
        }


# -----------------------------------------------------------------------------
# SignalAlertCard
# -----------------------------------------------------------------------------

class SignalAlertCardSchema(BaseModel):
    """Schema for SignalAlertCard component."""

    signal_id: str = Field(description="Unique identifier for this signal")
    title: str = Field(description="Brief signal headline")
    severity: Literal["high", "medium", "low"]
    signal_type: str = Field(
        description="Type: patent_cliff, clinical_trial, competitive_move, regulatory, market_shift, etc."
    )
    summary: str = Field(description="2-3 sentence summary of the signal")
    source: Optional[str] = Field(
        default=None,
        description="Where ARIA detected this signal",
    )
    affected_accounts: Optional[list[str]] = Field(
        default=None,
        description="Account names that may be impacted",
    )
    detected_at: Optional[str] = Field(
        default=None,
        description="When ARIA detected this signal",
    )

    class Config:
        json_schema_extra = {
            "description": (
                "Renders a market signal or intelligence alert card with severity indicator, "
                "summary, affected accounts, and an Investigate action button. Use this for "
                "market intelligence alerts, competitive moves, regulatory changes, clinical "
                "trial updates, patent cliffs, or any proactive signal ARIA wants to surface."
            )
        }


# -----------------------------------------------------------------------------
# ApprovalCard
# -----------------------------------------------------------------------------

class ApprovalCardSchema(BaseModel):
    """Schema for ApprovalCard component."""

    item_id: str = Field(description="Unique identifier for the item needing approval")
    item_type: str = Field(
        description="What type of item: task, recommendation, action, configuration"
    )
    title: str = Field(description="What needs approval")
    description: str = Field(description="Context for the approval decision")
    impact: Optional[str] = Field(
        default=None,
        description="What happens if approved",
    )
    urgency: Literal["immediate", "today", "this_week", "no_rush"] = Field(
        default="no_rush",
    )

    class Config:
        json_schema_extra = {
            "description": (
                "Renders a generic approval card for any action that requires user sign-off. "
                "Shows title, context, impact assessment, urgency indicator, and Approve/Reject "
                "buttons. Use this for any pending action, recommendation, or configuration "
                "change that ARIA needs the user to authorize."
            )
        }


# -----------------------------------------------------------------------------
# Helper function to export schemas for C1 metadata
# -----------------------------------------------------------------------------

def get_aria_custom_components() -> dict:
    """Returns ARIA's custom component schemas as JSON schemas for C1 metadata.

    Each component is converted to JSON Schema format that Thesys C1 expects
    in the metadata.thesys.c1_custom_components field.

    The keys must match the React component names exactly:
    - GoalPlanCard
    - EmailDraftCard
    - AgentStatusCard
    - SignalAlertCard
    - ApprovalCard

    Returns:
        Dict keyed by component name, values are JSON Schema dicts.
    """
    return {
        "GoalPlanCard": GoalPlanCardSchema.model_json_schema(),
        "EmailDraftCard": EmailDraftCardSchema.model_json_schema(),
        "AgentStatusCard": AgentStatusCardSchema.model_json_schema(),
        "SignalAlertCard": SignalAlertCardSchema.model_json_schema(),
        "ApprovalCard": ApprovalCardSchema.model_json_schema(),
    }
