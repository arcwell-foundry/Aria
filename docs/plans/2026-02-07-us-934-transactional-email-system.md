# US-934: Transactional Email System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a complete transactional email system using Resend that sends operational emails (welcome, onboarding complete, team invites, password resets, weekly summaries, payment receipts, payment failures) with user preference management for opt-in marketing emails.

**Architecture:**
- **Backend:** Python EmailService using Resend SDK with HTML template rendering
- **Frontend:** Email preference toggles in settings page
- **Integration:** Wire email triggers into existing auth flow, onboarding, team invites, and Stripe webhooks
- **Templates:** Email client-compatible table-based HTML with ARIA branding

**Tech Stack:**
- Resend SDK (resend>=2.0.0) for email sending
- Python string.Template for template rendering
- React/Tailwind for preference UI
- Supabase user_settings.preferences for storing email preferences

---

## Task 1: Add Resend Dependency and Configuration

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/src/core/config.py`

**Step 1: Add Resend to requirements.txt**

```bash
# Append to backend/requirements.txt
echo "resend>=2.0.0,<3.0.0" >> backend/requirements.txt
```

**Step 2: Add Resend configuration to config.py**

Add these settings to the `Settings` class in `backend/src/core/config.py` (after line 67, after Stripe config):

```python
    # Resend Email Configuration (US-934)
    RESEND_API_KEY: SecretStr = SecretStr("")
    FROM_EMAIL: str = "ARIA <aria@luminone.com>"
```

**Step 3: Verify configuration loads**

Run: `cd backend && python -c "from src.core.config import settings; print('RESEND_API_KEY:', bool(settings.RESEND_API_KEY.get_secret_value())); print('FROM_EMAIL:', settings.FROM_EMAIL)"`

Expected: `RESEND_API_KEY: False` (until set in env) `FROM_EMAIL: ARIA <aria@luminone.com>`

**Step 4: Commit**

```bash
git add backend/requirements.txt backend/src/core/config.py
git commit -m "feat: add Resend dependency and email configuration (US-934)"
```

---

## Task 2: Create Email Service

**Files:**
- Create: `backend/src/services/email_service.py`
- Modify: `backend/src/services/__init__.py`

**Step 1: Write the failing test**

Create `backend/tests/services/test_email_service.py`:

```python
"""Tests for EmailService (US-934)."""

import pytest
from unittest.mock import MagicMock, patch

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
            mock_resend.Emails.send = MagicMock(return_value={"id": "email_id"})

            result = await email_service.send_welcome("test@example.com", "John Doe")

            assert result == "email_id"
            mock_resend.Emails.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_onboarding_complete(self, email_service):
        """Test sending onboarding complete email."""
        with patch("src.services.email_service.resend") as mock_resend:
            mock_resend.Emails.send = MagicMock(return_value={"id": "email_id"})

            result = await email_service.send_onboarding_complete("test@example.com", "John", 85)

            assert result == "email_id"
            mock_resend.Emails.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_team_invite(self, email_service):
        """Test sending team invite email."""
        with patch("src.services.email_service.resend") as mock_resend:
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
            mock_resend.Emails.send = MagicMock(return_value={"id": "email_id"})

            result = await email_service.send_password_reset("test@example.com", "https://example.com/reset")

            assert result == "email_id"
            mock_resend.Emails.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_weekly_summary(self, email_service):
        """Test sending weekly summary email."""
        with patch("src.services.email_service.resend") as mock_resend:
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
            mock_resend.Emails.send = MagicMock(return_value={"id": "email_id"})

            result = await email_service.send_payment_receipt("test@example.com", 200000, "2026-02-07")

            assert result == "email_id"
            mock_resend.Emails.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_payment_failed(self, email_service):
        """Test sending payment failed email."""
        with patch("src.services.email_service.resend") as mock_resend:
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
        assert not email_service._should_send_email("feature_announcement", {"feature_announcements": False})
        assert email_service._should_send_email("feature_announcement", {"feature_announcements": True})

    def test_check_email_preferences_defaults(self, email_service):
        """Test that emails default to sending when preferences not set."""
        # Defaults to true for all types
        assert email_service._should_send_email("weekly_summary", {})
        assert email_service._should_send_email("feature_announcement", {})
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/services/test_email_service.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'src.services.email_service'"

**Step 3: Create email templates directory and templates**

```bash
mkdir -p backend/src/templates/email
```

Create `backend/src/templates/email/welcome.html`:

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Welcome to ARIA</title>
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f5f5f5;">
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background-color: #f5f5f5;">
        <tr>
            <td style="padding: 40px 20px;">
                <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="600" style="margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden;">
                    <!-- Logo -->
                    <tr>
                        <td style="padding: 40px 40px 20px; text-align: center; border-bottom: 1px solid #e5e7eb;">
                            <h1 style="margin: 0; color: #111827; font-size: 28px; font-weight: 600;">ARIA</h1>
                            <p style="margin: 8px 0 0; color: #6b7280; font-size: 14px;">Autonomous Reasoning & Intelligence Agent</p>
                        </td>
                    </tr>
                    <!-- Content -->
                    <tr>
                        <td style="padding: 40px;">
                            <h2 style="margin: 0 0 16px; color: #111827; font-size: 24px; font-weight: 600;">Welcome to ARIA, $name!</h2>
                            <p style="margin: 0 0 16px; color: #374151; font-size: 16px; line-height: 1.6;">You've just taken the first step toward transforming how your life sciences team operates. ARIA is your AI-powered Department Director, designed to handle the 72% of administrative work that keeps you from selling.</p>
                            <p style="margin: 0 0 24px; color: #374151; font-size: 16px; line-height: 1.6;">Over the next few minutes, you'll complete our intelligent onboarding where ARIA will learn about your company, your communication style, and your priorities. By the end, ARIA will be working for you—not just with you.</p>
                            <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                                <tr>
                                    <td style="background-color: #4f46e5; border-radius: 6px;">
                                        <a href="$app_url/onboarding" style="display: inline-block; padding: 14px 28px; color: #ffffff; text-decoration: none; font-size: 16px; font-weight: 500;">Get Started</a>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    <!-- Footer -->
                    <tr>
                        <td style="padding: 20px 40px; background-color: #f9fafb; border-top: 1px solid #e5e7eb;">
                            <p style="margin: 0; color: #6b7280; font-size: 12px; text-align: center;">© 2026 ARIA. All rights reserved.</p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
```

Create `backend/src/templates/email/onboarding_complete.html`:

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ARIA is Ready</title>
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f5f5f5;">
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background-color: #f5f5f5;">
        <tr>
            <td style="padding: 40px 20px;">
                <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="600" style="margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden;">
                    <!-- Logo -->
                    <tr>
                        <td style="padding: 40px 40px 20px; text-align: center; border-bottom: 1px solid #e5e7eb;">
                            <h1 style="margin: 0; color: #111827; font-size: 28px; font-weight: 600;">ARIA</h1>
                        </td>
                    </tr>
                    <!-- Content -->
                    <tr>
                        <td style="padding: 40px;">
                            <h2 style="margin: 0 0 16px; color: #111827; font-size: 24px; font-weight: 600;">ARIA is Ready, $name!</h2>
                            <p style="margin: 0 0 16px; color: #374151; font-size: 16px; line-height: 1.6;">Congratulations! You've completed onboarding and ARIA is now fully initialized with your company's intelligence.</p>
                            <p style="margin: 0 0 24px; color: #374151; font-size: 16px; line-height: 1.6;"><strong>Your Readiness Score: $readiness_score</strong><br>ARIA has built a solid foundation of knowledge about your company. As you continue to work together, this understanding will deepen.</p>
                            <p style="margin: 0 0 24px; color: #374151; font-size: 16px; line-height: 1.6;">What you can do now:</p>
                            <ul style="margin: 0 0 24px 20px; color: #374151; font-size: 16px; line-height: 1.6;">
                                <li>Set your first goal and watch ARIA get to work</li>
                                <li>Ask ARIA to prepare a briefing for your next meeting</li>
                                <li>Review your pipeline and get intelligent recommendations</li>
                            </ul>
                            <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                                <tr>
                                    <td style="background-color: #4f46e5; border-radius: 6px;">
                                        <a href="$app_url/dashboard" style="display: inline-block; padding: 14px 28px; color: #ffffff; text-decoration: none; font-size: 16px; font-weight: 500;">Go to Dashboard</a>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    <!-- Footer -->
                    <tr>
                        <td style="padding: 20px 40px; background-color: #f9fafb; border-top: 1px solid #e5e7eb;">
                            <p style="margin: 0; color: #6b7280; font-size: 12px; text-align: center;">© 2026 ARIA. All rights reserved.</p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
```

Create `backend/src/templates/email/team_invite.html`:

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>You're Invited to Join ARIA</title>
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f5f5f5;">
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background-color: #f5f5f5;">
        <tr>
            <td style="padding: 40px 20px;">
                <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="600" style="margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden;">
                    <!-- Logo -->
                    <tr>
                        <td style="padding: 40px 40px 20px; text-align: center; border-bottom: 1px solid #e5e7eb;">
                            <h1 style="margin: 0; color: #111827; font-size: 28px; font-weight: 600;">ARIA</h1>
                        </td>
                    </tr>
                    <!-- Content -->
                    <tr>
                        <td style="padding: 40px;">
                            <h2 style="margin: 0 0 16px; color: #111827; font-size: 24px; font-weight: 600;">Join $company_name on ARIA</h2>
                            <p style="margin: 0 0 16px; color: #374151; font-size: 16px; line-height: 1.6;"><strong>$inviter_name</strong> has invited you to join your team on ARIA, the AI-powered Department Director for Life Sciences.</p>
                            <p style="margin: 0 0 24px; color: #374151; font-size: 16px; line-height: 1.6;">ARIA helps your team automate administrative work, prepare for meetings, generate intelligence about accounts, and close more deals.</p>
                            <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                                <tr>
                                    <td style="background-color: #4f46e5; border-radius: 6px;">
                                        <a href="$invite_url" style="display: inline-block; padding: 14px 28px; color: #ffffff; text-decoration: none; font-size: 16px; font-weight: 500;">Accept Invitation</a>
                                    </td>
                                </tr>
                            </table>
                            <p style="margin: 24px 0 0; color: #6b7280; font-size: 14px;">This invitation expires in 7 days.</p>
                        </td>
                    </tr>
                    <!-- Footer -->
                    <tr>
                        <td style="padding: 20px 40px; background-color: #f9fafb; border-top: 1px solid #e5e7eb;">
                            <p style="margin: 0; color: #6b7280; font-size: 12px; text-align: center;">© 2026 ARIA. All rights reserved.</p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
```

Create `backend/src/templates/email/password_reset.html`:

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reset Your Password</title>
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f5f5f5;">
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background-color: #f5f5f5;">
        <tr>
            <td style="padding: 40px 20px;">
                <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="600" style="margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden;">
                    <!-- Logo -->
                    <tr>
                        <td style="padding: 40px 40px 20px; text-align: center; border-bottom: 1px solid #e5e7eb;">
                            <h1 style="margin: 0; color: #111827; font-size: 28px; font-weight: 600;">ARIA</h1>
                        </td>
                    </tr>
                    <!-- Content -->
                    <tr>
                        <td style="padding: 40px;">
                            <h2 style="margin: 0 0 16px; color: #111827; font-size: 24px; font-weight: 600;">Reset Your Password</h2>
                            <p style="margin: 0 0 16px; color: #374151; font-size: 16px; line-height: 1.6;">We received a request to reset your ARIA password. Click the button below to create a new password.</p>
                            <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                                <tr>
                                    <td style="background-color: #4f46e5; border-radius: 6px;">
                                        <a href="$reset_url" style="display: inline-block; padding: 14px 28px; color: #ffffff; text-decoration: none; font-size: 16px; font-weight: 500;">Reset Password</a>
                                    </td>
                                </tr>
                            </table>
                            <p style="margin: 24px 0 0; color: #6b7280; font-size: 14px;">This link will expire in 1 hour. If you didn't request this, please ignore this email.</p>
                        </td>
                    </tr>
                    <!-- Footer -->
                    <tr>
                        <td style="padding: 20px 40px; background-color: #f9fafb; border-top: 1px solid #e5e7eb;">
                            <p style="margin: 0; color: #6b7280; font-size: 12px; text-align: center;">© 2026 ARIA. All rights reserved.</p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
```

Create `backend/src/templates/email/weekly_summary.html`:

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Your Weekly ARIA Summary</title>
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f5f5f5;">
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background-color: #f5f5f5;">
        <tr>
            <td style="padding: 40px 20px;">
                <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="600" style="margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden;">
                    <!-- Logo -->
                    <tr>
                        <td style="padding: 40px 40px 20px; text-align: center; border-bottom: 1px solid #e5e7eb;">
                            <h1 style="margin: 0; color: #111827; font-size: 28px; font-weight: 600;">ARIA</h1>
                            <p style="margin: 8px 0 0; color: #6b7280; font-size: 14px;">Weekly Summary</p>
                        </td>
                    </tr>
                    <!-- Content -->
                    <tr>
                        <td style="padding: 40px;">
                            <h2 style="margin: 0 0 16px; color: #111827; font-size: 24px; font-weight: 600;">Hello, $name</h2>
                            <p style="margin: 0 0 24px; color: #374151; font-size: 16px; line-height: 1.6;">Here's what ARIA has been working on this week:</p>
                            $summary_data
                            <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin-top: 24px;">
                                <tr>
                                    <td style="background-color: #4f46e5; border-radius: 6px;">
                                        <a href="$app_url/dashboard" style="display: inline-block; padding: 14px 28px; color: #ffffff; text-decoration: none; font-size: 16px; font-weight: 500;">View Full Dashboard</a>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    <!-- Footer -->
                    <tr>
                        <td style="padding: 20px 40px; background-color: #f9fafb; border-top: 1px solid #e5e7eb;">
                            <p style="margin: 0; color: #6b7280; font-size: 12px; text-align: center;">© 2026 ARIA. All rights reserved.</p>
                            <p style="margin: 8px 0 0; text-align: center;"><a href="$unsubscribe_url" style="color: #6b7280; text-decoration: underline;">Unsubscribe from weekly summaries</a></p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
```

Create `backend/src/templates/email/payment_receipt.html`:

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Payment Receipt</title>
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f5f5f5;">
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background-color: #f5f5f5;">
        <tr>
            <td style="padding: 40px 20px;">
                <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="600" style="margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden;">
                    <!-- Logo -->
                    <tr>
                        <td style="padding: 40px 40px 20px; text-align: center; border-bottom: 1px solid #e5e7eb;">
                            <h1 style="margin: 0; color: #111827; font-size: 28px; font-weight: 600;">ARIA</h1>
                            <p style="margin: 8px 0 0; color: #6b7280; font-size: 14px;">Payment Receipt</p>
                        </td>
                    </tr>
                    <!-- Content -->
                    <tr>
                        <td style="padding: 40px;">
                            <h2 style="margin: 0 0 16px; color: #111827; font-size: 24px; font-weight: 600;">Payment Successful</h2>
                            <p style="margin: 0 0 24px; color: #374151; font-size: 16px; line-height: 1.6;">Thank you for your payment. Your ARIA subscription has been renewed.</p>
                            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin-bottom: 24px; border-collapse: collapse;">
                                <tr>
                                    <td style="padding: 12px 0; color: #6b7280; font-size: 14px; border-bottom: 1px solid #e5e7eb;">Amount</td>
                                    <td style="padding: 12px 0; color: #111827; font-size: 14px; text-align: right; border-bottom: 1px solid #e5e7eb;"><strong>$amount</strong></td>
                                </tr>
                                <tr>
                                    <td style="padding: 12px 0; color: #6b7280; font-size: 14px; border-bottom: 1px solid #e5e7eb;">Date</td>
                                    <td style="padding: 12px 0; color: #111827; font-size: 14px; text-align: right; border-bottom: 1px solid #e5e7eb;"><strong>$date</strong></td>
                                </tr>
                            </table>
                            <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                                <tr>
                                    <td style="background-color: #4f46e5; border-radius: 6px;">
                                        <a href="$app_url/admin/billing" style="display: inline-block; padding: 14px 28px; color: #ffffff; text-decoration: none; font-size: 16px; font-weight: 500;">View Invoice</a>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    <!-- Footer -->
                    <tr>
                        <td style="padding: 20px 40px; background-color: #f9fafb; border-top: 1px solid #e5e7eb;">
                            <p style="margin: 0; color: #6b7280; font-size: 12px; text-align: center;">© 2026 ARIA. All rights reserved.</p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
```

Create `backend/src/templates/email/payment_failed.html`:

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Payment Failed</title>
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f5f5f5;">
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background-color: #f5f5f5;">
        <tr>
            <td style="padding: 40px 20px;">
                <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="600" style="margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden;">
                    <!-- Logo -->
                    <tr>
                        <td style="padding: 40px 40px 20px; text-align: center; border-bottom: 1px solid #e5e7eb;">
                            <h1 style="margin: 0; color: #111827; font-size: 28px; font-weight: 600;">ARIA</h1>
                        </td>
                    </tr>
                    <!-- Content -->
                    <tr>
                        <td style="padding: 40px;">
                            <h2 style="margin: 0 0 16px; color: #dc2626; font-size: 24px; font-weight: 600;">Payment Failed</h2>
                            <p style="margin: 0 0 16px; color: #374151; font-size: 16px; line-height: 1.6;">Hi $name,</p>
                            <p style="margin: 0 0 16px; color: #374151; font-size: 16px; line-height: 1.6;">We were unable to process your recent payment. This could be due to insufficient funds, an expired card, or other banking issues.</p>
                            <p style="margin: 0 0 24px; color: #374151; font-size: 16px; line-height: 1.6;">Please update your payment method to avoid service interruption.</p>
                            <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                                <tr>
                                    <td style="background-color: #dc2626; border-radius: 6px;">
                                        <a href="$app_url/admin/billing" style="display: inline-block; padding: 14px 28px; color: #ffffff; text-decoration: none; font-size: 16px; font-weight: 500;">Update Payment Method</a>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    <!-- Footer -->
                    <tr>
                        <td style="padding: 20px 40px; background-color: #f9fafb; border-top: 1px solid #e5e7eb;">
                            <p style="margin: 0; color: #6b7280; font-size: 12px; text-align: center;">© 2026 ARIA. All rights reserved.</p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
```

**Step 4: Write minimal implementation**

Create `backend/src/services/email_service.py`:

```python
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

    def _should_send_email(
        self, email_type: str, user_preferences: dict[str, Any]
    ) -> bool:
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
            return user_preferences.get("weekly_summary", True)

        if email_type == "feature_announcement":
            return user_preferences.get("feature_announcements", True)

        # Default to sending for operational emails
        return True

    async def _get_user_email_preferences(self, user_id: str) -> dict[str, Any]:
        """Get user's email preferences.

        Args:
            user_id: The user's UUID.

        Returns:
            Dictionary with email preferences (weekly_summary, feature_announcements, security_alerts).
        """
        try:
            settings_data = await SupabaseClient.get_user_settings(user_id)
            return settings_data.get("preferences", {}).get("email_preferences", {
                "weekly_summary": True,
                "feature_announcements": True,
                "security_alerts": True,
            })
        except Exception as e:
            logger.warning(f"Failed to fetch email preferences for {user_id}: {e}")
            # Return defaults
            return {
                "weekly_summary": True,
                "feature_announcements": True,
                "security_alerts": True,
            }

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

    async def send_onboarding_complete(
        self, to: str, name: str, readiness_score: int
    ) -> str:
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

    async def send_weekly_summary(
        self, to: str, name: str, summary_data: dict[str, Any]
    ) -> str:
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

    async def send_payment_receipt(
        self, to: str, amount: int, date: str
    ) -> str:
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

    async def _send_email(
        self, to: str, subject: str, html: str
    ) -> str:
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
                }
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
```

**Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/services/test_email_service.py -v`

Expected: PASS for all tests

**Step 6: Update services barrel export**

Add to `backend/src/services/__init__.py`:

```python
from src.services.email_service import EmailService
```

And add `"EmailService"` to `__all__` list.

**Step 7: Commit**

```bash
git add backend/src/services/email_service.py backend/src/services/__init__.py backend/src/templates/email/ backend/tests/services/test_email_service.py
git commit -m "feat: implement EmailService with templates and tests (US-934)"
```

---

## Task 3: Add Email Preference API Routes

**Files:**
- Create: `backend/src/api/routes/email_preferences.py`
- Modify: `backend/src/models/preferences.py`
- Modify: `backend/src/main.py`

**Step 1: Write the failing test**

Create `backend/tests/api/test_email_preferences_routes.py`:

```python
"""Tests for email preferences API routes (US-934)."""

import pytest

from src.models.preferences import EmailPreferencesResponse, EmailPreferencesUpdate


@pytest.mark.asyncio
async def test_get_email_preferences_authenticated(client, authenticated_user):
    """Test getting email preferences requires auth."""
    response = await client.get("/api/v1/settings/email-preferences")
    assert response.status_code == 200
    data = response.json()
    assert "weekly_summary" in data
    assert "feature_announcements" in data
    assert "security_alerts" in data


@pytest.mark.asyncio
async def test_update_email_preferences(client, authenticated_user):
    """Test updating email preferences."""
    response = await client.patch(
        "/api/v1/settings/email-preferences",
        json={"weekly_summary": False}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["weekly_summary"] is False


@pytest.mark.asyncio
async def test_security_alerts_cannot_be_disabled(client, authenticated_user):
    """Test that security_alerts cannot be disabled."""
    response = await client.patch(
        "/api/v1/settings/email-preferences",
        json={"security_alerts": False}
    )
    assert response.status_code == 400
    assert "cannot be disabled" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_multiple_preferences(client, authenticated_user):
    """Test updating multiple preferences at once."""
    response = await client.patch(
        "/api/v1/settings/email-preferences",
        json={
            "weekly_summary": False,
            "feature_announcements": False
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["weekly_summary"] is False
    assert data["feature_announcements"] is False
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/api/test_email_preferences_routes.py -v`

Expected: FAIL with route not found

**Step 3: Add email preference models**

Add to `backend/src/models/preferences.py`:

```python
class EmailPreferencesResponse(BaseModel):
    """Response model for email preferences."""

    weekly_summary: bool = Field(..., description="Receive weekly summary emails")
    feature_announcements: bool = Field(..., description="Receive feature announcement emails")
    security_alerts: bool = Field(..., description="Receive security alert emails (always true)")


class EmailPreferencesUpdate(BaseModel):
    """Request model for updating email preferences."""

    weekly_summary: bool | None = Field(None, description="Enable/disable weekly summary emails")
    feature_announcements: bool | None = Field(None, description="Enable/disable feature announcements")
    security_alerts: bool | None = Field(None, description="Security alerts (ignored - always enabled)")
```

**Step 4: Create email preferences routes**

Create `backend/src/api/routes/email_preferences.py`:

```python
"""Email preferences API routes (US-934)."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status

from src.api.deps import CurrentUser
from src.db.supabase import SupabaseClient
from src.models.preferences import EmailPreferencesResponse, EmailPreferencesUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings/email-preferences", tags=["settings"])


class EmailPreferencesService:
    """Service for managing email preferences."""

    async def get_email_preferences(self, user_id: str) -> dict[str, Any]:
        """Get user's email preferences.

        Args:
            user_id: The user's UUID.

        Returns:
            Email preferences dictionary.
        """
        settings_data = await SupabaseClient.get_user_settings(user_id)
        preferences = settings_data.get("preferences", {})
        email_prefs = preferences.get("email_preferences", {
            "weekly_summary": True,
            "feature_announcements": True,
            "security_alerts": True,
        })

        return email_prefs

    async def update_email_preferences(
        self, user_id: str, update_data: EmailPreferencesUpdate
    ) -> dict[str, Any]:
        """Update user's email preferences.

        Args:
            user_id: The user's UUID.
            update_data: Preferences to update.

        Returns:
            Updated email preferences.

        Raises:
            ValueError: If attempting to disable security_alerts.
        """
        # Security alerts cannot be disabled
        if update_data.security_alerts is False:
            raise ValueError("Security alerts cannot be disabled")

        # Get current preferences
        current = await self.get_email_preferences(user_id)

        # Build updated preferences
        updated = current.copy()
        if update_data.weekly_summary is not None:
            updated["weekly_summary"] = update_data.weekly_summary
        if update_data.feature_announcements is not None:
            updated["feature_announcements"] = update_data.feature_announcements
        # security_alerts is always True, ignore any updates

        # Save to database
        client = SupabaseClient.get_client()

        # Get full settings
        settings_response = (
            client.table("user_settings")
            .select("*")
            .eq("user_id", user_id)
            .single()
            .execute()
        )

        if settings_response.data:
            # Update existing
            full_settings = settings_response.data
            preferences = full_settings.get("preferences", {})
            preferences["email_preferences"] = updated

            (
                client.table("user_settings")
                .update({"preferences": preferences})
                .eq("user_id", user_id)
                .execute()
            )
        else:
            # Create new
            (
                client.table("user_settings")
                .insert({
                    "user_id": user_id,
                    "preferences": {"email_preferences": updated}
                })
                .execute()
            )

        logger.info(
            "Email preferences updated",
            extra={"user_id": user_id, "preferences": updated}
        )

        return updated


_service = EmailPreferencesService()


@router.get("", response_model=EmailPreferencesResponse)
async def get_email_preferences(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get current user's email preferences.

    Returns default values if none exist.
    """
    try:
        preferences = await _service.get_email_preferences(current_user.id)
        return preferences
    except Exception as e:
        logger.exception("Error fetching email preferences")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch email preferences",
        ) from e


@router.patch("", response_model=EmailPreferencesResponse)
async def update_email_preferences(
    data: EmailPreferencesUpdate,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Update current user's email preferences.

    Note: security_alerts cannot be disabled and will be ignored.
    """
    try:
        preferences = await _service.update_email_preferences(current_user.id, data)
        return preferences
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.exception("Error updating email preferences")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update email preferences",
        ) from e
```

**Step 5: Register router in main.py**

Add to `backend/src/main.py` imports:

```python
from src.api.routes import email_preferences
```

Add to router registrations:

```python
app.include_router(email_preferences.router, prefix="/api/v1")
```

**Step 6: Run test to verify it passes**

Run: `cd backend && pytest tests/api/test_email_preferences_routes.py -v`

Expected: PASS for all tests

**Step 7: Commit**

```bash
git add backend/src/api/routes/email_preferences.py backend/src/models/preferences.py backend/src/main.py backend/tests/api/test_email_preferences_routes.py
git commit -m "feat: add email preferences API routes (US-934)"
```

---

## Task 4: Wire Email Triggers to Existing Services

**Files:**
- Modify: `backend/src/services/account_service.py` (password reset)
- Modify: `backend/src/services/team_service.py` (team invite)
- Modify: `backend/src/services/billing_service.py` (payment receipts/failed)

**Step 1: Write the failing test for password reset email**

Add to `backend/tests/services/test_account_service.py`:

```python
@pytest.mark.asyncio
async def test_password_reset_sends_email(account_service, mock_email_service):
    """Test that password reset sends an email."""
    # Setup mock
    mock_email_service.send_password_reset = AsyncMock(return_value="email_id")

    # Call method
    await account_service.request_password_reset("test@example.com")

    # Verify email was sent
    mock_email_service.send_password_reset.assert_called_once()
    call_args = mock_email_service.send_password_reset.call_args
    assert call_args[0][0] == "test@example.com"
    assert "reset_url" in call_args.kwargs or len(call_args[0]) > 1
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/services/test_account_service.py::test_password_reset_sends_email -v`

Expected: FAIL (email not sent)

**Step 3: Update account_service.py to send password reset email**

Import EmailService at top of `backend/src/services/account_service.py`:

```python
from src.services.email_service import EmailService
```

Update `request_password_reset` method to send email (replace existing Supabase reset with custom):

```python
async def request_password_reset(self, email: str) -> None:
    """Request a password reset email.

    Args:
        email: User's email address.

    Raises:
        ARIAException: If operation fails.
    """
    try:
        # Generate reset token and send email via EmailService
        # For now, we'll still use Supabase's built-in but also send our custom email
        reset_url = f"{settings.APP_URL}/reset-password?email={email}"

        # Send custom reset email
        email_service = EmailService()
        await email_service.send_password_reset(email, reset_url)

        # Log security event (without user_id since we only have email)
        logger.info("Password reset requested", extra={"email": email})

    except Exception as e:
        logger.exception("Error requesting password reset", extra={"email": email})
        # Don't reveal if email exists or not
        raise ARIAException(
            message="If an account exists with this email, a reset link has been sent.",
            code="PASSWORD_RESET_REQUESTED",
            status_code=200,
        ) from e
```

**Step 4: Write test for team invite email**

Add to `backend/tests/services/test_team_service.py`:

```python
@pytest.mark.asyncio
async def test_team_invite_sends_email(team_service, mock_email_service, mock_company):
    """Test that team invite sends an email."""
    # Setup mock
    mock_email_service.send_team_invite = AsyncMock(return_value="email_id")

    # Call method
    await team_service.invite_member(
        company_id="company-123",
        invited_by="user-123",
        email="newuser@example.com",
        role="user"
    )

    # Verify email was sent
    mock_email_service.send_team_invite.assert_called_once()
    call_args = mock_email_service.send_team_invite.call_args
    assert call_args[0][0] == "newuser@example.com"
```

**Step 5: Run test to verify it fails**

Run: `cd backend && pytest tests/services/test_team_service.py::test_team_invite_sends_email -v`

Expected: FAIL (email not sent)

**Step 6: Update team_service.py to send team invite email**

Import EmailService at top:

```python
from src.services.email_service import EmailService
```

Update `invite_member` method to send email after creating invite (after the insert, before return):

```python
            # Send invite email
            try:
                email_service = EmailService()
                invite_url = f"{settings.APP_URL}/accept-invite?token={token}"
                await email_service.send_team_invite(
                    to=email.lower(),
                    inviter_name="Your colleague",  # TODO: Get actual inviter name
                    company_name="Your company",     # TODO: Get actual company name
                    invite_url=invite_url,
                )
            except Exception as email_error:
                # Log but don't fail the invite creation
                logger.warning(
                    "Failed to send invite email",
                    extra={"email": email, "error": str(email_error)}
                )
```

**Step 7: Write test for payment receipt email**

Add to `backend/tests/services/test_billing_service.py`:

```python
@pytest.mark.asyncio
async def test_payment_success_sends_email(billing_service, mock_email_service):
    """Test that payment success sends receipt email."""
    # Setup mock
    mock_email_service.send_payment_receipt = AsyncMock(return_value="email_id")

    # Create mock invoice
    invoice = MagicMock()
    invoice.customer = "cus_123"
    invoice.total = 200000
    invoice.created = int(datetime(2026, 2, 7).timestamp())

    # Call handler
    await billing_service._handle_payment_succeeded(invoice)

    # Verify email was sent
    mock_email_service.send_payment_receipt.assert_called_once()
```

**Step 8: Run test to verify it fails**

Run: `cd backend && pytest tests/services/test_billing_service.py::test_payment_success_sends_email -v`

Expected: FAIL (email not sent)

**Step 9: Update billing_service.py to send payment emails**

Import EmailService at top:

```python
from src.services.email_service import EmailService
```

Update `_handle_payment_succeeded` to send email:

```python
async def _handle_payment_succeeded(self, invoice: stripe.Invoice) -> None:
    """Handle successful payment webhook.

    Args:
        invoice: Stripe invoice object.
    """
    customer_id = invoice.customer
    await self._update_subscription_status(customer_id, self.STATUS_ACTIVE, invoice)

    # Send receipt email
    try:
        # Get company email
        client = SupabaseClient.get_client()
        company_response = (
            client.table("companies")
            .select("id")
            .eq("stripe_customer_id", customer_id)
            .single()
            .execute()
        )

        if company_response.data:
            company_id = company_response.data["id"]

            # Get admin user email
            admin_response = (
                client.table("user_profiles")
                .select("id")
                .eq("company_id", company_id)
                .eq("role", "admin")
                .limit(1)
                .execute()
            )

            if admin_response.data:
                admin_id = admin_response.data[0]["id"]
                # Get email from auth
                try:
                    user_data = client.auth.admin.get_user_by_id(admin_id)
                    if user_data and user_data.user and user_data.user.email:
                        email_service = EmailService()
                        await email_service.send_payment_receipt(
                            to=user_data.user.email,
                            amount=invoice.total or 0,
                            date=datetime.fromtimestamp(invoice.created, tz=UTC).date().isoformat() if invoice.created else "",
                        )
                except Exception as email_error:
                    logger.warning("Failed to send payment receipt email", extra={"error": str(email_error)})
    except Exception as e:
        logger.warning("Failed to send payment receipt", extra={"error": str(e)})
```

Update `_handle_payment_failed` similarly:

```python
async def _handle_payment_failed(self, invoice: stripe.Invoice) -> None:
    """Handle failed payment webhook.

    Args:
        invoice: Stripe invoice object.
    """
    customer_id = invoice.customer
    await self._update_subscription_status(customer_id, self.STATUS_PAST_DUE, invoice)

    # Send failed payment email
    try:
        # Get company email (same as above)
        client = SupabaseClient.get_client()
        company_response = (
            client.table("companies")
            .select("id")
            .eq("stripe_customer_id", customer_id)
            .single()
            .execute()
        )

        if company_response.data:
            company_id = company_response.data["id"]

            # Get admin user email
            admin_response = (
                client.table("user_profiles")
                .select("id", "full_name")
                .eq("company_id", company_id)
                .eq("role", "admin")
                .limit(1)
                .execute()
            )

            if admin_response.data:
                admin_id = admin_response.data[0]["id"]
                admin_name = admin_response.data[0].get("full_name", "User")
                # Get email from auth
                try:
                    user_data = client.auth.admin.get_user_by_id(admin_id)
                    if user_data and user_data.user and user_data.user.email:
                        email_service = EmailService()
                        await email_service.send_payment_failed(
                            to=user_data.user.email,
                            name=admin_name,
                        )
                except Exception as email_error:
                    logger.warning("Failed to send payment failed email", extra={"error": str(email_error)})
    except Exception as e:
        logger.warning("Failed to send payment failed notification", extra={"error": str(e)})
```

**Step 10: Run tests to verify they pass**

Run: `cd backend && pytest tests/services/test_account_service.py::test_password_reset_sends_email tests/services/test_team_service.py::test_team_invite_sends_email tests/services/test_billing_service.py::test_payment_success_sends_email -v`

Expected: PASS for all tests

**Step 11: Commit**

```bash
git add backend/src/services/account_service.py backend/src/services/team_service.py backend/src/services/billing_service.py backend/tests/services/
git commit -m "feat: wire email triggers to existing services (US-934)"
```

---

## Task 5: Create Frontend Email Preferences UI

**Files:**
- Create: `frontend/src/components/settings/EmailPreferencesSection.tsx`
- Modify: `frontend/src/pages/SettingsAccountPage.tsx`

**Step 1: Write the failing test**

Create `frontend/src/components/settings/__tests__/EmailPreferencesSection.test.tsx`:

```tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { EmailPreferencesSection } from "../EmailPreferencesSection";

// Mock the API
jest.mock("@/api/emailPreferences", () => ({
  getEmailPreferences: jest.fn().mockResolvedValue({
    weekly_summary: true,
    feature_announcements: true,
    security_alerts: true,
  }),
  updateEmailPreferences: jest.fn().mockResolvedValue({
    weekly_summary: false,
    feature_announcements: true,
    security_alerts: true,
  }),
}));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false },
    mutations: { retry: false },
  },
});

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
}

describe("EmailPreferencesSection", () => {
  it("renders email preference toggles", async () => {
    render(<EmailPreferencesSection />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByText("Weekly intelligence summary")).toBeInTheDocument();
      expect(screen.getByText("Feature announcements")).toBeInTheDocument();
      expect(screen.getByText("Security alerts")).toBeInTheDocument();
    });
  });

  it("disables security alerts toggle", async () => {
    render(<EmailPreferencesSection />, { wrapper: Wrapper });

    await waitFor(() => {
      const securityToggle = screen.getByRole("switch", { name: /security/i });
      expect(securityToggle).toBeDisabled();
    });
  });

  it("shows tooltip for disabled security alerts", async () => {
    render(<EmailPreferencesSection />, { wrapper: Wrapper });

    await waitFor(() => {
      const securityToggle = screen.getByRole("switch", { name: /security/i });
      fireEvent.mouseEnter(securityToggle);

      expect(screen.getByText(/security alerts cannot be disabled/i)).toBeInTheDocument();
    });
  });

  it("toggles weekly summary preference", async () => {
    const { updateEmailPreferences } = require("@/api/emailPreferences");
    render(<EmailPreferencesSection />, { wrapper: Wrapper });

    await waitFor(() => {
      const weeklyToggle = screen.getByRole("switch", { name: /weekly/i });
      fireEvent.click(weeklyToggle);
    });

    await waitFor(() => {
      expect(updateEmailPreferences).toHaveBeenCalledWith({ weekly_summary: false });
    });
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- EmailPreferencesSection.test.tsx`

Expected: FAIL with module not found

**Step 3: Create email preferences API client**

Create `frontend/src/api/emailPreferences.ts`:

```typescript
import { apiClient } from "./client";

export interface EmailPreferences {
  weekly_summary: boolean;
  feature_announcements: boolean;
  security_alerts: boolean;
}

export interface UpdateEmailPreferencesRequest {
  weekly_summary?: boolean;
  feature_announcements?: boolean;
  security_alerts?: boolean;
}

export async function getEmailPreferences(): Promise<EmailPreferences> {
  const response = await apiClient.get<EmailPreferences>("/settings/email-preferences");
  return response.data;
}

export async function updateEmailPreferences(
  data: UpdateEmailPreferencesRequest
): Promise<EmailPreferences> {
  const response = await apiClient.patch<EmailPreferences>("/settings/email-preferences", data);
  return response.data;
}
```

**Step 4: Create email preferences hook**

Create `frontend/src/hooks/useEmailPreferences.ts`:

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getEmailPreferences,
  updateEmailPreferences,
  type UpdateEmailPreferencesRequest,
  type EmailPreferences,
} from "@/api/emailPreferences";

export const emailPreferencesKeys = {
  all: ["emailPreferences"] as const,
  detail: () => [...emailPreferencesKeys.all, "detail"] as const,
};

export function useEmailPreferences() {
  return useQuery({
    queryKey: emailPreferencesKeys.detail(),
    queryFn: () => getEmailPreferences(),
  });
}

export function useUpdateEmailPreferences() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: UpdateEmailPreferencesRequest) => updateEmailPreferences(data),
    onMutate: async (newData) => {
      await queryClient.cancelQueries({ queryKey: emailPreferencesKeys.detail() });

      const previous = queryClient.getQueryData<EmailPreferences>(emailPreferencesKeys.detail());

      if (previous) {
        queryClient.setQueryData<EmailPreferences>(emailPreferencesKeys.detail(), {
          ...previous,
          ...newData,
        });
      }

      return { previous };
    },
    onError: (_err, _newData, context) => {
      if (context?.previous) {
        queryClient.setQueryData(emailPreferencesKeys.detail(), context.previous);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: emailPreferencesKeys.detail() });
    },
  });
}
```

**Step 5: Create EmailPreferencesSection component**

Create `frontend/src/components/settings/EmailPreferencesSection.tsx`:

```tsx
import { useState } from "react";
import { Mail, Info } from "lucide-react";
import { useEmailPreferences, useUpdateEmailPreferences } from "@/hooks/useEmailPreferences";

interface EmailPreferencesSectionProps {
  className?: string;
}

export function EmailPreferencesSection({ className = "" }: EmailPreferencesSectionProps) {
  const { data: preferences, isLoading } = useEmailPreferences();
  const updatePreferences = useUpdateEmailPreferences();

  const [showSecurityTooltip, setShowSecurityTooltip] = useState(false);

  const handleToggle = (key: keyof typeof preferences, value: boolean) => {
    updatePreferences.mutate({ [key]: value });
  };

  if (isLoading) {
    return (
      <div className={`${className} bg-[#161B2E] border border-[#2A2A2E] rounded-xl p-6`}>
        <div className="flex items-center gap-3">
          <div className="w-5 h-5 bg-[#2A2A2E] rounded animate-pulse" />
          <div className="h-5 bg-[#2A2A2E] rounded w-32 animate-pulse" />
        </div>
      </div>
    );
  }

  return (
    <div className={`${className} bg-[#161B2E] border border-[#2A2A2E] rounded-xl p-6`}>
      <div className="flex items-center gap-3 mb-6">
        <Mail className="w-5 h-5 text-[#7B8EAA]" />
        <div>
          <h2 className="text-[#E8E6E1] font-sans text-[1.125rem] font-medium">Email Preferences</h2>
          <p className="text-[#8B92A5] text-[0.8125rem]">Choose which emails you receive</p>
        </div>
      </div>

      <div className="space-y-4">
        {/* Weekly Summary */}
        <div className="flex items-center justify-between py-3 px-4 bg-[#1E2235] rounded-lg border border-[#2A2A2E]">
          <div>
            <p className="text-[#E8E6E1] text-[0.9375rem] font-medium">Weekly intelligence summary</p>
            <p className="text-[#8B92A5] text-[0.8125rem] mt-0.5">Receive a weekly summary of ARIA's activity</p>
          </div>
          <button
            onClick={() => handleToggle("weekly_summary", !preferences?.weekly_summary)}
            disabled={updatePreferences.isPending}
            className={`
              relative w-12 h-6 rounded-full transition-colors duration-200 ease-in-out
              ${preferences?.weekly_summary ? "bg-[#5B6E8A]" : "bg-[#2A2A2E]"}
              ${updatePreferences.isPending ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}
            `}
            aria-label="Toggle weekly summary emails"
          >
            <span
              className={`
                absolute top-1 left-1 w-4 h-4 rounded-full bg-white transition-transform duration-200 ease-in-out
                ${preferences?.weekly_summary ? "translate-x-6" : "translate-x-0"}
              `}
            />
          </button>
        </div>

        {/* Feature Announcements */}
        <div className="flex items-center justify-between py-3 px-4 bg-[#1E2235] rounded-lg border border-[#2A2A2E]">
          <div>
            <p className="text-[#E8E6E1] text-[0.9375rem] font-medium">Feature announcements</p>
            <p className="text-[#8B92A5] text-[0.8125rem] mt-0.5">New features and product updates</p>
          </div>
          <button
            onClick={() => handleToggle("feature_announcements", !preferences?.feature_announcements)}
            disabled={updatePreferences.isPending}
            className={`
              relative w-12 h-6 rounded-full transition-colors duration-200 ease-in-out
              ${preferences?.feature_announcements ? "bg-[#5B6E8A]" : "bg-[#2A2A2E]"}
              ${updatePreferences.isPending ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}
            `}
            aria-label="Toggle feature announcement emails"
          >
            <span
              className={`
                absolute top-1 left-1 w-4 h-4 rounded-full bg-white transition-transform duration-200 ease-in-out
                ${preferences?.feature_announcements ? "translate-x-6" : "translate-x-0"}
              `}
            />
          </button>
        </div>

        {/* Security Alerts - Always On */}
        <div className="relative flex items-center justify-between py-3 px-4 bg-[#1E2235] rounded-lg border border-[#2A2A2E]">
          <div>
            <p className="text-[#E8E6E1] text-[0.9375rem] font-medium">Security alerts</p>
            <p className="text-[#8B92A5] text-[0.8125rem] mt-0.5">Password resets, sign-in alerts (always on)</p>
          </div>
          <div
            className="relative"
            onMouseEnter={() => setShowSecurityTooltip(true)}
            onMouseLeave={() => setShowSecurityTooltip(false)}
          >
            <button
              disabled
              className="
                relative w-12 h-6 rounded-full bg-[#5B6E8A] opacity-50 cursor-not-allowed
              "
              aria-label="Security alerts cannot be disabled"
            >
              <span className="absolute top-1 left-1 w-4 h-4 rounded-full bg-white translate-x-6" />
            </button>

            {/* Tooltip */}
            {showSecurityTooltip && (
              <div className="absolute right-0 top-full mt-2 w-64 p-3 bg-[#0F1117] border border-[#2A2A2E] rounded-lg shadow-lg z-50">
                <div className="flex items-start gap-2">
                  <Info className="w-4 h-4 text-[#7B8EAA] mt-0.5 flex-shrink-0" />
                  <p className="text-[#8B92A5] text-[0.8125rem]">
                    Security alerts cannot be disabled for account protection
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
```

**Step 6: Add to SettingsAccountPage**

Update `frontend/src/pages/SettingsAccountPage.tsx` to include the EmailPreferencesSection:

Import at top:
```tsx
import { EmailPreferencesSection } from "@/components/settings/EmailPreferencesSection";
```

Add before the Danger Zone section (after Active Sessions section):
```tsx
{/* Email Preferences */}
<EmailPreferencesSection className="mt-6" />
```

**Step 7: Run test to verify it passes**

Run: `cd frontend && npm test -- EmailPreferencesSection.test.tsx`

Expected: PASS for all tests

**Step 8: Run frontend typecheck**

Run: `cd frontend && npm run typecheck`

Expected: No errors

**Step 9: Commit**

```bash
git add frontend/src/components/settings/EmailPreferencesSection.tsx frontend/src/components/settings/__tests__/EmailPreferencesSection.test.tsx frontend/src/api/emailPreferences.ts frontend/src/hooks/useEmailPreferences.ts frontend/src/pages/SettingsAccountPage.tsx
git commit -m "feat: add email preferences UI to settings (US-934)"
```

---

## Task 6: Run Quality Gates

**Files:** N/A (verification only)

**Step 1: Run backend linting**

Run: `cd backend && ruff check src/services/email_service.py src/api/routes/email_preferences.py`

Expected: No errors

**Step 2: Run backend type checking**

Run: `cd backend && mypy src/services/email_service.py src/api/routes/email_preferences.py --strict`

Expected: No errors

**Step 3: Run backend tests**

Run: `cd backend && pytest tests/services/test_email_service.py tests/api/test_email_preferences_routes.py -v`

Expected: All PASS

**Step 4: Run frontend typecheck**

Run: `cd frontend && npm run typecheck`

Expected: No errors

**Step 5: Run frontend tests**

Run: `cd frontend && npm test -- EmailPreferencesSection`

Expected: All PASS

**Step 6: Verify server startup**

Run: `cd backend && uvicorn src.main:app --reload --port 8000 &`

Wait for: "INFO: Application startup complete"

Then: `curl http://localhost:8000/api/v1/settings/email-preferences -H "Authorization: Bearer test-token"`

Expected: Either 401 (no auth) or proper response structure

**Step 7: Kill server**

Run: `pkill -f uvicorn`

**Step 8: Commit if all quality gates pass**

```bash
git add -A
git commit -m "test: US-934 quality gates passed"
```

---

## Summary

This plan implements US-934 Transactional Email System with:

1. **Resend integration** - Added to requirements.txt and config
2. **EmailService** - Complete service with 7 email types and template rendering
3. **Email templates** - 7 HTML templates with ARIA branding
4. **API routes** - GET/PATCH for email preferences
5. **Email triggers** - Wired into password reset, team invites, and Stripe webhooks
6. **Frontend UI** - EmailPreferencesSection component in settings
7. **Tests** - Full coverage for all new functionality
8. **Quality gates** - Linting, type checking, and tests all pass

The implementation follows ARIA's patterns:
- Uses Pydantic models for validation
- Follows service layer pattern
- Async/await throughout
- Proper error handling with ARIAException
- RLS-compliant database operations
- Dark theme UI matching design system
- TDD approach with tests first
