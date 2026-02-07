"""Tests for OnboardingCompletionOrchestrator outcome recording."""

from typing import Any
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from src.onboarding.activation import OnboardingCompletionOrchestrator


def _mock_execute(data: Any) -> MagicMock:
    result = MagicMock()
    result.data = data
    return result


def _build_chain(execute_return: Any) -> MagicMock:
    chain = MagicMock()
    chain.select.return_value = chain
    chain.insert.return_value = chain
    chain.update.return_value = chain
    chain.eq.return_value = chain
    chain.maybe_single.return_value = chain
    chain.execute.return_value = _mock_execute(execute_return)
    return chain


@pytest.fixture()
def mock_db() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def orchestrator(mock_db: MagicMock) -> OnboardingCompletionOrchestrator:
    with patch("src.onboarding.activation.SupabaseClient") as mock_cls:
        mock_cls.get_client.return_value = mock_db
        return OnboardingCompletionOrchestrator()


@pytest.mark.asyncio()
async def test_activate_records_outcome(
    orchestrator: OnboardingCompletionOrchestrator,
    mock_db: MagicMock,
) -> None:
    """Activation records onboarding outcome after agent activation."""
    user_id = "user-123"
    onboarding_data = {
        "company_id": "comp-1",
        "company_discovery": {"website": "example.com"},
        "first_goal": {"goal_type": "lead_gen"},
        "integration_wizard": {"email_connected": True, "crm_connected": True},
        "enrichment": {"company_type": "cdmo"},
    }

    # Mock goal creation for each agent
    goal_chain = _build_chain([{"id": "goal-1"}])

    # Mock outcome recording state query
    state_row = {
        "id": "state-1",
        "user_id": user_id,
        "completed_steps": ["activation"],
        "skipped_steps": [],
        "started_at": "2026-02-07T10:00:00+00:00",
        "completed_at": "2026-02-07T10:15:00+00:00",
        "readiness_scores": {"overall": 75.0},
        "step_data": onboarding_data,
        "metadata": {},
    }
    state_chain = _build_chain(state_row)

    # Mock outcome insert
    outcome_row = {
        "id": "outcome-1",
        "user_id": user_id,
        "completion_time_minutes": 15.0,
    }
    outcome_chain = _build_chain([outcome_row])

    # Setup chain sequence: state query, goal creations, outcome state, outcome insert
    mock_db.table.side_effect = [
        state_chain,  # onboarding_state query
        goal_chain,   # scout goal
        goal_chain,   # analyst goal
        goal_chain,   # hunter goal
        goal_chain,   # operator goal
        goal_chain,   # scribe goal
        goal_chain,   # strategist goal
        state_chain,  # outcome state query
        outcome_chain,  # outcome insert
    ]

    # Mock OnboardingOutcomeTracker to verify it's called
    with patch("src.onboarding.activation.OnboardingOutcomeTracker") as mock_tracker_cls:
        mock_tracker = MagicMock()
        mock_tracker.record_outcome = AsyncMock(return_value=MagicMock(
            user_id=user_id,
            completion_time_minutes=15.0,
            steps_completed=8,
            company_type="cdmo",
            email_connected=True,
            crm_connected=True,
        ))
        mock_tracker_cls.return_value = mock_tracker

        result = await orchestrator.activate(user_id, onboarding_data)

        # Verify outcome tracker was called
        mock_tracker.record_outcome.assert_called_once_with(user_id)

    # Verify basic result structure
    assert result["user_id"] == user_id
    assert "activated_at" in result
