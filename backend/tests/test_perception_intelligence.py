"""Tests for perception intelligence service.

Covers all 4 public methods with mock Raven-1 analysis data:
- process_perception_analysis
- calculate_meeting_quality_score
- generate_perception_insights
- feed_to_conversion_scoring
"""

from unittest.mock import MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_db() -> MagicMock:
    """Create mock Supabase client."""
    return MagicMock()


def _make_raven_analysis(
    engagement: float = 0.85,
    attention: float = 0.80,
    sentiment: str = "positive",
    confusion_events: int = 1,
    disengagement_events: int = 0,
) -> dict:
    """Build a mock Raven-1 perception_analysis payload."""
    return {
        "engagement_score": engagement,
        "attention_level": attention,
        "sentiment": sentiment,
        "confusion_events": confusion_events,
        "disengagement_events": disengagement_events,
        "confused_topics": ["pricing"] if confusion_events > 0 else [],
        "engagement_trend": "stable",
    }


def _make_session_row(
    session_id: str = "sess-001",
    user_id: str = "user-001",
    lead_id: str | None = "lead-001",
    started_at: str = "2026-02-16T14:00:00+00:00",
    ended_at: str = "2026-02-16T14:25:00+00:00",
    perception_analysis: dict | None = None,
    perception_events: list | None = None,
) -> dict:
    return {
        "id": session_id,
        "user_id": user_id,
        "lead_id": lead_id,
        "started_at": started_at,
        "ended_at": ended_at,
        "perception_analysis": perception_analysis or _make_raven_analysis(),
        "perception_events": perception_events or [],
    }


# ─────────────────────────────────────────────────────────────────────────────
# process_perception_analysis
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_process_perception_analysis_with_lead(mock_db: MagicMock) -> None:
    """When session is linked to a lead, updates health score and creates events."""
    session = _make_session_row()
    analysis = _make_raven_analysis(engagement=0.85, sentiment="positive")

    # Mock video_sessions select
    session_select = MagicMock()
    session_select.data = [session]

    # Mock lead_memories select for health score update
    lead_select = MagicMock()
    lead_select.data = [{"health_score": 60}]

    # Track insert/update calls
    insert_result = MagicMock()
    insert_result.data = [{}]
    update_result = MagicMock()
    update_result.data = [{}]

    def table_side_effect(table_name: str) -> MagicMock:
        mock_table = MagicMock()
        if table_name == "video_sessions":
            mock_table.select.return_value.eq.return_value.execute.return_value = session_select
        elif table_name == "lead_memories":
            mock_table.select.return_value.eq.return_value.execute.return_value = lead_select
            mock_table.update.return_value.eq.return_value.execute.return_value = update_result
        elif table_name in ("lead_memory_events", "aria_activity", "health_score_history"):
            mock_table.insert.return_value.execute.return_value = insert_result
        elif table_name == "lead_memory_stakeholders":
            mock_table.update.return_value.eq.return_value.execute.return_value = update_result
        return mock_table

    mock_db.table.side_effect = table_side_effect

    with patch("src.services.perception_intelligence.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.perception_intelligence import PerceptionIntelligenceService

        service = PerceptionIntelligenceService()
        result = await service.process_perception_analysis("sess-001", analysis)

    assert result is not None
    assert result["session_id"] == "sess-001"
    assert result["lead_id"] == "lead-001"
    assert result["engagement"] == 0.85
    assert result["health_score_updated"] is True
    assert 0 <= result["quality_score"] <= 100


@pytest.mark.asyncio
async def test_process_perception_analysis_no_lead(mock_db: MagicMock) -> None:
    """When session has no lead, processes but skips lead updates."""
    session = _make_session_row(lead_id=None)
    analysis = _make_raven_analysis()

    session_select = MagicMock()
    session_select.data = [session]

    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        session_select
    )

    with patch("src.services.perception_intelligence.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.perception_intelligence import PerceptionIntelligenceService

        service = PerceptionIntelligenceService()
        result = await service.process_perception_analysis("sess-001", analysis)

    assert result is not None
    assert result["lead_id"] is None
    assert "health_score_updated" not in result


@pytest.mark.asyncio
async def test_process_perception_analysis_session_not_found(mock_db: MagicMock) -> None:
    """Returns None when video session doesn't exist."""
    session_select = MagicMock()
    session_select.data = []

    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        session_select
    )

    with patch("src.services.perception_intelligence.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.perception_intelligence import PerceptionIntelligenceService

        service = PerceptionIntelligenceService()
        result = await service.process_perception_analysis("nonexistent", {})

    assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# calculate_meeting_quality_score
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_quality_score_high_engagement() -> None:
    """High engagement + low confusion = high quality score."""
    session = _make_session_row(
        perception_analysis=_make_raven_analysis(
            engagement=0.95,
            attention=0.90,
            confusion_events=0,
            disengagement_events=0,
        ),
    )

    mock_db = MagicMock()
    select_result = MagicMock()
    select_result.data = [session]
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        select_result
    )

    with patch("src.services.perception_intelligence.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.perception_intelligence import PerceptionIntelligenceService

        service = PerceptionIntelligenceService()
        score = await service.calculate_meeting_quality_score("sess-001")

    # 0.95*40 + 0.90*25 + 20 (no events) + duration component
    assert score >= 70


@pytest.mark.asyncio
async def test_quality_score_low_engagement_high_confusion() -> None:
    """Low engagement + many confusion events = low quality score."""
    session = _make_session_row(
        perception_analysis=_make_raven_analysis(
            engagement=0.3,
            attention=0.25,
            confusion_events=5,
            disengagement_events=3,
        ),
    )

    mock_db = MagicMock()
    select_result = MagicMock()
    select_result.data = [session]
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        select_result
    )

    with patch("src.services.perception_intelligence.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.perception_intelligence import PerceptionIntelligenceService

        service = PerceptionIntelligenceService()
        score = await service.calculate_meeting_quality_score("sess-001")

    assert score <= 40


@pytest.mark.asyncio
async def test_quality_score_session_not_found() -> None:
    """Returns 50 (neutral) when session not found."""
    mock_db = MagicMock()
    select_result = MagicMock()
    select_result.data = []
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        select_result
    )

    with patch("src.services.perception_intelligence.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.perception_intelligence import PerceptionIntelligenceService

        service = PerceptionIntelligenceService()
        score = await service.calculate_meeting_quality_score("nonexistent")

    assert score == 50


# ─────────────────────────────────────────────────────────────────────────────
# generate_perception_insights
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_insights_high_engagement() -> None:
    """High engagement generates positive insight."""
    session = _make_session_row(
        perception_analysis=_make_raven_analysis(
            engagement=0.88,
            sentiment="positive",
            confusion_events=0,
        ),
    )

    mock_db = MagicMock()
    select_result = MagicMock()
    select_result.data = [session]
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        select_result
    )

    with patch("src.services.perception_intelligence.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.perception_intelligence import PerceptionIntelligenceService

        service = PerceptionIntelligenceService()
        insights = await service.generate_perception_insights("sess-001")

    assert len(insights) > 0
    assert any("highly engaged" in i for i in insights)
    assert any("positive" in i.lower() or "momentum" in i.lower() for i in insights)


@pytest.mark.asyncio
async def test_insights_confusion_detected() -> None:
    """Confusion topics generate clarification insights."""
    analysis = _make_raven_analysis(
        engagement=0.5,
        confusion_events=2,
        sentiment="neutral",
    )
    analysis["confused_topics"] = ["pricing", "timeline"]

    session = _make_session_row(perception_analysis=analysis)

    mock_db = MagicMock()
    select_result = MagicMock()
    select_result.data = [session]
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        select_result
    )

    with patch("src.services.perception_intelligence.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.perception_intelligence import PerceptionIntelligenceService

        service = PerceptionIntelligenceService()
        insights = await service.generate_perception_insights("sess-001")

    assert any("confusion" in i.lower() or "pricing" in i.lower() for i in insights)


@pytest.mark.asyncio
async def test_insights_declining_engagement() -> None:
    """Declining engagement trend generates warning insight."""
    analysis = _make_raven_analysis(engagement=0.5)
    analysis["engagement_trend"] = "declining"

    session = _make_session_row(
        perception_analysis=analysis,
        started_at="2026-02-16T14:00:00+00:00",
        ended_at="2026-02-16T14:50:00+00:00",  # 50 min session
    )

    mock_db = MagicMock()
    select_result = MagicMock()
    select_result.data = [session]
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        select_result
    )

    with patch("src.services.perception_intelligence.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.perception_intelligence import PerceptionIntelligenceService

        service = PerceptionIntelligenceService()
        insights = await service.generate_perception_insights("sess-001")

    assert any("declined" in i.lower() or "declining" in i.lower() for i in insights)


@pytest.mark.asyncio
async def test_insights_negative_sentiment() -> None:
    """Negative sentiment generates skepticism insight."""
    session = _make_session_row(
        perception_analysis=_make_raven_analysis(
            engagement=0.4,
            sentiment="negative",
        ),
    )

    mock_db = MagicMock()
    select_result = MagicMock()
    select_result.data = [session]
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        select_result
    )

    with patch("src.services.perception_intelligence.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.perception_intelligence import PerceptionIntelligenceService

        service = PerceptionIntelligenceService()
        insights = await service.generate_perception_insights("sess-001")

    assert any("skepticism" in i.lower() or "negative" in i.lower() for i in insights)


@pytest.mark.asyncio
async def test_insights_empty_for_missing_session() -> None:
    """Returns empty list when session not found."""
    mock_db = MagicMock()
    select_result = MagicMock()
    select_result.data = []
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        select_result
    )

    with patch("src.services.perception_intelligence.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.perception_intelligence import PerceptionIntelligenceService

        service = PerceptionIntelligenceService()
        insights = await service.generate_perception_insights("nonexistent")

    assert insights == []


# ─────────────────────────────────────────────────────────────────────────────
# feed_to_conversion_scoring
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_conversion_features_with_sessions() -> None:
    """Computes correct perception features from multiple sessions."""
    sessions = [
        _make_session_row(
            session_id="sess-001",
            perception_analysis=_make_raven_analysis(
                engagement=0.9, sentiment="positive", confusion_events=0,
            ),
            perception_events=[],
        ),
        _make_session_row(
            session_id="sess-002",
            perception_analysis=_make_raven_analysis(
                engagement=0.7, sentiment="positive", confusion_events=2,
            ),
            perception_events=[
                {"tool_name": "adapt_to_confusion"},
                {"tool_name": "adapt_to_confusion"},
            ],
        ),
        _make_session_row(
            session_id="sess-003",
            perception_analysis=_make_raven_analysis(
                engagement=0.6, sentiment="neutral", confusion_events=1,
            ),
            perception_events=[{"tool_name": "adapt_to_confusion"}],
        ),
    ]

    mock_db = MagicMock()
    select_result = MagicMock()
    select_result.data = sessions

    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = (
        select_result
    )

    with patch("src.services.perception_intelligence.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.perception_intelligence import PerceptionIntelligenceService

        service = PerceptionIntelligenceService()
        features = await service.feed_to_conversion_scoring("lead-001")

    # Average engagement: (0.9 + 0.7 + 0.6) / 3 ≈ 0.733
    assert 0.7 <= features["avg_meeting_engagement"] <= 0.8

    # 2 positive vs 0 negative → positive trajectory
    assert features["emotional_trajectory_positive"] is True

    # Confusion exists but moderate → moderate score
    assert 0.0 <= features["confusion_frequency"] <= 1.0


@pytest.mark.asyncio
async def test_conversion_features_no_sessions() -> None:
    """Returns neutral defaults when no sessions exist."""
    mock_db = MagicMock()
    select_result = MagicMock()
    select_result.data = []

    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = (
        select_result
    )

    with patch("src.services.perception_intelligence.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.perception_intelligence import PerceptionIntelligenceService

        service = PerceptionIntelligenceService()
        features = await service.feed_to_conversion_scoring("lead-no-sessions")

    assert features["avg_meeting_engagement"] == 0.5
    assert features["emotional_trajectory_positive"] is True
    assert features["confusion_frequency"] == 1.0


@pytest.mark.asyncio
async def test_conversion_features_negative_trajectory() -> None:
    """Negative majority → emotional_trajectory_positive is False."""
    sessions = [
        _make_session_row(
            session_id=f"sess-{i}",
            perception_analysis=_make_raven_analysis(
                engagement=0.4, sentiment="negative", confusion_events=3,
            ),
        )
        for i in range(3)
    ]

    mock_db = MagicMock()
    select_result = MagicMock()
    select_result.data = sessions

    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = (
        select_result
    )

    with patch("src.services.perception_intelligence.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.perception_intelligence import PerceptionIntelligenceService

        service = PerceptionIntelligenceService()
        features = await service.feed_to_conversion_scoring("lead-negative")

    assert features["emotional_trajectory_positive"] is False
    assert features["avg_meeting_engagement"] < 0.5


# ─────────────────────────────────────────────────────────────────────────────
# Quality score computation (unit-level)
# ─────────────────────────────────────────────────────────────────────────────


def test_compute_quality_score_perfect_session() -> None:
    """Perfect engagement + attention + no events = high score."""
    with patch("src.services.perception_intelligence.SupabaseClient"):
        from src.services.perception_intelligence import PerceptionIntelligenceService

        service = PerceptionIntelligenceService()
        score = service._compute_quality_score(
            engagement=1.0,
            attention=1.0,
            confusion_events=0,
            disengagement_events=0,
            session={
                "started_at": "2026-02-16T14:00:00+00:00",
                "ended_at": "2026-02-16T14:20:00+00:00",
            },
        )

    # 40 + 25 + 20 + 15 = 100
    assert score == 100


def test_compute_quality_score_terrible_session() -> None:
    """Zero engagement + many events = low score."""
    with patch("src.services.perception_intelligence.SupabaseClient"):
        from src.services.perception_intelligence import PerceptionIntelligenceService

        service = PerceptionIntelligenceService()
        score = service._compute_quality_score(
            engagement=0.0,
            attention=0.0,
            confusion_events=5,
            disengagement_events=5,
            session={
                "started_at": "2026-02-16T14:00:00+00:00",
                "ended_at": "2026-02-16T14:01:00+00:00",  # very short
            },
        )

    assert score <= 10


def test_compute_quality_score_no_duration() -> None:
    """Missing timestamps use neutral duration component."""
    with patch("src.services.perception_intelligence.SupabaseClient"):
        from src.services.perception_intelligence import PerceptionIntelligenceService

        service = PerceptionIntelligenceService()
        score = service._compute_quality_score(
            engagement=0.7,
            attention=0.7,
            confusion_events=1,
            disengagement_events=0,
            session={},
        )

    # 28 + 17.5 + 17 + 10 (neutral) = 72.5
    assert 70 <= score <= 75
