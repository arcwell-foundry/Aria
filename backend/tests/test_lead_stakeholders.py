"""Tests for LeadStakeholder dataclass and related enums.

This module tests the domain model for lead stakeholders, including:
- StakeholderRole enum for categorizing stakeholder roles
- Sentiment enum for tracking stakeholder sentiment
- LeadStakeholder dataclass for stakeholder representation and serialization
- LeadStakeholderService for managing stakeholder operations
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from src.core.exceptions import DatabaseError
from src.memory.lead_stakeholders import LeadStakeholder, LeadStakeholderService
from src.models.lead_memory import Sentiment, StakeholderRole


class TestStakeholderRoleEnum:
    """Tests for the StakeholderRole enum."""

    def test_stakeholder_role_enum_values(self):
        """Test StakeholderRole enum has correct string values."""
        assert StakeholderRole.DECISION_MAKER.value == "decision_maker"
        assert StakeholderRole.INFLUENCER.value == "influencer"
        assert StakeholderRole.CHAMPION.value == "champion"
        assert StakeholderRole.BLOCKER.value == "blocker"
        assert StakeholderRole.USER.value == "user"

    def test_stakeholder_role_enum_count(self):
        """Test StakeholderRole enum has exactly 5 values."""
        assert len(StakeholderRole) == 5


class TestSentimentEnum:
    """Tests for the Sentiment enum."""

    def test_sentiment_enum_values(self):
        """Test Sentiment enum has correct string values."""
        assert Sentiment.POSITIVE.value == "positive"
        assert Sentiment.NEUTRAL.value == "neutral"
        assert Sentiment.NEGATIVE.value == "negative"
        assert Sentiment.UNKNOWN.value == "unknown"

    def test_sentiment_enum_count(self):
        """Test Sentiment enum has exactly 4 values."""
        assert len(Sentiment) == 4


class TestLeadStakeholderDataclass:
    """Tests for the LeadStakeholder dataclass."""

    def test_lead_stakeholder_creation_all_fields(self):
        """Test creating a LeadStakeholder with all fields populated."""
        created_at = datetime(2025, 2, 4, 14, 30, tzinfo=UTC)
        last_contacted_at = datetime(2025, 2, 4, 15, 0, tzinfo=UTC)

        stakeholder = LeadStakeholder(
            id="stkh_123",
            lead_memory_id="lead_456",
            contact_email="john.smith@acme.com",
            contact_name="John Smith",
            title="VP of Engineering",
            role=StakeholderRole.DECISION_MAKER,
            influence_level=9,
            sentiment=Sentiment.POSITIVE,
            last_contacted_at=last_contacted_at,
            notes="Key champion, excited about our solution",
            created_at=created_at,
        )

        assert stakeholder.id == "stkh_123"
        assert stakeholder.lead_memory_id == "lead_456"
        assert stakeholder.contact_email == "john.smith@acme.com"
        assert stakeholder.contact_name == "John Smith"
        assert stakeholder.title == "VP of Engineering"
        assert stakeholder.role == StakeholderRole.DECISION_MAKER
        assert stakeholder.influence_level == 9
        assert stakeholder.sentiment == Sentiment.POSITIVE
        assert stakeholder.last_contacted_at == last_contacted_at
        assert stakeholder.notes == "Key champion, excited about our solution"
        assert stakeholder.created_at == created_at

    def test_lead_stakeholder_creation_minimal_fields(self):
        """Test creating a LeadStakeholder with only required fields."""
        created_at = datetime(2025, 2, 4, 14, 30, tzinfo=UTC)

        stakeholder = LeadStakeholder(
            id="stkh_123",
            lead_memory_id="lead_456",
            contact_email="john@acme.com",
            contact_name=None,
            title=None,
            role=None,
            influence_level=5,
            sentiment=Sentiment.NEUTRAL,
            last_contacted_at=None,
            notes=None,
            created_at=created_at,
        )

        assert stakeholder.id == "stkh_123"
        assert stakeholder.contact_name is None
        assert stakeholder.title is None
        assert stakeholder.role is None
        assert stakeholder.last_contacted_at is None
        assert stakeholder.notes is None

    def test_lead_stakeholder_to_dict(self):
        """Test serialization to dict with all fields."""
        created_at = datetime(2025, 2, 4, 14, 30, tzinfo=UTC)
        last_contacted_at = datetime(2025, 2, 4, 15, 0, tzinfo=UTC)

        stakeholder = LeadStakeholder(
            id="stkh_123",
            lead_memory_id="lead_456",
            contact_email="jane.doe@acme.com",
            contact_name="Jane Doe",
            title="CTO",
            role=StakeholderRole.CHAMPION,
            influence_level=8,
            sentiment=Sentiment.POSITIVE,
            last_contacted_at=last_contacted_at,
            notes="Very supportive",
            created_at=created_at,
        )

        result = stakeholder.to_dict()

        assert result["id"] == "stkh_123"
        assert result["lead_memory_id"] == "lead_456"
        assert result["contact_email"] == "jane.doe@acme.com"
        assert result["contact_name"] == "Jane Doe"
        assert result["title"] == "CTO"
        assert result["role"] == "champion"
        assert result["influence_level"] == 8
        assert result["sentiment"] == "positive"
        assert result["last_contacted_at"] == "2025-02-04T15:00:00+00:00"
        assert result["notes"] == "Very supportive"
        assert result["created_at"] == "2025-02-04T14:30:00+00:00"

    def test_lead_stakeholder_to_dict_with_none_values(self):
        """Test serialization to dict with None values."""
        created_at = datetime(2025, 2, 4, 14, 30, tzinfo=UTC)

        stakeholder = LeadStakeholder(
            id="stkh_123",
            lead_memory_id="lead_456",
            contact_email="bob@acme.com",
            contact_name=None,
            title=None,
            role=None,
            influence_level=5,
            sentiment=Sentiment.UNKNOWN,
            last_contacted_at=None,
            notes=None,
            created_at=created_at,
        )

        result = stakeholder.to_dict()

        assert result["contact_name"] is None
        assert result["title"] is None
        assert result["role"] is None
        assert result["last_contacted_at"] is None
        assert result["notes"] is None

    def test_lead_stakeholder_from_dict(self):
        """Test deserialization from dict with all fields."""
        data = {
            "id": "stkh_123",
            "lead_memory_id": "lead_456",
            "contact_email": "mike@acme.com",
            "contact_name": "Mike Johnson",
            "title": "Director of Sales",
            "role": "influencer",
            "influence_level": 7,
            "sentiment": "neutral",
            "last_contacted_at": "2025-02-04T15:00:00+00:00",
            "notes": "Needs more information",
            "created_at": "2025-02-04T14:30:00+00:00",
        }

        stakeholder = LeadStakeholder.from_dict(data)

        assert stakeholder.id == "stkh_123"
        assert stakeholder.lead_memory_id == "lead_456"
        assert stakeholder.contact_email == "mike@acme.com"
        assert stakeholder.contact_name == "Mike Johnson"
        assert stakeholder.title == "Director of Sales"
        assert stakeholder.role == StakeholderRole.INFLUENCER
        assert stakeholder.influence_level == 7
        assert stakeholder.sentiment == Sentiment.NEUTRAL
        assert stakeholder.last_contacted_at == datetime(2025, 2, 4, 15, 0, tzinfo=UTC)
        assert stakeholder.notes == "Needs more information"
        assert stakeholder.created_at == datetime(2025, 2, 4, 14, 30, tzinfo=UTC)

    def test_lead_stakeholder_from_dict_with_none_values(self):
        """Test deserialization from dict with None values."""
        data = {
            "id": "stkh_123",
            "lead_memory_id": "lead_456",
            "contact_email": "sarah@acme.com",
            "contact_name": None,
            "title": None,
            "role": None,
            "influence_level": 5,
            "sentiment": "unknown",
            "last_contacted_at": None,
            "notes": None,
            "created_at": "2025-02-04T14:30:00+00:00",
        }

        stakeholder = LeadStakeholder.from_dict(data)

        assert stakeholder.contact_name is None
        assert stakeholder.title is None
        assert stakeholder.role is None
        assert stakeholder.last_contacted_at is None
        assert stakeholder.notes is None

    def test_lead_stakeholder_from_dict_with_datetime_objects(self):
        """Test deserialization when datetime fields are already datetime objects."""
        created_at = datetime(2025, 2, 4, 14, 30, tzinfo=UTC)
        last_contacted_at = datetime(2025, 2, 4, 15, 0, tzinfo=UTC)

        data = {
            "id": "stkh_123",
            "lead_memory_id": "lead_456",
            "contact_email": "test@acme.com",
            "contact_name": "Test User",
            "title": "Test Role",
            "role": StakeholderRole.USER,
            "influence_level": 6,
            "sentiment": Sentiment.POSITIVE,
            "last_contacted_at": last_contacted_at,
            "notes": "Test notes",
            "created_at": created_at,
        }

        stakeholder = LeadStakeholder.from_dict(data)

        assert stakeholder.last_contacted_at == last_contacted_at
        assert stakeholder.created_at == created_at

    def test_round_trip_serialization(self):
        """Test that to_dict and from_dict preserve all data."""
        created_at = datetime(2025, 2, 4, 14, 30, tzinfo=UTC)
        last_contacted_at = datetime(2025, 2, 4, 15, 0, tzinfo=UTC)

        original = LeadStakeholder(
            id="stkh_123",
            lead_memory_id="lead_456",
            contact_email="alex@acme.com",
            contact_name="Alex Rivera",
            title="Chief Technology Officer",
            role=StakeholderRole.BLOCKER,
            influence_level=3,
            sentiment=Sentiment.NEGATIVE,
            last_contacted_at=last_contacted_at,
            notes="Concerned about integration complexity",
            created_at=created_at,
        )

        # Serialize and deserialize
        dict_data = original.to_dict()
        restored = LeadStakeholder.from_dict(dict_data)

        # Check all fields match
        assert restored.id == original.id
        assert restored.lead_memory_id == original.lead_memory_id
        assert restored.contact_email == original.contact_email
        assert restored.contact_name == original.contact_name
        assert restored.title == original.title
        assert restored.role == original.role
        assert restored.influence_level == original.influence_level
        assert restored.sentiment == original.sentiment
        assert restored.last_contacted_at == original.last_contacted_at
        assert restored.notes == original.notes
        assert restored.created_at == original.created_at


class TestLeadStakeholderService:
    """Tests for the LeadStakeholderService class."""

    def test_service_initialization(self):
        """Test that LeadStakeholderService can be instantiated with a db client."""
        mock_client = MagicMock()
        service = LeadStakeholderService(db_client=mock_client)
        assert service is not None
        assert service.db == mock_client

    @patch("src.db.supabase.SupabaseClient.get_client")
    def test_get_supabase_client_success(self, mock_get_client):
        """Test _get_supabase_client returns client successfully."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        service = LeadStakeholderService(db_client=mock_client)
        result = service._get_supabase_client()

        assert result == mock_client
        mock_get_client.assert_called_once()

    @patch("src.db.supabase.SupabaseClient.get_client")
    def test_get_supabase_client_failure_raises_database_error(self, mock_get_client):
        """Test _get_supabase_client raises DatabaseError on failure."""
        mock_get_client.side_effect = Exception("Connection failed")

        mock_client = MagicMock()
        service = LeadStakeholderService(db_client=mock_client)

        with pytest.raises(DatabaseError) as exc_info:
            service._get_supabase_client()

        assert "Failed to get Supabase client" in str(exc_info.value)
        assert "Connection failed" in str(exc_info.value)


class TestLeadStakeholderServiceAdd:
    """Tests for the add_stakeholder method."""

    @pytest.mark.asyncio
    async def test_add_stakeholder_all_fields(self):
        """Test adding a stakeholder with all fields."""
        service = LeadStakeholderService(db_client=MagicMock())

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [{"id": "new-stakeholder-id"}]
        mock_client.table.return_value.insert.return_value.execute.return_value = mock_response

        with patch.object(service, "_get_supabase_client", return_value=mock_client):
            stakeholder_id = await service.add_stakeholder(
                user_id="user-123",
                lead_memory_id="lead-456",
                contact_email="john@acme.com",
                contact_name="John Smith",
                title="VP Engineering",
                role=StakeholderRole.DECISION_MAKER,
                influence_level=9,
                sentiment=Sentiment.POSITIVE,
                notes="Key champion",
            )

            assert stakeholder_id == "new-stakeholder-id"
            mock_client.table.assert_called_once_with("lead_stakeholders")
            mock_client.table.return_value.insert.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_stakeholder_minimal_fields(self):
        """Test adding a stakeholder with minimal fields."""
        service = LeadStakeholderService(db_client=MagicMock())

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [{"id": "minimal-id"}]
        mock_client.table.return_value.insert.return_value.execute.return_value = mock_response

        with patch.object(service, "_get_supabase_client", return_value=mock_client):
            stakeholder_id = await service.add_stakeholder(
                user_id="user-123",
                lead_memory_id="lead-456",
                contact_email="minimal@acme.com",
            )

            assert stakeholder_id == "minimal-id"

    @pytest.mark.asyncio
    async def test_add_stakeholder_handles_database_error(self):
        """Test that database errors are properly wrapped."""
        service = LeadStakeholderService(db_client=MagicMock())

        mock_client = MagicMock()
        mock_client.table.side_effect = Exception("Connection lost")

        with patch.object(service, "_get_supabase_client", return_value=mock_client):
            with pytest.raises(DatabaseError):
                await service.add_stakeholder(
                    user_id="user-123",
                    lead_memory_id="lead-456",
                    contact_email="john@acme.com",
                )


class TestLeadStakeholderServiceList:
    """Tests for the list_by_lead method."""

    @pytest.mark.asyncio
    async def test_list_by_lead_with_stakeholders(self):
        """Test listing stakeholders when stakeholders exist."""
        service = LeadStakeholderService(db_client=MagicMock())

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [
            {
                "id": "stkh-1",
                "lead_memory_id": "lead-123",
                "contact_email": "john@acme.com",
                "contact_name": "John Smith",
                "title": "VP Engineering",
                "role": "decision_maker",
                "influence_level": 9,
                "sentiment": "positive",
                "last_contacted_at": "2025-02-04T15:00:00+00:00",
                "notes": "Key champion",
                "created_at": "2025-02-04T14:00:00+00:00",
            },
            {
                "id": "stkh-2",
                "lead_memory_id": "lead-123",
                "contact_email": "jane@acme.com",
                "contact_name": "Jane Doe",
                "title": "CTO",
                "role": "champion",
                "influence_level": 8,
                "sentiment": "positive",
                "last_contacted_at": None,
                "notes": None,
                "created_at": "2025-02-04T14:30:00+00:00",
            },
        ]

        # Create mock query builder
        mock_query = MagicMock()
        mock_query.eq.return_value = mock_query
        mock_query.order.return_value = mock_query
        mock_query.execute.return_value = mock_response

        mock_client.table.return_value.select.return_value = mock_query

        with patch.object(service, "_get_supabase_client", return_value=mock_client):
            stakeholders = await service.list_by_lead(
                user_id="user-123",
                lead_memory_id="lead-123",
            )

            assert len(stakeholders) == 2
            assert stakeholders[0].contact_email == "john@acme.com"
            assert stakeholders[1].contact_email == "jane@acme.com"

    @pytest.mark.asyncio
    async def test_list_by_lead_empty_result(self):
        """Test listing stakeholders when no stakeholders exist."""
        service = LeadStakeholderService(db_client=MagicMock())

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = []

        mock_query = MagicMock()
        mock_query.eq.return_value = mock_query
        mock_query.order.return_value = mock_query
        mock_query.execute.return_value = mock_response

        mock_client.table.return_value.select.return_value = mock_query

        with patch.object(service, "_get_supabase_client", return_value=mock_client):
            stakeholders = await service.list_by_lead(
                user_id="user-123",
                lead_memory_id="lead-123",
            )

            assert stakeholders == []


class TestLeadStakeholderServiceUpdate:
    """Tests for the update_stakeholder method."""

    @pytest.mark.asyncio
    async def test_update_stakeholder_all_fields(self):
        """Test updating a stakeholder with all fields."""
        service = LeadStakeholderService(db_client=MagicMock())

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [{"id": "stkh-123"}]
        mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            mock_response
        )

        with patch.object(service, "_get_supabase_client", return_value=mock_client):
            await service.update_stakeholder(
                user_id="user-123",
                stakeholder_id="stkh-123",
                contact_name="Updated Name",
                title="Updated Title",
                role=StakeholderRole.CHAMPION,
                influence_level=10,
                sentiment=Sentiment.POSITIVE,
                notes="Updated notes",
            )

            mock_client.table.assert_called_once_with("lead_stakeholders")
            mock_client.table.return_value.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_stakeholder_partial_fields(self):
        """Test updating a stakeholder with only some fields."""
        service = LeadStakeholderService(db_client=MagicMock())

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [{"id": "stkh-123"}]
        mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            mock_response
        )

        with patch.object(service, "_get_supabase_client", return_value=mock_client):
            await service.update_stakeholder(
                user_id="user-123",
                stakeholder_id="stkh-123",
                sentiment=Sentiment.NEGATIVE,
            )

            # Verify only sentiment was updated
            call_args = mock_client.table.return_value.update.call_args
            update_data = call_args[0][0]
            assert update_data["sentiment"] == "negative"
            assert "contact_name" not in update_data

    @pytest.mark.asyncio
    async def test_update_stakeholder_not_found(self):
        """Test updating a non-existent stakeholder raises DatabaseError."""
        service = LeadStakeholderService(db_client=MagicMock())

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = []
        mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            mock_response
        )

        with patch.object(service, "_get_supabase_client", return_value=mock_client):
            with pytest.raises(DatabaseError) as exc_info:
                await service.update_stakeholder(
                    user_id="user-123",
                    stakeholder_id="nonexistent",
                    contact_name="Test",
                )

            assert "not found" in str(exc_info.value)


class TestLeadStakeholderServiceRemove:
    """Tests for the remove_stakeholder method."""

    @pytest.mark.asyncio
    async def test_remove_stakeholder_success(self):
        """Test removing a stakeholder successfully."""
        service = LeadStakeholderService(db_client=MagicMock())

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [{"id": "stkh-123"}]
        mock_client.table.return_value.delete.return_value.eq.return_value.execute.return_value = (
            mock_response
        )

        with patch.object(service, "_get_supabase_client", return_value=mock_client):
            await service.remove_stakeholder(
                user_id="user-123",
                stakeholder_id="stkh-123",
            )

            mock_client.table.assert_called_once_with("lead_stakeholders")

    @pytest.mark.asyncio
    async def test_remove_stakeholder_not_found(self):
        """Test removing a non-existent stakeholder raises DatabaseError."""
        service = LeadStakeholderService(db_client=MagicMock())

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = []
        mock_client.table.return_value.delete.return_value.eq.return_value.execute.return_value = (
            mock_response
        )

        with patch.object(service, "_get_supabase_client", return_value=mock_client):
            with pytest.raises(DatabaseError) as exc_info:
                await service.remove_stakeholder(
                    user_id="user-123",
                    stakeholder_id="nonexistent",
                )

            assert "not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_remove_stakeholder_handles_database_error(self):
        """Test that database errors are properly wrapped."""
        service = LeadStakeholderService(db_client=MagicMock())

        mock_client = MagicMock()
        mock_client.table.side_effect = Exception("Connection lost")

        with patch.object(service, "_get_supabase_client", return_value=mock_client):
            with pytest.raises(DatabaseError):
                await service.remove_stakeholder(
                    user_id="user-123",
                    stakeholder_id="stkh-123",
                )
