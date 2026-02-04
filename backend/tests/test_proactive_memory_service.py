"""Tests for ProactiveMemoryService."""

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestProactiveMemoryServiceInit:
    """Tests for ProactiveMemoryService initialization."""

    def test_service_has_configurable_threshold(self) -> None:
        """Service should have configurable surfacing threshold."""
        from src.intelligence.proactive_memory import ProactiveMemoryService

        service = ProactiveMemoryService(db_client=MagicMock())
        assert hasattr(service, "SURFACING_THRESHOLD")
        assert 0.0 <= service.SURFACING_THRESHOLD <= 1.0

    def test_service_has_max_insights_limit(self) -> None:
        """Service should limit insights per response."""
        from src.intelligence.proactive_memory import ProactiveMemoryService

        service = ProactiveMemoryService(db_client=MagicMock())
        assert hasattr(service, "MAX_INSIGHTS_PER_RESPONSE")
        assert service.MAX_INSIGHTS_PER_RESPONSE == 2

    def test_service_has_cooldown_hours(self) -> None:
        """Service should have cooldown period for insights."""
        from src.intelligence.proactive_memory import ProactiveMemoryService

        service = ProactiveMemoryService(db_client=MagicMock())
        assert hasattr(service, "COOLDOWN_HOURS")
        assert service.COOLDOWN_HOURS >= 1


class TestRelevanceScoring:
    """Tests for relevance scoring logic."""

    def test_calculate_base_relevance_with_salience(self) -> None:
        """Base relevance should incorporate salience."""
        from src.intelligence.proactive_memory import ProactiveMemoryService

        service = ProactiveMemoryService(db_client=MagicMock())

        score = service._calculate_base_relevance(
            topic_overlap=0.5,
            salience=0.8,
        )

        assert score == pytest.approx(0.4, rel=0.01)

    def test_zero_overlap_gives_zero_relevance(self) -> None:
        """No topic overlap should give zero relevance."""
        from src.intelligence.proactive_memory import ProactiveMemoryService

        service = ProactiveMemoryService(db_client=MagicMock())

        score = service._calculate_base_relevance(
            topic_overlap=0.0,
            salience=1.0,
        )

        assert score == 0.0


class TestCooldownFiltering:
    """Tests for cooldown filtering logic."""

    @pytest.fixture
    def mock_db_with_recent(self) -> MagicMock:
        """Mock DB with recent surfaced insight."""
        mock = MagicMock()
        mock.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(
            data=[{"memory_id": "mem-123"}]
        )
        return mock

    @pytest.fixture
    def mock_db_empty(self) -> MagicMock:
        """Mock DB with no recent surfaced insights."""
        mock = MagicMock()
        mock.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(
            data=[]
        )
        return mock

    @pytest.mark.asyncio
    async def test_recently_surfaced_filtered_out(self, mock_db_with_recent: MagicMock) -> None:
        """Insights surfaced within cooldown period should be filtered."""
        from src.intelligence.proactive_memory import ProactiveMemoryService
        from src.models.proactive_insight import InsightType, ProactiveInsight

        service = ProactiveMemoryService(db_client=mock_db_with_recent)

        insights = [
            ProactiveInsight(
                insight_type=InsightType.PATTERN_MATCH,
                content="Test",
                relevance_score=0.9,
                source_memory_id="mem-123",
                source_memory_type="episodic",
                explanation="Test",
            ),
            ProactiveInsight(
                insight_type=InsightType.PATTERN_MATCH,
                content="Test 2",
                relevance_score=0.8,
                source_memory_id="mem-456",
                source_memory_type="episodic",
                explanation="Test 2",
            ),
        ]

        filtered = await service._filter_by_cooldown(
            user_id="user-123",
            insights=insights,
        )

        assert len(filtered) == 1
        assert filtered[0].source_memory_id == "mem-456"

    @pytest.mark.asyncio
    async def test_no_recent_all_pass(self, mock_db_empty: MagicMock) -> None:
        """Without recent surfacing, all insights should pass."""
        from src.intelligence.proactive_memory import ProactiveMemoryService
        from src.models.proactive_insight import InsightType, ProactiveInsight

        service = ProactiveMemoryService(db_client=mock_db_empty)

        insights = [
            ProactiveInsight(
                insight_type=InsightType.PATTERN_MATCH,
                content="Test",
                relevance_score=0.9,
                source_memory_id="mem-123",
                source_memory_type="episodic",
                explanation="Test",
            ),
        ]

        filtered = await service._filter_by_cooldown(
            user_id="user-123",
            insights=insights,
        )

        assert len(filtered) == 1


class TestThresholdFiltering:
    """Tests for threshold-based filtering."""

    def test_filter_below_threshold(self) -> None:
        """Insights below threshold should be filtered out."""
        from src.intelligence.proactive_memory import ProactiveMemoryService
        from src.models.proactive_insight import InsightType, ProactiveInsight

        service = ProactiveMemoryService(db_client=MagicMock())

        insights = [
            ProactiveInsight(
                insight_type=InsightType.PATTERN_MATCH,
                content="High relevance",
                relevance_score=0.9,
                source_memory_id="mem-1",
                source_memory_type="episodic",
                explanation="High",
            ),
            ProactiveInsight(
                insight_type=InsightType.PATTERN_MATCH,
                content="Low relevance",
                relevance_score=0.3,
                source_memory_id="mem-2",
                source_memory_type="episodic",
                explanation="Low",
            ),
        ]

        filtered = service._filter_by_threshold(insights=insights)

        assert len(filtered) == 1
        assert filtered[0].source_memory_id == "mem-1"

    def test_threshold_boundary(self) -> None:
        """Insights exactly at threshold should pass."""
        from src.intelligence.proactive_memory import ProactiveMemoryService
        from src.models.proactive_insight import InsightType, ProactiveInsight

        service = ProactiveMemoryService(db_client=MagicMock())

        insights = [
            ProactiveInsight(
                insight_type=InsightType.PATTERN_MATCH,
                content="At threshold",
                relevance_score=service.SURFACING_THRESHOLD,
                source_memory_id="mem-1",
                source_memory_type="episodic",
                explanation="At threshold",
            ),
        ]

        filtered = service._filter_by_threshold(insights=insights)

        assert len(filtered) == 1


class TestRecordSurfaced:
    """Tests for recording surfaced insights."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create mock DB for insert."""
        mock = MagicMock()
        mock.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "record-123"}]
        )
        return mock

    @pytest.mark.asyncio
    async def test_record_surfaced_inserts_to_db(self, mock_db: MagicMock) -> None:
        """record_surfaced should insert to surfaced_insights table."""
        from src.intelligence.proactive_memory import ProactiveMemoryService
        from src.models.proactive_insight import InsightType, ProactiveInsight

        service = ProactiveMemoryService(db_client=mock_db)

        insight = ProactiveInsight(
            insight_type=InsightType.TEMPORAL,
            content="Deadline approaching",
            relevance_score=0.9,
            source_memory_id="task-456",
            source_memory_type="prospective",
            explanation="Due in 2 days",
        )

        await service.record_surfaced(
            user_id="user-123",
            insight=insight,
            context="Discussing project timeline",
        )

        mock_db.table.assert_called_with("surfaced_insights")

    @pytest.mark.asyncio
    async def test_record_surfaced_returns_id(self, mock_db: MagicMock) -> None:
        """record_surfaced should return the created record ID."""
        from src.intelligence.proactive_memory import ProactiveMemoryService
        from src.models.proactive_insight import InsightType, ProactiveInsight

        service = ProactiveMemoryService(db_client=mock_db)

        insight = ProactiveInsight(
            insight_type=InsightType.TEMPORAL,
            content="Deadline approaching",
            relevance_score=0.9,
            source_memory_id="task-456",
            source_memory_type="prospective",
            explanation="Due in 2 days",
        )

        result = await service.record_surfaced(
            user_id="user-123",
            insight=insight,
            context="Discussing project timeline",
        )

        assert result == "record-123"


class TestRecordEngagement:
    """Tests for recording engagement with surfaced insights."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create mock DB for update."""
        mock = MagicMock()
        mock.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "record-123"}]
        )
        return mock

    @pytest.mark.asyncio
    async def test_record_engagement_updates_engaged(self, mock_db: MagicMock) -> None:
        """record_engagement should update the engaged status."""
        from src.intelligence.proactive_memory import ProactiveMemoryService

        service = ProactiveMemoryService(db_client=mock_db)

        await service.record_engagement(
            insight_id="record-123",
            engaged=True,
        )

        mock_db.table.assert_called_with("surfaced_insights")
        mock_db.table.return_value.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_engagement_with_dismiss(self, mock_db: MagicMock) -> None:
        """record_engagement should handle dismissal."""
        from src.intelligence.proactive_memory import ProactiveMemoryService

        service = ProactiveMemoryService(db_client=mock_db)

        await service.record_engagement(
            insight_id="record-123",
            engaged=False,
        )

        mock_db.table.assert_called_with("surfaced_insights")


class TestFindVolunteerableContext:
    """Tests for find_volunteerable_context method."""

    @pytest.fixture
    def mock_db_complex(self) -> MagicMock:
        """Create mock DB for complex queries."""
        mock = MagicMock()
        # Mock for cooldown filter (no recent insights)
        mock.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(
            data=[]
        )
        return mock

    @pytest.mark.asyncio
    async def test_find_volunteerable_returns_list(self, mock_db_complex: MagicMock) -> None:
        """find_volunteerable_context should return a list of insights."""
        from src.intelligence.proactive_memory import ProactiveMemoryService

        service = ProactiveMemoryService(db_client=mock_db_complex)

        result = await service.find_volunteerable_context(
            user_id="user-123",
            current_message="What's happening with the Johnson deal?",
            conversation_messages=[],
        )

        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_find_volunteerable_limits_results(self, mock_db_complex: MagicMock) -> None:
        """find_volunteerable_context should limit to MAX_INSIGHTS_PER_RESPONSE."""
        from src.intelligence.proactive_memory import ProactiveMemoryService

        service = ProactiveMemoryService(db_client=mock_db_complex)

        result = await service.find_volunteerable_context(
            user_id="user-123",
            current_message="Test message",
            conversation_messages=[],
        )

        # Should never exceed the max
        assert len(result) <= service.MAX_INSIGHTS_PER_RESPONSE


class TestGetSurfacedHistory:
    """Tests for getting surfaced insight history."""

    @pytest.fixture
    def mock_db_with_history(self) -> MagicMock:
        """Create mock DB with surfaced history."""
        mock = MagicMock()
        history_data = [
            {
                "id": "record-1",
                "user_id": "user-123",
                "memory_type": "episodic",
                "memory_id": "mem-1",
                "insight_type": "pattern_match",
                "context": "Sales discussion",
                "relevance_score": 0.8,
                "surfaced_at": "2026-02-03T10:00:00Z",
                "engaged": True,
            },
            {
                "id": "record-2",
                "user_id": "user-123",
                "memory_type": "semantic",
                "memory_id": "mem-2",
                "insight_type": "connection",
                "context": "Product review",
                "relevance_score": 0.7,
                "surfaced_at": "2026-02-03T09:00:00Z",
                "engaged": False,
            },
        ]
        mock.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=history_data
        )
        return mock

    @pytest.mark.asyncio
    async def test_get_surfaced_history_returns_list(self, mock_db_with_history: MagicMock) -> None:
        """get_surfaced_history should return list of dicts."""
        from src.intelligence.proactive_memory import ProactiveMemoryService

        service = ProactiveMemoryService(db_client=mock_db_with_history)

        result = await service.get_surfaced_history(
            user_id="user-123",
            limit=10,
        )

        assert isinstance(result, list)
        assert len(result) == 2

    @pytest.fixture
    def mock_db_with_engaged_filter(self) -> MagicMock:
        """Create mock DB that filters by engaged."""
        mock = MagicMock()
        engaged_data = [
            {
                "id": "record-1",
                "user_id": "user-123",
                "memory_type": "episodic",
                "memory_id": "mem-1",
                "insight_type": "pattern_match",
                "context": "Sales discussion",
                "relevance_score": 0.8,
                "surfaced_at": "2026-02-03T10:00:00Z",
                "engaged": True,
            },
        ]
        # Chain for engaged=True filter
        mock.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=engaged_data
        )
        return mock

    @pytest.mark.asyncio
    async def test_get_surfaced_history_filters_engaged(
        self, mock_db_with_engaged_filter: MagicMock
    ) -> None:
        """get_surfaced_history should filter by engaged when specified."""
        from src.intelligence.proactive_memory import ProactiveMemoryService

        service = ProactiveMemoryService(db_client=mock_db_with_engaged_filter)

        result = await service.get_surfaced_history(
            user_id="user-123",
            limit=10,
            engaged_only=True,
        )

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["engaged"] is True


class TestPlaceholderMethods:
    """Tests for placeholder finder methods."""

    def test_find_pattern_matches_returns_empty_list(self) -> None:
        """_find_pattern_matches placeholder should return empty list."""
        from src.intelligence.proactive_memory import ProactiveMemoryService

        service = ProactiveMemoryService(db_client=MagicMock())

        result = service._find_pattern_matches(
            user_id="user-123",
            current_message="Test",
            conversation_messages=[],
        )

        assert result == []

    def test_find_temporal_triggers_returns_empty_list(self) -> None:
        """_find_temporal_triggers placeholder should return empty list."""
        from src.intelligence.proactive_memory import ProactiveMemoryService

        service = ProactiveMemoryService(db_client=MagicMock())

        result = service._find_temporal_triggers(user_id="user-123")

        assert result == []

    def test_find_goal_relevant_returns_empty_list(self) -> None:
        """_find_goal_relevant placeholder should return empty list."""
        from src.intelligence.proactive_memory import ProactiveMemoryService

        service = ProactiveMemoryService(db_client=MagicMock())

        result = service._find_goal_relevant(
            user_id="user-123",
            current_message="Test",
        )

        assert result == []


class TestModuleExports:
    """Tests for module-level exports."""

    def test_proactive_memory_service_exported_from_intelligence(self) -> None:
        """ProactiveMemoryService should be importable from src.intelligence."""
        from src.intelligence import ProactiveMemoryService

        assert ProactiveMemoryService is not None
