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
        _build_chain([_make_db_row(readiness_scores={
            "corporate_memory": 85.0,
            "digital_twin": 75.0,
            "relationship_graph": 80.0,
            "integrations": 60.0,
            "goal_clarity": 70.0,
        })]),
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
        _build_chain([_make_db_row(readiness_scores={
            "corporate_memory": 0.0,
            "digital_twin": 0.0,
            "relationship_graph": 0.0,
            "integrations": 0.0,
            "goal_clarity": 0.0,
        })]),
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
