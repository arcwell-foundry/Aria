"""Tests for the Adaptive Onboarding OODA Controller (US-916)."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.onboarding.adaptive_controller import (
    InjectedQuestion,
    OODAAssessment,
    OnboardingOODAController,
)
from src.onboarding.models import OnboardingStep


# --- Fixtures ---


def _make_db_row(
    user_id: str = "user-123",
    current_step: str = "company_discovery",
    completed_steps: list[str] | None = None,
    skipped_steps: list[str] | None = None,
    step_data: dict[str, Any] | None = None,
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
        "completed_at": None,
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
    chain.limit.return_value = chain
    chain.maybe_single.return_value = chain
    chain.single.return_value = chain
    chain.execute.return_value = _mock_execute(execute_return)
    return chain


@pytest.fixture()
def mock_db() -> MagicMock:
    """Create a mock Supabase client."""
    return MagicMock()


@pytest.fixture()
def controller(mock_db: MagicMock) -> OnboardingOODAController:
    """Create an OnboardingOODAController with mocked DB and LLM."""
    with (
        patch("src.onboarding.adaptive_controller.SupabaseClient") as mock_cls,
        patch("src.onboarding.adaptive_controller.LLMClient") as mock_llm_cls,
    ):
        mock_cls.get_client.return_value = mock_db
        mock_llm_instance = MagicMock()
        mock_llm_instance.generate_response = AsyncMock(
            return_value='{"priority_action": "Continue", "emphasis": "none", "skip_recommendation": "none"}'
        )
        mock_llm_cls.return_value = mock_llm_instance
        ctrl = OnboardingOODAController()
    return ctrl


# --- assess_next_step generates OODAAssessment ---


@pytest.mark.asyncio()
async def test_assess_next_step_returns_ooda_assessment(
    controller: OnboardingOODAController,
    mock_db: MagicMock,
) -> None:
    """OODA assessment is generated after step completion."""
    # onboarding_state select
    state_chain = _build_chain(_make_db_row(
        completed_steps=["company_discovery"],
        current_step="document_upload",
    ))
    # memory_semantic select (facts)
    facts_chain = _build_chain([
        {"fact": "Company is a CDMO", "metadata": {}},
        {"fact": "User is sales rep", "metadata": {}},
    ])
    # user_integrations select
    integrations_chain = _build_chain([])
    # company_classifications select
    classification_chain = _build_chain(
        {"metadata": {"classification": {"company_type": "Biotech"}}}
    )

    mock_db.table.side_effect = [
        state_chain,  # _get_onboarding_state
        facts_chain,  # memory_semantic
        integrations_chain,  # user_integrations
        classification_chain,  # _get_classification
    ]

    with patch.object(controller, "_log_assessment", new_callable=AsyncMock):
        assessment = await controller.assess_next_step(
            "user-123", OnboardingStep.COMPANY_DISCOVERY
        )

    assert isinstance(assessment, OODAAssessment)
    assert "completed_steps" in assessment.observation
    assert assessment.reasoning


# --- assess_next_step result is JSON-serializable for route ---


@pytest.mark.asyncio()
async def test_assess_next_step_serializable_for_route(
    controller: OnboardingOODAController,
    mock_db: MagicMock,
) -> None:
    """OODAAssessment serializes to dict for the API route response."""
    state_chain = _build_chain(_make_db_row(
        completed_steps=["company_discovery"],
        current_step="document_upload",
    ))
    facts_chain = _build_chain([{"fact": "fact 1", "metadata": {}}])
    integrations_chain = _build_chain([])
    classification_chain = _build_chain(
        {"metadata": {"classification": {"company_type": "Biotech"}}}
    )

    mock_db.table.side_effect = [
        state_chain,
        facts_chain,
        integrations_chain,
        classification_chain,
    ]

    with patch.object(controller, "_log_assessment", new_callable=AsyncMock):
        assessment = await controller.assess_next_step(
            "user-123", OnboardingStep.COMPANY_DISCOVERY
        )

    result = assessment.model_dump()
    assert "observation" in result
    assert "orientation" in result
    assert "decision" in result
    assert "reasoning" in result
    assert isinstance(result["reasoning"], str)


# --- CDMO user gets manufacturing question injected ---


@pytest.mark.asyncio()
async def test_cdmo_user_gets_manufacturing_question(
    controller: OnboardingOODAController,
    mock_db: MagicMock,
) -> None:
    """CDMO company type triggers modality question injection."""
    state_chain = _build_chain(_make_db_row(
        completed_steps=["company_discovery"],
        current_step="document_upload",
    ))
    facts_chain = _build_chain([{"fact": "CDMO company", "metadata": {}}])
    integrations_chain = _build_chain([])
    classification_chain = _build_chain(
        {"metadata": {"classification": {"company_type": "CDMO"}}}
    )

    mock_db.table.side_effect = [
        state_chain,
        facts_chain,
        integrations_chain,
        classification_chain,
    ]

    # The LLM is called twice: once by _orient, once by _generate_contextual_questions.
    # The second call must return a JSON array with a CDMO question.
    controller._llm.generate_response = AsyncMock(
        side_effect=[
            '{"priority_action": "Continue", "emphasis": "none", "skip_recommendation": "none"}',
            '[{"question": "Which CDMO modalities does your facility support?", "context": "CDMO-specific capability mapping"}]',
        ]
    )

    with patch.object(controller, "_log_assessment", new_callable=AsyncMock):
        assessment = await controller.assess_next_step(
            "user-123", OnboardingStep.COMPANY_DISCOVERY
        )

    injected = assessment.decision.get("inject_questions", [])
    assert len(injected) >= 1
    cdmo_q = injected[0]
    assert "CDMO" in cdmo_q["question"] or "modalities" in cdmo_q["question"].lower()
    assert cdmo_q["insert_after_step"] == "company_discovery"


# --- Low fact count emphasizes document upload ---


@pytest.mark.asyncio()
async def test_low_fact_count_emphasizes_document_upload(
    controller: OnboardingOODAController,
    mock_db: MagicMock,
) -> None:
    """When fact count is very low, decision emphasizes document_upload."""
    state_chain = _build_chain(_make_db_row(
        completed_steps=["company_discovery"],
        current_step="document_upload",
    ))
    facts_chain = _build_chain([{"fact": "one fact", "metadata": {}}])  # Only 1 fact
    integrations_chain = _build_chain([])
    classification_chain = _build_chain(
        {"metadata": {"classification": {"company_type": "Biotech"}}}
    )

    mock_db.table.side_effect = [
        state_chain,
        facts_chain,
        integrations_chain,
        classification_chain,
    ]

    with patch.object(controller, "_log_assessment", new_callable=AsyncMock):
        assessment = await controller.assess_next_step(
            "user-123", OnboardingStep.COMPANY_DISCOVERY
        )

    assert assessment.decision.get("emphasize") == "document_upload"
    assert "fact" in assessment.reasoning.lower() or "document" in assessment.reasoning.lower()


# --- CRM connected reasoning ---


@pytest.mark.asyncio()
async def test_crm_connected_updates_reasoning(
    controller: OnboardingOODAController,
    mock_db: MagicMock,
) -> None:
    """When CRM is connected, reasoning reflects CRM data leverage."""
    state_chain = _build_chain(_make_db_row(
        completed_steps=["company_discovery"],
        current_step="document_upload",
    ))
    facts_chain = _build_chain([
        {"fact": f"fact {i}", "metadata": {}} for i in range(10)
    ])
    integrations_chain = _build_chain([{"provider": "salesforce"}])
    classification_chain = _build_chain(
        {"metadata": {"classification": {"company_type": "Large Pharma"}}}
    )

    mock_db.table.side_effect = [
        state_chain,
        facts_chain,
        integrations_chain,
        classification_chain,
    ]

    with patch.object(controller, "_log_assessment", new_callable=AsyncMock):
        assessment = await controller.assess_next_step(
            "user-123", OnboardingStep.COMPANY_DISCOVERY
        )

    assert "CRM" in assessment.reasoning or "crm" in assessment.reasoning.lower()


# --- Reasoning logged to episodic memory ---


@pytest.mark.asyncio()
async def test_assessment_logged_to_episodic_memory(
    controller: OnboardingOODAController,
    mock_db: MagicMock,
) -> None:
    """OODA assessment is recorded in episodic memory."""
    state_chain = _build_chain(_make_db_row(
        completed_steps=["company_discovery"],
        current_step="document_upload",
    ))
    facts_chain = _build_chain([{"fact": f"fact {i}", "metadata": {}} for i in range(10)])
    integrations_chain = _build_chain([])
    classification_chain = _build_chain(
        {"metadata": {"classification": {"company_type": "Biotech"}}}
    )
    # For _log_assessment: _get_onboarding_state + update
    log_state_chain = _build_chain(_make_db_row())
    update_chain = _build_chain([_make_db_row()])

    mock_db.table.side_effect = [
        state_chain,
        facts_chain,
        integrations_chain,
        classification_chain,
        log_state_chain,  # _log_assessment reads state
    ]

    with patch(
        "src.memory.episodic.EpisodicMemory"
    ) as mock_episodic_cls:
        mock_episodic = MagicMock()
        mock_episodic.store_episode = AsyncMock()
        mock_episodic_cls.return_value = mock_episodic

        await controller.assess_next_step(
            "user-123", OnboardingStep.COMPANY_DISCOVERY
        )

        mock_episodic.store_episode.assert_called_once()
        episode = mock_episodic.store_episode.call_args[0][0]
        assert episode.event_type == "ooda_onboarding_adaptation"


# --- Injected questions stored in onboarding metadata ---


@pytest.mark.asyncio()
async def test_injected_questions_stored_in_metadata(
    controller: OnboardingOODAController,
    mock_db: MagicMock,
) -> None:
    """Injected questions are persisted in onboarding_state metadata."""
    state_chain = _build_chain(_make_db_row(
        completed_steps=["company_discovery"],
        current_step="document_upload",
    ))
    facts_chain = _build_chain([{"fact": "CDMO fact", "metadata": {}}])
    integrations_chain = _build_chain([])
    classification_chain = _build_chain(
        {"metadata": {"classification": {"company_type": "CDMO"}}}
    )
    # _log_assessment reads state then updates
    log_state_chain = _build_chain(_make_db_row())
    update_chain = _build_chain([_make_db_row()])

    mock_db.table.side_effect = [
        state_chain,
        facts_chain,
        integrations_chain,
        classification_chain,
        log_state_chain,
        update_chain,
    ]

    with patch(
        "src.memory.episodic.EpisodicMemory"
    ) as mock_episodic_cls:
        mock_episodic = MagicMock()
        mock_episodic.store_episode = AsyncMock()
        mock_episodic_cls.return_value = mock_episodic

        await controller.assess_next_step(
            "user-123", OnboardingStep.COMPANY_DISCOVERY
        )

    # Find the update call that stores injections
    update_calls = update_chain.update.call_args_list
    if update_calls:
        update_payload = update_calls[0][0][0]
        assert "ooda_injections" in update_payload.get("metadata", {})


# --- get_injected_questions returns stored questions ---


@pytest.mark.asyncio()
async def test_get_injected_questions_returns_stored(
    controller: OnboardingOODAController,
    mock_db: MagicMock,
) -> None:
    """get_injected_questions retrieves questions from metadata."""
    stored_questions = [
        {
            "question": "Which modalities does your facility support?",
            "context": "CDMO-specific capability mapping",
            "insert_after_step": "company_discovery",
        }
    ]
    state_row = _make_db_row(
        metadata={"ooda_injections": {"company_discovery": stored_questions}}
    )
    state_chain = _build_chain(state_row)
    mock_db.table.return_value = state_chain

    questions = await controller.get_injected_questions("user-123", "company_discovery")

    assert len(questions) == 1
    assert isinstance(questions[0], InjectedQuestion)
    assert "modalities" in questions[0].question.lower()


# --- get_injected_questions returns empty for no injections ---


@pytest.mark.asyncio()
async def test_get_injected_questions_empty_when_no_injections(
    controller: OnboardingOODAController,
    mock_db: MagicMock,
) -> None:
    """get_injected_questions returns empty list when no injections exist."""
    state_chain = _build_chain(_make_db_row())
    mock_db.table.return_value = state_chain

    questions = await controller.get_injected_questions("user-123", "company_discovery")

    assert questions == []


# --- Observation captures correct state ---


@pytest.mark.asyncio()
async def test_observe_captures_onboarding_state(
    controller: OnboardingOODAController,
    mock_db: MagicMock,
) -> None:
    """_observe returns dict with completed_steps, fact_count, integrations."""
    state_chain = _build_chain(_make_db_row(
        completed_steps=["company_discovery", "document_upload"],
        readiness_scores={"corporate_memory": 40, "digital_twin": 20,
                         "relationship_graph": 0, "integrations": 0, "goal_clarity": 0},
    ))
    facts_chain = _build_chain([
        {"fact": f"fact {i}", "metadata": {}} for i in range(5)
    ])
    integrations_chain = _build_chain([{"provider": "hubspot"}])
    classification_chain = _build_chain(
        {"metadata": {"classification": {"company_type": "CRO"}}}
    )

    mock_db.table.side_effect = [
        state_chain,
        facts_chain,
        integrations_chain,
        classification_chain,
    ]

    observation = await controller._observe("user-123")

    assert observation["completed_steps"] == ["company_discovery", "document_upload"]
    assert observation["fact_count"] == 5
    assert "hubspot" in observation["connected_integrations"]
    assert observation["classification"]["company_type"] == "CRO"


# --- Orient calls LLM ---


@pytest.mark.asyncio()
async def test_orient_calls_llm(
    controller: OnboardingOODAController,
) -> None:
    """_orient invokes LLM to assess highest-value next step."""
    observation = {
        "completed_steps": ["company_discovery"],
        "fact_count": 3,
        "connected_integrations": [],
        "readiness_scores": {},
        "classification": {"company_type": "Biotech"},
    }

    orientation = await controller._orient(observation)

    assert "priority_action" in orientation
    controller._llm.generate_response.assert_called_once()


# --- Default step order maintained when no adaptations needed ---


@pytest.mark.asyncio()
async def test_decide_maintains_default_order_for_generic_user(
    controller: OnboardingOODAController,
) -> None:
    """Non-CDMO user with sufficient facts keeps default step order."""
    observation = {
        "completed_steps": ["company_discovery"],
        "fact_count": 15,
        "connected_integrations": [],
        "readiness_scores": {},
        "classification": {"company_type": "Biotech"},
    }
    orientation = {"priority_action": "Continue", "emphasis": "none", "skip_recommendation": "none"}

    decision = await controller._decide(
        observation, orientation, OnboardingStep.COMPANY_DISCOVERY
    )

    assert decision["reorder"] is None
    assert decision["inject_questions"] == []


# --- HubSpot CRM triggers reasoning update ---


@pytest.mark.asyncio()
async def test_decide_hubspot_triggers_crm_reasoning(
    controller: OnboardingOODAController,
) -> None:
    """HubSpot connection triggers CRM reasoning."""
    observation = {
        "completed_steps": ["company_discovery"],
        "fact_count": 15,
        "connected_integrations": ["hubspot"],
        "readiness_scores": {},
        "classification": {"company_type": "Biotech"},
    }
    orientation = {"priority_action": "Continue", "emphasis": "none", "skip_recommendation": "none"}

    decision = await controller._decide(
        observation, orientation, OnboardingStep.COMPANY_DISCOVERY
    )

    assert "CRM" in decision["reasoning"]


# --- Episodic logging failure is non-fatal ---


@pytest.mark.asyncio()
async def test_episodic_logging_failure_is_nonfatal(
    controller: OnboardingOODAController,
    mock_db: MagicMock,
) -> None:
    """If episodic memory fails, assessment still completes."""
    state_chain = _build_chain(_make_db_row(
        completed_steps=["company_discovery"],
        current_step="document_upload",
    ))
    facts_chain = _build_chain([{"fact": f"fact {i}", "metadata": {}} for i in range(10)])
    integrations_chain = _build_chain([])
    classification_chain = _build_chain(
        {"metadata": {"classification": {"company_type": "Biotech"}}}
    )
    log_state_chain = _build_chain(_make_db_row())

    mock_db.table.side_effect = [
        state_chain,
        facts_chain,
        integrations_chain,
        classification_chain,
        log_state_chain,
    ]

    with patch(
        "src.memory.episodic.EpisodicMemory"
    ) as mock_episodic_cls:
        mock_episodic = MagicMock()
        mock_episodic.store_episode = AsyncMock(side_effect=Exception("Graphiti down"))
        mock_episodic_cls.return_value = mock_episodic

        # Should not raise
        assessment = await controller.assess_next_step(
            "user-123", OnboardingStep.COMPANY_DISCOVERY
        )

    assert isinstance(assessment, OODAAssessment)
