"""Tests for LeadCollaborationService domain models.

This module tests the domain models for lead collaboration, including:
- ContributionStatus enum
- ContributionType enum
- Contribution dataclass for contribution representation
- Contributor dataclass for contributor representation
- LeadCollaborationService initialization
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from src.core.exceptions import DatabaseError
from src.services.lead_collaboration import (
    Contribution,
    ContributionStatus,
    ContributionType,
    Contributor,
    LeadCollaborationService,
)


class TestContributionStatusEnum:
    """Tests for the ContributionStatus enum."""

    def test_contribution_status_enum_values(self):
        """Test ContributionStatus enum has correct string values."""
        assert ContributionStatus.PENDING.value == "pending"
        assert ContributionStatus.MERGED.value == "merged"
        assert ContributionStatus.REJECTED.value == "rejected"

    def test_contribution_status_enum_count(self):
        """Test ContributionStatus enum has exactly 3 values."""
        assert len(ContributionStatus) == 3


class TestContributionTypeEnum:
    """Tests for the ContributionType enum."""

    def test_contribution_type_enum_values(self):
        """Test ContributionType enum has correct string values."""
        assert ContributionType.EVENT.value == "event"
        assert ContributionType.NOTE.value == "note"
        assert ContributionType.INSIGHT.value == "insight"

    def test_contribution_type_enum_count(self):
        """Test ContributionType enum has exactly 3 values."""
        assert len(ContributionType) == 3


class TestContributionDataclass:
    """Tests for the Contribution dataclass."""

    def test_contribution_creation_all_fields(self):
        """Test creating a Contribution with all fields populated."""
        created_at = datetime(2025, 2, 4, 14, 30, tzinfo=UTC)

        contribution = Contribution(
            id="cntrb_123",
            lead_memory_id="lead_456",
            contributor_id="user_789",
            contribution_type=ContributionType.EVENT,
            contribution_id="event_abc",
            status=ContributionStatus.PENDING,
            reviewed_by=None,
            reviewed_at=None,
            created_at=created_at,
        )

        assert contribution.id == "cntrb_123"
        assert contribution.lead_memory_id == "lead_456"
        assert contribution.contributor_id == "user_789"
        assert contribution.contribution_type == ContributionType.EVENT
        assert contribution.contribution_id == "event_abc"
        assert contribution.status == ContributionStatus.PENDING
        assert contribution.reviewed_by is None
        assert contribution.reviewed_at is None
        assert contribution.created_at == created_at

    def test_contribution_creation_with_review_fields(self):
        """Test creating a Contribution with review fields populated."""
        created_at = datetime(2025, 2, 4, 14, 30, tzinfo=UTC)
        reviewed_at = datetime(2025, 2, 4, 16, 0, tzinfo=UTC)

        contribution = Contribution(
            id="cntrb_456",
            lead_memory_id="lead_789",
            contributor_id="user_123",
            contribution_type=ContributionType.NOTE,
            contribution_id="note_xyz",
            status=ContributionStatus.MERGED,
            reviewed_by="user_owner",
            reviewed_at=reviewed_at,
            created_at=created_at,
        )

        assert contribution.id == "cntrb_456"
        assert contribution.reviewed_by == "user_owner"
        assert contribution.reviewed_at == reviewed_at
        assert contribution.status == ContributionStatus.MERGED

    def test_contribution_to_dict(self):
        """Test serialization to dict with all fields."""
        created_at = datetime(2025, 2, 4, 14, 30, tzinfo=UTC)

        contribution = Contribution(
            id="cntrb_789",
            lead_memory_id="lead_123",
            contributor_id="user_456",
            contribution_type=ContributionType.INSIGHT,
            contribution_id="insight_123",
            status=ContributionStatus.PENDING,
            reviewed_by=None,
            reviewed_at=None,
            created_at=created_at,
        )

        result = contribution.to_dict()

        assert result["id"] == "cntrb_789"
        assert result["lead_memory_id"] == "lead_123"
        assert result["contributor_id"] == "user_456"
        assert result["contribution_type"] == "insight"
        assert result["contribution_id"] == "insight_123"
        assert result["status"] == "pending"
        assert result["reviewed_by"] is None
        assert result["reviewed_at"] is None
        assert result["created_at"] == "2025-02-04T14:30:00+00:00"

    def test_contribution_to_dict_with_review(self):
        """Test serialization to dict with review fields."""
        created_at = datetime(2025, 2, 4, 14, 30, tzinfo=UTC)
        reviewed_at = datetime(2025, 2, 4, 16, 30, tzinfo=UTC)

        contribution = Contribution(
            id="cntrb_abc",
            lead_memory_id="lead_def",
            contributor_id="user_ghi",
            contribution_type=ContributionType.NOTE,
            contribution_id="note_123",
            status=ContributionStatus.REJECTED,
            reviewed_by="user_reviewer",
            reviewed_at=reviewed_at,
            created_at=created_at,
        )

        result = contribution.to_dict()

        assert result["id"] == "cntrb_abc"
        assert result["status"] == "rejected"
        assert result["reviewed_by"] == "user_reviewer"
        assert result["reviewed_at"] == "2025-02-04T16:30:00+00:00"

    def test_contribution_from_dict(self):
        """Test creating a Contribution from a dictionary."""
        data = {
            "id": "cntrb_xyz",
            "lead_memory_id": "lead_abc",
            "contributor_id": "user_def",
            "contribution_type": "event",
            "contribution_id": "event_456",
            "status": "pending",
            "reviewed_by": None,
            "reviewed_at": None,
            "created_at": "2025-02-04T14:30:00+00:00",
        }

        contribution = Contribution.from_dict(data)

        assert contribution.id == "cntrb_xyz"
        assert contribution.lead_memory_id == "lead_abc"
        assert contribution.contributor_id == "user_def"
        assert contribution.contribution_type == ContributionType.EVENT
        assert contribution.contribution_id == "event_456"
        assert contribution.status == ContributionStatus.PENDING
        assert contribution.reviewed_by is None
        assert contribution.reviewed_at is None
        assert contribution.created_at == datetime(2025, 2, 4, 14, 30, tzinfo=UTC)

    def test_contribution_from_dict_with_review(self):
        """Test creating a Contribution from a dictionary with review fields."""
        data = {
            "id": "cntrb_qwe",
            "lead_memory_id": "lead_rty",
            "contributor_id": "user_uio",
            "contribution_type": "note",
            "contribution_id": "note_789",
            "status": "merged",
            "reviewed_by": "user_owner",
            "reviewed_at": "2025-02-04T16:30:00+00:00",
            "created_at": "2025-02-04T14:30:00+00:00",
        }

        contribution = Contribution.from_dict(data)

        assert contribution.id == "cntrb_qwe"
        assert contribution.contribution_type == ContributionType.NOTE
        assert contribution.status == ContributionStatus.MERGED
        assert contribution.reviewed_by == "user_owner"
        assert contribution.reviewed_at == datetime(2025, 2, 4, 16, 30, tzinfo=UTC)

    def test_contribution_from_dict_with_none_contribution_id(self):
        """Test creating a Contribution with None contribution_id."""
        data = {
            "id": "cntrb_asd",
            "lead_memory_id": "lead_fgh",
            "contributor_id": "user_jkl",
            "contribution_type": "insight",
            "contribution_id": None,
            "status": "pending",
            "reviewed_by": None,
            "reviewed_at": None,
            "created_at": "2025-02-04T14:30:00+00:00",
        }

        contribution = Contribution.from_dict(data)

        assert contribution.id == "cntrb_asd"
        assert contribution.contribution_id is None
        assert contribution.contribution_type == ContributionType.INSIGHT


class TestContributorDataclass:
    """Tests for the Contributor dataclass."""

    def test_contributor_creation_all_fields(self):
        """Test creating a Contributor with all fields populated."""
        added_at = datetime(2025, 2, 4, 14, 30, tzinfo=UTC)

        contributor = Contributor(
            id="cntr_123",
            lead_memory_id="lead_456",
            name="Jane Doe",
            email="jane.doe@example.com",
            added_at=added_at,
            contribution_count=5,
        )

        assert contributor.id == "cntr_123"
        assert contributor.lead_memory_id == "lead_456"
        assert contributor.name == "Jane Doe"
        assert contributor.email == "jane.doe@example.com"
        assert contributor.added_at == added_at
        assert contributor.contribution_count == 5

    def test_contributor_creation_zero_contributions(self):
        """Test creating a Contributor with zero contributions."""
        added_at = datetime(2025, 2, 4, 14, 30, tzinfo=UTC)

        contributor = Contributor(
            id="cntr_789",
            lead_memory_id="lead_012",
            name="John Smith",
            email="john.smith@example.com",
            added_at=added_at,
            contribution_count=0,
        )

        assert contributor.contribution_count == 0

    def test_contributor_to_dict(self):
        """Test serialization to dict with all fields."""
        added_at = datetime(2025, 2, 4, 14, 30, tzinfo=UTC)

        contributor = Contributor(
            id="cntr_123",
            lead_memory_id="lead_456",
            name="Jane Doe",
            email="jane.doe@example.com",
            added_at=added_at,
            contribution_count=5,
        )

        result = contributor.to_dict()

        assert result["id"] == "cntr_123"
        assert result["lead_memory_id"] == "lead_456"
        assert result["name"] == "Jane Doe"
        assert result["email"] == "jane.doe@example.com"
        assert result["added_at"] == "2025-02-04T14:30:00+00:00"
        assert result["contribution_count"] == 5

    def test_contributor_from_dict(self):
        """Test creating a Contributor from a dictionary."""
        data = {
            "id": "cntr_xyz",
            "lead_memory_id": "lead_abc",
            "name": "Bob Johnson",
            "email": "bob.johnson@example.com",
            "added_at": "2025-02-04T14:30:00+00:00",
            "contribution_count": 10,
        }

        contributor = Contributor.from_dict(data)

        assert contributor.id == "cntr_xyz"
        assert contributor.lead_memory_id == "lead_abc"
        assert contributor.name == "Bob Johnson"
        assert contributor.email == "bob.johnson@example.com"
        assert contributor.added_at == datetime(2025, 2, 4, 14, 30, tzinfo=UTC)
        assert contributor.contribution_count == 10


class TestLeadCollaborationServiceInit:
    """Tests for the LeadCollaborationService initialization."""

    def test_service_initialization(self):
        """Test that the service initializes correctly with a db_client."""
        mock_client = MagicMock()

        service = LeadCollaborationService(db_client=mock_client)

        assert service.db == mock_client

    @patch("src.db.supabase.SupabaseClient.get_client")
    def test_get_supabase_client_success(self, mock_get_client):
        """Test _get_supabase_client returns the client successfully."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        service = LeadCollaborationService(db_client=MagicMock())
        result = service._get_supabase_client()

        assert result == mock_client
        mock_get_client.assert_called_once()

    @patch("src.db.supabase.SupabaseClient.get_client")
    def test_get_supabase_client_raises_database_error(self, mock_get_client):
        """Test _get_supabase_client raises DatabaseError on failure."""
        mock_get_client.side_effect = Exception("Connection failed")

        service = LeadCollaborationService(db_client=MagicMock())

        with pytest.raises(DatabaseError) as exc_info:
            service._get_supabase_client()

        assert "Failed to get Supabase client" in str(exc_info.value)


class TestAddContributor:
    """Tests for the add_contributor method."""

    @pytest.mark.asyncio
    @patch("src.services.lead_collaboration.LeadCollaborationService._get_supabase_client")
    async def test_add_contributor_creates_record(self, mock_get_client):
        """Test that add_contributor returns the contributor_id."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = []
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = (
            mock_response
        )
        mock_get_client.return_value = mock_client

        service = LeadCollaborationService(db_client=MagicMock())

        result = await service.add_contributor(
            user_id="user_123",
            lead_memory_id="lead_456",
            contributor_id="user_789",
        )

        assert result == "user_789"
        mock_client.table.assert_called_once_with("lead_memory_contributions")
        mock_get_client.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.services.lead_collaboration.LeadCollaborationService._get_supabase_client")
    async def test_add_contributor_with_existing_contributions(self, mock_get_client):
        """Test that add_contributor works when contributor already has contributions."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        # Simulate existing contributions
        mock_response.data = [
            {"id": "cntrb_1", "contributor_id": "user_789"},
            {"id": "cntrb_2", "contributor_id": "user_789"},
        ]
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = (
            mock_response
        )
        mock_get_client.return_value = mock_client

        service = LeadCollaborationService(db_client=MagicMock())

        result = await service.add_contributor(
            user_id="user_123",
            lead_memory_id="lead_456",
            contributor_id="user_789",
        )

        assert result == "user_789"
        mock_client.table.assert_called_once_with("lead_memory_contributions")

    @pytest.mark.asyncio
    @patch("src.services.lead_collaboration.LeadCollaborationService._get_supabase_client")
    async def test_add_contributor_handles_database_error(self, mock_get_client):
        """Test that add_contributor raises DatabaseError on database failure."""
        mock_client = MagicMock()
        mock_client.table.side_effect = Exception("Database connection failed")
        mock_get_client.return_value = mock_client

        service = LeadCollaborationService(db_client=MagicMock())

        with pytest.raises(DatabaseError) as exc_info:
            await service.add_contributor(
                user_id="user_123",
                lead_memory_id="lead_456",
                contributor_id="user_789",
            )

        assert "Failed to add contributor" in str(exc_info.value)
        mock_get_client.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.services.lead_collaboration.LeadCollaborationService._get_supabase_client")
    async def test_add_contributor_propagates_database_error(self, mock_get_client):
        """Test that add_contributor propagates DatabaseError directly."""
        from src.core.exceptions import DatabaseError

        mock_get_client.side_effect = DatabaseError("Custom database error")

        service = LeadCollaborationService(db_client=MagicMock())

        with pytest.raises(DatabaseError) as exc_info:
            await service.add_contributor(
                user_id="user_123",
                lead_memory_id="lead_456",
                contributor_id="user_789",
            )

        assert "Custom database error" in str(exc_info.value)


class TestSubmitContribution:
    """Tests for the submit_contribution method."""

    @pytest.mark.asyncio
    @patch("src.services.lead_collaboration.LeadCollaborationService._get_supabase_client")
    async def test_submit_note_contribution(self, mock_get_client):
        """Test submitting a note contribution."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [{"id": "cntrb_123", "lead_memory_id": "lead_456"}]
        mock_client.table.return_value.insert.return_value.execute.return_value = mock_response
        mock_get_client.return_value = mock_client

        service = LeadCollaborationService(db_client=MagicMock())

        result = await service.submit_contribution(
            user_id="user_789",
            lead_memory_id="lead_456",
            contribution_type=ContributionType.NOTE,
            contribution_id=None,
            content="This is a note contribution",
        )

        assert result == "cntrb_123"
        mock_client.table.assert_called_once_with("lead_memory_contributions")
        insert_call = mock_client.table.return_value.insert
        assert insert_call.called
        inserted_data = insert_call.call_args[0][0]
        assert inserted_data["lead_memory_id"] == "lead_456"
        assert inserted_data["contributor_id"] == "user_789"
        assert inserted_data["contribution_type"] == "note"
        assert inserted_data["status"] == "pending"
        assert inserted_data["contribution_id"] is None

    @pytest.mark.asyncio
    @patch("src.services.lead_collaboration.LeadCollaborationService._get_supabase_client")
    async def test_submit_event_contribution_with_id(self, mock_get_client):
        """Test submitting an event contribution with a contribution_id."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [{"id": "cntrb_456", "lead_memory_id": "lead_789"}]
        mock_client.table.return_value.insert.return_value.execute.return_value = mock_response
        mock_get_client.return_value = mock_client

        service = LeadCollaborationService(db_client=MagicMock())

        result = await service.submit_contribution(
            user_id="user_123",
            lead_memory_id="lead_789",
            contribution_type=ContributionType.EVENT,
            contribution_id="event_abc",
        )

        assert result == "cntrb_456"
        insert_call = mock_client.table.return_value.insert
        inserted_data = insert_call.call_args[0][0]
        assert inserted_data["lead_memory_id"] == "lead_789"
        assert inserted_data["contributor_id"] == "user_123"
        assert inserted_data["contribution_type"] == "event"
        assert inserted_data["contribution_id"] == "event_abc"
        assert inserted_data["status"] == "pending"

    @pytest.mark.asyncio
    @patch("src.services.lead_collaboration.LeadCollaborationService._get_supabase_client")
    async def test_submit_contribution_handles_database_error(self, mock_get_client):
        """Test that submit_contribution raises DatabaseError on database failure."""
        mock_client = MagicMock()
        mock_client.table.side_effect = Exception("Database connection failed")
        mock_get_client.return_value = mock_client

        service = LeadCollaborationService(db_client=MagicMock())

        with pytest.raises(DatabaseError) as exc_info:
            await service.submit_contribution(
                user_id="user_123",
                lead_memory_id="lead_456",
                contribution_type=ContributionType.INSIGHT,
            )

        assert "Failed to submit contribution" in str(exc_info.value)
        mock_get_client.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.services.lead_collaboration.LeadCollaborationService._get_supabase_client")
    async def test_submit_contribution_empty_response_data(self, mock_get_client):
        """Test that submit_contribution handles empty response data."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = []
        mock_client.table.return_value.insert.return_value.execute.return_value = mock_response
        mock_get_client.return_value = mock_client

        service = LeadCollaborationService(db_client=MagicMock())

        with pytest.raises(DatabaseError) as exc_info:
            await service.submit_contribution(
                user_id="user_123",
                lead_memory_id="lead_456",
                contribution_type=ContributionType.NOTE,
            )

        assert "Failed to insert contribution" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch("src.services.lead_collaboration.LeadCollaborationService._get_supabase_client")
    async def test_submit_contribution_missing_id_in_response(self, mock_get_client):
        """Test that submit_contribution handles missing id in response."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [{"lead_memory_id": "lead_456"}]  # Missing id
        mock_client.table.return_value.insert.return_value.execute.return_value = mock_response
        mock_get_client.return_value = mock_client

        service = LeadCollaborationService(db_client=MagicMock())

        with pytest.raises(DatabaseError) as exc_info:
            await service.submit_contribution(
                user_id="user_123",
                lead_memory_id="lead_456",
                contribution_type=ContributionType.EVENT,
            )

        assert "Failed to insert contribution" in str(exc_info.value)
