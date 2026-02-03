"""Tests for AttendeeProfileService."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_get_profile_returns_none_when_not_found() -> None:
    """Test get_profile returns None when profile doesn't exist."""
    with patch("src.services.attendee_profile.SupabaseClient") as mock_db_class:
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=None
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.attendee_profile import AttendeeProfileService

        service = AttendeeProfileService()
        result = await service.get_profile(email="unknown@example.com")

        assert result is None


@pytest.mark.asyncio
async def test_get_profile_returns_profile_when_found() -> None:
    """Test get_profile returns profile when it exists."""
    with patch("src.services.attendee_profile.SupabaseClient") as mock_db_class:
        mock_profile = {
            "id": "profile-123",
            "email": "john@example.com",
            "name": "John Smith",
            "title": "VP Sales",
            "company": "Acme Corp",
        }

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=mock_profile
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.attendee_profile import AttendeeProfileService

        service = AttendeeProfileService()
        result = await service.get_profile(email="john@example.com")

        assert result is not None
        assert result["name"] == "John Smith"


@pytest.mark.asyncio
async def test_get_profiles_batch_returns_found_profiles() -> None:
    """Test get_profiles_batch returns profiles for known emails."""
    with patch("src.services.attendee_profile.SupabaseClient") as mock_db_class:
        mock_profiles = [
            {"email": "john@example.com", "name": "John"},
            {"email": "jane@example.com", "name": "Jane"},
        ]

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.in_.return_value.execute.return_value = MagicMock(
            data=mock_profiles
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.attendee_profile import AttendeeProfileService

        service = AttendeeProfileService()
        result = await service.get_profiles_batch(
            emails=["john@example.com", "jane@example.com", "unknown@example.com"]
        )

        assert len(result) == 2
        assert "john@example.com" in result


@pytest.mark.asyncio
async def test_upsert_profile_creates_new_profile() -> None:
    """Test upsert_profile creates a new profile."""
    with patch("src.services.attendee_profile.SupabaseClient") as mock_db_class:
        mock_db = MagicMock()
        mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock(
            data=[{"email": "new@example.com", "name": "New Person"}]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.attendee_profile import AttendeeProfileService

        service = AttendeeProfileService()
        result = await service.upsert_profile(
            email="new@example.com",
            name="New Person",
            title="Manager",
            company="NewCo",
        )

        assert result["email"] == "new@example.com"


@pytest.mark.asyncio
async def test_is_stale_returns_true_for_old_profiles() -> None:
    """Test is_stale returns True for profiles older than threshold."""
    with patch("src.services.attendee_profile.SupabaseClient") as mock_db_class:
        # Profile researched 10 days ago
        old_time = (datetime.now(UTC) - timedelta(days=10)).isoformat()
        mock_profile = {
            "email": "old@example.com",
            "last_researched_at": old_time,
        }

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=mock_profile
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.attendee_profile import AttendeeProfileService

        service = AttendeeProfileService()
        result = await service.is_stale(email="old@example.com", max_age_days=7)

        assert result is True


@pytest.mark.asyncio
async def test_is_stale_returns_false_for_recent_profiles() -> None:
    """Test is_stale returns False for recently researched profiles."""
    with patch("src.services.attendee_profile.SupabaseClient") as mock_db_class:
        # Profile researched 3 days ago
        recent_time = (datetime.now(UTC) - timedelta(days=3)).isoformat()
        mock_profile = {
            "email": "recent@example.com",
            "last_researched_at": recent_time,
        }

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=mock_profile
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.attendee_profile import AttendeeProfileService

        service = AttendeeProfileService()
        result = await service.is_stale(email="recent@example.com", max_age_days=7)

        assert result is False


@pytest.mark.asyncio
async def test_is_stale_returns_true_for_missing_profiles() -> None:
    """Test is_stale returns True when profile doesn't exist."""
    with patch("src.services.attendee_profile.SupabaseClient") as mock_db_class:
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=None
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.attendee_profile import AttendeeProfileService

        service = AttendeeProfileService()
        result = await service.is_stale(email="missing@example.com", max_age_days=7)

        assert result is True


@pytest.mark.asyncio
async def test_is_stale_returns_true_when_no_last_researched_at() -> None:
    """Test is_stale returns True when profile has no last_researched_at."""
    with patch("src.services.attendee_profile.SupabaseClient") as mock_db_class:
        mock_profile = {
            "email": "incomplete@example.com",
            "last_researched_at": None,
        }

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=mock_profile
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.attendee_profile import AttendeeProfileService

        service = AttendeeProfileService()
        result = await service.is_stale(email="incomplete@example.com", max_age_days=7)

        assert result is True


@pytest.mark.asyncio
async def test_mark_not_found_updates_status() -> None:
    """Test mark_not_found updates the profile status to not_found."""
    with patch("src.services.attendee_profile.SupabaseClient") as mock_db_class:
        mock_db = MagicMock()
        mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock(
            data=[{"email": "unknown@example.com", "research_status": "not_found"}]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.attendee_profile import AttendeeProfileService

        service = AttendeeProfileService()
        result = await service.mark_not_found(email="unknown@example.com")

        assert result["research_status"] == "not_found"


@pytest.mark.asyncio
async def test_get_profiles_batch_returns_empty_for_empty_input() -> None:
    """Test get_profiles_batch returns empty dict for empty email list."""
    with patch("src.services.attendee_profile.SupabaseClient") as mock_db_class:
        mock_db = MagicMock()
        mock_db_class.get_client.return_value = mock_db

        from src.services.attendee_profile import AttendeeProfileService

        service = AttendeeProfileService()
        result = await service.get_profiles_batch(emails=[])

        assert result == {}
        # Should not call database for empty list
        mock_db.table.assert_not_called()


@pytest.mark.asyncio
async def test_get_profile_normalizes_email_to_lowercase() -> None:
    """Test get_profile normalizes email to lowercase."""
    with patch("src.services.attendee_profile.SupabaseClient") as mock_db_class:
        mock_db = MagicMock()
        mock_eq = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value = mock_eq
        mock_eq.single.return_value.execute.return_value = MagicMock(data=None)
        mock_db_class.get_client.return_value = mock_db

        from src.services.attendee_profile import AttendeeProfileService

        service = AttendeeProfileService()
        await service.get_profile(email="JOHN@EXAMPLE.COM")

        # Verify email was normalized to lowercase
        mock_db.table.return_value.select.return_value.eq.assert_called_once_with(
            "email", "john@example.com"
        )


@pytest.mark.asyncio
async def test_upsert_profile_normalizes_email_to_lowercase() -> None:
    """Test upsert_profile normalizes email to lowercase."""
    with patch("src.services.attendee_profile.SupabaseClient") as mock_db_class:
        mock_db = MagicMock()
        mock_upsert = MagicMock()
        mock_db.table.return_value.upsert.return_value = mock_upsert
        mock_upsert.execute.return_value = MagicMock(
            data=[{"email": "john@example.com", "name": "John"}]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.attendee_profile import AttendeeProfileService

        service = AttendeeProfileService()
        await service.upsert_profile(email="JOHN@EXAMPLE.COM", name="John")

        # Verify email was normalized in the upsert call
        call_args = mock_db.table.return_value.upsert.call_args
        assert call_args[0][0]["email"] == "john@example.com"


@pytest.mark.asyncio
async def test_get_profiles_batch_normalizes_emails_to_lowercase() -> None:
    """Test get_profiles_batch normalizes emails to lowercase."""
    with patch("src.services.attendee_profile.SupabaseClient") as mock_db_class:
        mock_db = MagicMock()
        mock_in_ = MagicMock()
        mock_db.table.return_value.select.return_value.in_.return_value = mock_in_
        mock_in_.execute.return_value = MagicMock(data=[])
        mock_db_class.get_client.return_value = mock_db

        from src.services.attendee_profile import AttendeeProfileService

        service = AttendeeProfileService()
        await service.get_profiles_batch(emails=["JOHN@EXAMPLE.COM", "Jane@Example.COM"])

        # Verify emails were normalized to lowercase
        mock_db.table.return_value.select.return_value.in_.assert_called_once_with(
            "email", ["john@example.com", "jane@example.com"]
        )
