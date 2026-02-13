"""Tests for the onboarding orchestrator and state machine."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.onboarding.models import (
    SKIPPABLE_STEPS,
    STEP_ORDER,
    OnboardingStep,
    ReadinessScores,
)
from src.onboarding.orchestrator import OnboardingOrchestrator


# --- Fixtures ---


def _make_db_row(
    user_id: str = "user-123",
    current_step: str = "company_discovery",
    completed_steps: list[str] | None = None,
    skipped_steps: list[str] | None = None,
    step_data: dict[str, Any] | None = None,
    completed_at: str | None = None,
    readiness_scores: dict[str, float] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a mock onboarding_state DB row."""
    return {
        "id": "state-abc",
        "user_id": user_id,
        "current_step": current_step,
        "step_data": step_data or {},
        "completed_steps": completed_steps or [],
        "skipped_steps": skipped_steps or [],
        "started_at": "2026-02-06T00:00:00+00:00",
        "updated_at": "2026-02-06T00:00:00+00:00",
        "completed_at": completed_at,
        "readiness_scores": readiness_scores
        or {
            "corporate_memory": 0,
            "digital_twin": 0,
            "relationship_graph": 0,
            "integrations": 0,
            "goal_clarity": 0,
        },
        "metadata": metadata or {},
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
def orchestrator(mock_db: MagicMock) -> OnboardingOrchestrator:
    """Create an OnboardingOrchestrator with mocked DB."""
    with patch("src.onboarding.orchestrator.SupabaseClient") as mock_cls:
        mock_cls.get_client.return_value = mock_db
        orch = OnboardingOrchestrator()
    return orch


# --- State creation ---


@pytest.mark.asyncio()
async def test_get_or_create_state_creates_new(
    orchestrator: OnboardingOrchestrator,
    mock_db: MagicMock,
) -> None:
    """New user gets a fresh onboarding state at company_discovery."""
    row = _make_db_row()

    # First call: select returns None (no existing state)
    select_chain = _build_chain(None)
    # Second call: insert returns the new row
    insert_chain = _build_chain([row])

    mock_db.table.side_effect = [select_chain, insert_chain]

    with patch.object(orchestrator, "_record_episodic_event", new_callable=AsyncMock):
        response = await orchestrator.get_or_create_state("user-123")

    assert response.state.user_id == "user-123"
    assert response.state.current_step == OnboardingStep.COMPANY_DISCOVERY
    assert response.completed_count == 0
    assert response.is_complete is False
    assert response.total_steps == len(STEP_ORDER)


@pytest.mark.asyncio()
async def test_get_or_create_state_returns_existing(
    orchestrator: OnboardingOrchestrator,
    mock_db: MagicMock,
) -> None:
    """Returning user gets their existing state."""
    row = _make_db_row(
        current_step="user_profile",
        completed_steps=["company_discovery", "document_upload"],
    )
    select_chain = _build_chain(row)
    mock_db.table.return_value = select_chain

    response = await orchestrator.get_or_create_state("user-123")

    assert response.state.current_step == OnboardingStep.USER_PROFILE
    assert response.completed_count == 2


# --- Step completion ---


@pytest.mark.asyncio()
async def test_complete_step_advances_to_next(
    orchestrator: OnboardingOrchestrator,
    mock_db: MagicMock,
) -> None:
    """Completing a step moves to the next one in order."""
    current_row = _make_db_row(current_step="company_discovery")
    updated_row = _make_db_row(
        current_step="document_upload",
        completed_steps=["company_discovery"],
        step_data={"company_discovery": {"name": "Acme"}},
    )

    # _get_state select, then update
    select_chain = _build_chain(current_row)
    update_chain = _build_chain([updated_row])
    mock_db.table.side_effect = [select_chain, update_chain]

    with patch.object(orchestrator, "_record_episodic_event", new_callable=AsyncMock):
        with patch.object(
            orchestrator, "_trigger_step_processing", new_callable=AsyncMock
        ):
            response = await orchestrator.complete_step(
                "user-123",
                OnboardingStep.COMPANY_DISCOVERY,
                {"name": "Acme"},
            )

    assert response.state.current_step == OnboardingStep.DOCUMENT_UPLOAD
    assert "company_discovery" in response.state.completed_steps


@pytest.mark.asyncio()
async def test_complete_step_wrong_step_raises(
    orchestrator: OnboardingOrchestrator,
    mock_db: MagicMock,
) -> None:
    """Completing a step that isn't the current one raises ValueError."""
    row = _make_db_row(current_step="company_discovery")
    select_chain = _build_chain(row)
    mock_db.table.return_value = select_chain

    with pytest.raises(ValueError, match="Cannot complete step"):
        await orchestrator.complete_step(
            "user-123",
            OnboardingStep.USER_PROFILE,
            {},
        )


@pytest.mark.asyncio()
async def test_complete_step_no_state_raises(
    orchestrator: OnboardingOrchestrator,
    mock_db: MagicMock,
) -> None:
    """Completing a step with no onboarding state raises ValueError."""
    select_chain = _build_chain(None)
    mock_db.table.return_value = select_chain

    with pytest.raises(ValueError, match="No onboarding state found"):
        await orchestrator.complete_step(
            "user-123",
            OnboardingStep.COMPANY_DISCOVERY,
            {},
        )


@pytest.mark.asyncio()
async def test_complete_last_step_sets_completed_at(
    orchestrator: OnboardingOrchestrator,
    mock_db: MagicMock,
) -> None:
    """Completing the final step sets completed_at."""
    completed = [s.value for s in STEP_ORDER[:-1]]
    current_row = _make_db_row(
        current_step="activation",
        completed_steps=completed,
    )
    updated_row = _make_db_row(
        current_step="activation",
        completed_steps=completed + ["activation"],
        completed_at="2026-02-06T12:00:00+00:00",
    )

    select_chain = _build_chain(current_row)
    update_chain = _build_chain([updated_row])
    mock_db.table.side_effect = [select_chain, update_chain]

    with patch.object(orchestrator, "_record_episodic_event", new_callable=AsyncMock):
        with patch.object(
            orchestrator, "_trigger_step_processing", new_callable=AsyncMock
        ):
            response = await orchestrator.complete_step(
                "user-123",
                OnboardingStep.ACTIVATION,
                {},
            )

    assert response.is_complete is True


@pytest.mark.asyncio()
async def test_step_data_merges_across_steps(
    orchestrator: OnboardingOrchestrator,
    mock_db: MagicMock,
) -> None:
    """Step data accumulates across completed steps."""
    current_row = _make_db_row(
        current_step="document_upload",
        completed_steps=["company_discovery"],
        step_data={"company_discovery": {"name": "Acme"}},
    )
    updated_row = _make_db_row(
        current_step="user_profile",
        completed_steps=["company_discovery", "document_upload"],
        step_data={
            "company_discovery": {"name": "Acme"},
            "document_upload": {"files": 3},
        },
    )

    select_chain = _build_chain(current_row)
    update_chain = _build_chain([updated_row])
    mock_db.table.side_effect = [select_chain, update_chain]

    with patch.object(orchestrator, "_record_episodic_event", new_callable=AsyncMock):
        with patch.object(
            orchestrator, "_trigger_step_processing", new_callable=AsyncMock
        ):
            response = await orchestrator.complete_step(
                "user-123",
                OnboardingStep.DOCUMENT_UPLOAD,
                {"files": 3},
            )

    assert "company_discovery" in response.state.step_data
    assert "document_upload" in response.state.step_data


# --- Skip logic ---


@pytest.mark.asyncio()
async def test_skip_skippable_step(
    orchestrator: OnboardingOrchestrator,
    mock_db: MagicMock,
) -> None:
    """Skippable steps can be skipped and advance to next."""
    current_row = _make_db_row(current_step="document_upload")
    updated_row = _make_db_row(
        current_step="user_profile",
        skipped_steps=["document_upload"],
        metadata={"skip_reason_document_upload": "not ready"},
    )

    select_chain = _build_chain(current_row)
    update_chain = _build_chain([updated_row])
    mock_db.table.side_effect = [select_chain, update_chain]

    with patch.object(orchestrator, "_record_episodic_event", new_callable=AsyncMock):
        response = await orchestrator.skip_step(
            "user-123",
            OnboardingStep.DOCUMENT_UPLOAD,
            "not ready",
        )

    assert "document_upload" in response.state.skipped_steps
    assert response.state.current_step == OnboardingStep.USER_PROFILE


@pytest.mark.asyncio()
async def test_skip_non_skippable_raises(
    orchestrator: OnboardingOrchestrator,
) -> None:
    """Non-skippable steps raise ValueError."""
    with pytest.raises(ValueError, match="cannot be skipped"):
        await orchestrator.skip_step(
            "user-123",
            OnboardingStep.COMPANY_DISCOVERY,
        )


def test_skippable_steps_are_correct() -> None:
    """Verify the expected set of skippable steps."""
    assert SKIPPABLE_STEPS == {
        OnboardingStep.DOCUMENT_UPLOAD,
        OnboardingStep.WRITING_SAMPLES,
        OnboardingStep.EMAIL_INTEGRATION,
    }


# --- Progress calculation ---


def test_progress_percentage_no_skips(
    orchestrator: OnboardingOrchestrator,
) -> None:
    """Progress is completed / total * 100."""
    row = _make_db_row(
        current_step="user_profile",
        completed_steps=["company_discovery", "document_upload"],
    )
    state = orchestrator._parse_state(row)
    response = orchestrator._build_response(state)

    # 2 / 8 * 100 = 25.0
    assert response.progress_percentage == 25.0
    assert response.completed_count == 2
    assert response.total_steps == 8


def test_progress_percentage_with_skips(
    orchestrator: OnboardingOrchestrator,
) -> None:
    """Skipped steps reduce effective total."""
    row = _make_db_row(
        current_step="user_profile",
        completed_steps=["company_discovery"],
        skipped_steps=["document_upload"],
    )
    state = orchestrator._parse_state(row)
    response = orchestrator._build_response(state)

    # 1 / (8 - 1) * 100 = 14.3
    assert response.progress_percentage == pytest.approx(14.3, abs=0.1)


def test_progress_complete(
    orchestrator: OnboardingOrchestrator,
) -> None:
    """100% progress when all steps completed."""
    all_steps = [s.value for s in STEP_ORDER]
    row = _make_db_row(
        current_step="activation",
        completed_steps=all_steps,
        completed_at="2026-02-06T12:00:00+00:00",
    )
    state = orchestrator._parse_state(row)
    response = orchestrator._build_response(state)

    assert response.progress_percentage == 100.0
    assert response.is_complete is True


# --- Routing decision ---


@pytest.mark.asyncio()
async def test_routing_new_user(
    orchestrator: OnboardingOrchestrator,
    mock_db: MagicMock,
) -> None:
    """New user with no state routes to 'onboarding'."""
    # Profile check: no admin role
    profile_chain = _build_chain(None)
    # Onboarding state: not found
    state_chain = _build_chain(None)
    mock_db.table.side_effect = [profile_chain, state_chain]

    route = await orchestrator.get_routing_decision("user-123")
    assert route == "onboarding"


@pytest.mark.asyncio()
async def test_routing_incomplete_onboarding(
    orchestrator: OnboardingOrchestrator,
    mock_db: MagicMock,
) -> None:
    """User with incomplete onboarding routes to 'onboarding' to complete it."""
    profile_chain = _build_chain(None)
    state_chain = _build_chain({"completed_at": None, "current_step": "user_profile"})
    mock_db.table.side_effect = [profile_chain, state_chain]

    route = await orchestrator.get_routing_decision("user-123")
    assert route == "onboarding"


@pytest.mark.asyncio()
async def test_routing_complete_onboarding(
    orchestrator: OnboardingOrchestrator,
    mock_db: MagicMock,
) -> None:
    """User with completed onboarding routes to 'dashboard'."""
    profile_chain = _build_chain(None)
    state_chain = _build_chain({
        "completed_at": "2026-02-06T12:00:00+00:00",
        "current_step": "activation",
    })
    mock_db.table.side_effect = [profile_chain, state_chain]

    route = await orchestrator.get_routing_decision("user-123")
    assert route == "dashboard"


@pytest.mark.asyncio()
async def test_routing_admin_user(
    orchestrator: OnboardingOrchestrator,
    mock_db: MagicMock,
) -> None:
    """Admin user routes to 'admin'."""
    profile_chain = _build_chain({"role": "admin"})
    mock_db.table.return_value = profile_chain

    route = await orchestrator.get_routing_decision("user-123")
    assert route == "admin"


# --- Readiness scores ---


@pytest.mark.asyncio()
async def test_readiness_scores_update(
    orchestrator: OnboardingOrchestrator,
    mock_db: MagicMock,
) -> None:
    """Readiness scores update for valid keys."""
    row = _make_db_row()
    select_chain = _build_chain(row)
    update_chain = _build_chain([row])
    mock_db.table.side_effect = [select_chain, update_chain]

    await orchestrator.update_readiness_scores(
        "user-123", {"corporate_memory": 42.5, "digital_twin": 75.0}
    )

    # Verify update was called
    update_chain.update.assert_called_once()
    call_args = update_chain.update.call_args[0][0]
    assert call_args["readiness_scores"]["corporate_memory"] == 42.5
    assert call_args["readiness_scores"]["digital_twin"] == 75.0


@pytest.mark.asyncio()
async def test_readiness_scores_clamped(
    orchestrator: OnboardingOrchestrator,
    mock_db: MagicMock,
) -> None:
    """Readiness scores are clamped to 0-100."""
    row = _make_db_row()
    select_chain = _build_chain(row)
    update_chain = _build_chain([row])
    mock_db.table.side_effect = [select_chain, update_chain]

    await orchestrator.update_readiness_scores(
        "user-123", {"corporate_memory": 150.0, "digital_twin": -10.0}
    )

    call_args = update_chain.update.call_args[0][0]
    assert call_args["readiness_scores"]["corporate_memory"] == 100.0
    assert call_args["readiness_scores"]["digital_twin"] == 0.0


@pytest.mark.asyncio()
async def test_readiness_scores_ignores_unknown_keys(
    orchestrator: OnboardingOrchestrator,
    mock_db: MagicMock,
) -> None:
    """Unknown readiness score keys are silently ignored."""
    row = _make_db_row()
    select_chain = _build_chain(row)
    update_chain = _build_chain([row])
    mock_db.table.side_effect = [select_chain, update_chain]

    await orchestrator.update_readiness_scores(
        "user-123", {"nonexistent_key": 50.0, "corporate_memory": 30.0}
    )

    call_args = update_chain.update.call_args[0][0]
    assert "nonexistent_key" not in call_args["readiness_scores"]
    assert call_args["readiness_scores"]["corporate_memory"] == 30.0


# --- Step order ---


def test_step_order_has_eight_steps() -> None:
    """There are exactly 8 onboarding steps."""
    assert len(STEP_ORDER) == 8


def test_step_order_starts_with_company_discovery() -> None:
    """First step is always company_discovery."""
    assert STEP_ORDER[0] == OnboardingStep.COMPANY_DISCOVERY


def test_step_order_ends_with_activation() -> None:
    """Last step is always activation."""
    assert STEP_ORDER[-1] == OnboardingStep.ACTIVATION


# --- _get_next_step ---


def test_get_next_step_simple(
    orchestrator: OnboardingOrchestrator,
) -> None:
    """Next step after company_discovery is document_upload."""
    next_step = orchestrator._get_next_step(
        OnboardingStep.COMPANY_DISCOVERY, [], []
    )
    assert next_step == OnboardingStep.DOCUMENT_UPLOAD


def test_get_next_step_skips_completed(
    orchestrator: OnboardingOrchestrator,
) -> None:
    """Skips over already completed steps."""
    next_step = orchestrator._get_next_step(
        OnboardingStep.COMPANY_DISCOVERY,
        ["document_upload"],
        [],
    )
    assert next_step == OnboardingStep.USER_PROFILE


def test_get_next_step_skips_skipped(
    orchestrator: OnboardingOrchestrator,
) -> None:
    """Skips over skipped steps."""
    next_step = orchestrator._get_next_step(
        OnboardingStep.COMPANY_DISCOVERY,
        [],
        ["document_upload"],
    )
    assert next_step == OnboardingStep.USER_PROFILE


def test_get_next_step_returns_none_at_end(
    orchestrator: OnboardingOrchestrator,
) -> None:
    """Returns None when no steps remain."""
    next_step = orchestrator._get_next_step(
        OnboardingStep.ACTIVATION, [], []
    )
    assert next_step is None
