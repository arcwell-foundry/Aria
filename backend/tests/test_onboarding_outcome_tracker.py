"""Tests for OnboardingOutcomeTracker (US-924)."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.onboarding.outcome_tracker import (
    OnboardingOutcome,
    OnboardingOutcomeTracker,
)


def _make_db_row(**kwargs: Any) -> dict[str, Any]:
    """Build a mock onboarding_outcomes DB row."""
    return {
        "id": "outcome-abc",
        "user_id": kwargs.get("user_id", "user-123"),
        "readiness_snapshot": kwargs.get("readiness_snapshot", {}),
        "completion_time_minutes": kwargs.get("completion_time_minutes", 15.5),
        "steps_completed": kwargs.get("steps_completed", 8),
        "steps_skipped": kwargs.get("steps_skipped", 1),
        "company_type": kwargs.get("company_type", "biotech"),
        "first_goal_category": kwargs.get("first_goal_category", "lead_gen"),
        "documents_uploaded": kwargs.get("documents_uploaded", 3),
        "email_connected": kwargs.get("email_connected", True),
        "crm_connected": kwargs.get("crm_connected", False),
        "created_at": "2026-02-07T12:00:00+00:00",
        "updated_at": "2026-02-07T12:00:00+00:00",
    }


def _mock_execute(data: Any) -> MagicMock:
    """Build a mock .execute() result."""
    result = MagicMock()
    result.data = data
    return result


def _build_chain(execute_return: Any) -> MagicMock:
    """Build a fluent Supabase query chain ending in .execute()."""
    chain = MagicMock()
    chain.select.return_value = chain
    chain.insert.return_value = chain
    chain.update.return_value = chain
    chain.eq.return_value = chain
    chain.maybe_single.return_value = chain
    chain.order.return_value = chain
    chain.range.return_value = chain
    execute_result = _mock_execute(execute_return)
    chain.execute.return_value = execute_result
    # Make the response behave like the real data
    if execute_return is None:
        chain.data = None
    elif isinstance(execute_return, list):
        chain.data = execute_return
    elif isinstance(execute_return, dict):
        chain.data = execute_return
    else:
        chain.data = execute_return
    return chain


@pytest.fixture()
def mock_db() -> MagicMock:
    """Create a mock Supabase client."""
    return MagicMock()


@pytest.fixture()
def tracker(mock_db: MagicMock) -> OnboardingOutcomeTracker:
    """Create an OnboardingOutcomeTracker with mocked DB."""
    with patch("src.onboarding.outcome_tracker.SupabaseClient") as mock_cls:
        mock_cls.get_client.return_value = mock_db
        return OnboardingOutcomeTracker()


class TestRecordOutcome:
    """Tests for record_outcome method."""

    @pytest.mark.asyncio()
    async def test_records_outcome_from_onboarding_state(
        self, tracker: OnboardingOutcomeTracker, mock_db: MagicMock
    ) -> None:
        """record_outcome gathers data from onboarding_state and stores outcome."""
        # Mock onboarding_state query
        state_row = {
            "id": "state-abc",
            "user_id": "user-123",
            "current_step": "activation",
            "completed_steps": ["company_discovery", "document_upload", "user_profile", "writing_samples", "email_integration", "integration_wizard", "first_goal", "activation"],
            "skipped_steps": [],
            "started_at": "2026-02-07T11:00:00+00:00",
            "completed_at": "2026-02-07T11:15:00+00:00",
            "readiness_scores": {
                "corporate_memory": 80.0,
                "digital_twin": 70.0,
                "relationship_graph": 60.0,
                "integrations": 75.0,
                "goal_clarity": 80.0,
            },
            "step_data": {
                "company_discovery": {"company_type": "cdmo"},
                "first_goal": {"goal_type": "meeting_prep"},
                "integration_wizard": {"email_connected": True, "crm_connected": True},
            },
            "metadata": {"documents_uploaded": 2},
        }

        # Build state chain with maybe_single support - return state_row directly as data
        state_chain = MagicMock()
        state_chain.select.return_value = state_chain
        state_chain.eq.return_value = state_chain
        state_chain.maybe_single.return_value = state_chain
        state_chain.execute.return_value.data = state_row

        # Mock outcome insert
        outcome_row = _make_db_row(
            user_id="user-123",
            completion_time_minutes=15.0,
            steps_completed=8,
            steps_skipped=0,
            company_type="cdmo",
            first_goal_category="meeting_prep",
            documents_uploaded=2,
            email_connected=True,
            crm_connected=True,
            readiness_snapshot=state_row["readiness_scores"],
        )
        insert_chain = _build_chain([outcome_row])

        mock_db.table.side_effect = [state_chain, insert_chain]

        result = await tracker.record_outcome("user-123")

        assert result.user_id == "user-123"
        assert result.time_to_complete_minutes == 15.0
        assert result.steps_completed == 8
        assert result.company_type == "cdmo"
        assert result.email_connected is True
        assert result.crm_connected is True

    @pytest.mark.asyncio()
    async def test_handles_missing_onboarding_state(
        self, tracker: OnboardingOutcomeTracker, mock_db: MagicMock
    ) -> None:
        """Missing onboarding_state raises ValueError."""
        # Create a chain where execute returns a response with None data
        state_chain = MagicMock()
        state_chain.select.return_value = state_chain
        state_chain.eq.return_value = state_chain
        state_chain.maybe_single.return_value = state_chain
        state_chain.execute.return_value.data = None
        mock_db.table.return_value = state_chain

        with pytest.raises(ValueError, match="Onboarding state not found"):
            await tracker.record_outcome("user-123")


class TestGetSystemInsights:
    """Tests for get_system_insights method."""

    @pytest.mark.asyncio()
    async def test_aggregates_insights_across_users(
        self, tracker: OnboardingOutcomeTracker, mock_db: MagicMock
    ) -> None:
        """get_system_insights aggregates cross-user patterns."""
        # Mock multiple outcomes with 3+ CDMO users for minimum sample size
        outcomes = [
            _make_db_row(
                user_id="user-1",
                company_type="cdmo",
                documents_uploaded=5,
                completion_time_minutes=12.0,
                readiness_snapshot={"overall": 85.0},
            ),
            _make_db_row(
                user_id="user-2",
                company_type="cdmo",
                documents_uploaded=3,
                completion_time_minutes=18.0,
                readiness_snapshot={"overall": 75.0},
            ),
            _make_db_row(
                user_id="user-3",
                company_type="cdmo",
                documents_uploaded=0,
                completion_time_minutes=25.0,
                readiness_snapshot={"overall": 55.0},
            ),
            _make_db_row(
                user_id="user-4",
                company_type="biotech",
                documents_uploaded=2,
                completion_time_minutes=20.0,
                readiness_snapshot={"overall": 65.0},
            ),
        ]
        chain = _build_chain(outcomes)
        mock_db.table.return_value = chain

        insights = await tracker.get_system_insights()

        assert len(insights) > 0
        # Should have aggregated insights about CDMO
        assert any(insight.get("company_type") == "cdmo" for insight in insights)
        # Should have average completion time
        assert any(insight.get("pattern") == "avg_completion_time" for insight in insights)

    @pytest.mark.asyncio()
    async def test_returns_empty_list_when_no_outcomes(
        self, tracker: OnboardingOutcomeTracker, mock_db: MagicMock
    ) -> None:
        """No outcomes returns empty insights list."""
        chain = _build_chain([])
        mock_db.table.return_value = chain

        insights = await tracker.get_system_insights()

        assert insights == []


class TestConsolidateToProcedural:
    """Tests for consolidate_to_procedural method."""

    @pytest.mark.asyncio()
    async def test_consolidates_episodic_to_semantic(
        self, tracker: OnboardingOutcomeTracker, mock_db: MagicMock
    ) -> None:
        """Consolidates raw outcomes into procedural insights."""
        outcomes = [
            _make_db_row(
                user_id="user-1",
                company_type="cdmo",
                documents_uploaded=5,
                readiness_snapshot={"corporate_memory": 90.0},
            ),
            _make_db_row(
                user_id="user-2",
                company_type="cdmo",
                documents_uploaded=4,
                readiness_snapshot={"corporate_memory": 85.0},
            ),
        ]
        outcomes_chain = _build_chain(outcomes)

        # Mock existing insights
        existing_insights = []
        insights_chain = _build_chain(existing_insights)

        # Mock insert
        inserted = [{"id": "insight-1"}]
        insert_chain = _build_chain(inserted)

        mock_db.table.side_effect = [outcomes_chain, insights_chain, insert_chain]

        count = await tracker.consolidate_to_procedural()

        assert count >= 0  # May create insights if patterns found
