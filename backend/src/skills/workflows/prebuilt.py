"""Pre-built workflow definitions shipped with ARIA.

These workflows are available out-of-the-box and marked ``is_shared=True``
so they appear in every user's workflow library without per-user copies.

Three workflows are provided:

* **Morning Prep** -- Runs a morning briefing at 6 AM on weekdays and
  pushes the summary to Slack.
* **Post-Meeting** -- Fires after a calendar event ends, prompts the user
  for meeting notes (approval gate), extracts action items, and drafts a
  follow-up email.
* **Signal Alert** -- Evaluates incoming market signals and, when the
  relevance score exceeds 0.8, formats the signal and pushes alerts to
  Slack and in-app notifications.
"""

from src.skills.workflows.models import (
    UserWorkflowDefinition,
    WorkflowAction,
    WorkflowMetadata,
    WorkflowTrigger,
)


def get_prebuilt_workflows() -> list[UserWorkflowDefinition]:
    """Return every pre-built workflow definition.

    Returns:
        A list of :class:`UserWorkflowDefinition` instances, all with
        ``is_shared=True``.
    """
    return [
        _morning_prep(),
        _post_meeting(),
        _signal_alert(),
    ]


# ---------------------------------------------------------------------------
# Individual builders
# ---------------------------------------------------------------------------


def _morning_prep() -> UserWorkflowDefinition:
    """Build the Morning Prep workflow."""
    return UserWorkflowDefinition(
        name="Morning Prep",
        trigger=WorkflowTrigger(
            type="time",
            cron_expression="0 6 * * 1-5",
        ),
        actions=[
            WorkflowAction(
                step_id="briefing",
                action_type="run_skill",
                config={"skill_id": "morning-briefing", "template": "daily_summary"},
            ),
            WorkflowAction(
                step_id="notify",
                action_type="send_notification",
                config={"channel": "slack"},
            ),
        ],
        metadata=WorkflowMetadata(
            category="productivity",
            icon="sun",
            color="#F59E0B",
            description="Daily morning briefing delivered to Slack at 6 AM on weekdays.",
        ),
        is_shared=True,
    )


def _post_meeting() -> UserWorkflowDefinition:
    """Build the Post-Meeting workflow."""
    return UserWorkflowDefinition(
        name="Post-Meeting",
        trigger=WorkflowTrigger(
            type="event",
            event_type="calendar_event_ended",
        ),
        actions=[
            WorkflowAction(
                step_id="notes",
                action_type="run_skill",
                config={"skill_id": "meeting-notes-prompt"},
                requires_approval=True,
            ),
            WorkflowAction(
                step_id="actions",
                action_type="run_skill",
                config={"skill_id": "action-item-extractor"},
            ),
            WorkflowAction(
                step_id="email",
                action_type="draft_email",
                config={"purpose": "follow_up"},
            ),
        ],
        metadata=WorkflowMetadata(
            category="follow_up",
            icon="calendar",
            color="#3B82F6",
            description=(
                "After a meeting ends, prompts for notes, extracts action "
                "items, and drafts a follow-up email."
            ),
        ),
        is_shared=True,
    )


def _signal_alert() -> UserWorkflowDefinition:
    """Build the Signal Alert workflow."""
    return UserWorkflowDefinition(
        name="Signal Alert",
        trigger=WorkflowTrigger(
            type="condition",
            condition_field="market_signals.relevance_score",
            condition_operator="gt",
            condition_value=0.8,
        ),
        actions=[
            WorkflowAction(
                step_id="format",
                action_type="run_skill",
                config={"skill_id": "signal-formatter", "template": "alert_summary"},
            ),
            WorkflowAction(
                step_id="alert",
                action_type="send_notification",
                config={"channels": ["slack", "in-app"]},
            ),
        ],
        metadata=WorkflowMetadata(
            category="monitoring",
            icon="radar",
            color="#EF4444",
            description=(
                "Alerts via Slack and in-app notification when a market "
                "signal scores above 0.8 relevance."
            ),
        ),
        is_shared=True,
    )
