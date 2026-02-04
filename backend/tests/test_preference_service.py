"""Tests for PreferenceService."""

from unittest.mock import MagicMock, patch

import pytest

from src.models.preferences import DefaultTone, MeetingBriefLeadHours, PreferenceUpdate


@pytest.fixture
def mock_db() -> MagicMock:
    """Create mock Supabase client."""
    return MagicMock()


@pytest.mark.asyncio
async def test_get_preferences_existing_user(mock_db: MagicMock) -> None:
    """Test get_preferences returns preferences for existing user."""
    with patch("src.services.preference_service.SupabaseClient") as mock_db_class:
        expected_prefs = {
            "id": "pref-123",
            "user_id": "user-456",
            "briefing_time": "08:00:00",
            "meeting_brief_lead_hours": 24,
            "notification_email": True,
            "notification_in_app": True,
            "default_tone": "friendly",
            "tracked_competitors": [],
            "timezone": "UTC",
            "created_at": "2026-02-03T10:00:00Z",
            "updated_at": "2026-02-03T10:00:00Z",
        }

        # Mock successful response
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=expected_prefs
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.preference_service import PreferenceService

        service = PreferenceService()
        result = await service.get_preferences("user-456")

        assert result["id"] == "pref-123"
        assert result["user_id"] == "user-456"
        assert result["briefing_time"] == "08:00:00"
        assert result["meeting_brief_lead_hours"] == 24
        assert result["notification_email"] is True
        assert result["default_tone"] == "friendly"

        # Verify table query was made
        mock_db.table.assert_called_with("user_preferences")


@pytest.mark.asyncio
async def test_get_preferences_creates_defaults_when_not_found(mock_db: MagicMock) -> None:
    """Test get_preferences creates default preferences when user has none."""
    with patch("src.services.preference_service.SupabaseClient") as mock_db_class:
        default_prefs = {
            "id": "pref-new",
            "user_id": "user-789",
            "briefing_time": "08:00:00",
            "meeting_brief_lead_hours": 24,
            "notification_email": True,
            "notification_in_app": True,
            "default_tone": "friendly",
            "tracked_competitors": [],
            "timezone": "UTC",
            "created_at": "2026-02-03T10:00:00Z",
            "updated_at": "2026-02-03T10:00:00Z",
        }

        # Mock not found response (None data)
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=None
        )
        # Mock insert response
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[default_prefs]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.preference_service import PreferenceService

        service = PreferenceService()
        result = await service.get_preferences("user-789")

        assert result["id"] == "pref-new"
        assert result["user_id"] == "user-789"

        # Verify insert was called
        mock_db.table.return_value.insert.assert_called_once()


@pytest.mark.asyncio
async def test_update_preferences(mock_db: MagicMock) -> None:
    """Test update_preferences updates and returns updated data."""
    with patch("src.services.preference_service.SupabaseClient") as mock_db_class:
        existing_prefs = {
            "id": "pref-123",
            "user_id": "user-456",
            "briefing_time": "08:00:00",
            "meeting_brief_lead_hours": 24,
            "notification_email": True,
            "notification_in_app": True,
            "default_tone": "friendly",
            "tracked_competitors": [],
            "timezone": "UTC",
        }
        updated_prefs = {
            "id": "pref-123",
            "user_id": "user-456",
            "briefing_time": "09:30",
            "meeting_brief_lead_hours": 12,
            "notification_email": False,
            "notification_in_app": True,
            "default_tone": "formal",
            "tracked_competitors": ["Competitor A", "Competitor B"],
            "timezone": "America/New_York",
            "updated_at": "2026-02-03T12:00:00Z",
        }

        # Mock get_preferences (existing)
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=existing_prefs
        )
        # Mock update response
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[updated_prefs]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.preference_service import PreferenceService

        service = PreferenceService()
        update_data = PreferenceUpdate(
            briefing_time="09:30",
            meeting_brief_lead_hours=MeetingBriefLeadHours.TWELVE_HOURS,
            notification_email=False,
            default_tone=DefaultTone.FORMAL,
            tracked_competitors=["Competitor A", "Competitor B"],
            timezone="America/New_York",
        )
        result = await service.update_preferences("user-456", update_data)

        assert result["id"] == "pref-123"
        assert result["briefing_time"] == "09:30"
        assert result["meeting_brief_lead_hours"] == 12
        assert result["notification_email"] is False
        assert result["default_tone"] == "formal"
        assert result["tracked_competitors"] == ["Competitor A", "Competitor B"]
        assert result["timezone"] == "America/New_York"

        # Verify update was called
        mock_db.table.return_value.update.assert_called_once()


@pytest.mark.asyncio
async def test_update_preferences_partial_update(mock_db: MagicMock) -> None:
    """Test update_preferences with only some fields set."""
    with patch("src.services.preference_service.SupabaseClient") as mock_db_class:
        existing_prefs = {
            "id": "pref-123",
            "user_id": "user-456",
            "briefing_time": "08:00:00",
            "meeting_brief_lead_hours": 24,
            "notification_email": True,
            "notification_in_app": True,
            "default_tone": "friendly",
            "tracked_competitors": [],
            "timezone": "UTC",
        }
        updated_prefs = {
            "id": "pref-123",
            "user_id": "user-456",
            "briefing_time": "08:00:00",
            "meeting_brief_lead_hours": 24,
            "notification_email": False,
            "notification_in_app": True,
            "default_tone": "friendly",
            "tracked_competitors": [],
            "timezone": "UTC",
            "updated_at": "2026-02-03T12:00:00Z",
        }

        # Mock get_preferences (existing)
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=existing_prefs
        )
        # Mock update response
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[updated_prefs]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.preference_service import PreferenceService

        service = PreferenceService()
        # Only update notification_email
        update_data = PreferenceUpdate(notification_email=False)
        result = await service.update_preferences("user-456", update_data)

        assert result["notification_email"] is False
        # Other fields should remain unchanged
        assert result["briefing_time"] == "08:00:00"
        assert result["meeting_brief_lead_hours"] == 24
        assert result["default_tone"] == "friendly"


@pytest.mark.asyncio
async def test_update_preferences_no_changes(mock_db: MagicMock) -> None:
    """Test update_preferences returns current prefs when no fields to update."""
    with patch("src.services.preference_service.SupabaseClient") as mock_db_class:
        existing_prefs = {
            "id": "pref-123",
            "user_id": "user-456",
            "briefing_time": "08:00:00",
            "meeting_brief_lead_hours": 24,
            "notification_email": True,
            "notification_in_app": True,
            "default_tone": "friendly",
            "tracked_competitors": [],
            "timezone": "UTC",
        }

        # Mock get_preferences (existing)
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=existing_prefs
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.preference_service import PreferenceService

        service = PreferenceService()
        # Empty update - all None values
        update_data = PreferenceUpdate()
        result = await service.update_preferences("user-456", update_data)

        assert result == existing_prefs
        # Verify update was NOT called (no changes)
        mock_db.table.return_value.update.assert_not_called()


@pytest.mark.asyncio
async def test_update_preferences_creates_defaults_if_not_exists(mock_db: MagicMock) -> None:
    """Test update_preferences creates defaults if user has no preferences."""
    with patch("src.services.preference_service.SupabaseClient") as mock_db_class:
        default_prefs = {
            "id": "pref-new",
            "user_id": "user-new",
            "briefing_time": "08:00:00",
            "meeting_brief_lead_hours": 24,
            "notification_email": True,
            "notification_in_app": True,
            "default_tone": "friendly",
            "tracked_competitors": [],
            "timezone": "UTC",
        }
        updated_prefs = {
            "id": "pref-new",
            "user_id": "user-new",
            "briefing_time": "10:00",
            "meeting_brief_lead_hours": 24,
            "notification_email": True,
            "notification_in_app": True,
            "default_tone": "friendly",
            "tracked_competitors": [],
            "timezone": "UTC",
            "updated_at": "2026-02-03T12:00:00Z",
        }

        # First call (get_preferences initial check) returns None
        # Second call (after insert) returns default_prefs
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = [
            MagicMock(data=None),  # First get (not found)
        ]
        # Mock insert response for _create_default_preferences
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[default_prefs]
        )
        # Mock update response
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[updated_prefs]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.preference_service import PreferenceService

        service = PreferenceService()
        update_data = PreferenceUpdate(briefing_time="10:00")
        result = await service.update_preferences("user-new", update_data)

        assert result["briefing_time"] == "10:00"
        # Verify insert was called (to create defaults)
        mock_db.table.return_value.insert.assert_called_once()


@pytest.mark.asyncio
async def test_create_default_preferences(mock_db: MagicMock) -> None:
    """Test _create_default_preferences inserts default record."""
    with patch("src.services.preference_service.SupabaseClient") as mock_db_class:
        default_prefs = {
            "id": "pref-123",
            "user_id": "user-456",
            "briefing_time": "08:00:00",
            "meeting_brief_lead_hours": 24,
            "notification_email": True,
            "notification_in_app": True,
            "default_tone": "friendly",
            "tracked_competitors": [],
            "timezone": "UTC",
            "created_at": "2026-02-03T10:00:00Z",
            "updated_at": "2026-02-03T10:00:00Z",
        }

        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[default_prefs]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.preference_service import PreferenceService

        service = PreferenceService()
        result = await service._create_default_preferences("user-456")

        assert result["id"] == "pref-123"
        assert result["user_id"] == "user-456"

        # Verify insert was called with user_id
        call_args = mock_db.table.return_value.insert.call_args
        assert call_args[0][0]["user_id"] == "user-456"
