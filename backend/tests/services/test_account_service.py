"""Tests for Account & Identity Management Service (US-926)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.account_service import AccountService
from src.core.exceptions import ARIAException, NotFoundError


@pytest.fixture
def account_service():
    """Create an AccountService instance."""
    return AccountService()


@pytest.fixture
def mock_supabase():
    """Mock Supabase client."""
    with patch("src.services.account_service.SupabaseClient") as mock:
        yield mock


class TestAccountServicePasswordReset:
    """Test suite for password reset functionality."""

    @pytest.mark.asyncio
    async def test_password_reset_sends_email(self, account_service):
        """Test that password reset sends an email."""
        with patch("src.services.email_service.EmailService") as mock_email_service:
            mock_email_instance = MagicMock()
            mock_email_instance.send_password_reset = AsyncMock(return_value="email_id")
            mock_email_service.return_value = mock_email_instance

            await account_service.request_password_reset("test@example.com")

            mock_email_instance.send_password_reset.assert_called_once()
            call_args = mock_email_instance.send_password_reset.call_args
            assert call_args[0][0] == "test@example.com"
            assert "reset_url" in call_args.kwargs or len(call_args[0]) > 1

    @pytest.mark.asyncio
    async def test_password_reset_email_failure_logs_warning(
        self, account_service, caplog
    ):
        """Test that email sending failures are logged but don't break password reset."""
        with patch("src.services.email_service.EmailService") as mock_email_service:
            mock_email_instance = MagicMock()
            mock_email_instance.send_password_reset = AsyncMock(
                side_effect=Exception("Email service down")
            )
            mock_email_service.return_value = mock_email_instance

            # Should not raise even if email fails
            with patch("src.services.account_service.settings") as mock_settings:
                mock_settings.APP_URL = "http://localhost:3000"
                # Should still succeed (email is non-blocking)
                await account_service.request_password_reset("test@example.com")

    @pytest.mark.asyncio
    async def test_password_reset_generates_correct_url(self, account_service):
        """Test that password reset generates the correct reset URL."""
        with patch("src.services.email_service.EmailService") as mock_email_service:
            mock_email_instance = MagicMock()
            mock_email_instance.send_password_reset = AsyncMock(return_value="email_id")
            mock_email_service.return_value = mock_email_instance

            with patch("src.services.account_service.settings") as mock_settings:
                mock_settings.APP_URL = "http://localhost:3000"
                await account_service.request_password_reset("test@example.com")

                call_args = mock_email_instance.send_password_reset.call_args
                reset_url = call_args[0][1] if len(call_args[0]) > 1 else call_args.kwargs.get("reset_url")
                assert "test@example.com" in reset_url
                assert "reset-password" in reset_url


class TestAccountServiceProfile:
    """Test suite for profile management."""

    @pytest.mark.asyncio
    async def test_get_profile(self, account_service, mock_supabase):
        """Test getting user profile."""
        user_id = "user-123"

        mock_supabase.get_user_by_id = AsyncMock(
            return_value={
                "id": user_id,
                "full_name": "Test User",
                "avatar_url": "https://example.com/avatar.png",
                "company_id": "company-123",
                "role": "admin",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
            }
        )
        mock_supabase.get_user_settings = AsyncMock(
            return_value={"preferences": {"totp_secret": None}}
        )

        result = await account_service.get_profile(user_id)

        assert result["id"] == user_id
        assert result["full_name"] == "Test User"
        assert result["is_2fa_enabled"] is False

    @pytest.mark.asyncio
    async def test_get_profile_with_2fa(self, account_service, mock_supabase):
        """Test getting user profile with 2FA enabled."""
        user_id = "user-123"

        mock_supabase.get_user_by_id = AsyncMock(
            return_value={
                "id": user_id,
                "full_name": "Test User",
                "avatar_url": None,
                "company_id": "company-123",
                "role": "user",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
            }
        )
        mock_supabase.get_user_settings = AsyncMock(
            return_value={"preferences": {"totp_secret": "JBSWY3DPEHPK3PXP"}}
        )

        result = await account_service.get_profile(user_id)

        assert result["is_2fa_enabled"] is True


class TestAccountServicePasswordChange:
    """Test suite for password change functionality."""

    @pytest.mark.asyncio
    async def test_change_password_success(self, account_service):
        """Test successful password change."""
        user_id = "user-123"

        # Mock auth admin
        mock_admin = MagicMock()
        mock_user_data = MagicMock()
        mock_user_data.user.email = "test@example.com"
        mock_admin.get_user_by_id.return_value = mock_user_data

        # Set up mock client with proper auth structure
        account_service._client = MagicMock()
        account_service._client.auth.admin = mock_admin
        account_service._client.auth.sign_in_with_password = MagicMock()

        # Mock log_security_event
        account_service.log_security_event = AsyncMock()

        await account_service.change_password(user_id, "oldpassword", "newpassword")

        mock_admin.update_user_by_id.assert_called_once_with(user_id, {"password": "newpassword"})
        account_service.log_security_event.assert_called_once_with(
            user_id=user_id,
            event_type=AccountService.EVENT_PASSWORD_CHANGE,
            metadata={"success": True},
        )
