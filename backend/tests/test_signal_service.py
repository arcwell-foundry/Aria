"""Tests for market signal service."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_db() -> MagicMock:
    """Create mock Supabase client."""
    mock_client = MagicMock()
    return mock_client


@pytest.mark.asyncio
async def test_create_signal_stores_in_database(mock_db: MagicMock) -> None:
    """Test create_signal stores signal in database."""
    with patch("src.services.signal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": "signal-123",
                    "user_id": "user-456",
                    "company_name": "Acme Corp",
                    "signal_type": "funding",
                    "headline": "Acme raises $50M Series B",
                    "summary": "Acme Corp announced a $50M Series B funding round.",
                    "source_url": "https://example.com/article",
                    "source_name": "TechCrunch",
                    "relevance_score": 0.85,
                    "detected_at": "2026-02-02T10:00:00Z",
                    "read_at": None,
                    "linked_lead_id": None,
                    "metadata": {},
                }
            ]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.models.signal import SignalCreate, SignalType
        from src.services.signal_service import SignalService

        service = SignalService()
        data = SignalCreate(
            company_name="Acme Corp",
            signal_type=SignalType.FUNDING,
            headline="Acme raises $50M Series B",
            summary="Acme Corp announced a $50M Series B funding round.",
            source_url="https://example.com/article",
            source_name="TechCrunch",
            relevance_score=0.85,
        )

        result = await service.create_signal("user-456", data)

        assert result["id"] == "signal-123"
        assert result["company_name"] == "Acme Corp"
        assert result["signal_type"] == "funding"
        assert result["headline"] == "Acme raises $50M Series B"

        # Verify insert was called
        mock_db.table.assert_called_with("market_signals")


@pytest.mark.asyncio
async def test_get_signals_returns_all_signals_by_default(mock_db: MagicMock) -> None:
    """Test get_signals returns all signals without filters."""
    with patch("src.services.signal_service.SupabaseClient") as mock_db_class:
        expected_signals = [
            {"id": "signal-1", "company_name": "Acme Corp", "signal_type": "funding"},
            {"id": "signal-2", "company_name": "Beta Inc", "signal_type": "hiring"},
        ]
        # Setup DB mock
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=expected_signals
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.signal_service import SignalService

        service = SignalService()
        result = await service.get_signals("user-456")

        assert len(result) == 2
        assert result == expected_signals

        # Verify query was built correctly
        mock_db.table.assert_called_with("market_signals")
        mock_db.table.return_value.select.assert_called_with("*")


@pytest.mark.asyncio
async def test_get_signals_filters_unread_only(mock_db: MagicMock) -> None:
    """Test get_signals filters unread signals when requested."""
    with patch("src.services.signal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_is = MagicMock()
        mock_is.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "signal-1", "read_at": None}]
        )
        mock_db.table.return_value.select.return_value.eq.return_value.is_ = mock_is
        mock_db_class.get_client.return_value = mock_db

        from src.services.signal_service import SignalService

        service = SignalService()
        await service.get_signals("user-456", unread_only=True)

        # Verify is_ was called with read_at and "null"
        mock_is.assert_called_once_with("read_at", "null")


@pytest.mark.asyncio
async def test_get_signals_filters_by_signal_type(mock_db: MagicMock) -> None:
    """Test get_signals filters by signal type."""
    with patch("src.services.signal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "signal-1", "signal_type": "funding"}]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.models.signal import SignalType
        from src.services.signal_service import SignalService

        service = SignalService()
        await service.get_signals("user-456", signal_type=SignalType.FUNDING)

        # Verify eq was called with signal_type
        mock_db.table.return_value.select.return_value.eq.assert_called_with("user_id", "user-456")


@pytest.mark.asyncio
async def test_get_signals_filters_by_company_name(mock_db: MagicMock) -> None:
    """Test get_signals filters by company name."""
    with patch("src.services.signal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_ilike = MagicMock()
        mock_ilike.return_value.order.return_value.limit.return_value.execute.return_value = (
            MagicMock(data=[{"id": "signal-1", "company_name": "Acme Corp"}])
        )
        mock_db.table.return_value.select.return_value.eq.return_value.ilike = mock_ilike
        mock_db_class.get_client.return_value = mock_db

        from src.services.signal_service import SignalService

        service = SignalService()
        await service.get_signals("user-456", company_name="Acme")

        # Verify ilike was called with company pattern
        mock_ilike.assert_called_once_with("company_name", "%Acme%")


@pytest.mark.asyncio
async def test_mark_as_read_updates_timestamp(mock_db: MagicMock) -> None:
    """Test mark_as_read updates the read_at timestamp."""
    with patch("src.services.signal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "signal-123", "read_at": "2026-02-02T10:00:00Z"}]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.signal_service import SignalService

        service = SignalService()
        result = await service.mark_as_read("user-456", "signal-123")

        assert result["id"] == "signal-123"
        assert result["read_at"] is not None


@pytest.mark.asyncio
async def test_mark_as_read_returns_none_for_not_found(mock_db: MagicMock) -> None:
    """Test mark_as_read returns None when signal not found."""
    with patch("src.services.signal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock to return empty data
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.signal_service import SignalService

        service = SignalService()
        result = await service.mark_as_read("user-456", "signal-999")

        assert result is None


@pytest.mark.asyncio
async def test_mark_all_read_updates_all_unread_signals(mock_db: MagicMock) -> None:
    """Test mark_all_read updates all unread signals."""
    with patch("src.services.signal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_db.table.return_value.update.return_value.eq.return_value.is_.return_value.execute.return_value = MagicMock(
            data=[
                {"id": "signal-1"},
                {"id": "signal-2"},
                {"id": "signal-3"},
            ]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.signal_service import SignalService

        service = SignalService()
        count = await service.mark_all_read("user-456")

        assert count == 3


@pytest.mark.asyncio
async def test_dismiss_signal_sets_dismissed_at(mock_db: MagicMock) -> None:
    """Test dismiss_signal sets dismissed_at timestamp."""
    with patch("src.services.signal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "signal-123", "dismissed_at": "2026-02-02T10:00:00Z"}]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.signal_service import SignalService

        service = SignalService()
        result = await service.dismiss_signal("user-456", "signal-123")

        assert result["id"] == "signal-123"
        assert result["dismissed_at"] is not None


@pytest.mark.asyncio
async def test_get_unread_count_returns_count(mock_db: MagicMock) -> None:
    """Test get_unread_count returns the count of unread signals."""
    with patch("src.services.signal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_db.table.return_value.select.return_value.eq.return_value.is_.return_value.execute.return_value = MagicMock(
            count=5
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.signal_service import SignalService

        service = SignalService()
        count = await service.get_unread_count("user-456")

        assert count == 5


@pytest.mark.asyncio
async def test_get_unread_count_returns_zero_when_no_signals(mock_db: MagicMock) -> None:
    """Test get_unread_count returns 0 when count is None."""
    with patch("src.services.signal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_db.table.return_value.select.return_value.eq.return_value.is_.return_value.execute.return_value = MagicMock(
            count=None
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.signal_service import SignalService

        service = SignalService()
        count = await service.get_unread_count("user-456")

        assert count == 0


# Monitored Entities Tests


@pytest.mark.asyncio
async def test_add_monitored_entity_upserts_to_database(mock_db: MagicMock) -> None:
    """Test add_monitored_entity upserts entity to database."""
    with patch("src.services.signal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": "entity-123",
                    "user_id": "user-456",
                    "entity_type": "company",
                    "entity_name": "Acme Corp",
                    "monitoring_config": {"frequency": "daily"},
                    "is_active": True,
                }
            ]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.models.signal import EntityType, MonitoredEntityCreate
        from src.services.signal_service import SignalService

        service = SignalService()
        data = MonitoredEntityCreate(
            entity_type=EntityType.COMPANY,
            entity_name="Acme Corp",
            monitoring_config={"frequency": "daily"},
        )

        result = await service.add_monitored_entity("user-456", data)

        assert result["id"] == "entity-123"
        assert result["entity_name"] == "Acme Corp"
        assert result["entity_type"] == "company"


@pytest.mark.asyncio
async def test_get_monitored_entities_returns_active_by_default(mock_db: MagicMock) -> None:
    """Test get_monitored_entities returns active entities by default."""
    with patch("src.services.signal_service.SupabaseClient") as mock_db_class:
        expected_entities = [
            {"id": "entity-1", "entity_name": "Acme Corp", "is_active": True},
            {"id": "entity-2", "entity_name": "Beta Inc", "is_active": True},
        ]
        # Setup DB mock
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
            data=expected_entities
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.signal_service import SignalService

        service = SignalService()
        result = await service.get_monitored_entities("user-456")

        assert len(result) == 2
        assert result == expected_entities


@pytest.mark.asyncio
async def test_get_monitored_entities_can_return_inactive(mock_db: MagicMock) -> None:
    """Test get_monitored_entities can include inactive entities."""
    with patch("src.services.signal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock without active_only filter
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
            data=[{"id": "entity-1", "is_active": False}]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.signal_service import SignalService

        service = SignalService()
        await service.get_monitored_entities("user-456", active_only=False)

        # Verify only one eq was called (for user_id)
        mock_db.table.return_value.select.return_value.eq.assert_called_once_with(
            "user_id", "user-456"
        )


@pytest.mark.asyncio
async def test_remove_monitored_entity_deactivates_entity(mock_db: MagicMock) -> None:
    """Test remove_monitored_entity sets is_active to False."""
    with patch("src.services.signal_service.SupabaseClient") as mock_db_class:
        # Setup DB mock
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "entity-123", "is_active": False}]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.signal_service import SignalService

        service = SignalService()
        result = await service.remove_monitored_entity("user-456", "entity-123")

        assert result is True
