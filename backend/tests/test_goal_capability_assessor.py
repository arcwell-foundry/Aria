"""Tests for GoalCapabilityAssessor facade."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.capability import CapabilityGap, TaskCapabilityReport
from src.services.goal_capability_assessor import GoalCapabilityAssessor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_db_response(data: list[dict] | None = None):
    """Build a mock Supabase response object."""
    resp = MagicMock()
    resp.data = data or []
    return resp


def _make_gap(
    capability: str,
    severity: str,
    current_provider: str | None = None,
    current_quality: float = 0,
) -> CapabilityGap:
    """Build a CapabilityGap for testing."""
    return CapabilityGap(
        capability=capability,
        step={"description": "test step"},
        severity=severity,
        current_provider=current_provider,
        current_quality=current_quality,
        can_proceed=severity == "degraded",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGoalCapabilityAssessor:
    """Tests for GoalCapabilityAssessor.assess_plan()."""

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        return db

    @pytest.fixture
    def assessor(self, mock_db):
        return GoalCapabilityAssessor(mock_db)

    @pytest.mark.asyncio
    async def test_assess_plan_all_ready(self, assessor):
        """No gaps detected → all tasks are ready."""
        tasks = [
            {"title": "Research company", "description": "Analyze target company"},
            {"title": "Draft email", "description": "Write outreach email"},
        ]

        with patch.object(
            assessor._detector,
            "analyze_capabilities_for_plan",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await assessor.assess_plan(tasks, "user-1", "Test Goal")

        assert not result["has_blocking"]
        assert not result["has_degraded"]
        assert len(result["task_reports"]) == 2
        assert all(r.capability_status == "ready" for r in result["task_reports"])
        assert len(result["all_gaps"]) == 0
        assert result["gap_message"] == ""

    @pytest.mark.asyncio
    async def test_assess_plan_with_blocked(self, assessor):
        """Blocking gap → task marked as blocked with blocking_capabilities."""
        tasks = [{"title": "Read CRM", "description": "Read CRM pipeline data"}]
        blocking_gap = _make_gap("read_crm_pipeline", "blocking")

        with patch.object(
            assessor._detector,
            "analyze_capabilities_for_plan",
            new_callable=AsyncMock,
            return_value=[blocking_gap],
        ):
            result = await assessor.assess_plan(tasks, "user-1", "Test Goal")

        assert result["has_blocking"]
        assert not result["has_degraded"]
        report = result["task_reports"][0]
        assert report.capability_status == "blocked"
        assert "read_crm_pipeline" in report.blocking_capabilities
        assert len(report.gaps) == 1

    @pytest.mark.asyncio
    async def test_assess_plan_with_degraded(self, assessor):
        """Degraded gap → task marked as degraded with degradation_notes."""
        tasks = [{"title": "Research", "description": "Research company info"}]
        degraded_gap = _make_gap(
            "research_company", "degraded",
            current_provider="web_search",
            current_quality=0.5,
        )

        with patch.object(
            assessor._detector,
            "analyze_capabilities_for_plan",
            new_callable=AsyncMock,
            return_value=[degraded_gap],
        ):
            result = await assessor.assess_plan(tasks, "user-1", "Test Goal")

        assert not result["has_blocking"]
        assert result["has_degraded"]
        report = result["task_reports"][0]
        assert report.capability_status == "degraded"
        assert len(report.degradation_notes) == 1
        assert "web_search" in report.degradation_notes[0]
        assert "50%" in report.degradation_notes[0]

    @pytest.mark.asyncio
    async def test_assess_plan_mixed(self, assessor):
        """Mix of ready, degraded, blocked → correct flags."""
        tasks = [
            {"title": "Ready Task", "description": "Simple research"},
            {"title": "Degraded Task", "description": "Email analysis"},
            {"title": "Blocked Task", "description": "CRM update"},
        ]

        degraded_gap = _make_gap(
            "read_email", "degraded",
            current_provider="web_fallback",
            current_quality=0.4,
        )
        blocking_gap = _make_gap("write_crm", "blocking")

        call_count = 0

        async def mock_analyze(plan, user_id):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return []  # ready
            elif call_count == 2:
                return [degraded_gap]
            else:
                return [blocking_gap]

        with patch.object(
            assessor._detector,
            "analyze_capabilities_for_plan",
            side_effect=mock_analyze,
        ):
            result = await assessor.assess_plan(tasks, "user-1", "Mixed Goal")

        assert result["has_blocking"]
        assert result["has_degraded"]
        reports = result["task_reports"]
        assert reports[0].capability_status == "ready"
        assert reports[1].capability_status == "degraded"
        assert reports[2].capability_status == "blocked"
        assert len(result["all_gaps"]) == 2

    @pytest.mark.asyncio
    async def test_assess_plan_graceful_failure(self, assessor):
        """Detector raises exception → all tasks default to ready."""
        tasks = [
            {"title": "Task A", "description": "Do something"},
            {"title": "Task B", "description": "Do something else"},
        ]

        with patch.object(
            assessor._detector,
            "analyze_capabilities_for_plan",
            new_callable=AsyncMock,
            side_effect=Exception("LLM unavailable"),
        ):
            result = await assessor.assess_plan(tasks, "user-1", "Error Goal")

        assert not result["has_blocking"]
        assert not result["has_degraded"]
        assert len(result["task_reports"]) == 2
        assert all(r.capability_status == "ready" for r in result["task_reports"])

    @pytest.mark.asyncio
    async def test_check_gaps_resolved_unblocks(self, assessor):
        """Previously blocked task now has available provider → unblocked."""
        blocked_tasks = [
            {
                "title": "CRM Task",
                "blocking_capabilities": ["read_crm_pipeline"],
            }
        ]

        mock_provider = MagicMock()
        mock_provider.quality_score = 0.9

        with patch.object(
            assessor._graph,
            "get_best_available",
            new_callable=AsyncMock,
            return_value=mock_provider,
        ):
            unblocked = await assessor.check_gaps_resolved(blocked_tasks, "user-1")

        assert len(unblocked) == 1
        assert unblocked[0]["title"] == "CRM Task"

    @pytest.mark.asyncio
    async def test_check_gaps_resolved_still_blocked(self, assessor):
        """Still no provider → empty result."""
        blocked_tasks = [
            {
                "title": "CRM Task",
                "blocking_capabilities": ["read_crm_pipeline"],
            }
        ]

        with patch.object(
            assessor._graph,
            "get_best_available",
            new_callable=AsyncMock,
            return_value=None,
        ):
            unblocked = await assessor.check_gaps_resolved(blocked_tasks, "user-1")

        assert len(unblocked) == 0

    @pytest.mark.asyncio
    async def test_gap_message_generated(self, assessor):
        """ProvisioningConversation.format_gap_message() called when gaps exist."""
        tasks = [{"title": "Email Task", "description": "Send email"}]
        gap = _make_gap("send_email", "blocking")

        with (
            patch.object(
                assessor._detector,
                "analyze_capabilities_for_plan",
                new_callable=AsyncMock,
                return_value=[gap],
            ),
            patch.object(
                assessor._conversation,
                "format_gap_message",
                new_callable=AsyncMock,
                return_value="I need email access to proceed.",
            ) as mock_format,
        ):
            result = await assessor.assess_plan(tasks, "user-1", "Email Goal")

        mock_format.assert_called_once()
        assert result["gap_message"] == "I need email access to proceed."
