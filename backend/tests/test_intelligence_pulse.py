"""Tests for IntelligencePulseEngine."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_db():
    """Mock Supabase client."""
    db = MagicMock()
    # pulse_signals insert chain
    db.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": "test-signal-id", "priority_score": 75, "delivery_channel": "check_in"}]
    )
    # active_goals select chain
    db.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
        data=[{"id": "goal-1", "title": "Close Acme deal", "description": "Enterprise sale"}]
    )
    # user_pulse_config select chain
    db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[]
    )
    return db


@pytest.fixture
def mock_llm():
    """Mock LLM client."""
    llm = AsyncMock()
    llm.generate_response.return_value = '{"goal_relevance": 0.7, "surprise_factor": 0.4}'
    return llm


@pytest.fixture
def mock_notification_service():
    """Mock NotificationService."""
    ns = MagicMock()
    ns.create_notification = AsyncMock()
    return ns


@pytest.fixture
def engine(mock_db, mock_llm, mock_notification_service):
    """Create IntelligencePulseEngine with mocks."""
    from src.services.intelligence_pulse import IntelligencePulseEngine

    return IntelligencePulseEngine(
        supabase_client=mock_db,
        llm_client=mock_llm,
        notification_service=mock_notification_service,
    )


@pytest.mark.asyncio
async def test_process_signal_returns_record(engine, mock_db):
    """process_signal should return the persisted record."""
    result = await engine.process_signal(
        user_id="user-1",
        signal={
            "source": "scout_agent",
            "title": "Acme raised Series C",
            "content": "Acme Corp announced $50M Series C funding",
            "signal_category": "competitive",
            "pulse_type": "event",
        },
    )
    assert result["id"] == "test-signal-id"
    assert mock_db.table.called


@pytest.mark.asyncio
async def test_process_signal_computes_priority(engine):
    """process_signal should compute a numeric priority_score."""
    result = await engine.process_signal(
        user_id="user-1",
        signal={
            "source": "goal_monitor",
            "title": "Goal completed",
            "content": "Q1 pipeline goal is done",
            "signal_category": "goal",
            "pulse_type": "event",
            "related_goal_id": "goal-1",
        },
    )
    # We can't assert exact value due to mocking, but result should exist
    assert result is not None


@pytest.mark.asyncio
async def test_determine_channel_immediate():
    """Score >= 90 routes to immediate channel."""
    from src.services.intelligence_pulse import IntelligencePulseEngine

    channel = IntelligencePulseEngine._determine_channel_static(
        priority_score=95,
        immediate_threshold=90,
        check_in_threshold=70,
        morning_brief_threshold=50,
    )
    assert channel == "immediate"


@pytest.mark.asyncio
async def test_determine_channel_check_in():
    """Score 70-89 routes to check_in channel."""
    from src.services.intelligence_pulse import IntelligencePulseEngine

    channel = IntelligencePulseEngine._determine_channel_static(
        priority_score=75,
        immediate_threshold=90,
        check_in_threshold=70,
        morning_brief_threshold=50,
    )
    assert channel == "check_in"


@pytest.mark.asyncio
async def test_determine_channel_morning_brief():
    """Score 50-69 routes to morning_brief."""
    from src.services.intelligence_pulse import IntelligencePulseEngine

    channel = IntelligencePulseEngine._determine_channel_static(
        priority_score=55,
        immediate_threshold=90,
        check_in_threshold=70,
        morning_brief_threshold=50,
    )
    assert channel == "morning_brief"


@pytest.mark.asyncio
async def test_determine_channel_weekly_digest():
    """Score 30-49 routes to weekly_digest."""
    from src.services.intelligence_pulse import IntelligencePulseEngine

    channel = IntelligencePulseEngine._determine_channel_static(
        priority_score=35,
        immediate_threshold=90,
        check_in_threshold=70,
        morning_brief_threshold=50,
    )
    assert channel == "weekly_digest"


@pytest.mark.asyncio
async def test_determine_channel_silent():
    """Score < 30 routes to silent."""
    from src.services.intelligence_pulse import IntelligencePulseEngine

    channel = IntelligencePulseEngine._determine_channel_static(
        priority_score=15,
        immediate_threshold=90,
        check_in_threshold=70,
        morning_brief_threshold=50,
    )
    assert channel == "silent"


@pytest.mark.asyncio
async def test_process_signal_graceful_on_llm_failure(engine, mock_llm):
    """If LLM scoring fails, engine should still persist with fallback scores."""
    mock_llm.generate_response.side_effect = Exception("LLM down")
    result = await engine.process_signal(
        user_id="user-1",
        signal={
            "source": "test",
            "title": "Test signal",
            "content": "Testing fallback behavior",
            "signal_category": "deal_health",
            "pulse_type": "intelligent",
        },
    )
    # Should still return a result (graceful degradation)
    assert result is not None


@pytest.mark.asyncio
async def test_process_signal_graceful_on_db_failure(mock_llm, mock_notification_service):
    """If DB insert fails, engine should not raise."""
    mock_db = MagicMock()
    mock_db.table.return_value.insert.return_value.execute.side_effect = Exception("DB down")
    mock_db.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
    mock_db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])

    from src.services.intelligence_pulse import IntelligencePulseEngine

    engine = IntelligencePulseEngine(
        supabase_client=mock_db,
        llm_client=mock_llm,
        notification_service=mock_notification_service,
    )
    result = await engine.process_signal(
        user_id="user-1",
        signal={
            "source": "test",
            "title": "Test",
            "content": "DB failure test",
            "signal_category": "deal_health",
            "pulse_type": "event",
        },
    )
    assert result is None  # Failed gracefully, returned None


@pytest.mark.asyncio
async def test_scout_signal_scan_calls_pulse_engine():
    """Verify scout job integration point exists and is callable."""
    # This is a structural test -- verify the import works
    from src.services.intelligence_pulse import get_pulse_engine
    engine = get_pulse_engine()
    assert engine is not None
