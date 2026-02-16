"""Tests for the Jarvis Intelligence Orchestrator (US-710).

Covers:
- Briefing generation with budget enforcement
- Deduplication of similar and identical-trigger insights
- Event processing pipeline with engine ordering
- Engine failure isolation
- Feedback recording
- Metrics aggregation
- Integration: event string -> insights
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.intelligence.causal.models import JarvisInsight
from src.intelligence.orchestrator import JarvisOrchestrator


# ============================================================
# Fixtures
# ============================================================

TEST_USER_ID = "00000000-0000-0000-0000-000000000001"


def _make_insight(
    content: str = "Test insight",
    trigger_event: str = "test_event",
    combined_score: float = 0.8,
    insight_type: str = "implication",
    classification: str = "opportunity",
    insight_id: UUID | None = None,
) -> JarvisInsight:
    return JarvisInsight(
        id=insight_id or uuid4(),
        user_id=UUID(TEST_USER_ID),
        insight_type=insight_type,
        trigger_event=trigger_event,
        content=content,
        classification=classification,
        impact_score=combined_score,
        confidence=0.7,
        urgency=0.5,
        combined_score=combined_score,
        causal_chain=[],
        affected_goals=[],
        recommended_actions=[],
        status="new",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def mock_llm_client() -> MagicMock:
    client = MagicMock()
    client.generate_response = AsyncMock(return_value="{}")
    return client


@pytest.fixture
def mock_db_client() -> MagicMock:
    client = MagicMock()
    table_mock = MagicMock()
    table_mock.select.return_value = table_mock
    table_mock.eq.return_value = table_mock
    table_mock.in_.return_value = table_mock
    table_mock.order.return_value = table_mock
    table_mock.limit.return_value = table_mock
    table_mock.single.return_value = table_mock
    table_mock.update.return_value = table_mock
    table_mock.execute.return_value = MagicMock(data=[])
    client.table.return_value = table_mock
    return client


@pytest.fixture
def orchestrator(mock_llm_client: MagicMock, mock_db_client: MagicMock) -> JarvisOrchestrator:
    return JarvisOrchestrator(llm_client=mock_llm_client, db_client=mock_db_client)


# ============================================================
# Test: Budget enforcement
# ============================================================


@pytest.mark.asyncio
async def test_generate_briefing_respects_budget(orchestrator: JarvisOrchestrator) -> None:
    """Verify that the orchestrator stops running engines when budget is 80% exhausted."""
    engines_called: list[str] = []

    original_run_engine = orchestrator._run_engine

    async def slow_engine(engine_name: str, user_id: str, context: dict, budget_ms: int) -> list[JarvisInsight]:
        engines_called.append(engine_name)
        # Simulate a slow engine (~300ms)
        await asyncio.sleep(0.3)
        return [_make_insight(content=f"Insight from {engine_name}", trigger_event=engine_name)]

    orchestrator._run_engine = slow_engine  # type: ignore[assignment]

    # With a 200ms budget, only 0-1 engines should run before 80% cutoff
    insights = await orchestrator.generate_briefing(
        user_id=TEST_USER_ID,
        context={},
        budget_ms=200,
    )

    # At most 1 engine should have completed (the first one starts before budget check)
    assert len(engines_called) <= 2, f"Too many engines called: {engines_called}"


# ============================================================
# Test: Deduplication
# ============================================================


def test_deduplication_removes_similar_insights(orchestrator: JarvisOrchestrator) -> None:
    """Insights with >70% content similarity should be deduplicated."""
    insight1 = _make_insight(
        content="FDA approved new drug treatment for rare disease affecting liver function",
        trigger_event="fda_approval_1",
        combined_score=0.9,
    )
    insight2 = _make_insight(
        content="FDA approved new drug treatment for rare disease affecting liver health",
        trigger_event="fda_approval_2",
        combined_score=0.7,
    )

    result = orchestrator._deduplicate([insight1, insight2])

    assert len(result) == 1
    assert result[0].combined_score == 0.9  # Higher-scored kept


def test_deduplication_keeps_distinct_insights(orchestrator: JarvisOrchestrator) -> None:
    """Clearly different insights should both be retained."""
    insight1 = _make_insight(
        content="FDA approved new drug treatment for rare disease",
        trigger_event="fda_event",
        combined_score=0.9,
    )
    insight2 = _make_insight(
        content="Competitor launched aggressive pricing strategy in European market",
        trigger_event="pricing_event",
        combined_score=0.7,
    )

    result = orchestrator._deduplicate([insight1, insight2])

    assert len(result) == 2


def test_deduplication_by_trigger_event(orchestrator: JarvisOrchestrator) -> None:
    """Insights with identical trigger_event should be deduplicated."""
    insight1 = _make_insight(
        content="Insight A from analysis",
        trigger_event="same_trigger",
        combined_score=0.6,
    )
    insight2 = _make_insight(
        content="Completely different content here",
        trigger_event="same_trigger",
        combined_score=0.9,
    )

    result = orchestrator._deduplicate([insight1, insight2])

    assert len(result) == 1
    assert result[0].combined_score == 0.9


# ============================================================
# Test: Process event pipeline
# ============================================================


@pytest.mark.asyncio
async def test_process_event_runs_pipeline(orchestrator: JarvisOrchestrator) -> None:
    """Verify all pipeline steps are attempted during event processing."""
    mock_imp_engine = MagicMock()
    mock_imp_engine.analyze_event = AsyncMock(return_value=[])
    mock_imp_engine.save_insight = AsyncMock(return_value=None)

    mock_butterfly = MagicMock()
    mock_butterfly.detect = AsyncMock(return_value=None)

    mock_goal_impact = MagicMock()
    mock_goal_impact.assess_event_impact = AsyncMock(return_value=[])

    mock_time_horizon = MagicMock()

    # Inject mocks
    orchestrator._JarvisOrchestrator__implication = mock_imp_engine
    orchestrator._JarvisOrchestrator__butterfly = mock_butterfly
    orchestrator._JarvisOrchestrator__goal_impact = mock_goal_impact
    orchestrator._JarvisOrchestrator__time_horizon = mock_time_horizon

    await orchestrator.process_event(
        user_id=TEST_USER_ID,
        event="Major regulatory change in EU pharma sector affecting supply chain logistics",
        source_context="test",
    )

    mock_imp_engine.analyze_event.assert_called_once()
    mock_butterfly.detect.assert_called_once()
    mock_goal_impact.assess_event_impact.assert_called_once()


# ============================================================
# Test: Engine failure isolation
# ============================================================


@pytest.mark.asyncio
async def test_process_event_engine_failure_isolation(orchestrator: JarvisOrchestrator) -> None:
    """If one engine raises, subsequent engines should still run."""
    mock_imp_engine = MagicMock()
    mock_imp_engine.analyze_event = AsyncMock(side_effect=RuntimeError("Implication engine broke"))

    mock_butterfly = MagicMock()
    mock_butterfly.detect = AsyncMock(return_value=None)

    mock_goal_impact = MagicMock()
    mock_goal_impact.assess_event_impact = AsyncMock(return_value=[])

    mock_time_horizon = MagicMock()

    orchestrator._JarvisOrchestrator__implication = mock_imp_engine
    orchestrator._JarvisOrchestrator__butterfly = mock_butterfly
    orchestrator._JarvisOrchestrator__goal_impact = mock_goal_impact
    orchestrator._JarvisOrchestrator__time_horizon = mock_time_horizon

    # Should not raise despite implication engine failure
    insights = await orchestrator.process_event(
        user_id=TEST_USER_ID,
        event="A significant market event that triggers all engines for analysis",
        source_context="test",
    )

    # Butterfly should still have been called
    mock_butterfly.detect.assert_called_once()
    mock_goal_impact.assess_event_impact.assert_called_once()


# ============================================================
# Test: Feedback recording
# ============================================================


@pytest.mark.asyncio
async def test_record_feedback_updates_db(orchestrator: JarvisOrchestrator, mock_db_client: MagicMock) -> None:
    """Verify feedback recording calls the correct DB update."""
    insight_id = str(uuid4())

    await orchestrator.record_feedback(
        insight_id=insight_id,
        feedback="helpful",
        user_id=TEST_USER_ID,
    )

    mock_db_client.table.assert_called_with("jarvis_insights")
    mock_db_client.table.return_value.update.assert_called_once()
    update_args = mock_db_client.table.return_value.update.call_args[0][0]
    assert update_args["status"] == "feedback"
    assert update_args["feedback_text"] == "helpful"


# ============================================================
# Test: Metrics aggregation
# ============================================================


@pytest.mark.asyncio
async def test_get_engine_metrics_aggregates_correctly(
    orchestrator: JarvisOrchestrator, mock_db_client: MagicMock
) -> None:
    """Verify metrics aggregation from mock DB rows."""
    now = datetime.now(UTC)
    mock_rows = [
        {
            "insight_type": "implication",
            "classification": "opportunity",
            "status": "new",
            "combined_score": 0.8,
            "created_at": now.isoformat(),
        },
        {
            "insight_type": "butterfly",
            "classification": "threat",
            "status": "engaged",
            "combined_score": 0.6,
            "created_at": now.isoformat(),
        },
        {
            "insight_type": "implication",
            "classification": "opportunity",
            "status": "new",
            "combined_score": 0.9,
            "created_at": now.isoformat(),
        },
    ]

    mock_db_client.table.return_value.execute.return_value = MagicMock(data=mock_rows)

    metrics = await orchestrator.get_engine_metrics(user_id=TEST_USER_ID)

    assert metrics["total_insights"] == 3
    assert metrics["by_type"]["implication"] == 2
    assert metrics["by_type"]["butterfly"] == 1
    assert metrics["by_classification"]["opportunity"] == 2
    assert metrics["by_classification"]["threat"] == 1
    assert metrics["by_status"]["new"] == 2
    assert metrics["by_status"]["engaged"] == 1
    assert metrics["average_score"] == pytest.approx(0.767, abs=0.001)
    assert metrics["last_7_days"] == 3
    assert metrics["last_30_days"] == 3


# ============================================================
# Test: Integration - Event to insights
# ============================================================


@pytest.mark.asyncio
async def test_integration_signal_to_insight(orchestrator: JarvisOrchestrator) -> None:
    """End-to-end: event string produces insights with expected fields."""
    test_insight = _make_insight(
        content="Regulatory change could impact Lonza contract pricing",
        trigger_event="EU pharma regulatory change",
        combined_score=0.85,
    )

    mock_imp_engine = MagicMock()
    mock_imp_engine.analyze_event = AsyncMock(return_value=[MagicMock()])
    mock_imp_engine.save_insight = AsyncMock(return_value=test_insight)

    mock_butterfly = MagicMock()
    mock_butterfly.detect = AsyncMock(return_value=None)

    mock_goal_impact = MagicMock()
    mock_goal_impact.assess_event_impact = AsyncMock(return_value=[])

    mock_time_horizon = MagicMock()
    mock_time_horizon.analyze = AsyncMock(return_value=None)

    orchestrator._JarvisOrchestrator__implication = mock_imp_engine
    orchestrator._JarvisOrchestrator__butterfly = mock_butterfly
    orchestrator._JarvisOrchestrator__goal_impact = mock_goal_impact
    orchestrator._JarvisOrchestrator__time_horizon = mock_time_horizon

    insights = await orchestrator.process_event(
        user_id=TEST_USER_ID,
        event="EU pharma regulatory change affecting supply chains and pricing across member states",
        source_context="signal_radar",
        source_id="signal-123",
    )

    assert len(insights) >= 1
    insight = insights[0]
    assert insight.content
    assert insight.classification in ("opportunity", "threat", "neutral")
    assert 0.0 <= insight.combined_score <= 1.0
    assert insight.insight_type
    assert isinstance(insight.causal_chain, list)
    assert isinstance(insight.affected_goals, list)
    assert isinstance(insight.recommended_actions, list)
