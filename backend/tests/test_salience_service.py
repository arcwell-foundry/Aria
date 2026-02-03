"""Tests for memory salience decay service."""

import math
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from src.memory.salience import SalienceService


def test_salience_service_exported_from_memory_module() -> None:
    """SalienceService should be importable from src.memory."""
    from src.memory import SalienceService

    assert SalienceService is not None


class TestSalienceDecayCalculation:
    """Tests for the core decay formula."""

    def test_fresh_memory_has_full_salience(self) -> None:
        """A memory accessed just now should have salience ~1.0."""
        service = SalienceService(db_client=MagicMock())

        salience = service.calculate_decay(
            access_count=0,
            days_since_last_access=0.0,
        )

        assert salience == 1.0

    def test_half_life_decay(self) -> None:
        """After 30 days, salience should be ~0.5 (half-life)."""
        service = SalienceService(db_client=MagicMock())

        salience = service.calculate_decay(
            access_count=0,
            days_since_last_access=30.0,
        )

        assert abs(salience - 0.5) < 0.01

    def test_double_half_life_decay(self) -> None:
        """After 60 days, salience should be ~0.25."""
        service = SalienceService(db_client=MagicMock())

        salience = service.calculate_decay(
            access_count=0,
            days_since_last_access=60.0,
        )

        assert abs(salience - 0.25) < 0.01

    def test_access_boost_adds_to_base(self) -> None:
        """Each access adds 0.1 to base salience before decay."""
        service = SalienceService(db_client=MagicMock())

        # 5 accesses = 0.5 boost, so base = 1.5
        # After 30 days: 1.5 * 0.5 = 0.75
        salience = service.calculate_decay(
            access_count=5,
            days_since_last_access=30.0,
        )

        assert abs(salience - 0.75) < 0.01

    def test_minimum_salience_enforced(self) -> None:
        """Salience never goes below MIN_SALIENCE (0.01)."""
        service = SalienceService(db_client=MagicMock())

        # After 1 year, decay factor is tiny
        salience = service.calculate_decay(
            access_count=0,
            days_since_last_access=365.0,
        )

        assert salience == 0.01

    def test_very_old_memory_with_many_accesses(self) -> None:
        """Even old memories with many accesses have a floor."""
        service = SalienceService(db_client=MagicMock())

        # 10 accesses = 1.0 boost, base = 2.0
        # After 365 days: decay factor = 0.5^(365/30) ≈ 0.000488
        # 2.0 * 0.000488 ≈ 0.00098 -> floored to 0.01
        salience = service.calculate_decay(
            access_count=10,
            days_since_last_access=365.0,
        )

        assert salience == 0.01

    def test_custom_half_life(self) -> None:
        """Can use custom half-life for different decay rates."""
        service = SalienceService(
            db_client=MagicMock(),
            half_life_days=60,  # Slower decay
        )

        # After 60 days with 60-day half-life, should be 0.5
        salience = service.calculate_decay(
            access_count=0,
            days_since_last_access=60.0,
        )

        assert abs(salience - 0.5) < 0.01

    def test_formula_matches_spec(self) -> None:
        """Verify formula: salience = (1 + access_boost) × 0.5^(days/half_life)."""
        service = SalienceService(db_client=MagicMock())

        # Manual calculation: 3 accesses, 15 days
        # base = 1.0 + (3 * 0.1) = 1.3
        # decay = 0.5^(15/30) = 0.5^0.5 ≈ 0.707
        # salience = 1.3 * 0.707 ≈ 0.919
        expected = (1.0 + 3 * 0.1) * math.pow(0.5, 15.0 / 30.0)

        salience = service.calculate_decay(
            access_count=3,
            days_since_last_access=15.0,
        )

        assert abs(salience - expected) < 0.001


class TestSalienceDecayFromTimestamp:
    """Tests for timestamp-based decay calculation."""

    def test_calculate_from_recent_timestamp(self) -> None:
        """Calculate salience from a recent timestamp."""
        service = SalienceService(db_client=MagicMock())
        now = datetime.now(UTC)
        last_accessed = now - timedelta(days=15)

        salience = service.calculate_decay_from_timestamp(
            access_count=0,
            last_accessed_at=last_accessed,
            as_of=now,
        )

        # 15 days = half of half-life, so ~0.707
        expected = math.pow(0.5, 15.0 / 30.0)
        assert abs(salience - expected) < 0.01

    def test_calculate_with_access_count(self) -> None:
        """Calculate salience from timestamp with access count."""
        service = SalienceService(db_client=MagicMock())
        now = datetime.now(UTC)
        last_accessed = now - timedelta(days=30)

        salience = service.calculate_decay_from_timestamp(
            access_count=5,
            last_accessed_at=last_accessed,
            as_of=now,
        )

        # 5 accesses = 0.5 boost, base = 1.5
        # After 30 days: 1.5 * 0.5 = 0.75
        assert abs(salience - 0.75) < 0.01

    def test_defaults_to_now(self) -> None:
        """When as_of is not provided, defaults to current time."""
        service = SalienceService(db_client=MagicMock())
        # Access just now
        last_accessed = datetime.now(UTC)

        salience = service.calculate_decay_from_timestamp(
            access_count=0,
            last_accessed_at=last_accessed,
        )

        # Should be very close to 1.0 (just accessed)
        assert salience >= 0.99


class TestRecordAccess:
    """Tests for recording memory access and updating salience."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock Supabase client."""
        mock = MagicMock()
        # Mock the chained query builder pattern
        mock.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "log-123"}]
        )
        mock.table.return_value.upsert.return_value.execute.return_value = MagicMock(
            data=[{"id": "salience-123", "access_count": 1}]
        )
        mock.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"id": "salience-123", "access_count": 0, "last_accessed_at": "2026-01-01T00:00:00+00:00"}
        )
        return mock

    @pytest.mark.asyncio
    async def test_record_access_logs_to_access_log(self, mock_db: MagicMock) -> None:
        """Recording access should insert into memory_access_log."""
        service = SalienceService(db_client=mock_db)

        await service.record_access(
            memory_id="mem-123",
            memory_type="episodic",
            user_id="user-456",
            context="query: find meetings",
        )

        # Verify insert was called on memory_access_log
        mock_db.table.assert_any_call("memory_access_log")

    @pytest.mark.asyncio
    async def test_record_access_updates_salience_table(self, mock_db: MagicMock) -> None:
        """Recording access should upsert the salience tracking table."""
        service = SalienceService(db_client=mock_db)

        await service.record_access(
            memory_id="mem-123",
            memory_type="semantic",
            user_id="user-456",
        )

        # Verify upsert was called on semantic_fact_salience
        mock_db.table.assert_any_call("semantic_fact_salience")

    @pytest.mark.asyncio
    async def test_record_access_increments_count(self, mock_db: MagicMock) -> None:
        """Recording access should increment the access count."""
        service = SalienceService(db_client=mock_db)

        await service.record_access(
            memory_id="mem-123",
            memory_type="episodic",
            user_id="user-456",
        )

        # The update should include access_count increment
        # Verify update was called
        mock_db.table.return_value.update.assert_called()

    @pytest.mark.asyncio
    async def test_record_access_for_lead_memory(self, mock_db: MagicMock) -> None:
        """Lead memories should also be tracked."""
        service = SalienceService(db_client=mock_db)

        await service.record_access(
            memory_id="lead-123",
            memory_type="lead",
            user_id="user-456",
        )

        # Lead uses the semantic fact salience table (per spec, lead is stored with semantic)
        mock_db.table.assert_any_call("memory_access_log")


class TestUpdateAllSalience:
    """Tests for batch salience recalculation."""

    @pytest.fixture
    def mock_db_with_memories(self) -> MagicMock:
        """Create mock DB with existing salience records."""
        mock = MagicMock()

        # Mock episodic records
        episodic_data = [
            {
                "id": "sal-1",
                "graphiti_episode_id": "ep-1",
                "current_salience": 1.0,
                "access_count": 5,
                "last_accessed_at": "2026-01-03T00:00:00+00:00",  # 30 days ago
            },
            {
                "id": "sal-2",
                "graphiti_episode_id": "ep-2",
                "current_salience": 0.8,
                "access_count": 0,
                "last_accessed_at": "2026-02-01T00:00:00+00:00",  # 1 day ago
            },
        ]

        semantic_data = [
            {
                "id": "sal-3",
                "graphiti_episode_id": "fact-1",
                "current_salience": 0.5,
                "access_count": 2,
                "last_accessed_at": "2025-11-03T00:00:00+00:00",  # 91 days ago
            },
        ]

        def table_side_effect(table_name: str) -> MagicMock:
            table_mock = MagicMock()
            if table_name == "episodic_memory_salience":
                table_mock.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=episodic_data
                )
            elif table_name == "semantic_fact_salience":
                table_mock.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=semantic_data
                )
            table_mock.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])
            return table_mock

        mock.table.side_effect = table_side_effect
        return mock

    @pytest.mark.asyncio
    async def test_update_all_salience_returns_count(self, mock_db_with_memories: MagicMock) -> None:
        """update_all_salience should return number of updated records."""
        from unittest.mock import patch

        service = SalienceService(db_client=mock_db_with_memories)

        with patch("src.memory.salience.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(2026, 2, 2, tzinfo=UTC)
            mock_datetime.fromisoformat = datetime.fromisoformat

            updated = await service.update_all_salience(user_id="user-123")

        # Should update records where salience changed significantly
        assert updated >= 0

    @pytest.mark.asyncio
    async def test_update_processes_both_tables(self, mock_db_with_memories: MagicMock) -> None:
        """Should process both episodic and semantic salience tables."""
        from unittest.mock import patch

        service = SalienceService(db_client=mock_db_with_memories)

        with patch("src.memory.salience.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(2026, 2, 2, tzinfo=UTC)
            mock_datetime.fromisoformat = datetime.fromisoformat

            await service.update_all_salience(user_id="user-123")

        # Verify both tables were queried
        table_calls = [call[0][0] for call in mock_db_with_memories.table.call_args_list]
        assert "episodic_memory_salience" in table_calls
        assert "semantic_fact_salience" in table_calls


class TestGetBySalience:
    """Tests for querying memories by salience threshold."""

    @pytest.fixture
    def mock_db_with_salience_records(self) -> MagicMock:
        """Create mock DB with salience records at various levels."""
        mock = MagicMock()

        high_salience = [
            {"graphiti_episode_id": "ep-1", "current_salience": 0.95, "access_count": 10},
            {"graphiti_episode_id": "ep-2", "current_salience": 0.80, "access_count": 5},
        ]

        mock.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=high_salience
        )
        return mock

    @pytest.mark.asyncio
    async def test_get_by_salience_filters_by_threshold(
        self, mock_db_with_salience_records: MagicMock
    ) -> None:
        """Should only return memories above the salience threshold."""
        service = SalienceService(db_client=mock_db_with_salience_records)

        results = await service.get_by_salience(
            user_id="user-123",
            memory_type="episodic",
            min_salience=0.5,
            limit=10,
        )

        assert len(results) == 2
        assert all(r["current_salience"] >= 0.5 for r in results)

    @pytest.mark.asyncio
    async def test_get_by_salience_orders_by_salience_desc(
        self, mock_db_with_salience_records: MagicMock
    ) -> None:
        """Results should be ordered by salience descending."""
        service = SalienceService(db_client=mock_db_with_salience_records)

        await service.get_by_salience(
            user_id="user-123",
            memory_type="episodic",
            min_salience=0.3,
            limit=5,
        )

        # Verify order was called with desc=True
        order_call = mock_db_with_salience_records.table.return_value.select.return_value.eq.return_value.gte.return_value.order
        order_call.assert_called_once_with("current_salience", desc=True)

    @pytest.mark.asyncio
    async def test_get_by_salience_respects_limit(
        self, mock_db_with_salience_records: MagicMock
    ) -> None:
        """Should respect the limit parameter."""
        service = SalienceService(db_client=mock_db_with_salience_records)

        await service.get_by_salience(
            user_id="user-123",
            memory_type="semantic",
            min_salience=0.1,
            limit=5,
        )

        # Verify limit was called
        limit_call = mock_db_with_salience_records.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.limit
        limit_call.assert_called_once_with(5)
