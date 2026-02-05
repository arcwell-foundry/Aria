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

        # Mock lead_memories query to get owner (returns empty, so no notification sent)
        mock_lead_response = MagicMock()
        mock_lead_response.data = []
        mock_lead_query = MagicMock()
        mock_lead_query.execute.return_value = mock_lead_response
        mock_lead_eq = MagicMock()
        mock_lead_eq.eq.return_value = mock_lead_query
        mock_lead_select = MagicMock()
        mock_lead_select.select.return_value = mock_lead_eq

        # Mock contributions insert
        mock_contrib_response = MagicMock()
        mock_contrib_response.data = [{"id": "cntrb_123", "lead_memory_id": "lead_456"}]
        mock_client.table.return_value.insert.return_value.execute.return_value = mock_contrib_response

        # Configure table to return different mocks
        table_call_count = [0]

        def table_side_effect(table_name):
            table_call_count[0] += 1
            if table_name == "lead_memories" and table_call_count[0] == 1:
                return mock_lead_select
            elif table_name == "lead_memory_contributions":
                return mock_client.table.return_value
            return MagicMock()

        mock_client.table.side_effect = table_side_effect
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
        # Verify both tables were called
        assert mock_client.table.call_count >= 2
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

    @pytest.mark.asyncio
    @patch("src.services.notification_service.NotificationService.create_notification")
    @patch("src.services.lead_collaboration.LeadCollaborationService._get_supabase_client")
    async def test_submit_contribution_sends_notification_to_owner(self, mock_get_client, mock_create_notification):
        """Test that submit_contribution sends notification to lead owner when contributor is different."""
        mock_client = MagicMock()

        # Mock lead_memories query to get owner
        mock_lead_response = MagicMock()
        mock_lead_response.data = [{"user_id": "user_owner"}]
        mock_lead_query = MagicMock()
        mock_lead_query.execute.return_value = mock_lead_response
        mock_lead_eq = MagicMock()
        mock_lead_eq.eq.return_value = mock_lead_query
        mock_lead_select = MagicMock()
        mock_lead_select.select.return_value = mock_lead_eq

        # Mock contributions insert
        mock_contrib_response = MagicMock()
        mock_contrib_response.data = [{"id": "cntrb_123", "lead_memory_id": "lead_456"}]
        mock_client.table.return_value.insert.return_value.execute.return_value = mock_contrib_response

        # Configure table to return different mocks
        table_call_count = [0]

        def table_side_effect(table_name):
            table_call_count[0] += 1
            if table_name == "lead_memories" and table_call_count[0] == 1:
                return mock_lead_select
            elif table_name == "lead_memory_contributions":
                return mock_client.table.return_value
            return MagicMock()

        mock_client.table.side_effect = table_side_effect
        mock_get_client.return_value = mock_client

        # Mock create_notification to return a notification response
        from src.models.notification import NotificationType, NotificationResponse
        from datetime import datetime, timezone

        mock_create_notification.return_value = NotificationResponse(
            id="notif_123",
            user_id="user_owner",
            type=NotificationType.TASK_DUE,
            title="New contribution pending review",
            message="A new note contribution has been submitted for your review.",
            link="/leads/lead_456",
            metadata={"contribution_id": "cntrb_123", "lead_memory_id": "lead_456"},
            read_at=None,
            created_at=datetime.now(timezone.utc),
        )

        service = LeadCollaborationService(db_client=MagicMock())

        result = await service.submit_contribution(
            user_id="user_contributor",  # Different from owner
            lead_memory_id="lead_456",
            contribution_type=ContributionType.NOTE,
            content="This is a note contribution",
        )

        assert result == "cntrb_123"
        # Verify notification was created for the owner
        mock_create_notification.assert_called_once()
        call_kwargs = mock_create_notification.call_args.kwargs
        assert call_kwargs["user_id"] == "user_owner"
        assert call_kwargs["type"] == NotificationType.TASK_DUE
        assert call_kwargs["title"] == "New contribution pending review"
        assert "note contribution" in call_kwargs["message"]
        assert call_kwargs["link"] == "/leads/lead_456"
        assert call_kwargs["metadata"]["contribution_id"] == "cntrb_123"
        assert call_kwargs["metadata"]["lead_memory_id"] == "lead_456"

    @pytest.mark.asyncio
    @patch("src.services.notification_service.NotificationService.create_notification")
    @patch("src.services.lead_collaboration.LeadCollaborationService._get_supabase_client")
    async def test_submit_contribution_no_notification_when_owner_is_contributor(self, mock_get_client, mock_create_notification):
        """Test that submit_contribution does not send notification when owner is the contributor."""
        mock_client = MagicMock()

        # Mock lead_memories query to get owner (same as contributor)
        mock_lead_response = MagicMock()
        mock_lead_response.data = [{"user_id": "user_owner"}]
        mock_lead_query = MagicMock()
        mock_lead_query.execute.return_value = mock_lead_response
        mock_lead_eq = MagicMock()
        mock_lead_eq.eq.return_value = mock_lead_query
        mock_lead_select = MagicMock()
        mock_lead_select.select.return_value = mock_lead_eq

        # Mock contributions insert
        mock_contrib_response = MagicMock()
        mock_contrib_response.data = [{"id": "cntrb_456", "lead_memory_id": "lead_789"}]
        mock_client.table.return_value.insert.return_value.execute.return_value = mock_contrib_response

        # Configure table to return different mocks
        table_call_count = [0]

        def table_side_effect(table_name):
            table_call_count[0] += 1
            if table_name == "lead_memories" and table_call_count[0] == 1:
                return mock_lead_select
            elif table_name == "lead_memory_contributions":
                return mock_client.table.return_value
            return MagicMock()

        mock_client.table.side_effect = table_side_effect
        mock_get_client.return_value = mock_client

        service = LeadCollaborationService(db_client=MagicMock())

        result = await service.submit_contribution(
            user_id="user_owner",  # Same as owner
            lead_memory_id="lead_789",
            contribution_type=ContributionType.EVENT,
            contribution_id="event_abc",
        )

        assert result == "cntrb_456"
        # Verify notification was NOT created since owner is the contributor
        mock_create_notification.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.services.notification_service.NotificationService.create_notification")
    @patch("src.services.lead_collaboration.LeadCollaborationService._get_supabase_client")
    async def test_submit_contribution_handles_each_contribution_type(self, mock_get_client, mock_create_notification):
        """Test that submit_contribution generates correct message for each contribution type."""
        from src.models.notification import NotificationType, NotificationResponse
        from datetime import datetime, timezone

        mock_create_notification.return_value = NotificationResponse(
            id="notif_123",
            user_id="user_owner",
            type=NotificationType.TASK_DUE,
            title="New contribution pending review",
            message="",
            link="/leads/lead_456",
            metadata={},
            read_at=None,
            created_at=datetime.now(timezone.utc),
        )

        for contribution_type, expected_type_desc in [
            (ContributionType.EVENT, "event"),
            (ContributionType.NOTE, "note"),
            (ContributionType.INSIGHT, "insight"),
        ]:
            mock_client = MagicMock()

            # Mock lead_memories query to get owner
            mock_lead_response = MagicMock()
            mock_lead_response.data = [{"user_id": "user_owner"}]
            mock_lead_query = MagicMock()
            mock_lead_query.execute.return_value = mock_lead_response
            mock_lead_eq = MagicMock()
            mock_lead_eq.eq.return_value = mock_lead_query
            mock_lead_select = MagicMock()
            mock_lead_select.select.return_value = mock_lead_eq

            # Mock contributions insert
            mock_contrib_response = MagicMock()
            mock_contrib_response.data = [{"id": f"cntrb_{contribution_type.value}", "lead_memory_id": "lead_456"}]
            mock_client.table.return_value.insert.return_value.execute.return_value = mock_contrib_response

            # Configure table to return different mocks
            table_call_count = [0]

            def table_side_effect(table_name):
                table_call_count[0] += 1
                if table_name == "lead_memories" and table_call_count[0] == 1:
                    return mock_lead_select
                elif table_name == "lead_memory_contributions":
                    return mock_client.table.return_value
                return MagicMock()

            mock_client.table.side_effect = table_side_effect
            mock_get_client.return_value = mock_client

            service = LeadCollaborationService(db_client=MagicMock())

            await service.submit_contribution(
                user_id="user_contributor",
                lead_memory_id="lead_456",
                contribution_type=contribution_type,
            )

            # Verify the correct type description was used in the message
            call_kwargs = mock_create_notification.call_args.kwargs
            assert expected_type_desc in call_kwargs["message"]


class TestGetPendingContributions:
    """Tests for the get_pending_contributions method."""

    @pytest.mark.asyncio
    @patch("src.services.lead_collaboration.LeadCollaborationService._get_supabase_client")
    async def test_get_pending_contributions_returns_list(self, mock_get_client):
        """Test that get_pending_contributions returns a list of Contribution instances."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        # Mock data already sorted by created_at descending (as Supabase would return)
        mock_response.data = [
            {
                "id": "cntrb_456",
                "lead_memory_id": "lead_456",
                "contributor_id": "user_123",
                "contribution_type": "note",
                "contribution_id": None,
                "status": "pending",
                "reviewed_by": None,
                "reviewed_at": None,
                "created_at": "2025-02-04T15:00:00+00:00",
            },
            {
                "id": "cntrb_123",
                "lead_memory_id": "lead_456",
                "contributor_id": "user_789",
                "contribution_type": "event",
                "contribution_id": "event_abc",
                "status": "pending",
                "reviewed_by": None,
                "reviewed_at": None,
                "created_at": "2025-02-04T14:30:00+00:00",
            },
        ]

        # Mock the query chain: table().select().eq().eq().order().execute()
        mock_query = MagicMock()
        mock_query.execute.return_value = mock_response
        mock_order = MagicMock()
        mock_order.order.return_value = mock_query
        mock_eq2 = MagicMock()
        mock_eq2.eq.return_value = mock_order
        mock_eq1 = MagicMock()
        mock_eq1.eq.return_value = mock_eq2
        mock_select = MagicMock()
        mock_select.select.return_value = mock_eq1
        mock_client.table.return_value = mock_select

        mock_get_client.return_value = mock_client

        service = LeadCollaborationService(db_client=MagicMock())

        result = await service.get_pending_contributions(
            user_id="user_456",
            lead_memory_id="lead_456",
        )

        assert len(result) == 2
        assert all(isinstance(c, Contribution) for c in result)

        # Verify the contributions are sorted by created_at descending (newest first)
        assert result[0].id == "cntrb_456"
        assert result[1].id == "cntrb_123"

        # Verify query was constructed correctly
        mock_client.table.assert_called_once_with("lead_memory_contributions")
        mock_select.select.assert_called_once_with("*")
        mock_eq1.eq.assert_called_once_with("lead_memory_id", "lead_456")
        mock_eq2.eq.assert_called_once_with("status", "pending")
        mock_order.order.assert_called_once_with("created_at", desc=True)
        mock_query.execute.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.services.lead_collaboration.LeadCollaborationService._get_supabase_client")
    async def test_get_pending_contributions_empty(self, mock_get_client):
        """Test that get_pending_contributions returns an empty list when no contributions."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = []

        # Mock the query chain
        mock_query = MagicMock()
        mock_query.execute.return_value = mock_response
        mock_order = MagicMock()
        mock_order.order.return_value = mock_query
        mock_eq2 = MagicMock()
        mock_eq2.eq.return_value = mock_order
        mock_eq1 = MagicMock()
        mock_eq1.eq.return_value = mock_eq2
        mock_select = MagicMock()
        mock_select.select.return_value = mock_eq1
        mock_client.table.return_value = mock_select

        mock_get_client.return_value = mock_client

        service = LeadCollaborationService(db_client=MagicMock())

        result = await service.get_pending_contributions(
            user_id="user_456",
            lead_memory_id="lead_456",
        )

        assert result == []
        mock_client.table.assert_called_once_with("lead_memory_contributions")

    @pytest.mark.asyncio
    @patch("src.services.lead_collaboration.LeadCollaborationService._get_supabase_client")
    async def test_get_pending_contributions_handles_database_error(self, mock_get_client):
        """Test that get_pending_contributions raises DatabaseError on database failure."""
        mock_client = MagicMock()
        mock_client.table.side_effect = Exception("Database connection failed")
        mock_get_client.return_value = mock_client

        service = LeadCollaborationService(db_client=MagicMock())

        with pytest.raises(DatabaseError) as exc_info:
            await service.get_pending_contributions(
                user_id="user_456",
                lead_memory_id="lead_456",
            )

        assert "Failed to get pending contributions" in str(exc_info.value)
        mock_get_client.assert_called_once()


class TestReviewContribution:
    """Tests for the review_contribution method."""

    @pytest.mark.asyncio
    @patch("src.services.lead_collaboration.LeadCollaborationService._get_supabase_client")
    async def test_review_merge_contribution(self, mock_get_client):
        """Test that review_contribution updates status to MERGED for merge action."""
        from src.core.exceptions import ValidationError

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [
            {
                "id": "cntrb_123",
                "lead_memory_id": "lead_456",
                "status": "merged",
                "reviewed_by": "user_owner",
                "reviewed_at": "2025-02-04T16:00:00+00:00",
            }
        ]
        mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            mock_response
        )
        mock_get_client.return_value = mock_client

        service = LeadCollaborationService(db_client=MagicMock())

        await service.review_contribution(
            user_id="user_owner",
            contribution_id="cntrb_123",
            action="merge",
        )

        # Verify update was called with correct data
        mock_client.table.assert_called_once_with("lead_memory_contributions")
        update_call = mock_client.table.return_value.update
        update_data = update_call.call_args[0][0]
        assert update_data["status"] == "merged"
        assert update_data["reviewed_by"] == "user_owner"
        assert "reviewed_at" in update_data
        mock_get_client.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.services.lead_collaboration.LeadCollaborationService._get_supabase_client")
    async def test_review_reject_contribution(self, mock_get_client):
        """Test that review_contribution updates status to REJECTED for reject action."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [
            {
                "id": "cntrb_456",
                "lead_memory_id": "lead_789",
                "status": "rejected",
                "reviewed_by": "user_owner",
                "reviewed_at": "2025-02-04T16:00:00+00:00",
            }
        ]
        mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            mock_response
        )
        mock_get_client.return_value = mock_client

        service = LeadCollaborationService(db_client=MagicMock())

        await service.review_contribution(
            user_id="user_owner",
            contribution_id="cntrb_456",
            action="reject",
        )

        # Verify update was called with correct data
        mock_client.table.assert_called_once_with("lead_memory_contributions")
        update_call = mock_client.table.return_value.update
        update_data = update_call.call_args[0][0]
        assert update_data["status"] == "rejected"
        assert update_data["reviewed_by"] == "user_owner"
        assert "reviewed_at" in update_data

    @pytest.mark.asyncio
    async def test_review_invalid_action_raises(self):
        """Test that review_contribution raises ValidationError for invalid action."""
        from src.core.exceptions import ValidationError

        mock_client = MagicMock()
        service = LeadCollaborationService(db_client=mock_client)

        with pytest.raises(ValidationError) as exc_info:
            await service.review_contribution(
                user_id="user_owner",
                contribution_id="cntrb_123",
                action="invalid",
            )

        assert "Invalid action" in str(exc_info.value)
        assert exc_info.value.details.get("field") == "action"

    @pytest.mark.asyncio
    @patch("src.services.lead_collaboration.LeadCollaborationService._get_supabase_client")
    async def test_review_contribution_not_found_raises_database_error(self, mock_get_client):
        """Test that review_contribution raises DatabaseError when contribution not found."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = []
        mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            mock_response
        )
        mock_get_client.return_value = mock_client

        service = LeadCollaborationService(db_client=MagicMock())

        with pytest.raises(DatabaseError) as exc_info:
            await service.review_contribution(
                user_id="user_owner",
                contribution_id="nonexistent",
                action="merge",
            )

        assert "not found" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch("src.services.lead_collaboration.LeadCollaborationService._get_supabase_client")
    async def test_review_contribution_handles_database_error(self, mock_get_client):
        """Test that review_contribution raises DatabaseError on database failure."""
        mock_client = MagicMock()
        mock_client.table.side_effect = Exception("Database connection failed")
        mock_get_client.return_value = mock_client

        service = LeadCollaborationService(db_client=MagicMock())

        with pytest.raises(DatabaseError) as exc_info:
            await service.review_contribution(
                user_id="user_owner",
                contribution_id="cntrb_123",
                action="merge",
            )

        assert "Failed to review contribution" in str(exc_info.value)
        mock_get_client.assert_called_once()


class TestGetContributors:
    """Tests for the get_contributors method."""

    @pytest.mark.asyncio
    @patch("src.services.lead_collaboration.LeadCollaborationService._get_supabase_client")
    async def test_get_contributors_returns_list(self, mock_get_client):
        """Test that get_contributors returns a list of Contributor instances with counts."""
        mock_client = MagicMock()

        # Mock contributions response
        mock_contributions_response = MagicMock()
        mock_contributions_response.data = [
            {"contributor_id": "user_123", "created_at": "2025-02-04T10:00:00+00:00"},
            {"contributor_id": "user_123", "created_at": "2025-02-04T11:00:00+00:00"},
            {"contributor_id": "user_456", "created_at": "2025-02-04T12:00:00+00:00"},
            {"contributor_id": "user_789", "created_at": "2025-02-04T13:00:00+00:00"},
            {"contributor_id": "user_789", "created_at": "2025-02-04T14:00:00+00:00"},
            {"contributor_id": "user_789", "created_at": "2025-02-04T15:00:00+00:00"},
        ]

        # Mock user profiles response
        mock_users_response = MagicMock()
        mock_users_response.data = [
            {"id": "user_123", "full_name": "Alice Johnson", "email": "alice@example.com"},
            {"id": "user_456", "full_name": "Bob Smith", "email": "bob@example.com"},
            {"id": "user_789", "full_name": "Carol Davis", "email": "carol@example.com"},
        ]

        # Set up the mock chain for contributions query
        mock_contributions_query = MagicMock()
        mock_contributions_query.execute.return_value = mock_contributions_response
        mock_contributions_eq = MagicMock()
        mock_contributions_eq.eq.return_value = mock_contributions_query
        mock_contributions_select = MagicMock()
        mock_contributions_select.select.return_value = mock_contributions_eq

        # Set up the mock chain for users query
        mock_users_query = MagicMock()
        mock_users_query.execute.return_value = mock_users_response
        mock_users_in = MagicMock()
        mock_users_in.in_.return_value = mock_users_query
        mock_users_select = MagicMock()
        mock_users_select.select.return_value = mock_users_in

        # Configure table to return different mocks based on call
        table_call_count = [0]

        def table_side_effect(table_name):
            table_call_count[0] += 1
            if table_name == "lead_memory_contributions" and table_call_count[0] == 1:
                return mock_contributions_select
            elif table_name == "user_profiles":
                return mock_users_select
            return MagicMock()

        mock_client.table.side_effect = table_side_effect
        mock_get_client.return_value = mock_client

        service = LeadCollaborationService(db_client=MagicMock())

        result = await service.get_contributors(
            user_id="user_owner",
            lead_memory_id="lead_456",
        )

        assert len(result) == 3
        assert all(isinstance(c, Contributor) for c in result)

        # Find each contributor by ID
        alice = next(c for c in result if c.id == "user_123")
        bob = next(c for c in result if c.id == "user_456")
        carol = next(c for c in result if c.id == "user_789")

        # Verify Alice has 2 contributions
        assert alice.name == "Alice Johnson"
        assert alice.email == "alice@example.com"
        assert alice.contribution_count == 2
        assert alice.lead_memory_id == "lead_456"

        # Verify Bob has 1 contribution
        assert bob.name == "Bob Smith"
        assert bob.email == "bob@example.com"
        assert bob.contribution_count == 1

        # Verify Carol has 3 contributions
        assert carol.name == "Carol Davis"
        assert carol.email == "carol@example.com"
        assert carol.contribution_count == 3

    @pytest.mark.asyncio
    @patch("src.services.lead_collaboration.LeadCollaborationService._get_supabase_client")
    async def test_get_contributors_uses_earliest_added_at(self, mock_get_client):
        """Test that get_contributors uses the earliest created_at as added_at."""
        mock_client = MagicMock()

        # Mock contributions response - user_123 has contributions at different times
        mock_contributions_response = MagicMock()
        mock_contributions_response.data = [
            {"contributor_id": "user_123", "created_at": "2025-02-04T11:00:00+00:00"},
            {"contributor_id": "user_123", "created_at": "2025-02-04T10:00:00+00:00"},  # Earliest
            {"contributor_id": "user_123", "created_at": "2025-02-04T12:00:00+00:00"},
        ]

        # Mock user profiles response
        mock_users_response = MagicMock()
        mock_users_response.data = [
            {"id": "user_123", "full_name": "Alice Johnson", "email": "alice@example.com"},
        ]

        # Set up the mock chain for contributions query
        mock_contributions_query = MagicMock()
        mock_contributions_query.execute.return_value = mock_contributions_response
        mock_contributions_eq = MagicMock()
        mock_contributions_eq.eq.return_value = mock_contributions_query
        mock_contributions_select = MagicMock()
        mock_contributions_select.select.return_value = mock_contributions_eq

        # Set up the mock chain for users query
        mock_users_query = MagicMock()
        mock_users_query.execute.return_value = mock_users_response
        mock_users_in = MagicMock()
        mock_users_in.in_.return_value = mock_users_query
        mock_users_select = MagicMock()
        mock_users_select.select.return_value = mock_users_in

        # Configure table to return different mocks based on call
        table_call_count = [0]

        def table_side_effect(table_name):
            table_call_count[0] += 1
            if table_name == "lead_memory_contributions" and table_call_count[0] == 1:
                return mock_contributions_select
            elif table_name == "user_profiles":
                return mock_users_select
            return MagicMock()

        mock_client.table.side_effect = table_side_effect
        mock_get_client.return_value = mock_client

        service = LeadCollaborationService(db_client=MagicMock())

        result = await service.get_contributors(
            user_id="user_owner",
            lead_memory_id="lead_456",
        )

        assert len(result) == 1
        alice = result[0]

        # Verify the earliest timestamp is used (10:00, not 11:00 or 12:00)
        assert alice.added_at == datetime(2025, 2, 4, 10, 0, tzinfo=UTC)
        assert alice.contribution_count == 3

    @pytest.mark.asyncio
    @patch("src.services.lead_collaboration.LeadCollaborationService._get_supabase_client")
    async def test_get_contributors_sorts_by_added_at(self, mock_get_client):
        """Test that get_contributors sorts results by added_at ascending."""
        mock_client = MagicMock()

        # Mock contributions response - contributors in different order than added_at
        mock_contributions_response = MagicMock()
        mock_contributions_response.data = [
            {"contributor_id": "user_789", "created_at": "2025-02-04T15:00:00+00:00"},  # Latest
            {"contributor_id": "user_123", "created_at": "2025-02-04T10:00:00+00:00"},  # Earliest
            {"contributor_id": "user_456", "created_at": "2025-02-04T12:00:00+00:00"},  # Middle
        ]

        # Mock user profiles response
        mock_users_response = MagicMock()
        mock_users_response.data = [
            {"id": "user_123", "full_name": "Alice Johnson", "email": "alice@example.com"},
            {"id": "user_456", "full_name": "Bob Smith", "email": "bob@example.com"},
            {"id": "user_789", "full_name": "Carol Davis", "email": "carol@example.com"},
        ]

        # Set up the mock chain for contributions query
        mock_contributions_query = MagicMock()
        mock_contributions_query.execute.return_value = mock_contributions_response
        mock_contributions_eq = MagicMock()
        mock_contributions_eq.eq.return_value = mock_contributions_query
        mock_contributions_select = MagicMock()
        mock_contributions_select.select.return_value = mock_contributions_eq

        # Set up the mock chain for users query
        mock_users_query = MagicMock()
        mock_users_query.execute.return_value = mock_users_response
        mock_users_in = MagicMock()
        mock_users_in.in_.return_value = mock_users_query
        mock_users_select = MagicMock()
        mock_users_select.select.return_value = mock_users_in

        # Configure table to return different mocks based on call
        table_call_count = [0]

        def table_side_effect(table_name):
            table_call_count[0] += 1
            if table_name == "lead_memory_contributions" and table_call_count[0] == 1:
                return mock_contributions_select
            elif table_name == "user_profiles":
                return mock_users_select
            return MagicMock()

        mock_client.table.side_effect = table_side_effect
        mock_get_client.return_value = mock_client

        service = LeadCollaborationService(db_client=MagicMock())

        result = await service.get_contributors(
            user_id="user_owner",
            lead_memory_id="lead_456",
        )

        assert len(result) == 3

        # Verify sorted by added_at ascending (oldest first)
        assert result[0].id == "user_123"  # 10:00
        assert result[1].id == "user_456"  # 12:00
        assert result[2].id == "user_789"  # 15:00

    @pytest.mark.asyncio
    @patch("src.services.lead_collaboration.LeadCollaborationService._get_supabase_client")
    async def test_get_contributors_skips_null_created_at(self, mock_get_client):
        """Test that get_contributors skips contributions with NULL created_at."""
        mock_client = MagicMock()

        # Mock contributions response with NULL created_at values
        mock_contributions_response = MagicMock()
        mock_contributions_response.data = [
            {"contributor_id": "user_123", "created_at": "2025-02-04T10:00:00+00:00"},
            {"contributor_id": "user_123", "created_at": None},  # Should be skipped
            {"contributor_id": "user_456", "created_at": None},  # Entire user should be excluded
        ]

        # Mock user profiles response
        mock_users_response = MagicMock()
        mock_users_response.data = [
            {"id": "user_123", "full_name": "Alice Johnson", "email": "alice@example.com"},
        ]

        # Set up the mock chain for contributions query
        mock_contributions_query = MagicMock()
        mock_contributions_query.execute.return_value = mock_contributions_response
        mock_contributions_eq = MagicMock()
        mock_contributions_eq.eq.return_value = mock_contributions_query
        mock_contributions_select = MagicMock()
        mock_contributions_select.select.return_value = mock_contributions_eq

        # Set up the mock chain for users query
        mock_users_query = MagicMock()
        mock_users_query.execute.return_value = mock_users_response
        mock_users_in = MagicMock()
        mock_users_in.in_.return_value = mock_users_query
        mock_users_select = MagicMock()
        mock_users_select.select.return_value = mock_users_in

        # Configure table to return different mocks based on call
        table_call_count = [0]

        def table_side_effect(table_name):
            table_call_count[0] += 1
            if table_name == "lead_memory_contributions" and table_call_count[0] == 1:
                return mock_contributions_select
            elif table_name == "user_profiles":
                return mock_users_select
            return MagicMock()

        mock_client.table.side_effect = table_side_effect
        mock_get_client.return_value = mock_client

        service = LeadCollaborationService(db_client=MagicMock())

        result = await service.get_contributors(
            user_id="user_owner",
            lead_memory_id="lead_456",
        )

        # Only user_123 should be included (user_456 had only NULL created_at)
        assert len(result) == 1
        assert result[0].id == "user_123"
        assert result[0].contribution_count == 1

    @pytest.mark.asyncio
    @patch("src.services.lead_collaboration.LeadCollaborationService._get_supabase_client")
    async def test_get_contributors_empty(self, mock_get_client):
        """Test that get_contributors returns an empty list when no contributors."""
        mock_client = MagicMock()

        # Mock empty contributions response
        mock_contributions_response = MagicMock()
        mock_contributions_response.data = []

        mock_query = MagicMock()
        mock_query.execute.return_value = mock_contributions_response
        mock_eq = MagicMock()
        mock_eq.eq.return_value = mock_query
        mock_select = MagicMock()
        mock_select.select.return_value = mock_eq

        mock_client.table.return_value = mock_select
        mock_get_client.return_value = mock_client

        service = LeadCollaborationService(db_client=MagicMock())

        result = await service.get_contributors(
            user_id="user_owner",
            lead_memory_id="lead_456",
        )

        assert result == []
        mock_client.table.assert_called_once_with("lead_memory_contributions")

    @pytest.mark.asyncio
    @patch("src.services.lead_collaboration.LeadCollaborationService._get_supabase_client")
    async def test_get_contributors_handles_missing_user_profile(self, mock_get_client):
        """Test that get_contributors handles missing user profiles gracefully."""
        mock_client = MagicMock()

        # Mock contributions response
        mock_contributions_response = MagicMock()
        mock_contributions_response.data = [
            {"contributor_id": "user_123", "created_at": "2025-02-04T10:00:00+00:00"},
        ]

        # Mock user profiles response - user not found
        mock_users_response = MagicMock()
        mock_users_response.data = []

        # Set up the mock chain for contributions query
        mock_contributions_query = MagicMock()
        mock_contributions_query.execute.return_value = mock_contributions_response
        mock_contributions_eq = MagicMock()
        mock_contributions_eq.eq.return_value = mock_contributions_query
        mock_contributions_select = MagicMock()
        mock_contributions_select.select.return_value = mock_contributions_eq

        # Set up the mock chain for users query
        mock_users_query = MagicMock()
        mock_users_query.execute.return_value = mock_users_response
        mock_users_in = MagicMock()
        mock_users_in.in_.return_value = mock_users_query
        mock_users_select = MagicMock()
        mock_users_select.select.return_value = mock_users_in

        # Configure table to return different mocks based on call
        table_call_count = [0]

        def table_side_effect(table_name):
            table_call_count[0] += 1
            if table_name == "lead_memory_contributions" and table_call_count[0] == 1:
                return mock_contributions_select
            elif table_name == "user_profiles":
                return mock_users_select
            return MagicMock()

        mock_client.table.side_effect = table_side_effect
        mock_get_client.return_value = mock_client

        service = LeadCollaborationService(db_client=MagicMock())

        result = await service.get_contributors(
            user_id="user_owner",
            lead_memory_id="lead_456",
        )

        # Should still return a contributor with empty name/email
        assert len(result) == 1
        assert result[0].id == "user_123"
        assert result[0].name == ""
        assert result[0].email == ""
        assert result[0].contribution_count == 1

    @pytest.mark.asyncio
    @patch("src.services.lead_collaboration.LeadCollaborationService._get_supabase_client")
    async def test_get_contributors_handles_database_error(self, mock_get_client):
        """Test that get_contributors raises DatabaseError on database failure."""
        mock_client = MagicMock()
        mock_client.table.side_effect = Exception("Database connection failed")
        mock_get_client.return_value = mock_client

        service = LeadCollaborationService(db_client=MagicMock())

        with pytest.raises(DatabaseError) as exc_info:
            await service.get_contributors(
                user_id="user_owner",
                lead_memory_id="lead_456",
            )

        assert "Failed to get contributors" in str(exc_info.value)
        mock_get_client.assert_called_once()
