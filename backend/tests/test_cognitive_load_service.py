"""Tests for CognitiveLoadMonitor service."""

from unittest.mock import MagicMock

import pytest


class TestMessageBrevityCalculation:
    """Tests for message brevity factor calculation."""

    def test_very_short_message_high_brevity(self) -> None:
        """Messages under 20 chars should score 1.0 (high load indicator)."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        score = monitor._normalize_brevity(avg_length=10)
        assert score == 1.0

    def test_long_message_low_brevity(self) -> None:
        """Messages over 200 chars should score 0.0 (low load indicator)."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        score = monitor._normalize_brevity(avg_length=250)
        assert score == 0.0

    def test_medium_message_proportional_brevity(self) -> None:
        """Messages of 110 chars (midpoint) should score ~0.5."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        score = monitor._normalize_brevity(avg_length=110)
        assert 0.45 <= score <= 0.55


class TestTypoRateCalculation:
    """Tests for typo rate factor calculation."""

    def test_no_messages_zero_typo_rate(self) -> None:
        """Empty message list should return 0.0."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        score = monitor._calculate_typo_rate(messages=[])
        assert score == 0.0

    def test_correction_marker_increases_typo_rate(self) -> None:
        """Messages starting with * (correction) should increase typo rate."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        messages = [
            {"content": "I need help"},
            {"content": "*I meant help with"},
        ]
        score = monitor._calculate_typo_rate(messages=messages)
        assert score > 0.0

    def test_repeated_chars_increases_typo_rate(self) -> None:
        """Repeated characters (like 'helllp') indicate rushed typing."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        messages = [
            {"content": "helllp me please"},
            {"content": "I'm stresssed"},
        ]
        score = monitor._calculate_typo_rate(messages=messages)
        assert score > 0.0

    def test_clean_messages_low_typo_rate(self) -> None:
        """Clean messages without errors should score low."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        messages = [
            {"content": "Can you help me with a sales report?"},
            {"content": "I need data for Q4 performance."},
        ]
        score = monitor._calculate_typo_rate(messages=messages)
        assert score == 0.0


class TestMessageVelocityCalculation:
    """Tests for message velocity factor calculation."""

    def test_single_message_zero_velocity(self) -> None:
        """Single message cannot have velocity."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        messages = [{"content": "Hello", "created_at": "2026-02-03T12:00:00Z"}]
        score = monitor._calculate_velocity(messages=messages)
        assert score == 0.0

    def test_rapid_messages_high_velocity(self) -> None:
        """Messages < 5 seconds apart should score 1.0."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        messages = [
            {"content": "Help", "created_at": "2026-02-03T12:00:00Z"},
            {"content": "Now", "created_at": "2026-02-03T12:00:02Z"},
            {"content": "Please", "created_at": "2026-02-03T12:00:04Z"},
        ]
        score = monitor._calculate_velocity(messages=messages)
        assert score == 1.0

    def test_relaxed_messages_low_velocity(self) -> None:
        """Messages > 60 seconds apart should score 0.0."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        messages = [
            {"content": "Hello", "created_at": "2026-02-03T12:00:00Z"},
            {"content": "World", "created_at": "2026-02-03T12:02:00Z"},
        ]
        score = monitor._calculate_velocity(messages=messages)
        assert score == 0.0


class TestTimeOfDayFactor:
    """Tests for time of day factor calculation."""

    def test_late_night_high_factor(self) -> None:
        """Late night (10pm-6am) should score 0.8."""
        from datetime import datetime
        from unittest.mock import patch

        from src.intelligence.cognitive_load import CognitiveLoadMonitor

        monitor = CognitiveLoadMonitor(db_client=MagicMock())

        with patch("src.intelligence.cognitive_load.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 3, 23, 0)  # 11pm
            score = monitor._time_of_day_factor()

        assert score == 0.8

    def test_core_hours_low_factor(self) -> None:
        """Core hours (8am-6pm) should score 0.2."""
        from datetime import datetime
        from unittest.mock import patch

        from src.intelligence.cognitive_load import CognitiveLoadMonitor

        monitor = CognitiveLoadMonitor(db_client=MagicMock())

        with patch("src.intelligence.cognitive_load.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 3, 14, 0)  # 2pm
            score = monitor._time_of_day_factor()

        assert score == 0.2


class TestWeightedScoreCalculation:
    """Tests for the weighted score formula."""

    def test_all_zeros_gives_zero(self) -> None:
        """All factors at 0 should give score near 0."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        factors = {
            "message_brevity": 0.0,
            "typo_rate": 0.0,
            "message_velocity": 0.0,
            "calendar_density": 0.0,
            "time_of_day": 0.0,
        }
        score = monitor._calculate_weighted_score(factors)
        assert score == 0.0

    def test_all_ones_gives_one(self) -> None:
        """All factors at 1 should give score of 1."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        factors = {
            "message_brevity": 1.0,
            "typo_rate": 1.0,
            "message_velocity": 1.0,
            "calendar_density": 1.0,
            "time_of_day": 1.0,
        }
        score = monitor._calculate_weighted_score(factors)
        assert score == 1.0

    def test_weights_sum_to_one(self) -> None:
        """WEIGHTS should sum to 1.0."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        total = sum(monitor.WEIGHTS.values())
        assert abs(total - 1.0) < 0.001


class TestLoadLevelDetermination:
    """Tests for determining load level from score."""

    def test_low_threshold(self) -> None:
        """Score < 0.3 should be LOW."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor
        from src.models.cognitive_load import LoadLevel

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        level = monitor._determine_level(score=0.25)
        assert level == LoadLevel.LOW

    def test_medium_threshold(self) -> None:
        """Score 0.3-0.5 should be MEDIUM."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor
        from src.models.cognitive_load import LoadLevel

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        level = monitor._determine_level(score=0.4)
        assert level == LoadLevel.MEDIUM

    def test_high_threshold(self) -> None:
        """Score 0.5-0.7 should be HIGH."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor
        from src.models.cognitive_load import LoadLevel

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        level = monitor._determine_level(score=0.6)
        assert level == LoadLevel.HIGH

    def test_critical_threshold(self) -> None:
        """Score > 0.85 should be CRITICAL."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor
        from src.models.cognitive_load import LoadLevel

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        level = monitor._determine_level(score=0.9)
        assert level == LoadLevel.CRITICAL


class TestRecommendationGeneration:
    """Tests for response style recommendations."""

    def test_low_load_detailed_recommendation(self) -> None:
        """LOW load should recommend detailed responses."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor
        from src.models.cognitive_load import LoadLevel

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        rec = monitor._get_recommendation(level=LoadLevel.LOW, factors={})
        assert rec == "detailed"

    def test_high_load_concise_recommendation(self) -> None:
        """HIGH load should recommend concise responses."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor
        from src.models.cognitive_load import LoadLevel

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        rec = monitor._get_recommendation(level=LoadLevel.HIGH, factors={})
        assert rec == "concise"

    def test_critical_load_urgent_recommendation(self) -> None:
        """CRITICAL load should recommend concise_urgent responses."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor
        from src.models.cognitive_load import LoadLevel

        monitor = CognitiveLoadMonitor(db_client=MagicMock())
        rec = monitor._get_recommendation(level=LoadLevel.CRITICAL, factors={})
        assert rec == "concise_urgent"


class TestEstimateLoadIntegration:
    """Integration tests for the estimate_load method."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock Supabase client for integration tests."""
        mock = MagicMock()
        # Mock the chained query builder pattern for insert
        mock.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "snapshot-123"}]
        )
        return mock

    @pytest.mark.asyncio
    async def test_estimate_load_returns_cognitive_load_state(self, mock_db: MagicMock) -> None:
        """estimate_load should return a CognitiveLoadState."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor
        from src.models.cognitive_load import CognitiveLoadState

        monitor = CognitiveLoadMonitor(db_client=mock_db)
        messages = [
            {"content": "Hello", "created_at": "2026-02-03T12:00:00Z"},
            {"content": "World", "created_at": "2026-02-03T12:00:30Z"},
        ]

        result = await monitor.estimate_load(
            user_id="user-123",
            recent_messages=messages,
            session_id="session-456",
            calendar_density=0.5,
        )

        assert isinstance(result, CognitiveLoadState)
        assert 0.0 <= result.score <= 1.0
        assert result.recommendation in ["detailed", "balanced", "concise", "concise_urgent"]

    @pytest.mark.asyncio
    async def test_estimate_load_stores_snapshot(self, mock_db: MagicMock) -> None:
        """estimate_load should store a snapshot in the database."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor

        monitor = CognitiveLoadMonitor(db_client=mock_db)
        messages = [
            {"content": "Help me please!", "created_at": "2026-02-03T12:00:00Z"},
        ]

        await monitor.estimate_load(
            user_id="user-123",
            recent_messages=messages,
            session_id="session-456",
            calendar_density=0.3,
        )

        # Verify insert was called on cognitive_load_snapshots
        mock_db.table.assert_any_call("cognitive_load_snapshots")


class TestGetCurrentLoad:
    """Tests for retrieving current cognitive load."""

    @pytest.fixture
    def mock_db_with_snapshot(self) -> MagicMock:
        """Create mock DB with existing snapshot."""
        mock = MagicMock()
        snapshot_data = {
            "id": "snapshot-123",
            "user_id": "user-123",
            "load_level": "medium",
            "load_score": 0.45,
            "factors": {"message_brevity": 0.5, "typo_rate": 0.2},
            "session_id": "session-456",
            "measured_at": "2026-02-03T12:00:00Z",
        }
        mock.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[snapshot_data]
        )
        return mock

    @pytest.mark.asyncio
    async def test_get_current_load_returns_state(self, mock_db_with_snapshot: MagicMock) -> None:
        """get_current_load should return the most recent load state."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor
        from src.models.cognitive_load import CognitiveLoadState

        monitor = CognitiveLoadMonitor(db_client=mock_db_with_snapshot)

        result = await monitor.get_current_load(user_id="user-123")

        assert result is not None
        assert isinstance(result, CognitiveLoadState)

    @pytest.fixture
    def mock_db_empty(self) -> MagicMock:
        """Create mock DB with no snapshots."""
        mock = MagicMock()
        mock.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[]
        )
        return mock

    @pytest.mark.asyncio
    async def test_get_current_load_returns_none_if_no_data(self, mock_db_empty: MagicMock) -> None:
        """get_current_load should return None if no snapshots exist."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor

        monitor = CognitiveLoadMonitor(db_client=mock_db_empty)

        result = await monitor.get_current_load(user_id="user-123")

        assert result is None


class TestGetLoadHistory:
    """Tests for retrieving cognitive load history."""

    @pytest.fixture
    def mock_db_with_history(self) -> MagicMock:
        """Create mock DB with multiple snapshots."""
        mock = MagicMock()
        history_data = [
            {
                "id": "snapshot-1",
                "user_id": "user-123",
                "load_level": "low",
                "load_score": 0.2,
                "factors": {},
                "session_id": "session-1",
                "measured_at": "2026-02-03T12:00:00Z",
            },
            {
                "id": "snapshot-2",
                "user_id": "user-123",
                "load_level": "medium",
                "load_score": 0.4,
                "factors": {},
                "session_id": "session-2",
                "measured_at": "2026-02-03T11:00:00Z",
            },
        ]
        mock.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=history_data
        )
        return mock

    @pytest.mark.asyncio
    async def test_get_load_history_returns_list(self, mock_db_with_history: MagicMock) -> None:
        """get_load_history should return a list of snapshots."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor

        monitor = CognitiveLoadMonitor(db_client=mock_db_with_history)

        result = await monitor.get_load_history(user_id="user-123", limit=10)

        assert isinstance(result, list)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_load_history_respects_limit(self, mock_db_with_history: MagicMock) -> None:
        """get_load_history should respect the limit parameter."""
        from src.intelligence.cognitive_load import CognitiveLoadMonitor

        monitor = CognitiveLoadMonitor(db_client=mock_db_with_history)

        await monitor.get_load_history(user_id="user-123", limit=5)

        # Verify limit was called with correct value
        mock_db_with_history.table.return_value.select.return_value.eq.return_value.order.return_value.limit.assert_called_with(
            5
        )


class TestModuleExports:
    """Tests for module-level exports."""

    def test_cognitive_load_monitor_exported_from_intelligence(self) -> None:
        """CognitiveLoadMonitor should be importable from src.intelligence."""
        from src.intelligence import CognitiveLoadMonitor

        assert CognitiveLoadMonitor is not None
