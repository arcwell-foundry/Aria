"""Tests for self-reflection and self-correction module."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.companion.self_reflection import (
    AcknowledgeMistakeRequest,
    DailyReflection,
    ReflectRequest,
    SelfAssessment,
    SelfReflectionService,
    Trend,
)

# ── Enum Tests ───────────────────────────────────────────────────────────────


def test_trend_enum_values() -> None:
    """Test Trend enum has expected values."""
    assert Trend.IMPROVING.value == "improving"
    assert Trend.STABLE.value == "stable"
    assert Trend.DECLINING.value == "declining"


# ── DailyReflection Tests ─────────────────────────────────────────────────────


def test_daily_reflection_to_dict() -> None:
    """Test DailyReflection.to_dict serializes correctly."""
    reflection = DailyReflection(
        id="test-id",
        user_id="user-123",
        reflection_date=datetime(2026, 2, 16, 12, 0, 0, tzinfo=UTC),
        total_interactions=10,
        positive_outcomes=[{"description": "Great response", "evidence": "User smiled"}],
        negative_outcomes=[{"description": "Missed context", "evidence": "User asked again"}],
        patterns_detected=["User prefers concise answers"],
        improvement_opportunities=[{"area": "Context tracking", "action": "Review history"}],
    )
    data = reflection.to_dict()

    assert data["id"] == "test-id"
    assert data["user_id"] == "user-123"
    assert data["total_interactions"] == 10
    assert len(data["positive_outcomes"]) == 1
    assert len(data["negative_outcomes"]) == 1
    assert "User prefers concise answers" in data["patterns_detected"]


def test_daily_reflection_from_dict() -> None:
    """Test DailyReflection.from_dict creates correct instance."""
    data = {
        "id": "from-dict-id",
        "user_id": "user-456",
        "reflection_date": "2026-02-16T12:00:00+00:00",
        "total_interactions": 5,
        "positive_outcomes": [],
        "negative_outcomes": [],
        "patterns_detected": ["Pattern 1"],
        "improvement_opportunities": [],
        "created_at": "2026-02-16T12:00:00+00:00",
    }

    reflection = DailyReflection.from_dict(data)

    assert reflection.id == "from-dict-id"
    assert reflection.user_id == "user-456"
    assert reflection.total_interactions == 5
    assert len(reflection.patterns_detected) == 1


def test_daily_reflection_defaults() -> None:
    """Test DailyReflection has proper defaults."""
    reflection = DailyReflection(
        id="test",
        user_id="user",
        reflection_date=datetime.now(UTC),
        total_interactions=0,
    )

    assert reflection.positive_outcomes == []
    assert reflection.negative_outcomes == []
    assert reflection.patterns_detected == []
    assert reflection.improvement_opportunities == []


# ── SelfAssessment Tests ──────────────────────────────────────────────────────


def test_self_assessment_to_dict() -> None:
    """Test SelfAssessment.to_dict serializes correctly."""
    assessment = SelfAssessment(
        id="assessment-id",
        user_id="user-123",
        assessment_period="weekly",
        overall_score=0.75,
        strengths=["Clear communication", "Fast response time"],
        weaknesses=["Sometimes misses context"],
        mistakes_acknowledged=[{"mistake": "Wrong data", "learning": "Always verify"}],
        improvement_plan=[{"area": "Context", "priority": 1, "actions": ["Review history"]}],
        trend=Trend.IMPROVING,
    )
    data = assessment.to_dict()

    assert data["id"] == "assessment-id"
    assert data["assessment_period"] == "weekly"
    assert data["overall_score"] == 0.75
    assert data["trend"] == "improving"
    assert len(data["strengths"]) == 2
    assert len(data["weaknesses"]) == 1


def test_self_assessment_from_dict() -> None:
    """Test SelfAssessment.from_dict creates correct instance."""
    data = {
        "id": "from-dict-assessment",
        "user_id": "user-789",
        "assessment_period": "monthly",
        "overall_score": 0.65,
        "strengths": ["Strength 1"],
        "weaknesses": ["Weakness 1"],
        "mistakes_acknowledged": [],
        "improvement_plan": [],
        "trend": "declining",
        "created_at": "2026-02-16T12:00:00+00:00",
    }

    assessment = SelfAssessment.from_dict(data)

    assert assessment.id == "from-dict-assessment"
    assert assessment.assessment_period == "monthly"
    assert assessment.overall_score == 0.65
    assert assessment.trend == Trend.DECLINING


def test_self_assessment_trend_defaults_to_stable() -> None:
    """Test SelfAssessment.from_dict defaults invalid trend to stable."""
    data = {
        "id": "test",
        "user_id": "user",
        "assessment_period": "weekly",
        "overall_score": 0.5,
        "trend": "invalid_trend",
    }

    assessment = SelfAssessment.from_dict(data)
    assert assessment.trend == Trend.STABLE


# ── Pydantic Model Tests ──────────────────────────────────────────────────────


def test_reflect_request_defaults() -> None:
    """Test ReflectRequest has correct default."""
    request = ReflectRequest()
    assert request.period == "daily"


def test_reflect_request_custom_period() -> None:
    """Test ReflectRequest accepts custom period."""
    request = ReflectRequest(period="weekly")
    assert request.period == "weekly"


def test_acknowledge_mistake_request_validation() -> None:
    """Test AcknowledgeMistakeRequest validates min/max length."""
    # Valid
    request = AcknowledgeMistakeRequest(mistake_description="A" * 50)
    assert len(request.mistake_description) == 50

    # Too short should fail
    with pytest.raises(ValueError):
        AcknowledgeMistakeRequest(mistake_description="short")


# ── SelfReflectionService Tests ───────────────────────────────────────────────


class TestSelfReflectionService:
    """Tests for SelfReflectionService."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create mock database client."""
        return MagicMock()

    @pytest.fixture
    def mock_llm(self) -> AsyncMock:
        """Create mock LLM client."""
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db: MagicMock, mock_llm: AsyncMock) -> SelfReflectionService:
        """Create service with mocked dependencies."""
        return SelfReflectionService(
            db_client=mock_db,
            llm_client=mock_llm,
        )

    @pytest.mark.asyncio
    async def test_daily_reflection_with_interactions(
        self,
        service: SelfReflectionService,
        mock_db: MagicMock,
        mock_llm: AsyncMock,
    ) -> None:
        """Test reflection generated from today's data."""
        # Mock database queries
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.side_effect = [
            # Conversations
            MagicMock(data=[{"id": "conv-1", "messages": [{"role": "user", "content": "Hi"}]}]),
            # Feedback
            MagicMock(data=[{"rating": "up"}, {"rating": "up"}, {"rating": "down"}]),
            # Actions
            MagicMock(data=[{"action_type": "email", "status": "completed"}]),
        ]

        # Mock LLM response
        mock_llm.generate_response.return_value = json.dumps(
            {
                "positive_outcomes": [{"description": "Good response", "evidence": "Thumbs up"}],
                "negative_outcomes": [{"description": "Misunderstood", "evidence": "Thumbs down"}],
                "patterns_detected": ["User prefers morning interactions"],
                "improvement_opportunities": [{"area": "Clarification", "action": "Ask follow-up"}],
            }
        )

        # Mock database insert
        mock_db.table.return_value.insert.return_value.execute = MagicMock()

        reflection = await service.run_daily_reflection("test-user")

        assert reflection["user_id"] == "test-user"
        assert reflection["total_interactions"] > 0
        assert len(reflection["positive_outcomes"]) >= 0
        assert len(reflection["patterns_detected"]) >= 0

    @pytest.mark.asyncio
    async def test_daily_reflection_empty_day(
        self,
        service: SelfReflectionService,
        mock_db: MagicMock,
    ) -> None:
        """Test graceful handling of no interactions."""
        # Mock empty database queries
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.side_effect = [
            MagicMock(data=[]),  # Conversations
            MagicMock(data=[]),  # Feedback
            MagicMock(data=[]),  # Actions
        ]

        reflection = await service.run_daily_reflection("test-user")

        assert reflection["total_interactions"] == 0
        assert "No interactions today" in reflection["patterns_detected"]

    @pytest.mark.asyncio
    async def test_self_assessment_generation(
        self,
        service: SelfReflectionService,
        mock_db: MagicMock,
        mock_llm: AsyncMock,
    ) -> None:
        """Test weekly assessment aggregates daily data."""
        # Mock reflections query
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.execute.return_value = MagicMock(
            data=[
                DailyReflection(
                    id="r1",
                    user_id="test-user",
                    reflection_date=datetime.now(UTC),
                    total_interactions=5,
                    positive_outcomes=[{"d": "p1"}],
                    negative_outcomes=[],
                ).to_dict(),
                DailyReflection(
                    id="r2",
                    user_id="test-user",
                    reflection_date=datetime.now(UTC),
                    total_interactions=3,
                    positive_outcomes=[{"d": "p2"}],
                    negative_outcomes=[{"d": "n1"}],
                ).to_dict(),
            ]
        )

        # Mock previous assessment query
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=None
        )

        # Mock LLM response
        mock_llm.generate_response.return_value = json.dumps(
            {
                "strengths": ["Clear communication"],
                "weaknesses": ["Sometimes verbose"],
                "mistakes_acknowledged": [{"mistake": "Late response", "learning": "Prioritize"}],
                "improvement_plan": [
                    {"area": "Time management", "priority": 1, "actions": ["Set timers"]}
                ],
            }
        )

        # Mock database insert
        mock_db.table.return_value.insert.return_value.execute = MagicMock()

        assessment = await service.generate_self_assessment("test-user", period="weekly")

        assert assessment["assessment_period"] == "weekly"
        assert "overall_score" in assessment
        assert assessment["trend"] in ["improving", "stable", "declining"]

    @pytest.mark.asyncio
    async def test_mistake_acknowledgment_no_excuses(
        self,
        service: SelfReflectionService,
        mock_db: MagicMock,
        mock_llm: AsyncMock,
    ) -> None:
        """Test acknowledgment has no 'but' or deflection."""
        # Mock database insert (non-critical)
        mock_db.table.return_value.insert.return_value.execute = MagicMock()

        # Mock LLM response
        mock_llm.generate_response.return_value = (
            "I made a mistake by providing incorrect information. "
            "I should have verified the data before responding. "
            "I will be more careful in the future."
        )

        acknowledgment = await service.acknowledge_mistake(
            user_id="test-user",
            mistake_description="I provided outdated pricing information",
        )

        # Acknowledgment should not contain excuses
        assert "but" not in acknowledgment.lower()
        assert "however" not in acknowledgment.lower()
        # Should use "I" statements
        assert "I" in acknowledgment

    @pytest.mark.asyncio
    async def test_improvement_plan_prioritized(
        self,
        service: SelfReflectionService,
        mock_db: MagicMock,
    ) -> None:
        """Test improvement plan areas are sorted by priority."""
        # Mock latest assessment with list (not single dict)
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[
                SelfAssessment(
                    id="assessment-1",
                    user_id="test-user",
                    assessment_period="weekly",
                    overall_score=0.7,
                    improvement_plan=[
                        {"area": "Low priority", "priority": 5, "actions": ["Action"]},
                        {"area": "High priority", "priority": 1, "actions": ["Action"]},
                        {"area": "Medium priority", "priority": 3, "actions": ["Action"]},
                    ],
                ).to_dict()
            ]
        )

        plan = await service.get_improvement_plan("test-user")

        assert len(plan["areas"]) == 3
        # Should be sorted by priority
        if len(plan["areas"]) > 1:
            priorities = [a.get("priority", 999) for a in plan["areas"]]
            assert priorities == sorted(priorities)

    @pytest.mark.asyncio
    async def test_improvement_plan_no_assessment(
        self,
        service: SelfReflectionService,
        mock_db: MagicMock,
    ) -> None:
        """Test improvement plan returns helpful message when no assessment exists."""
        # Mock no assessment
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=None
        )

        plan = await service.get_improvement_plan("test-user")

        assert plan["areas"] == []
        assert plan["progress_indicators"]["has_assessment"] is False
        assert "No assessment available" in plan["progress_indicators"]["message"]

    @pytest.mark.asyncio
    async def test_trend_detection_improving(
        self,
        service: SelfReflectionService,
        mock_db: MagicMock,
        mock_llm: AsyncMock,
    ) -> None:
        """Test score increase detected as improving."""
        # Set up mock for reflections query - returns a list
        reflections_mock = MagicMock()
        reflections_mock.data = [
            DailyReflection(
                id="r1",
                user_id="test-user",
                reflection_date=datetime.now(UTC),
                total_interactions=10,
                positive_outcomes=[{"d": "p1"}, {"d": "p2"}, {"d": "p3"}],
                negative_outcomes=[{"d": "n1"}],
            ).to_dict(),
        ]

        # Set up mock for previous assessment - returns a single item list
        assessment_mock = MagicMock()
        assessment_mock.data = [
            SelfAssessment(
                id="prev",
                user_id="test-user",
                assessment_period="weekly",
                overall_score=0.5,
            ).to_dict()
        ]

        # Track which query we're on
        query_count = [0]

        def mock_table(table_name: str) -> MagicMock:
            mock = MagicMock()

            def mock_execute() -> MagicMock:
                query_count[0] += 1
                if table_name == "daily_reflections":
                    return reflections_mock
                elif table_name == "companion_self_assessments":
                    return assessment_mock
                return MagicMock(data=None)

            # Build the chain
            mock.select.return_value.eq.return_value.gte.return_value.order.return_value.execute = (
                mock_execute
            )
            mock.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute = mock_execute
            mock.select.return_value.eq.return_value.order.return_value.limit.return_value.execute = mock_execute
            mock.insert.return_value.execute = MagicMock()
            return mock

        mock_db.table = mock_table

        # Mock LLM response
        mock_llm.generate_response.return_value = json.dumps(
            {
                "strengths": [],
                "weaknesses": [],
                "mistakes_acknowledged": [],
                "improvement_plan": [],
            }
        )

        assessment = await service.generate_self_assessment("test-user", period="weekly")

        # Score should be 0.75 (3 positive / 4 total), which is > 0.5 + 0.05
        assert assessment["trend"] == Trend.IMPROVING.value

    @pytest.mark.asyncio
    async def test_trend_detection_declining(
        self,
        service: SelfReflectionService,
        mock_db: MagicMock,
        mock_llm: AsyncMock,
    ) -> None:
        """Test score decrease detected as declining."""
        # Set up mock for reflections query - returns a list
        reflections_mock = MagicMock()
        reflections_mock.data = [
            DailyReflection(
                id="r1",
                user_id="test-user",
                reflection_date=datetime.now(UTC),
                total_interactions=10,
                positive_outcomes=[{"d": "p1"}],
                negative_outcomes=[{"d": "n1"}, {"d": "n2"}, {"d": "n3"}],
            ).to_dict(),
        ]

        # Set up mock for previous assessment - returns a single item list
        assessment_mock = MagicMock()
        assessment_mock.data = [
            SelfAssessment(
                id="prev",
                user_id="test-user",
                assessment_period="weekly",
                overall_score=0.8,
            ).to_dict()
        ]

        def mock_table(table_name: str) -> MagicMock:
            mock = MagicMock()

            def mock_execute() -> MagicMock:
                if table_name == "daily_reflections":
                    return reflections_mock
                elif table_name == "companion_self_assessments":
                    return assessment_mock
                return MagicMock(data=None)

            # Build the chain
            mock.select.return_value.eq.return_value.gte.return_value.order.return_value.execute = (
                mock_execute
            )
            mock.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute = mock_execute
            mock.select.return_value.eq.return_value.order.return_value.limit.return_value.execute = mock_execute
            mock.insert.return_value.execute = MagicMock()
            return mock

        mock_db.table = mock_table

        # Mock LLM response
        mock_llm.generate_response.return_value = json.dumps(
            {
                "strengths": [],
                "weaknesses": [],
                "mistakes_acknowledged": [],
                "improvement_plan": [],
            }
        )

        assessment = await service.generate_self_assessment("test-user", period="weekly")

        # Score should be 0.25 (1 positive / 4 total), which is < 0.8 - 0.05
        assert assessment["trend"] == Trend.DECLINING.value

    @pytest.mark.asyncio
    async def test_trend_detection_stable(
        self,
        service: SelfReflectionService,
        mock_db: MagicMock,
        mock_llm: AsyncMock,
    ) -> None:
        """Test score within threshold detected as stable."""
        # Set up mock for reflections query - returns a list
        reflections_mock = MagicMock()
        reflections_mock.data = [
            DailyReflection(
                id="r1",
                user_id="test-user",
                reflection_date=datetime.now(UTC),
                total_interactions=10,
                positive_outcomes=[{"d": "p1"}, {"d": "p2"}],
                negative_outcomes=[{"d": "n1"}, {"d": "n2"}],
            ).to_dict(),
        ]

        # Set up mock for previous assessment - returns a single item list
        assessment_mock = MagicMock()
        assessment_mock.data = [
            SelfAssessment(
                id="prev",
                user_id="test-user",
                assessment_period="weekly",
                overall_score=0.52,
            ).to_dict()
        ]

        def mock_table(table_name: str) -> MagicMock:
            mock = MagicMock()

            def mock_execute() -> MagicMock:
                if table_name == "daily_reflections":
                    return reflections_mock
                elif table_name == "companion_self_assessments":
                    return assessment_mock
                return MagicMock(data=None)

            # Build the chain
            mock.select.return_value.eq.return_value.gte.return_value.order.return_value.execute = (
                mock_execute
            )
            mock.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute = mock_execute
            mock.select.return_value.eq.return_value.order.return_value.limit.return_value.execute = mock_execute
            mock.insert.return_value.execute = MagicMock()
            return mock

        mock_db.table = mock_table

        # Mock LLM response
        mock_llm.generate_response.return_value = json.dumps(
            {
                "strengths": [],
                "weaknesses": [],
                "mistakes_acknowledged": [],
                "improvement_plan": [],
            }
        )

        assessment = await service.generate_self_assessment("test-user", period="weekly")

        # Score should be 0.5 (2 positive / 4 total), within 0.05 of 0.52
        assert assessment["trend"] == Trend.STABLE.value

    @pytest.mark.asyncio
    async def test_llm_failure_graceful_degradation(
        self,
        service: SelfReflectionService,
        mock_db: MagicMock,
        mock_llm: AsyncMock,
    ) -> None:
        """Test service handles LLM failures gracefully."""
        # Mock database queries with data
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.side_effect = [
            MagicMock(data=[{"id": "c1", "messages": [{"role": "user"}]}]),
            MagicMock(data=[{"rating": "up"}]),
            MagicMock(data=[{"action_type": "email", "status": "completed"}]),
        ]

        # Mock LLM failure
        mock_llm.generate_response.side_effect = Exception("LLM error")

        # Mock database insert
        mock_db.table.return_value.insert.return_value.execute = MagicMock()

        # Should not raise - should create reflection with defaults
        reflection = await service.run_daily_reflection("test-user")

        assert reflection["user_id"] == "test-user"
        assert isinstance(reflection["positive_outcomes"], list)
        assert isinstance(reflection["negative_outcomes"], list)

    @pytest.mark.asyncio
    async def test_acknowledgment_llm_failure_returns_fallback(
        self,
        service: SelfReflectionService,
        mock_llm: AsyncMock,
    ) -> None:
        """Test acknowledgment returns fallback when LLM fails."""
        mock_llm.generate_response.side_effect = Exception("LLM error")

        acknowledgment = await service.acknowledge_mistake(
            user_id="test-user",
            mistake_description="Test mistake",
        )

        assert "mistake" in acknowledgment.lower()
        assert "responsibility" in acknowledgment.lower()

    @pytest.mark.asyncio
    async def test_dataclass_serialization_round_trip(
        self,
    ) -> None:
        """Test to_dict/from_dict round-trip for dataclasses."""
        original_reflection = DailyReflection(
            id="test-id",
            user_id="user-123",
            reflection_date=datetime(2026, 2, 16, 12, 0, 0, tzinfo=UTC),
            total_interactions=5,
            positive_outcomes=[{"d": "p"}],
            negative_outcomes=[{"d": "n"}],
            patterns_detected=["Pattern"],
            improvement_opportunities=[{"area": "A", "action": "B"}],
        )

        data = original_reflection.to_dict()
        restored = DailyReflection.from_dict(data)

        assert restored.id == original_reflection.id
        assert restored.user_id == original_reflection.user_id
        assert restored.total_interactions == original_reflection.total_interactions
        assert len(restored.positive_outcomes) == len(original_reflection.positive_outcomes)

        original_assessment = SelfAssessment(
            id="assessment-id",
            user_id="user-123",
            assessment_period="weekly",
            overall_score=0.75,
            strengths=["S1", "S2"],
            weaknesses=["W1"],
            mistakes_acknowledged=[{"m": "M1", "l": "L1"}],
            improvement_plan=[{"area": "A", "priority": 1, "actions": ["Act"]}],
            trend=Trend.IMPROVING,
        )

        data = original_assessment.to_dict()
        restored = SelfAssessment.from_dict(data)

        assert restored.id == original_assessment.id
        assert restored.overall_score == original_assessment.overall_score
        assert restored.trend == original_assessment.trend
        assert len(restored.strengths) == len(original_assessment.strengths)
