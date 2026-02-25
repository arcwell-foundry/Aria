"""Tests for UserMentalModelService."""

import time
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest


class TestUserMentalModelInit:
    """Tests for UserMentalModel dataclass and service initialization."""

    def test_model_has_all_fields(self) -> None:
        """UserMentalModel should have all required fields."""
        from src.intelligence.user_model import UserMentalModel

        model = UserMentalModel(
            user_id="user-1",
            stress_trend="stable",
            decision_style="analytical",
            preferred_depth="standard",
            current_focus="Close Novartis deal",
            active_goal_count=3,
            overdue_goal_count=1,
            avg_messages_per_session=8.5,
            peak_activity_hour=10,
            communication_preferences={"preferred_tone": "direct"},
        )

        assert model.user_id == "user-1"
        assert model.stress_trend == "stable"
        assert model.decision_style == "analytical"
        assert model.preferred_depth == "standard"
        assert model.current_focus == "Close Novartis deal"
        assert model.active_goal_count == 3
        assert model.overdue_goal_count == 1
        assert model.avg_messages_per_session == 8.5
        assert model.peak_activity_hour == 10
        assert model.communication_preferences["preferred_tone"] == "direct"

    def test_to_prompt_section(self) -> None:
        """to_prompt_section should format all fields for system prompt."""
        from src.intelligence.user_model import UserMentalModel

        model = UserMentalModel(
            user_id="user-1",
            stress_trend="improving",
            decision_style="collaborative",
            preferred_depth="detailed",
            current_focus="Q4 pipeline review",
            active_goal_count=5,
            overdue_goal_count=2,
            avg_messages_per_session=12.3,
            peak_activity_hour=14,
            communication_preferences={
                "preferred_tone": "warm",
                "communication_style": "formal",
            },
        )

        section = model.to_prompt_section()
        assert "improving" in section
        assert "collaborative" in section
        assert "detailed" in section
        assert "Q4 pipeline review" in section
        assert "5" in section
        assert "2 overdue" in section
        assert "12.3" in section
        assert "14:00" in section
        assert "warm" in section
        assert "formal" in section

    def test_service_init(self) -> None:
        """UserMentalModelService should initialize with db_client."""
        from src.intelligence.user_model import UserMentalModelService

        db = MagicMock()
        service = UserMentalModelService(db_client=db)
        assert service._db is db
        assert service._cache == {}


class TestStressTrend:
    """Tests for stress trend detection."""

    @pytest.mark.asyncio
    async def test_stable_with_insufficient_data(self) -> None:
        """Should return 'stable' when fewer than 4 snapshots."""
        from src.intelligence.user_model import UserMentalModelService

        db = MagicMock()
        mock_result = MagicMock()
        mock_result.data = [
            {"load_score": 0.5, "measured_at": datetime.now(UTC).isoformat()},
            {"load_score": 0.6, "measured_at": datetime.now(UTC).isoformat()},
        ]
        db.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = mock_result

        service = UserMentalModelService(db_client=db)
        result = await service._compute_stress_trend("user-1")
        assert result == "stable"

    @pytest.mark.asyncio
    async def test_improving_when_recent_scores_lower(self) -> None:
        """Should return 'improving' when recent scores are significantly lower."""
        from src.intelligence.user_model import UserMentalModelService

        db = MagicMock()
        now = datetime.now(UTC)
        mock_result = MagicMock()
        mock_result.data = [
            # Older (higher stress)
            {"load_score": 0.8, "measured_at": (now - timedelta(days=6)).isoformat()},
            {"load_score": 0.7, "measured_at": (now - timedelta(days=5)).isoformat()},
            {"load_score": 0.75, "measured_at": (now - timedelta(days=4)).isoformat()},
            # Recent (lower stress)
            {"load_score": 0.4, "measured_at": (now - timedelta(days=2)).isoformat()},
            {"load_score": 0.3, "measured_at": (now - timedelta(days=1)).isoformat()},
            {"load_score": 0.35, "measured_at": now.isoformat()},
        ]
        db.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = mock_result

        service = UserMentalModelService(db_client=db)
        result = await service._compute_stress_trend("user-1")
        assert result == "improving"

    @pytest.mark.asyncio
    async def test_worsening_when_recent_scores_higher(self) -> None:
        """Should return 'worsening' when recent scores are significantly higher."""
        from src.intelligence.user_model import UserMentalModelService

        db = MagicMock()
        now = datetime.now(UTC)
        mock_result = MagicMock()
        mock_result.data = [
            # Older (lower stress)
            {"load_score": 0.3, "measured_at": (now - timedelta(days=6)).isoformat()},
            {"load_score": 0.2, "measured_at": (now - timedelta(days=5)).isoformat()},
            {"load_score": 0.25, "measured_at": (now - timedelta(days=4)).isoformat()},
            # Recent (higher stress)
            {"load_score": 0.7, "measured_at": (now - timedelta(days=2)).isoformat()},
            {"load_score": 0.8, "measured_at": (now - timedelta(days=1)).isoformat()},
            {"load_score": 0.75, "measured_at": now.isoformat()},
        ]
        db.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = mock_result

        service = UserMentalModelService(db_client=db)
        result = await service._compute_stress_trend("user-1")
        assert result == "worsening"

    @pytest.mark.asyncio
    async def test_stable_on_db_error(self) -> None:
        """Should return 'stable' when database query fails."""
        from src.intelligence.user_model import UserMentalModelService

        db = MagicMock()
        db.table.side_effect = Exception("DB error")

        service = UserMentalModelService(db_client=db)
        result = await service._compute_stress_trend("user-1")
        assert result == "stable"


class TestDecisionStyle:
    """Tests for decision style inference."""

    @pytest.mark.asyncio
    async def test_analytical_from_keywords(self) -> None:
        """Should detect analytical style from data-focused summaries."""
        from src.intelligence.user_model import UserMentalModelService

        db = MagicMock()
        mock_result = MagicMock()
        mock_result.data = [
            {"summary": "Discussed metrics and benchmark data for ROI analysis. Compared evidence from research findings with statistical methodology."},
            {"summary": "Reviewed data and numbers for percentage calculations and correlation analysis."},
        ]
        db.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = mock_result

        service = UserMentalModelService(db_client=db)
        result = await service._compute_decision_style("user-1")
        assert result == "analytical"

    @pytest.mark.asyncio
    async def test_intuitive_from_keywords(self) -> None:
        """Should detect intuitive style from gut-feel summaries."""
        from src.intelligence.user_model import UserMentalModelService

        db = MagicMock()
        mock_result = MagicMock()
        mock_result.data = [
            {"summary": "User said just go with gut feel and trust the instinct on this one."},
            {"summary": "Quickly decided to go with the obvious hunch about the vibe of the deal."},
        ]
        db.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = mock_result

        service = UserMentalModelService(db_client=db)
        result = await service._compute_decision_style("user-1")
        assert result == "intuitive"

    @pytest.mark.asyncio
    async def test_collaborative_from_keywords(self) -> None:
        """Should detect collaborative style from team-focused summaries."""
        from src.intelligence.user_model import UserMentalModelService

        db = MagicMock()
        mock_result = MagicMock()
        mock_result.data = [
            {"summary": "Need to align with team and get stakeholder consensus from the meeting input."},
            {"summary": "Will collaborate with team and coordinate feedback to discuss and agree on approach."},
        ]
        db.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = mock_result

        service = UserMentalModelService(db_client=db)
        result = await service._compute_decision_style("user-1")
        assert result == "collaborative"

    @pytest.mark.asyncio
    async def test_unknown_with_no_data(self) -> None:
        """Should return 'unknown' when no episodes exist."""
        from src.intelligence.user_model import UserMentalModelService

        db = MagicMock()
        mock_result = MagicMock()
        mock_result.data = []
        db.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = mock_result

        service = UserMentalModelService(db_client=db)
        result = await service._compute_decision_style("user-1")
        assert result == "unknown"


class TestPreferredDepth:
    """Tests for preferred depth detection."""

    @pytest.mark.asyncio
    async def test_brief_from_high_brevity(self) -> None:
        """High brevity scores (short messages) should indicate 'brief' preference."""
        from src.intelligence.user_model import UserMentalModelService

        db = MagicMock()
        mock_result = MagicMock()
        mock_result.data = [
            {"factors": {"message_brevity": 0.8}},
            {"factors": {"message_brevity": 0.9}},
            {"factors": {"message_brevity": 0.7}},
        ]
        db.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = mock_result

        service = UserMentalModelService(db_client=db)
        result = await service._compute_preferred_depth("user-1")
        assert result == "brief"

    @pytest.mark.asyncio
    async def test_detailed_from_low_brevity(self) -> None:
        """Low brevity scores (long messages) should indicate 'detailed' preference."""
        from src.intelligence.user_model import UserMentalModelService

        db = MagicMock()
        mock_result = MagicMock()
        mock_result.data = [
            {"factors": {"message_brevity": 0.1}},
            {"factors": {"message_brevity": 0.2}},
            {"factors": {"message_brevity": 0.15}},
        ]
        db.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = mock_result

        service = UserMentalModelService(db_client=db)
        result = await service._compute_preferred_depth("user-1")
        assert result == "detailed"

    @pytest.mark.asyncio
    async def test_standard_from_medium_brevity(self) -> None:
        """Medium brevity scores should indicate 'standard' preference."""
        from src.intelligence.user_model import UserMentalModelService

        db = MagicMock()
        mock_result = MagicMock()
        mock_result.data = [
            {"factors": {"message_brevity": 0.5}},
            {"factors": {"message_brevity": 0.45}},
            {"factors": {"message_brevity": 0.55}},
        ]
        db.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = mock_result

        service = UserMentalModelService(db_client=db)
        result = await service._compute_preferred_depth("user-1")
        assert result == "standard"


class TestCaching:
    """Tests for model caching."""

    @pytest.mark.asyncio
    async def test_model_cached_for_ttl(self) -> None:
        """get_model should return cached result within TTL."""
        from src.intelligence.user_model import UserMentalModel, UserMentalModelService

        db = MagicMock()

        service = UserMentalModelService(db_client=db)

        # Pre-populate cache
        model = UserMentalModel(
            user_id="user-1",
            stress_trend="stable",
            decision_style="analytical",
            preferred_depth="standard",
            current_focus="Test",
            active_goal_count=1,
            overdue_goal_count=0,
            avg_messages_per_session=5.0,
            peak_activity_hour=9,
        )
        service._cache["user-1"] = (model, time.monotonic())

        # Should return cached version without hitting DB
        result = await service.get_model("user-1")
        assert result.decision_style == "analytical"
        # DB table() should NOT have been called for a second computation
        assert db.table.call_count == 0

    @pytest.mark.asyncio
    async def test_zero_llm_calls(self) -> None:
        """UserMentalModelService must make zero LLM calls."""
        from src.intelligence.user_model import UserMentalModelService

        db = MagicMock()
        # Set up all DB calls to return empty data
        mock_result = MagicMock()
        mock_result.data = []
        db.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = mock_result
        db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_result
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_result
        db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = mock_result

        service = UserMentalModelService(db_client=db)
        model = await service.get_model("user-1")

        # The service should have returned a model with defaults
        assert model.stress_trend == "stable"
        assert model.decision_style == "unknown"
        assert model.preferred_depth == "standard"
        # No LLM client exists in the service at all — it's pure heuristics
        assert not hasattr(service, "_llm")
