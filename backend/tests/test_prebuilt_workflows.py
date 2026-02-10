"""Tests for pre-built workflow definitions."""

from src.skills.workflows.models import UserWorkflowDefinition
from src.skills.workflows.prebuilt import get_prebuilt_workflows


def test_get_prebuilt_workflows_returns_three() -> None:
    """All three pre-built workflows are returned."""
    workflows = get_prebuilt_workflows()
    assert len(workflows) == 3


def test_all_prebuilt_workflows_are_shared() -> None:
    """Every pre-built workflow must have is_shared=True."""
    workflows = get_prebuilt_workflows()
    for wf in workflows:
        assert wf.is_shared is True, f"{wf.name} should be shared"


def test_morning_prep_trigger_is_cron() -> None:
    """Morning Prep workflow fires on a cron schedule (6 AM weekdays)."""
    workflows = get_prebuilt_workflows()
    morning = _find_workflow(workflows, "Morning Prep")

    assert morning.trigger.type == "cron"
    assert morning.trigger.params["schedule"] == "0 6 * * 1-5"


def test_morning_prep_has_correct_actions() -> None:
    """Morning Prep has 2 actions: run_skill then send_notification."""
    workflows = get_prebuilt_workflows()
    morning = _find_workflow(workflows, "Morning Prep")

    assert len(morning.actions) == 2
    assert morning.actions[0].type == "run_skill"
    assert morning.actions[0].skill_id == "morning-briefing"
    assert morning.actions[1].type == "send_notification"


def test_post_meeting_trigger_is_event() -> None:
    """Post-Meeting workflow triggers on calendar_event_ended event."""
    workflows = get_prebuilt_workflows()
    post = _find_workflow(workflows, "Post-Meeting")

    assert post.trigger.type == "event"
    assert post.trigger.params["event_name"] == "calendar_event_ended"


def test_post_meeting_has_correct_actions() -> None:
    """Post-Meeting has 3 actions: notes prompt, action items, email draft."""
    workflows = get_prebuilt_workflows()
    post = _find_workflow(workflows, "Post-Meeting")

    assert len(post.actions) == 3


def test_post_meeting_first_step_requires_approval() -> None:
    """Post-Meeting first step (meeting-notes-prompt) requires user approval."""
    workflows = get_prebuilt_workflows()
    post = _find_workflow(workflows, "Post-Meeting")

    assert post.actions[0].requires_approval is True


def test_signal_alert_trigger_is_condition() -> None:
    """Signal Alert workflow triggers on a relevance score condition."""
    workflows = get_prebuilt_workflows()
    signal = _find_workflow(workflows, "Signal Alert")

    assert signal.trigger.type == "condition"
    assert "market_signals.relevance_score > 0.8" in signal.trigger.params["expression"]


def test_signal_alert_has_correct_actions() -> None:
    """Signal Alert has 2 actions: format signal then notify."""
    workflows = get_prebuilt_workflows()
    signal = _find_workflow(workflows, "Signal Alert")

    assert len(signal.actions) == 2
    assert signal.actions[0].type == "run_skill"
    assert signal.actions[0].skill_id == "signal-formatter"
    assert signal.actions[1].type == "send_notification"


def test_workflow_metadata_categories() -> None:
    """Each workflow has expected category in its metadata."""
    workflows = get_prebuilt_workflows()

    morning = _find_workflow(workflows, "Morning Prep")
    post = _find_workflow(workflows, "Post-Meeting")
    signal = _find_workflow(workflows, "Signal Alert")

    assert morning.metadata.category == "productivity"
    assert post.metadata.category == "follow_up"
    assert signal.metadata.category == "monitoring"


def test_workflow_metadata_icons() -> None:
    """Each workflow has the expected icon."""
    workflows = get_prebuilt_workflows()

    morning = _find_workflow(workflows, "Morning Prep")
    post = _find_workflow(workflows, "Post-Meeting")
    signal = _find_workflow(workflows, "Signal Alert")

    assert morning.metadata.icon == "sun"
    assert post.metadata.icon == "calendar"
    assert signal.metadata.icon == "radar"


def test_workflow_metadata_colors() -> None:
    """Each workflow has the expected color."""
    workflows = get_prebuilt_workflows()

    morning = _find_workflow(workflows, "Morning Prep")
    post = _find_workflow(workflows, "Post-Meeting")
    signal = _find_workflow(workflows, "Signal Alert")

    assert morning.metadata.color == "#F59E0B"
    assert post.metadata.color == "#3B82F6"
    assert signal.metadata.color == "#EF4444"


def test_all_workflows_are_valid_pydantic_models() -> None:
    """Every returned object is a valid UserWorkflowDefinition."""
    workflows = get_prebuilt_workflows()
    for wf in workflows:
        assert isinstance(wf, UserWorkflowDefinition)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_workflow(
    workflows: list[UserWorkflowDefinition],
    name: str,
) -> UserWorkflowDefinition:
    """Find a workflow by name or fail with a clear message."""
    for wf in workflows:
        if wf.name == name:
            return wf
    raise AssertionError(f"Workflow '{name}' not found in {[w.name for w in workflows]}")
