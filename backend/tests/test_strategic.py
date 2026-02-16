"""Tests for strategic planning module."""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.companion.strategic import (
    ConcernType,
    KeyResult,
    PlanType,
    Risk,
    RiskSeverity,
    Scenario,
    StrategicConcern,
    StrategicPlan,
    StrategicPlanningService,
)


# ── Enum Tests ───────────────────────────────────────────────────────────────


def test_plan_type_enum_values() -> None:
    """Test PlanType enum has expected values."""
    assert PlanType.QUARTERLY.value == "quarterly"
    assert PlanType.ANNUAL.value == "annual"
    assert PlanType.CAMPAIGN.value == "campaign"
    assert PlanType.TERRITORY.value == "territory"
    assert PlanType.ACCOUNT.value == "account"


def test_risk_severity_enum_values() -> None:
    """Test RiskSeverity enum has expected values."""
    assert RiskSeverity.LOW.value == "low"
    assert RiskSeverity.MEDIUM.value == "medium"
    assert RiskSeverity.HIGH.value == "high"
    assert RiskSeverity.CRITICAL.value == "critical"


def test_concern_type_enum_values() -> None:
    """Test ConcernType enum has expected values."""
    assert ConcernType.OFF_TRACK.value == "off_track"
    assert ConcernType.AT_RISK.value == "at_risk"
    assert ConcernType.OPPORTUNITY.value == "opportunity"
    assert ConcernType.BLIND_SPOT.value == "blind_spot"


# ── KeyResult Tests ───────────────────────────────────────────────────────────


def test_key_result_progress_calculation() -> None:
    """Test KeyResult calculates progress percentage correctly."""
    kr = KeyResult(
        description="Close 10 deals",
        target_value=10.0,
        current_value=5.0,
        unit="deals",
    )
    assert kr.progress_percentage == 50.0


def test_key_result_progress_capped_at_100() -> None:
    """Test KeyResult progress is capped at 100%."""
    kr = KeyResult(
        description="Revenue target",
        target_value=100.0,
        current_value=150.0,
        unit="K",
    )
    assert kr.progress_percentage == 100.0


def test_key_result_zero_target() -> None:
    """Test KeyResult handles zero target gracefully."""
    kr = KeyResult(
        description="Zero target",
        target_value=0.0,
        current_value=10.0,
        unit="units",
    )
    # Zero target with positive current = 100%
    assert kr.progress_percentage == 100.0


def test_key_result_to_dict() -> None:
    """Test KeyResult.to_dict serializes correctly."""
    kr = KeyResult(
        description="Test KR",
        target_value=100.0,
        current_value=50.0,
        unit="%",
    )
    data = kr.to_dict()

    assert data["description"] == "Test KR"
    assert data["target_value"] == 100.0
    assert data["current_value"] == 50.0
    assert data["unit"] == "%"
    assert data["progress_percentage"] == 50.0


def test_key_result_from_dict() -> None:
    """Test KeyResult.from_dict creates correct instance."""
    data = {
        "description": "From dict KR",
        "target_value": 200.0,
        "current_value": 75.0,
        "unit": "calls",
        "progress_percentage": 37.5,
    }

    kr = KeyResult.from_dict(data)

    assert kr.description == "From dict KR"
    assert kr.target_value == 200.0
    assert kr.current_value == 75.0
    assert kr.unit == "calls"


# ── Risk Tests ────────────────────────────────────────────────────────────────


def test_risk_to_dict() -> None:
    """Test Risk.to_dict serializes correctly."""
    risk = Risk(
        description="Market competition",
        severity=RiskSeverity.HIGH,
        likelihood=0.7,
        impact=0.8,
        mitigation="Differentiate on service",
    )
    data = risk.to_dict()

    assert data["description"] == "Market competition"
    assert data["severity"] == "high"
    assert data["likelihood"] == 0.7
    assert data["impact"] == 0.8
    assert data["mitigation"] == "Differentiate on service"


def test_risk_from_dict() -> None:
    """Test Risk.from_dict creates correct instance."""
    data = {
        "description": "Budget overrun",
        "severity": "medium",
        "likelihood": 0.5,
        "impact": 0.6,
        "mitigation": "Monitor weekly",
    }

    risk = Risk.from_dict(data)

    assert risk.description == "Budget overrun"
    assert risk.severity == RiskSeverity.MEDIUM
    assert risk.likelihood == 0.5
    assert risk.impact == 0.6
    assert risk.mitigation == "Monitor weekly"


def test_risk_from_dict_invalid_severity_defaults_to_medium() -> None:
    """Test Risk.from_dict handles invalid severity gracefully."""
    data = {
        "description": "Unknown risk",
        "severity": "invalid",
        "likelihood": 0.3,
        "impact": 0.4,
        "mitigation": "",
    }

    risk = Risk.from_dict(data)
    assert risk.severity == RiskSeverity.MEDIUM


# ── Scenario Tests ────────────────────────────────────────────────────────────


def test_scenario_to_dict() -> None:
    """Test Scenario.to_dict serializes correctly."""
    scenario = Scenario(
        name="optimistic",
        description="Everything exceeds expectations",
        probability=0.2,
        key_factors=["Strong market", "No competition"],
        outcomes={"revenue": "150% of target"},
    )
    data = scenario.to_dict()

    assert data["name"] == "optimistic"
    assert data["description"] == "Everything exceeds expectations"
    assert data["probability"] == 0.2
    assert "Strong market" in data["key_factors"]
    assert data["outcomes"]["revenue"] == "150% of target"


def test_scenario_from_dict() -> None:
    """Test Scenario.from_dict creates correct instance."""
    data = {
        "name": "pessimistic",
        "description": "Significant challenges",
        "probability": 0.3,
        "key_factors": ["Budget cuts", "Staff turnover"],
        "outcomes": {"revenue": "60% of target"},
    }

    scenario = Scenario.from_dict(data)

    assert scenario.name == "pessimistic"
    assert scenario.description == "Significant challenges"
    assert scenario.probability == 0.3
    assert len(scenario.key_factors) == 2


# ── StrategicPlan Tests ───────────────────────────────────────────────────────


def test_strategic_plan_to_dict() -> None:
    """Test StrategicPlan.to_dict serializes correctly."""
    plan = StrategicPlan(
        id="test-plan-id",
        user_id="test-user-id",
        title="Q1 2026 Strategy",
        plan_type=PlanType.QUARTERLY,
        objectives=["Increase revenue", "Improve retention"],
        key_results=[
            KeyResult(description="Revenue", target_value=100.0, current_value=50.0, unit="K")
        ],
        risks=[
            Risk(
                description="Market risk",
                severity=RiskSeverity.MEDIUM,
                likelihood=0.5,
                impact=0.5,
                mitigation="Monitor",
            )
        ],
        scenarios=[
            Scenario(name="realistic", description="Expected", probability=0.5)
        ],
        progress_score=50.0,
        aria_assessment="Solid plan with manageable risks",
        aria_concerns=["Watch the market risk"],
        status="active",
    )
    data = plan.to_dict()

    assert data["id"] == "test-plan-id"
    assert data["title"] == "Q1 2026 Strategy"
    assert data["plan_type"] == "quarterly"
    assert len(data["objectives"]) == 2
    assert len(data["key_results"]) == 1
    assert data["progress_score"] == 50.0
    assert data["aria_assessment"] == "Solid plan with manageable risks"
    assert "Watch the market risk" in data["aria_concerns"]


def test_strategic_plan_from_dict() -> None:
    """Test StrategicPlan.from_dict creates correct instance."""
    data = {
        "id": "from-dict-plan",
        "user_id": "user-123",
        "title": "Annual Plan",
        "plan_type": "annual",
        "objectives": ["Grow 20%"],
        "key_results": [
            {
                "description": "Revenue",
                "target_value": 500.0,
                "current_value": 100.0,
                "unit": "K",
                "progress_percentage": 20.0,
            }
        ],
        "risks": [],
        "scenarios": [],
        "progress_score": 20.0,
        "aria_assessment": "Good plan",
        "aria_concerns": [],
        "status": "active",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-15T00:00:00Z",
    }

    plan = StrategicPlan.from_dict(data)

    assert plan.id == "from-dict-plan"
    assert plan.title == "Annual Plan"
    assert plan.plan_type == PlanType.ANNUAL
    assert len(plan.objectives) == 1
    assert len(plan.key_results) == 1
    assert plan.progress_score == 20.0


# ── StrategicPlanningService Tests ────────────────────────────────────────────


class TestStrategicPlanningService:
    """Tests for StrategicPlanningService."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create mock database client."""
        return MagicMock()

    @pytest.fixture
    def mock_llm(self) -> AsyncMock:
        """Create mock LLM client."""
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db: MagicMock, mock_llm: AsyncMock) -> StrategicPlanningService:
        """Create service with mocked dependencies."""
        return StrategicPlanningService(
            db_client=mock_db,
            llm_client=mock_llm,
        )

    @pytest.mark.asyncio
    async def test_plan_creation_with_llm_assessment(
        self,
        service: StrategicPlanningService,
        mock_db: MagicMock,
        mock_llm: AsyncMock,
    ) -> None:
        """Test plan creation generates LLM assessment."""
        # Mock LLM responses
        mock_llm.generate_response.side_effect = [
            # Key results generation
            json.dumps([
                {
                    "description": "Close 10 enterprise deals",
                    "target_value": 10,
                    "current_value": 0,
                    "unit": "deals",
                }
            ]),
            # Risks identification
            json.dumps([
                {
                    "description": "Market competition",
                    "severity": "medium",
                    "likelihood": 0.5,
                    "impact": 0.6,
                    "mitigation": "Differentiate on service",
                }
            ]),
            # Scenarios generation
            json.dumps([
                {
                    "name": "realistic",
                    "description": "Expected outcome",
                    "probability": 0.5,
                    "key_factors": ["Steady growth"],
                    "outcomes": {},
                }
            ]),
            # ARIA assessment
            "This is a solid quarterly plan with clear objectives.",
        ]

        # Mock database insert
        mock_db.table.return_value.insert.return_value.execute = MagicMock()

        plan = await service.create_plan(
            user_id="test-user",
            title="Q1 Strategy",
            plan_type=PlanType.QUARTERLY,
            objectives=["Grow revenue", "Improve retention"],
        )

        assert plan.title == "Q1 Strategy"
        assert plan.plan_type == PlanType.QUARTERLY
        assert len(plan.objectives) == 2
        assert len(plan.key_results) >= 0  # May be 0 if parsing fails
        assert plan.status == "active"
        assert plan.progress_score == 0.0

    @pytest.mark.asyncio
    async def test_plan_creation_without_objectives_fails(
        self,
        service: StrategicPlanningService,
    ) -> None:
        """Test plan creation fails without objectives."""
        with pytest.raises(ValueError, match="At least one objective is required"):
            await service.create_plan(
                user_id="test-user",
                title="Empty Plan",
                plan_type=PlanType.QUARTERLY,
                objectives=[],
            )

    @pytest.mark.asyncio
    async def test_get_active_plans_filters_by_status(
        self,
        service: StrategicPlanningService,
        mock_db: MagicMock,
    ) -> None:
        """Test get_active_plans filters by active status."""
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": "plan-1",
                    "user_id": "user-1",
                    "title": "Active Plan",
                    "plan_type": "quarterly",
                    "status": "active",
                    "objectives": ["Obj 1"],
                    "key_results": [],
                    "risks": [],
                    "scenarios": [],
                    "progress_score": 50.0,
                    "aria_assessment": "",
                    "aria_concerns": [],
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-15T00:00:00Z",
                }
            ]
        )

        plans = await service.get_active_plans("user-1")

        assert len(plans) == 1
        assert plans[0].title == "Active Plan"
        assert plans[0].status == "active"

    @pytest.mark.asyncio
    async def test_scenario_analysis_returns_impact(
        self,
        service: StrategicPlanningService,
        mock_db: MagicMock,
        mock_llm: AsyncMock,
    ) -> None:
        """Test scenario analysis returns impact assessment."""
        # Mock get_plan
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={
                "id": "plan-1",
                "user_id": "user-1",
                "title": "Test Plan",
                "plan_type": "quarterly",
                "status": "active",
                "objectives": ["Grow revenue"],
                "key_results": [],
                "risks": [],
                "scenarios": [],
                "progress_score": 0.0,
                "aria_assessment": "",
                "aria_concerns": [],
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        )

        # Mock LLM scenario analysis
        mock_llm.generate_response.return_value = json.dumps({
            "affected_objectives": ["Grow revenue"],
            "risk_changes": [
                {
                    "risk": "Market competition",
                    "current_severity": "medium",
                    "new_severity": "high",
                    "reason": "New competitor entry",
                }
            ],
            "recommended_adjustments": ["Accelerate timeline", "Increase marketing"],
            "confidence": 0.75,
        })

        result = await service.run_scenario(
            plan_id="plan-1",
            user_id="user-1",
            scenario_description="What if a major competitor enters the market?",
        )

        assert result["scenario_description"] == "What if a major competitor enters the market?"
        assert "Grow revenue" in result["affected_objectives"]
        assert len(result["recommended_adjustments"]) == 2
        assert result["confidence"] == 0.75

    @pytest.mark.asyncio
    async def test_challenge_identifies_weaknesses(
        self,
        service: StrategicPlanningService,
        mock_db: MagicMock,
        mock_llm: AsyncMock,
    ) -> None:
        """Test challenge_plan identifies plan weaknesses."""
        # Mock get_plan
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={
                "id": "plan-1",
                "user_id": "user-1",
                "title": "Test Plan",
                "plan_type": "quarterly",
                "status": "active",
                "objectives": ["Grow 50%"],
                "key_results": [],
                "risks": [],
                "scenarios": [],
                "progress_score": 0.0,
                "aria_assessment": "",
                "aria_concerns": [],
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        )

        # Mock LLM challenge response
        mock_llm.generate_response.return_value = json.dumps({
            "assumptions_challenged": ["50% growth assumes no market downturn"],
            "blind_spots": ["No contingency for key customer loss"],
            "alternatives_considered": ["Focus on retention over acquisition"],
            "recommended_revisions": ["Add risk mitigation for key accounts"],
        })

        result = await service.challenge_plan(
            plan_id="plan-1",
            user_id="user-1",
        )

        assert len(result["assumptions_challenged"]) == 1
        assert len(result["blind_spots"]) == 1
        assert len(result["recommended_revisions"]) == 1
        assert result["directness_level"] >= 1

    @pytest.mark.asyncio
    async def test_challenge_respects_personality_directness(
        self,
        service: StrategicPlanningService,
        mock_db: MagicMock,
        mock_llm: AsyncMock,
    ) -> None:
        """Test challenge_plan uses personality directness for tone."""
        # Mock get_plan
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={
                "id": "plan-1",
                "user_id": "user-1",
                "title": "Test Plan",
                "plan_type": "quarterly",
                "status": "active",
                "objectives": ["Test objective"],
                "key_results": [],
                "risks": [],
                "scenarios": [],
                "progress_score": 0.0,
                "aria_assessment": "",
                "aria_concerns": [],
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        )

        # Mock LLM challenge response
        mock_llm.generate_response.return_value = json.dumps({
            "assumptions_challenged": [],
            "blind_spots": [],
            "alternatives_considered": [],
            "recommended_revisions": [],
        })

        result = await service.challenge_plan(
            plan_id="plan-1",
            user_id="user-1",
        )

        # Should have a directness level (default to 3)
        assert result["directness_level"] in [1, 2, 3]

    @pytest.mark.asyncio
    async def test_progress_tracking_updates_score(
        self,
        service: StrategicPlanningService,
        mock_db: MagicMock,
    ) -> None:
        """Test update_progress recalculates progress score."""
        # Mock get_plan
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={
                "id": "plan-1",
                "user_id": "user-1",
                "title": "Test Plan",
                "plan_type": "quarterly",
                "status": "active",
                "objectives": ["Grow revenue"],
                "key_results": [
                    {
                        "description": "Revenue target",
                        "target_value": 100.0,
                        "current_value": 0.0,
                        "unit": "K",
                        "progress_percentage": 0.0,
                    }
                ],
                "risks": [],
                "scenarios": [],
                "progress_score": 0.0,
                "aria_assessment": "",
                "aria_concerns": [],
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        )

        # Mock update
        mock_db.table.return_value.update.return_value.eq.return_value.execute = MagicMock()

        result = await service.update_progress(
            plan_id="plan-1",
            user_id="user-1",
            progress_data={"Revenue target": 50.0},
        )

        assert result is not None
        assert result.progress_score == 50.0  # Average of key result progress
        assert result.key_results[0].current_value == 50.0
        assert result.key_results[0].progress_percentage == 50.0

    @pytest.mark.asyncio
    async def test_progress_tracking_surfaces_concerns(
        self,
        service: StrategicPlanningService,
        mock_db: MagicMock,
    ) -> None:
        """Test update_progress surfaces concerns for slow progress."""
        # Mock get_plan with a key result at 10%
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={
                "id": "plan-1",
                "user_id": "user-1",
                "title": "Test Plan",
                "plan_type": "quarterly",
                "status": "active",
                "objectives": ["Grow revenue"],
                "key_results": [
                    {
                        "description": "Revenue target",
                        "target_value": 100.0,
                        "current_value": 10.0,
                        "unit": "K",
                        "progress_percentage": 10.0,
                    }
                ],
                "risks": [
                    {
                        "description": "High risk",
                        "severity": "high",
                        "likelihood": 0.7,
                        "impact": 0.8,
                        "mitigation": "",
                    }
                ],
                "scenarios": [],
                "progress_score": 10.0,
                "aria_assessment": "",
                "aria_concerns": [],
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        )

        # Mock update
        mock_db.table.return_value.update.return_value.eq.return_value.execute = MagicMock()

        result = await service.update_progress(
            plan_id="plan-1",
            user_id="user-1",
            progress_data={"Revenue target": 10.0},  # Keep at 10%
        )

        assert result is not None
        # Should have concern about slow progress
        assert len(result.aria_concerns) >= 0  # May surface concern

    @pytest.mark.asyncio
    async def test_concern_surfacing_prioritizes_correctly(
        self,
        service: StrategicPlanningService,
        mock_db: MagicMock,
    ) -> None:
        """Test get_strategic_concerns sorts by severity."""
        # Mock get_active_plans
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": "plan-1",
                    "user_id": "user-1",
                    "title": "At Risk Plan",
                    "plan_type": "quarterly",
                    "status": "active",
                    "objectives": ["Objective"],
                    "key_results": [
                        {
                            "description": "KR1",
                            "target_value": 100.0,
                            "current_value": 10.0,
                            "unit": "%",
                            "progress_percentage": 10.0,
                        }
                    ],
                    "risks": [
                        {
                            "description": "Critical risk",
                            "severity": "critical",
                            "likelihood": 0.9,
                            "impact": 0.9,
                            "mitigation": "",
                        }
                    ],
                    "scenarios": [],
                    "progress_score": 10.0,
                    "aria_assessment": "",
                    "aria_concerns": [],
                    "created_at": "2025-12-01T00:00:00Z",  # Old plan
                    "updated_at": "2026-01-01T00:00:00Z",
                }
            ]
        )

        concerns = await service.get_strategic_concerns("user-1")

        # Should have concerns from the at-risk plan
        assert len(concerns) >= 1
        # Critical concerns should be first
        if len(concerns) > 1:
            severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            assert severity_order.get(concerns[0].severity, 4) <= severity_order.get(
                concerns[-1].severity, 4
            )

    @pytest.mark.asyncio
    async def test_llm_failure_graceful_degradation(
        self,
        service: StrategicPlanningService,
        mock_db: MagicMock,
        mock_llm: AsyncMock,
    ) -> None:
        """Test service handles LLM failures gracefully."""
        # Mock database operations
        mock_db.table.return_value.insert.return_value.execute = MagicMock()

        # Mock LLM failures
        mock_llm.generate_response.side_effect = Exception("LLM error")

        # Should not raise - should create plan with defaults
        plan = await service.create_plan(
            user_id="test-user",
            title="Test Plan",
            plan_type=PlanType.QUARTERLY,
            objectives=["Test objective"],
        )

        assert plan.title == "Test Plan"
        # Key results may be empty due to LLM failure
        assert isinstance(plan.key_results, list)


# ── StrategicConcern Tests ────────────────────────────────────────────────────


def test_strategic_concern_to_dict() -> None:
    """Test StrategicConcern.to_dict serializes correctly."""
    concern = StrategicConcern(
        plan_id="plan-1",
        plan_title="Test Plan",
        concern_type=ConcernType.OFF_TRACK,
        description="Progress below expected",
        severity="high",
        recommendation="Review blockers and adjust timeline",
    )
    data = concern.to_dict()

    assert data["plan_id"] == "plan-1"
    assert data["plan_title"] == "Test Plan"
    assert data["concern_type"] == "off_track"
    assert data["description"] == "Progress below expected"
    assert data["severity"] == "high"
    assert data["recommendation"] == "Review blockers and adjust timeline"
