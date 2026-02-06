"""Tests for the onboarding readiness score service (US-913)."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.onboarding.readiness import (
    WEIGHTS,
    OnboardingReadinessService,
    ReadinessBreakdown,
)

# --- Fixtures ---


def _make_db_row(
    user_id: str = "user-123",
    readiness_scores: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Build a mock onboarding_state DB row."""
    return {
        "id": "state-abc",
        "user_id": user_id,
        "current_step": "company_discovery",
        "step_data": {},
        "completed_steps": [],
        "skipped_steps": [],
        "started_at": "2026-02-06T00:00:00+00:00",
        "updated_at": "2026-02-06T00:00:00+00:00",
        "completed_at": None,
        "readiness_scores": readiness_scores
        or {
            "corporate_memory": 0,
            "digital_twin": 0,
            "relationship_graph": 0,
            "integrations": 0,
            "goal_clarity": 0,
        },
        "metadata": {},
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
    chain.in_.return_value = chain
    chain.maybe_single.return_value = chain
    chain.single.return_value = chain
    chain.execute.return_value = _mock_execute(execute_return)
    return chain


@pytest.fixture()
def mock_db() -> MagicMock:
    """Create a mock Supabase client."""
    client = MagicMock()
    return client


@pytest.fixture()
def service(mock_db: MagicMock) -> OnboardingReadinessService:
    """Create an OnboardingReadinessService with mocked DB."""
    with patch("src.onboarding.readiness.SupabaseClient") as mock_cls:
        mock_cls.get_client.return_value = mock_db
        return OnboardingReadinessService()


# --- Weight constants ---


def test_weights_sum_to_one() -> None:
    """Readiness score weights must sum to 1.0."""
    total = sum(WEIGHTS.values())
    assert total == pytest.approx(1.0, abs=0.01)


def test_weights_have_expected_keys() -> None:
    """Weights dictionary has all five expected domains."""
    expected_keys = {
        "corporate_memory",
        "digital_twin",
        "relationship_graph",
        "integrations",
        "goal_clarity",
    }
    assert set(WEIGHTS.keys()) == expected_keys


# --- get_readiness ---


@pytest.mark.asyncio()
async def test_get_readiness_returns_current_scores(
    service: OnboardingReadinessService,
    mock_db: MagicMock,
) -> None:
    """get_readiness returns stored scores with calculated overall and modifier."""
    row = _make_db_row(
        readiness_scores={
            "corporate_memory": 80.0,
            "digital_twin": 60.0,
            "relationship_graph": 40.0,
            "integrations": 20.0,
            "goal_clarity": 0.0,
        }
    )
    select_chain = _build_chain(row)
    mock_db.table.return_value = select_chain

    result = await service.get_readiness("user-123")

    # Overall = 80*0.25 + 60*0.25 + 40*0.20 + 20*0.15 + 0*0.15 = 20 + 15 + 8 + 3 + 0 = 46
    assert result.corporate_memory == 80.0
    assert result.digital_twin == 60.0
    assert result.relationship_graph == 40.0
    assert result.integrations == 20.0
    assert result.goal_clarity == 0.0
    assert result.overall == pytest.approx(46.0, abs=0.1)
    assert result.confidence_modifier == "moderate"  # 30-59


@pytest.mark.asyncio()
async def test_get_readiness_confidence_low(
    service: OnboardingReadinessService,
    mock_db: MagicMock,
) -> None:
    """Overall < 30 maps to 'low' confidence modifier."""
    row = _make_db_row(
        readiness_scores={
            "corporate_memory": 10.0,
            "digital_twin": 10.0,
            "relationship_graph": 10.0,
            "integrations": 10.0,
            "goal_clarity": 10.0,
        }
    )
    select_chain = _build_chain(row)
    mock_db.table.return_value = select_chain

    result = await service.get_readiness("user-123")

    assert result.overall == 10.0
    assert result.confidence_modifier == "low"


@pytest.mark.asyncio()
async def test_get_readiness_confidence_moderate(
    service: OnboardingReadinessService,
    mock_db: MagicMock,
) -> None:
    """Overall 30-59 maps to 'moderate' confidence modifier."""
    row = _make_db_row(
        readiness_scores={
            "corporate_memory": 50.0,
            "digital_twin": 50.0,
            "relationship_graph": 50.0,
            "integrations": 50.0,
            "goal_clarity": 50.0,
        }
    )
    select_chain = _build_chain(row)
    mock_db.table.return_value = select_chain

    result = await service.get_readiness("user-123")

    assert result.overall == 50.0
    assert result.confidence_modifier == "moderate"


@pytest.mark.asyncio()
async def test_get_readiness_confidence_high(
    service: OnboardingReadinessService,
    mock_db: MagicMock,
) -> None:
    """Overall 60-79 maps to 'high' confidence modifier."""
    row = _make_db_row(
        readiness_scores={
            "corporate_memory": 70.0,
            "digital_twin": 70.0,
            "relationship_graph": 70.0,
            "integrations": 70.0,
            "goal_clarity": 70.0,
        }
    )
    select_chain = _build_chain(row)
    mock_db.table.return_value = select_chain

    result = await service.get_readiness("user-123")

    assert result.overall == 70.0
    assert result.confidence_modifier == "high"


@pytest.mark.asyncio()
async def test_get_readiness_confidence_very_high(
    service: OnboardingReadinessService,
    mock_db: MagicMock,
) -> None:
    """Overall 80+ maps to 'very_high' confidence modifier."""
    row = _make_db_row(
        readiness_scores={
            "corporate_memory": 90.0,
            "digital_twin": 90.0,
            "relationship_graph": 90.0,
            "integrations": 90.0,
            "goal_clarity": 90.0,
        }
    )
    select_chain = _build_chain(row)
    mock_db.table.return_value = select_chain

    result = await service.get_readiness("user-123")

    assert result.overall == 90.0
    assert result.confidence_modifier == "very_high"


@pytest.mark.asyncio()
async def test_get_readiness_boundary_30_is_moderate(
    service: OnboardingReadinessService,
    mock_db: MagicMock,
) -> None:
    """Overall exactly 30 maps to 'moderate' (not 'low')."""
    row = _make_db_row(
        readiness_scores={
            "corporate_memory": 30.0,
            "digital_twin": 30.0,
            "relationship_graph": 30.0,
            "integrations": 30.0,
            "goal_clarity": 30.0,
        }
    )
    select_chain = _build_chain(row)
    mock_db.table.return_value = select_chain

    result = await service.get_readiness("user-123")

    assert result.overall == 30.0
    assert result.confidence_modifier == "moderate"


@pytest.mark.asyncio()
async def test_get_readiness_boundary_60_is_high(
    service: OnboardingReadinessService,
    mock_db: MagicMock,
) -> None:
    """Overall exactly 60 maps to 'high' (not 'moderate')."""
    row = _make_db_row(
        readiness_scores={
            "corporate_memory": 60.0,
            "digital_twin": 60.0,
            "relationship_graph": 60.0,
            "integrations": 60.0,
            "goal_clarity": 60.0,
        }
    )
    select_chain = _build_chain(row)
    mock_db.table.return_value = select_chain

    result = await service.get_readiness("user-123")

    assert result.overall == 60.0
    assert result.confidence_modifier == "high"


@pytest.mark.asyncio()
async def test_get_readiness_boundary_80_is_very_high(
    service: OnboardingReadinessService,
    mock_db: MagicMock,
) -> None:
    """Overall exactly 80 maps to 'very_high' (not 'high')."""
    row = _make_db_row(
        readiness_scores={
            "corporate_memory": 80.0,
            "digital_twin": 80.0,
            "relationship_graph": 80.0,
            "integrations": 80.0,
            "goal_clarity": 80.0,
        }
    )
    select_chain = _build_chain(row)
    mock_db.table.return_value = select_chain

    result = await service.get_readiness("user-123")

    assert result.overall == 80.0
    assert result.confidence_modifier == "very_high"


@pytest.mark.asyncio()
async def test_get_readiness_no_state_returns_zeros(
    service: OnboardingReadinessService,
    mock_db: MagicMock,
) -> None:
    """No onboarding state returns all zeros with 'low' confidence."""
    select_chain = _build_chain(None)
    mock_db.table.return_value = select_chain

    result = await service.get_readiness("user-123")

    assert result.corporate_memory == 0.0
    assert result.digital_twin == 0.0
    assert result.relationship_graph == 0.0
    assert result.integrations == 0.0
    assert result.goal_clarity == 0.0
    assert result.overall == 0.0
    assert result.confidence_modifier == "low"


# --- recalculate ---


@pytest.mark.asyncio()
async def test_recalculate_queries_actual_data(
    service: OnboardingReadinessService,
    mock_db: MagicMock,
) -> None:
    """recalculate queries actual data state rather than incremental updates."""
    # Mock state
    state_row = _make_db_row()
    state_chain = _build_chain(state_row)

    # Update chain (the second table() call after state query)
    updated_row = _make_db_row(
        readiness_scores={
            "corporate_memory": 50.0,
            "digital_twin": 50.0,
            "relationship_graph": 50.0,
            "integrations": 50.0,
            "goal_clarity": 50.0,
        }
    )
    update_chain = _build_chain([updated_row])

    # Only two table() calls: state query and update
    mock_db.table.side_effect = [state_chain, update_chain]

    with (
        patch.object(service, "_calculate_corporate_memory", return_value=50.0),
        patch.object(service, "_calculate_digital_twin", return_value=50.0),
        patch.object(service, "_calculate_relationship_graph", return_value=50.0),
        patch.object(service, "_calculate_integrations", return_value=50.0),
        patch.object(service, "_calculate_goal_clarity", return_value=50.0),
    ):
        await service.recalculate("user-123")

    # Should update the database with new scores
    update_chain.update.assert_called_once()
    update_chain.eq.assert_called_once_with("user_id", "user-123")


@pytest.mark.asyncio()
async def test_recalculate_returns_updated_scores(
    service: OnboardingReadinessService,
    mock_db: MagicMock,
) -> None:
    """recalculate returns the newly calculated scores."""
    state_row = _make_db_row()
    state_chain = _build_chain(state_row)

    # Mock queries to return data
    mock_db.table.side_effect = [
        state_chain,
        _build_chain({"count": 100}),
        _build_chain({"count": 10}),
        _build_chain({"count": 50}),
        _build_chain([{"provider": "google"}]),
        _build_chain([{"id": "goal-1"}, {"id": "goal-2"}]),
        _build_chain(
            [
                _make_db_row(
                    readiness_scores={
                        "corporate_memory": 85.0,
                        "digital_twin": 75.0,
                        "relationship_graph": 80.0,
                        "integrations": 60.0,
                        "goal_clarity": 70.0,
                    }
                )
            ]
        ),
    ]

    with (
        patch.object(service, "_calculate_corporate_memory", return_value=85.0),
        patch.object(service, "_calculate_digital_twin", return_value=75.0),
        patch.object(service, "_calculate_relationship_graph", return_value=80.0),
        patch.object(service, "_calculate_integrations", return_value=60.0),
        patch.object(service, "_calculate_goal_clarity", return_value=70.0),
    ):
        result = await service.recalculate("user-123")

    assert result.corporate_memory == 85.0
    assert result.digital_twin == 75.0
    assert result.relationship_graph == 80.0
    assert result.integrations == 60.0
    assert result.goal_clarity == 70.0
    # Overall = 85*0.25 + 75*0.25 + 80*0.20 + 60*0.15 + 70*0.15 = 21.25 + 18.75 + 16 + 9 + 10.5 = 75.5
    assert result.overall == pytest.approx(75.5, abs=0.1)
    assert result.confidence_modifier == "high"


@pytest.mark.asyncio()
async def test_recalculate_clamps_scores_to_0_100(
    service: OnboardingReadinessService,
    mock_db: MagicMock,
) -> None:
    """Recalculated scores are clamped to 0-100 range."""
    state_row = _make_db_row()
    state_chain = _build_chain(state_row)

    mock_db.table.side_effect = [
        state_chain,
        _build_chain({"count": 0}),
        _build_chain({"count": 0}),
        _build_chain({"count": 0}),
        _build_chain([]),
        _build_chain([]),
        _build_chain(
            [
                _make_db_row(
                    readiness_scores={
                        "corporate_memory": 0.0,
                        "digital_twin": 0.0,
                        "relationship_graph": 0.0,
                        "integrations": 0.0,
                        "goal_clarity": 0.0,
                    }
                )
            ]
        ),
    ]

    with (
        patch.object(service, "_calculate_corporate_memory", return_value=-10.0),
        patch.object(service, "_calculate_digital_twin", return_value=150.0),
        patch.object(service, "_calculate_relationship_graph", return_value=50.0),
        patch.object(service, "_calculate_integrations", return_value=50.0),
        patch.object(service, "_calculate_goal_clarity", return_value=50.0),
    ):
        result = await service.recalculate("user-123")

    # Should be clamped to 0-100
    assert result.corporate_memory == 0.0
    assert result.digital_twin == 100.0


# --- ReadinessBreakdown model ---


def test_readiness_breakdown_model() -> None:
    """ReadinessBreakdown Pydantic model works correctly."""
    breakdown = ReadinessBreakdown(
        corporate_memory=80.0,
        digital_twin=60.0,
        relationship_graph=40.0,
        integrations=20.0,
        goal_clarity=0.0,
        overall=46.0,
        confidence_modifier="moderate",
    )

    assert breakdown.corporate_memory == 80.0
    assert breakdown.confidence_modifier == "moderate"

    # Test model_dump
    data = breakdown.model_dump()
    assert "overall" in data
    assert "confidence_modifier" in data


def test_readiness_breakdown_default_values() -> None:
    """ReadinessBreakdown has sensible defaults."""
    breakdown = ReadinessBreakdown()

    assert breakdown.corporate_memory == 0.0
    assert breakdown.digital_twin == 0.0
    assert breakdown.relationship_graph == 0.0
    assert breakdown.integrations == 0.0
    assert breakdown.goal_clarity == 0.0
    assert breakdown.overall == 0.0
    assert breakdown.confidence_modifier == "low"


# --- Real calculation tests ---


class TestCorporateMemoryCalculation:
    """Tests for real corporate memory score calculation."""

    @pytest.mark.asyncio()
    async def test_no_company_returns_zero(
        self, service: OnboardingReadinessService, mock_db: MagicMock
    ) -> None:
        """No company linked -> 0 score."""
        chain = _build_chain(None)
        mock_db.table.return_value = chain
        score = await service._calculate_corporate_memory("user-123")
        assert score == 0.0

    @pytest.mark.asyncio()
    async def test_no_facts_no_docs_returns_zero(
        self, service: OnboardingReadinessService, mock_db: MagicMock
    ) -> None:
        """Company exists but no facts or docs -> 0 score."""
        profile_chain = _build_chain({"company_id": "comp-1"})
        facts_chain = _build_chain([])
        docs_chain = _build_chain([])
        mock_db.table.side_effect = [profile_chain, facts_chain, docs_chain]
        score = await service._calculate_corporate_memory("user-123")
        assert score == 0.0

    @pytest.mark.asyncio()
    async def test_facts_contribute_up_to_60(
        self, service: OnboardingReadinessService, mock_db: MagicMock
    ) -> None:
        """Facts give 1 point each, capped at 60."""
        profile_chain = _build_chain({"company_id": "comp-1"})
        facts = [{"id": f"f{i}"} for i in range(80)]
        facts_chain = _build_chain(facts)
        docs_chain = _build_chain([])
        mock_db.table.side_effect = [profile_chain, facts_chain, docs_chain]
        score = await service._calculate_corporate_memory("user-123")
        assert score == 60.0

    @pytest.mark.asyncio()
    async def test_docs_contribute_8_each_up_to_40(
        self, service: OnboardingReadinessService, mock_db: MagicMock
    ) -> None:
        """Docs give 8 points each, capped at 40."""
        profile_chain = _build_chain({"company_id": "comp-1"})
        facts_chain = _build_chain([])
        docs = [{"id": f"d{i}"} for i in range(10)]
        docs_chain = _build_chain(docs)
        mock_db.table.side_effect = [profile_chain, facts_chain, docs_chain]
        score = await service._calculate_corporate_memory("user-123")
        assert score == 40.0

    @pytest.mark.asyncio()
    async def test_combined_caps_at_100(
        self, service: OnboardingReadinessService, mock_db: MagicMock
    ) -> None:
        """Facts + docs combined cap at 100."""
        profile_chain = _build_chain({"company_id": "comp-1"})
        facts = [{"id": f"f{i}"} for i in range(80)]
        facts_chain = _build_chain(facts)
        docs = [{"id": f"d{i}"} for i in range(10)]
        docs_chain = _build_chain(docs)
        mock_db.table.side_effect = [profile_chain, facts_chain, docs_chain]
        score = await service._calculate_corporate_memory("user-123")
        assert score == 100.0


class TestDigitalTwinCalculation:
    """Tests for real digital twin score calculation."""

    @pytest.mark.asyncio()
    async def test_no_settings_returns_zero(
        self, service: OnboardingReadinessService, mock_db: MagicMock
    ) -> None:
        """No user settings -> 0 score."""
        chain = _build_chain(None)
        mock_db.table.return_value = chain
        score = await service._calculate_digital_twin("user-123")
        assert score == 0.0

    @pytest.mark.asyncio()
    async def test_writing_style_adds_50(
        self, service: OnboardingReadinessService, mock_db: MagicMock
    ) -> None:
        """Writing style present -> 50 points."""
        settings = {"preferences": {"digital_twin": {"writing_style": {"avg_sentence_length": 15}}}}
        chain = _build_chain(settings)
        mock_db.table.return_value = chain
        score = await service._calculate_digital_twin("user-123")
        assert score == 50.0

    @pytest.mark.asyncio()
    async def test_personality_calibration_adds_50(
        self, service: OnboardingReadinessService, mock_db: MagicMock
    ) -> None:
        """Personality calibration present -> 50 points."""
        settings = {
            "preferences": {"digital_twin": {"personality_calibration": {"directness": 0.7}}}
        }
        chain = _build_chain(settings)
        mock_db.table.return_value = chain
        score = await service._calculate_digital_twin("user-123")
        assert score == 50.0

    @pytest.mark.asyncio()
    async def test_both_gives_100(
        self, service: OnboardingReadinessService, mock_db: MagicMock
    ) -> None:
        """Both writing style + personality -> 100."""
        settings = {
            "preferences": {
                "digital_twin": {
                    "writing_style": {"x": 1},
                    "personality_calibration": {"y": 1},
                }
            }
        }
        chain = _build_chain(settings)
        mock_db.table.return_value = chain
        score = await service._calculate_digital_twin("user-123")
        assert score == 100.0

    @pytest.mark.asyncio()
    async def test_empty_digital_twin_returns_zero(
        self, service: OnboardingReadinessService, mock_db: MagicMock
    ) -> None:
        """Empty digital_twin dict -> 0."""
        settings = {"preferences": {"digital_twin": {}}}
        chain = _build_chain(settings)
        mock_db.table.return_value = chain
        score = await service._calculate_digital_twin("user-123")
        assert score == 0.0


class TestRelationshipGraphCalculation:
    """Tests for real relationship graph score calculation."""

    @pytest.mark.asyncio()
    async def test_no_leads_returns_zero(
        self, service: OnboardingReadinessService, mock_db: MagicMock
    ) -> None:
        """No lead memories -> 0 score."""
        chain = _build_chain([])
        mock_db.table.return_value = chain
        score = await service._calculate_relationship_graph("user-123")
        assert score == 0.0

    @pytest.mark.asyncio()
    async def test_leads_contribute_10_each_cap_50(
        self, service: OnboardingReadinessService, mock_db: MagicMock
    ) -> None:
        """Leads give 10 points each, capped at 50."""
        leads = [{"id": f"l{i}"} for i in range(8)]
        leads_chain = _build_chain(leads)
        stakeholders_chain = _build_chain([])
        mock_db.table.side_effect = [leads_chain, stakeholders_chain]
        score = await service._calculate_relationship_graph("user-123")
        assert score == 50.0  # 8 leads * 10 = 80, capped at 50

    @pytest.mark.asyncio()
    async def test_stakeholders_contribute_5_each_cap_50(
        self, service: OnboardingReadinessService, mock_db: MagicMock
    ) -> None:
        """Stakeholders give 5 points each, capped at 50."""
        leads = [{"id": "l1"}]
        leads_chain = _build_chain(leads)
        stakeholders = [{"id": f"s{i}"} for i in range(12)]
        stakeholders_chain = _build_chain(stakeholders)
        mock_db.table.side_effect = [leads_chain, stakeholders_chain]
        score = await service._calculate_relationship_graph("user-123")
        assert score == 60.0  # 1*10 + min(12*5,50) = 10+50 = 60

    @pytest.mark.asyncio()
    async def test_combined_caps_at_100(
        self, service: OnboardingReadinessService, mock_db: MagicMock
    ) -> None:
        """Leads + stakeholders combined cap at 100."""
        leads = [{"id": f"l{i}"} for i in range(8)]
        leads_chain = _build_chain(leads)
        stakeholders = [{"id": f"s{i}"} for i in range(15)]
        stakeholders_chain = _build_chain(stakeholders)
        mock_db.table.side_effect = [leads_chain, stakeholders_chain]
        score = await service._calculate_relationship_graph("user-123")
        assert score == 100.0  # 50 (lead cap) + 50 (stakeholder cap) = 100


class TestIntegrationsCalculation:
    """Tests for real integrations score calculation."""

    @pytest.mark.asyncio()
    async def test_no_integrations_returns_zero(
        self, service: OnboardingReadinessService, mock_db: MagicMock
    ) -> None:
        """No connected integrations -> 0 score."""
        chain = _build_chain([])
        mock_db.table.return_value = chain
        score = await service._calculate_integrations("user-123")
        assert score == 0.0

    @pytest.mark.asyncio()
    async def test_each_active_adds_25(
        self, service: OnboardingReadinessService, mock_db: MagicMock
    ) -> None:
        """Each active integration adds 25 points."""
        integrations = [
            {"integration_type": "gmail", "status": "active"},
            {"integration_type": "google_calendar", "status": "active"},
            {"integration_type": "salesforce", "status": "active"},
        ]
        chain = _build_chain(integrations)
        mock_db.table.return_value = chain
        score = await service._calculate_integrations("user-123")
        assert score == 75.0

    @pytest.mark.asyncio()
    async def test_caps_at_100(
        self, service: OnboardingReadinessService, mock_db: MagicMock
    ) -> None:
        """Score caps at 100 with 4+ integrations."""
        integrations = [{"integration_type": f"int{i}", "status": "active"} for i in range(5)]
        chain = _build_chain(integrations)
        mock_db.table.return_value = chain
        score = await service._calculate_integrations("user-123")
        assert score == 100.0


class TestGoalClarityCalculation:
    """Tests for real goal clarity score calculation."""

    @pytest.mark.asyncio()
    async def test_no_goals_returns_zero(
        self, service: OnboardingReadinessService, mock_db: MagicMock
    ) -> None:
        """No goals -> 0 score."""
        chain = _build_chain([])
        mock_db.table.return_value = chain
        score = await service._calculate_goal_clarity("user-123")
        assert score == 0.0

    @pytest.mark.asyncio()
    async def test_goals_contribute_30_each_cap_60(
        self, service: OnboardingReadinessService, mock_db: MagicMock
    ) -> None:
        """Goals give 30 points each, capped at 60."""
        goals = [
            {"id": "g1", "status": "active"},
            {"id": "g2", "status": "active"},
            {"id": "g3", "status": "active"},
        ]
        goals_chain = _build_chain(goals)
        agents_chain = _build_chain([])
        mock_db.table.side_effect = [goals_chain, agents_chain]
        score = await service._calculate_goal_clarity("user-123")
        assert score == 60.0  # 3 * 30 = 90, capped at 60

    @pytest.mark.asyncio()
    async def test_agent_assignments_add_10_each_cap_40(
        self, service: OnboardingReadinessService, mock_db: MagicMock
    ) -> None:
        """Agent assignments give 10 points each, capped at 40."""
        goals = [{"id": "g1"}]
        goals_chain = _build_chain(goals)
        agents = [{"id": f"a{i}"} for i in range(6)]
        agents_chain = _build_chain(agents)
        mock_db.table.side_effect = [goals_chain, agents_chain]
        score = await service._calculate_goal_clarity("user-123")
        assert score == 70.0  # 1*30 + min(6*10,40) = 30+40 = 70

    @pytest.mark.asyncio()
    async def test_combined_caps_at_100(
        self, service: OnboardingReadinessService, mock_db: MagicMock
    ) -> None:
        """Goals + agents combined cap at 100."""
        goals = [{"id": f"g{i}"} for i in range(3)]
        goals_chain = _build_chain(goals)
        agents = [{"id": f"a{i}"} for i in range(6)]
        agents_chain = _build_chain(agents)
        mock_db.table.side_effect = [goals_chain, agents_chain]
        score = await service._calculate_goal_clarity("user-123")
        assert score == 100.0  # 60 (goal cap) + 40 (agent cap) = 100
