"""ARIA custom actions for Thesys C1 generative UI.

Defines Pydantic models for actions that C1 renders as interactive buttons.
All actions use dynamic parameterized payloads — NO hardcoded IDs.
"""

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Action Schemas — tell C1 what buttons to generate and what params they carry
# ---------------------------------------------------------------------------


class ApproveGoalAction(BaseModel):
    """User approves a proposed goal/plan."""

    goal_id: str
    goal_name: str


class ModifyGoalAction(BaseModel):
    """User wants to modify a proposed goal/plan."""

    goal_id: str
    goal_name: str


class ApproveEmailAction(BaseModel):
    """User approves a drafted email for sending."""

    email_draft_id: str
    recipient: str
    subject: str


class EditEmailAction(BaseModel):
    """User wants to edit a drafted email."""

    email_draft_id: str


class DismissEmailAction(BaseModel):
    """User dismisses/discards a drafted email."""

    email_draft_id: str


class InvestigateSignalAction(BaseModel):
    """User wants to investigate a market signal further."""

    signal_id: str
    signal_type: str  # e.g., "patent_cliff", "clinical_trial", "competitive_move"


class ViewLeadDetailAction(BaseModel):
    """User wants to see full details on a lead."""

    lead_id: str
    lead_name: str


class ExecuteTaskAction(BaseModel):
    """User approves execution of a pending task."""

    task_id: str
    task_description: str


class ViewBattleCardAction(BaseModel):
    """User wants to open a full battle card."""

    competitor_id: str
    competitor_name: str


# ---------------------------------------------------------------------------
# Helper function to export schemas for C1 metadata
# ---------------------------------------------------------------------------


def get_aria_custom_actions() -> dict:
    """Returns ARIA's custom actions as JSON schemas for C1 metadata.

    Each action is converted to JSON Schema format that Thesys C1 expects
    in the metadata.thesys.c1_custom_actions field.

    Returns:
        Dict keyed by action name, values are JSON Schema dicts.
    """
    return {
        "approve_goal": ApproveGoalAction.model_json_schema(),
        "modify_goal": ModifyGoalAction.model_json_schema(),
        "approve_email": ApproveEmailAction.model_json_schema(),
        "edit_email": EditEmailAction.model_json_schema(),
        "dismiss_email": DismissEmailAction.model_json_schema(),
        "investigate_signal": InvestigateSignalAction.model_json_schema(),
        "view_lead_detail": ViewLeadDetailAction.model_json_schema(),
        "execute_task": ExecuteTaskAction.model_json_schema(),
        "view_battle_card": ViewBattleCardAction.model_json_schema(),
    }
