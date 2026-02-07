"""Email Service (US-934).

Provides transactional email functionality using Resend.
Handles welcome emails, onboarding complete, team invites,
password resets, weekly summaries, and payment notifications.
"""

import logging
from pathlib import Path
from string import Template
from typing import Any

import resend

from src.core.config import settings
from src.core.exceptions import ARIAException
from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


class EmailError(ARIAException):
    """Email operation error."""

    def __init__(self, message: str = "Email operation failed") -> None:
        """Initialize email error.

        Args:
            message: Error details.
        """
        super().__init__(
            message=message,
            code="EMAIL_ERROR",
            status_code=500,
        )


class EmailService:
    """Service for sending transactional emails via Resend."""

    def __init__(self) -> None:
        """Initialize EmailService."""
        self._api_key = settings.RESEND_API_KEY.get_secret_value()
        if not self._api_key:
            logger.warning("RESEND_API_KEY not configured - emails will be logged but not sent")
        else:
            resend.api_key = self._api_key

        # Template directory
        self._template_dir = Path(__file__).parent.parent / "templates" / "email"

    def _get_template(self, template_name: str) -> Template:
        """Load an email template.

        Args:
            template_name: Name of template file (without .html extension).

        Returns:
            Template object ready for substitution.

        Raises:
            EmailError: If template file not found.
        """
        template_path = self._template_dir / f"{template_name}.html"
        try:
            content = template_path.read_text()
            return Template(content)
        except FileNotFoundError as e:
            logger.error(f"Template not found: {template_path}")
            raise EmailError(f"Email template '{template_name}' not found") from e

    def _should_send_email(self, email_type: str, user_preferences: dict[str, Any]) -> bool:
        """Check if email should be sent based on user preferences.

        Args:
            email_type: Type of email (weekly_summary, feature_announcement, password_reset, etc.)
            user_preferences: User's email preferences from user_settings.preferences

        Returns:
            True if email should be sent, False otherwise.
        """
        # Security alerts (password_reset, etc.) cannot be disabled
        if email_type in {"password_reset", "security_alert"}:
            return True

        # Marketing emails respect preferences
        if email_type == "weekly_summary":
            pref_value = user_preferences.get("weekly_summary", True)
            return bool(pref_value) if isinstance(pref_value, (bool, int)) else True

        if email_type == "feature_announcement":
            pref_value = user_preferences.get("feature_announcements", True)
            return bool(pref_value) if isinstance(pref_value, (bool, int)) else True

        # Default to sending for operational emails
        return True

    async def _get_user_email_preferences(self, user_id: str) -> dict[str, Any]:
        """Get user's email preferences.

        Args:
            user_id: The user's UUID.

        Returns:
            Dictionary with email preferences (weekly_summary, feature_announcements, security_alerts).
        """
        defaults = {
            "weekly_summary": True,
            "feature_announcements": True,
            "security_alerts": True,
        }

        try:
            settings_data = await SupabaseClient.get_user_settings(user_id)
            preferences = settings_data.get("preferences", {})
            if isinstance(preferences, dict):
                email_prefs = preferences.get("email_preferences")
                if isinstance(email_prefs, dict):
                    # Cast to satisfy mypy since we've already checked it's a dict
                    return dict(email_prefs)
            return defaults
        except Exception as e:
            logger.warning(f"Failed to fetch email preferences for {user_id}: {e}")
            # Return defaults
            return defaults

    async def send_welcome(self, to: str, name: str) -> str:
        """Send welcome email to new user.

        Args:
            to: Recipient email address.
            name: User's full name.

        Returns:
            Email ID from Resend.

        Raises:
            EmailError: If sending fails.
        """
        template = self._get_template("welcome")
        html = template.substitute(
            name=name,
            app_url=settings.APP_URL,
        )

        return await self._send_email(
            to=to,
            subject="Welcome to ARIA",
            html=html,
        )

    async def send_onboarding_complete(self, to: str, name: str, readiness_score: int) -> str:
        """Send onboarding complete email.

        Args:
            to: Recipient email address.
            name: User's full name.
            readiness_score: User's readiness score (0-100).

        Returns:
            Email ID from Resend.

        Raises:
            EmailError: If sending fails.
        """
        template = self._get_template("onboarding_complete")
        html = template.substitute(
            name=name,
            readiness_score=str(readiness_score),
            app_url=settings.APP_URL,
        )

        return await self._send_email(
            to=to,
            subject="ARIA is Ready",
            html=html,
        )

    async def send_team_invite(
        self, to: str, inviter_name: str, company_name: str, invite_url: str
    ) -> str:
        """Send team invite email.

        Args:
            to: Recipient email address.
            inviter_name: Name of user who sent the invite.
            company_name: Company name.
            invite_url: Invite acceptance URL.

        Returns:
            Email ID from Resend.

        Raises:
            EmailError: If sending fails.
        """
        template = self._get_template("team_invite")
        html = template.substitute(
            inviter_name=inviter_name,
            company_name=company_name,
            invite_url=invite_url,
        )

        return await self._send_email(
            to=to,
            subject=f"Join {company_name} on ARIA",
            html=html,
        )

    async def send_password_reset(self, to: str, reset_url: str) -> str:
        """Send password reset email.

        Args:
            to: Recipient email address.
            reset_url: Password reset URL.

        Returns:
            Email ID from Resend.

        Raises:
            EmailError: If sending fails.
        """
        template = self._get_template("password_reset")
        html = template.substitute(reset_url=reset_url)

        return await self._send_email(
            to=to,
            subject="Reset Your ARIA Password",
            html=html,
        )

    async def send_weekly_summary(self, to: str, name: str, summary_data: dict[str, Any]) -> str:
        """Send weekly summary email (opt-in).

        Args:
            to: Recipient email address.
            name: User's full name.
            summary_data: Dictionary with summary content.

        Returns:
            Email ID from Resend.

        Raises:
            EmailError: If sending fails.
        """
        # Check user preferences - this is an opt-in email
        # We need user_id to check preferences, but email address is uniquely tied to user
        # For now, we'll send and let the caller handle preference checking
        template = self._get_template("weekly_summary")

        # Format summary data as HTML list
        summary_html = ""
        for key, value in summary_data.items():
            summary_html += f'<p style="margin: 0 0 8px; color: #374151; font-size: 14px;"><strong>{key}:</strong> {value}</p>'

        html = template.substitute(
            name=name,
            summary_data=summary_html,
            app_url=settings.APP_URL,
            unsubscribe_url=f"{settings.APP_URL}/settings/email-preferences",
        )

        return await self._send_email(
            to=to,
            subject="Your Weekly ARIA Summary",
            html=html,
        )

    async def send_payment_receipt(self, to: str, amount: int, date: str) -> str:
        """Send payment receipt email.

        Args:
            to: Recipient email address.
            amount: Amount in cents (e.g., 200000 for $2000.00).
            date: Payment date in ISO format.

        Returns:
            Email ID from Resend.

        Raises:
            EmailError: If sending fails.
        """
        # Convert cents to dollars
        amount_dollars = f"${amount / 100:,.2f}"

        template = self._get_template("payment_receipt")
        html = template.substitute(
            amount=amount_dollars,
            date=date,
            app_url=settings.APP_URL,
        )

        return await self._send_email(
            to=to,
            subject="ARIA Payment Receipt",
            html=html,
        )

    async def send_payment_failed(self, to: str, name: str) -> str:
        """Send payment failed notification email.

        Args:
            to: Recipient email address.
            name: User's full name.

        Returns:
            Email ID from Resend.

        Raises:
            EmailError: If sending fails.
        """
        template = self._get_template("payment_failed")
        html = template.substitute(
            name=name,
            app_url=settings.APP_URL,
        )

        return await self._send_email(
            to=to,
            subject="ARIA Payment Failed - Action Required",
            html=html,
        )

    async def _send_email(self, to: str, subject: str, html: str) -> str:
        """Send an email via Resend.

        Args:
            to: Recipient email address.
            subject: Email subject line.
            html: Email HTML content.

        Returns:
            Email ID from Resend.

        Raises:
            EmailError: If sending fails.
        """
        if not self._api_key:
            # Log instead of sending if not configured
            logger.info(
                "Email not sent (RESEND_API_KEY not configured)",
                extra={
                    "to": to,
                    "subject": subject,
                },
            )
            return "mock_email_id"

        try:
            params: resend.Emails.SendParams = {
                "from": settings.FROM_EMAIL,
                "to": [to],
                "subject": subject,
                "html": html,
            }

            result = resend.Emails.send(params)
            email_id = result.get("id", "")

            logger.info(
                "Email sent successfully",
                extra={"email_id": email_id, "to": to, "subject": subject},
            )
            return email_id

        except Exception as e:
            logger.exception("Error sending email", extra={"to": to, "subject": subject})
            raise EmailError(f"Failed to send email: {e}") from e
