"""Tests for the continuous self-improvement loop module (US-809)."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.companion.self_improvement import (
    ImprovementArea,
    ImprovementCycleResponse,
    SelfImprovementLoop,
    WeeklyReportResponse,
)

# ── ImprovementArea Dataclass Tests ──────────────────────────────────────────


def test_improvement_area_to_dict() -> None:
    """Test ImprovementArea.to_dict serializes correctly."""
    area = ImprovementArea(
        area="Context Retention",
        current_performance=0.6,
        target_performance=0.9,
        gap=0.3,
        improvement_actions=["Review conversation history", "Track follow-ups"],
        priority=1,
    )
    data = area.to_dict()

    assert data["area"] == "Context Retention"
    assert data["current_performance"] == 0.6
    assert data["target_performance"] == 0.9
    assert data["gap"] == 0.3
    assert len(data["improvement_actions"]) == 2
    assert data["priority"] == 1


def test_improvement_area_from_dict() -> None:
    """Test ImprovementArea.from_dict creates correct instance."""
    data = {
        "area": "Proactive Suggestions",
        "current_performance": 0.5,
        "target_performance": 0.85,
        "gap": 0.35,
        "improvement_actions": ["Analyze user patterns"],
        "priority": 2,
    }
    area = ImprovementArea.from_dict(data)

    assert area.area == "Proactive Suggestions"
    assert area.current_performance == 0.5
    assert area.target_performance == 0.85
    assert area.gap == 0.35
    assert len(area.improvement_actions) == 1
    assert area.priority == 2


def test_improvement_area_round_trip() -> None:
    """Test ImprovementArea survives to_dict -> from_dict round trip."""
    original = ImprovementArea(
        area="Emotional Intelligence",
        current_performance=0.7,
        target_performance=0.95,
        gap=0.25,
        improvement_actions=["Read user tone", "Adjust response empathy"],
        priority=3,
    )
    restored = ImprovementArea.from_dict(original.to_dict())

    assert restored.area == original.area
    assert restored.current_performance == original.current_performance
    assert restored.target_performance == original.target_performance
    assert restored.gap == original.gap
    assert restored.improvement_actions == original.improvement_actions
    assert restored.priority == original.priority


def test_improvement_area_defaults() -> None:
    """Test ImprovementArea has proper defaults."""
    area = ImprovementArea(
        area="Test",
        current_performance=0.0,
        target_performance=1.0,
        gap=1.0,
    )
    assert area.improvement_actions == []
    assert area.priority == 1


# ── Pydantic Model Tests ────────────────────────────────────────────────────


def test_improvement_cycle_response_defaults() -> None:
    """Test ImprovementCycleResponse has proper defaults."""
    response = ImprovementCycleResponse()
    assert response.areas == []
    assert response.action_plan == []
    assert response.performance_trend == {}


def test_weekly_report_response_defaults() -> None:
    """Test WeeklyReportResponse has proper defaults."""
    response = WeeklyReportResponse()
    assert response.summary == ""
    assert response.interaction_count == 0
    assert response.improvement_metrics == {}
    assert response.wins == []
    assert response.areas_to_work_on == []
    assert response.week_over_week == {}


# ── SelfImprovementLoop Tests ───────────────────────────────────────────────


class TestSelfImprovementLoop:
    """Tests for SelfImprovementLoop service."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create mock database client."""
        return MagicMock()

    @pytest.fixture
    def mock_llm(self) -> AsyncMock:
        """Create mock LLM client."""
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db: MagicMock, mock_llm: AsyncMock) -> SelfImprovementLoop:
        """Create service with mocked dependencies."""
        return SelfImprovementLoop(
            db_client=mock_db,
            llm_client=mock_llm,
        )

    @pytest.mark.asyncio
    async def test_improvement_cycle_identifies_gaps(
        self,
        service: SelfImprovementLoop,
        mock_db: MagicMock,
        mock_llm: AsyncMock,
    ) -> None:
        """Test improvement cycle identifies gaps from reflections."""
        # Mock 7 daily reflections with mixed outcomes
        mock_reflections = [
            {
                "id": f"ref-{i}",
                "user_id": "user-1",
                "reflection_date": f"2026-02-{10 + i}T00:00:00+00:00",
                "total_interactions": 5,
                "positive_outcomes": [{"description": "Good"}] * (3 if i % 2 == 0 else 1),
                "negative_outcomes": [{"description": "Bad"}] * (1 if i % 2 == 0 else 2),
                "patterns_detected": ["User prefers concise"],
                "improvement_opportunities": [{"area": "Clarity", "action": "Be direct"}],
            }
            for i in range(7)
        ]

        # Mock DB query for reflections
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.execute.return_value = MagicMock(
            data=mock_reflections
        )

        # Mock LLM gap analysis response
        mock_llm.generate_response.return_value = json.dumps(
            {
                "areas": [
                    {
                        "area": "Response Clarity",
                        "current_performance": 0.6,
                        "target_performance": 0.9,
                        "gap": 0.3,
                        "improvement_actions": ["Use simpler language", "Add examples"],
                        "priority": 1,
                    },
                    {
                        "area": "Context Retention",
                        "current_performance": 0.5,
                        "target_performance": 0.85,
                        "gap": 0.35,
                        "improvement_actions": ["Review history before responding"],
                        "priority": 2,
                    },
                ]
            }
        )

        # Mock DB insert for storing cycle
        mock_db.table.return_value.insert.return_value.execute = MagicMock()

        result = await service.run_improvement_cycle("user-1")

        assert len(result["top_improvement_areas"]) == 2
        assert result["top_improvement_areas"][0]["area"] == "Response Clarity"
        assert result["top_improvement_areas"][0]["priority"] == 1
        assert len(result["action_plan"]) == 3
        assert result["performance_trend"]["total_reflections"] == 7
        assert result["performance_trend"]["total_positive"] > 0
        assert result["performance_trend"]["total_negative"] > 0

    @pytest.mark.asyncio
    async def test_improvement_cycle_empty_reflections(
        self,
        service: SelfImprovementLoop,
        mock_db: MagicMock,
    ) -> None:
        """Test improvement cycle handles no reflections gracefully."""
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.execute.return_value = MagicMock(
            data=[]
        )

        result = await service.run_improvement_cycle("user-1")

        assert result["top_improvement_areas"] == []
        assert result["action_plan"] == []
        assert result["performance_trend"]["status"] == "no_data"

    @pytest.mark.asyncio
    async def test_regression_detection(
        self,
        service: SelfImprovementLoop,
        mock_db: MagicMock,
    ) -> None:
        """Test regression detection with declining performance."""
        # 14 reflections: first 7 (baseline) mostly positive, last 7 (recent) mostly negative
        # Note: ordered desc so recent comes first
        reflections = []
        # Recent period (worse)
        for _i in range(7):
            reflections.append(
                {
                    "positive_outcomes": [{"description": "ok"}],
                    "negative_outcomes": [{"description": "bad"}] * 4,
                    "total_interactions": 5,
                }
            )
        # Baseline period (better)
        for _i in range(7):
            reflections.append(
                {
                    "positive_outcomes": [{"description": "great"}] * 4,
                    "negative_outcomes": [{"description": "minor"}],
                    "total_interactions": 5,
                }
            )

        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.execute.return_value = MagicMock(
            data=reflections
        )

        regressions = await service.detect_regression("user-1")

        assert len(regressions) > 0
        # Should detect the positive ratio decline
        assert any("declined" in r or "decreased" in r or "increased" in r for r in regressions)

    @pytest.mark.asyncio
    async def test_regression_detection_insufficient_data(
        self,
        service: SelfImprovementLoop,
        mock_db: MagicMock,
    ) -> None:
        """Test regression detection returns empty for insufficient data."""
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.execute.return_value = MagicMock(
            data=[{"positive_outcomes": [{"d": "ok"}], "negative_outcomes": []}]
        )

        regressions = await service.detect_regression("user-1")
        assert regressions == []

    @pytest.mark.asyncio
    async def test_current_focus_top3(
        self,
        service: SelfImprovementLoop,
        mock_db: MagicMock,
    ) -> None:
        """Test get_current_focus returns top 3 areas."""
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "improvement_areas": [
                        {
                            "area": "Clarity",
                            "current_performance": 0.5,
                            "target_performance": 0.9,
                            "gap": 0.4,
                            "priority": 1,
                        },
                        {
                            "area": "Empathy",
                            "current_performance": 0.6,
                            "target_performance": 0.9,
                            "gap": 0.3,
                            "priority": 2,
                        },
                        {
                            "area": "Speed",
                            "current_performance": 0.7,
                            "target_performance": 0.9,
                            "gap": 0.2,
                            "priority": 3,
                        },
                        {
                            "area": "Depth",
                            "current_performance": 0.4,
                            "target_performance": 0.8,
                            "gap": 0.4,
                            "priority": 4,
                        },
                        {
                            "area": "Creativity",
                            "current_performance": 0.5,
                            "target_performance": 0.8,
                            "gap": 0.3,
                            "priority": 5,
                        },
                    ]
                }
            ]
        )

        focus = await service.get_current_focus("user-1")

        assert len(focus) == 3
        assert focus[0] == "Clarity"
        assert focus[1] == "Empathy"
        assert focus[2] == "Speed"

    @pytest.mark.asyncio
    async def test_current_focus_empty(
        self,
        service: SelfImprovementLoop,
        mock_db: MagicMock,
    ) -> None:
        """Test get_current_focus returns empty for no cycles."""
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[]
        )

        focus = await service.get_current_focus("user-1")
        assert focus == []

    @pytest.mark.asyncio
    async def test_learning_application(
        self,
        service: SelfImprovementLoop,
        mock_db: MagicMock,
    ) -> None:
        """Test apply_learning stores learning and returns confirmation."""
        mock_db.table.return_value.insert.return_value.execute = MagicMock()

        result = await service.apply_learning(
            user_id="user-1",
            area="Response Clarity",
            learning_data={"insight": "Shorter sentences improve comprehension"},
        )

        assert result["area"] == "Response Clarity"
        assert result["applied"] is True
        assert "learning_id" in result
        # Verify DB was called
        mock_db.table.assert_called_with("companion_learnings")

    @pytest.mark.asyncio
    async def test_weekly_report_generation(
        self,
        service: SelfImprovementLoop,
        mock_db: MagicMock,
        mock_llm: AsyncMock,
    ) -> None:
        """Test weekly report generates with comparison data."""
        # Mock reflections for this week and previous week
        this_week_reflections = [
            {
                "total_interactions": 8,
                "positive_outcomes": [{"d": "win1"}, {"d": "win2"}],
                "negative_outcomes": [{"d": "miss1"}],
            }
            for _ in range(5)
        ]
        prev_week_reflections = [
            {
                "total_interactions": 6,
                "positive_outcomes": [{"d": "win1"}],
                "negative_outcomes": [{"d": "miss1"}, {"d": "miss2"}],
            }
            for _ in range(4)
        ]

        # Two DB calls for reflections (this week + prev week)
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.lte.return_value.order.return_value.execute.side_effect = [
            MagicMock(data=this_week_reflections),
            MagicMock(data=prev_week_reflections),
        ]

        # Mock LLM response for report
        mock_llm.generate_response.return_value = json.dumps(
            {
                "summary": "Strong week with improved positive outcomes.",
                "wins": ["Better context retention", "Faster response times"],
                "areas_to_work_on": ["Proactive suggestions could improve"],
            }
        )

        result = await service.generate_weekly_report("user-1")

        assert result["summary"] == "Strong week with improved positive outcomes."
        assert result["interaction_count"] == 40  # 8 * 5
        assert len(result["wins"]) == 2
        assert len(result["areas_to_work_on"]) == 1
        assert result["week_over_week"]["positive_change"] > 0
        assert result["improvement_metrics"]["total_positive"] == 10

    @pytest.mark.asyncio
    async def test_llm_failure_graceful_degradation(
        self,
        service: SelfImprovementLoop,
        mock_db: MagicMock,
        mock_llm: AsyncMock,
    ) -> None:
        """Test graceful degradation when LLM fails."""
        # Mock reflections
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "positive_outcomes": [{"d": "ok"}],
                    "negative_outcomes": [],
                    "patterns_detected": [],
                    "improvement_opportunities": [],
                }
            ]
            * 3
        )

        # LLM raises exception
        mock_llm.generate_response.side_effect = Exception("LLM unavailable")

        # Mock DB insert
        mock_db.table.return_value.insert.return_value.execute = MagicMock()

        result = await service.run_improvement_cycle("user-1")

        # Should return empty areas but still have trend data
        assert result["top_improvement_areas"] == []
        assert result["action_plan"] == []
        assert result["performance_trend"]["total_reflections"] == 3
