"""Tests for EmailService (US-934)."""

from unittest.mock import MagicMock, patch

import pytest
import resend

from src.services.email_service import EmailService


@pytest.fixture
def email_service():
    """Create EmailService instance."""
    return EmailService()


class TestEmailService:
    """Test EmailService functionality."""

    @pytest.mark.asyncio
    async def test_send_welcome(self, email_service):
        """Test sending welcome email."""
        with patch("src.services.email_service.resend") as mock_resend:
            # Set api_key so the service doesn't return mock_email_id
            email_service._api_key = "test_key"
            resend.api_key = "test_key"
            mock_resend.Emails.send = MagicMock(return_value={"id": "email_id"})

            result = await email_service.send_welcome("test@example.com", "John Doe")

            assert result == "email_id"
            mock_resend.Emails.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_onboarding_complete(self, email_service):
        """Test sending onboarding complete email."""
        with patch("src.services.email_service.resend") as mock_resend:
            email_service._api_key = "test_key"
            resend.api_key = "test_key"
            mock_resend.Emails.send = MagicMock(return_value={"id": "email_id"})

            result = await email_service.send_onboarding_complete("test@example.com", "John", 85)

            assert result == "email_id"
            mock_resend.Emails.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_team_invite(self, email_service):
        """Test sending team invite email."""
        with patch("src.services.email_service.resend") as mock_resend:
            email_service._api_key = "test_key"
            resend.api_key = "test_key"
            mock_resend.Emails.send = MagicMock(return_value={"id": "email_id"})

            result = await email_service.send_team_invite(
                "test@example.com", "Inviter Name", "Acme Corp", "https://example.com/invite"
            )

            assert result == "email_id"
            mock_resend.Emails.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_password_reset(self, email_service):
        """Test sending password reset email."""
        with patch("src.services.email_service.resend") as mock_resend:
            email_service._api_key = "test_key"
            resend.api_key = "test_key"
            mock_resend.Emails.send = MagicMock(return_value={"id": "email_id"})

            result = await email_service.send_password_reset(
                "test@example.com", "https://example.com/reset"
            )

            assert result == "email_id"
            mock_resend.Emails.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_weekly_summary(self, email_service):
        """Test sending weekly summary email."""
        with patch("src.services.email_service.resend") as mock_resend:
            email_service._api_key = "test_key"
            resend.api_key = "test_key"
            mock_resend.Emails.send = MagicMock(return_value={"id": "email_id"})

            result = await email_service.send_weekly_summary(
                "test@example.com", "John", {"insights": 5, "leads": 2}
            )

            assert result == "email_id"
            mock_resend.Emails.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_payment_receipt(self, email_service):
        """Test sending payment receipt email."""
        with patch("src.services.email_service.resend") as mock_resend:
            email_service._api_key = "test_key"
            resend.api_key = "test_key"
            mock_resend.Emails.send = MagicMock(return_value={"id": "email_id"})

            result = await email_service.send_payment_receipt(
                "test@example.com", 200000, "2026-02-07"
            )

            assert result == "email_id"
            mock_resend.Emails.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_payment_failed(self, email_service):
        """Test sending payment failed email."""
        with patch("src.services.email_service.resend") as mock_resend:
            email_service._api_key = "test_key"
            resend.api_key = "test_key"
            mock_resend.Emails.send = MagicMock(return_value={"id": "email_id"})

            result = await email_service.send_payment_failed("test@example.com", "John")

            assert result == "email_id"
            mock_resend.Emails.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_template_renders_without_errors(self, email_service):
        """Test that all templates render without errors."""
        templates = [
            "welcome",
            "onboarding_complete",
            "team_invite",
            "password_reset",
            "weekly_summary",
            "payment_receipt",
            "payment_failed",
        ]

        for template_name in templates:
            template = email_service._get_template(template_name)
            # Should not raise
            html = template.substitute(
                name="Test User",
                company_name="Acme Corp",
                invite_url="https://example.com",
                reset_url="https://example.com/reset",
                readiness_score="85",
                summary_data="Weekly summary content",
                amount="$200,000",
                date="2026-02-07",
                inviter_name="Jane Doe",
                unsubscribe_url="https://example.com/unsubscribe",
                app_url="https://example.com",
            )
            assert "<!DOCTYPE html>" in html or "<html" in html

    def test_check_email_preferences_opt_in(self, email_service):
        """Test that opt-in emails respect user preferences."""
        # Security alerts always true
        assert email_service._should_send_email("password_reset", {"security_alerts": True})
        assert email_service._should_send_email("password_reset", {"security_alerts": False})

        # Weekly summary respects preferences
        assert not email_service._should_send_email("weekly_summary", {"weekly_summary": False})
        assert email_service._should_send_email("weekly_summary", {"weekly_summary": True})

    def test_check_email_preferences_feature_announcements(self, email_service):
        """Test that feature announcements respect user preferences."""
        # Feature announcements respect preferences
        assert not email_service._should_send_email(
            "feature_announcement", {"feature_announcements": False}
        )
        assert email_service._should_send_email(
            "feature_announcement", {"feature_announcements": True}
        )

    def test_check_email_preferences_defaults(self, email_service):
        """Test that emails default to sending when preferences not set."""
        # Defaults to true for all types
        assert email_service._should_send_email("weekly_summary", {})
        assert email_service._should_send_email("feature_announcement", {})
