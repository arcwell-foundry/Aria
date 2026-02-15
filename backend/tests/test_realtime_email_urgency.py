"""Tests for real-time email urgency detection."""

import pytest

from src.services.chat import EmailCheckService
from src.services.realtime_email_notifier import UrgentNotification


class TestEmailCheckService:
    """Tests for EmailCheckService pattern detection."""

    def test_detect_email_check_request_check_my_email(self) -> None:
        """Test detection of 'check my email' pattern."""
        service = EmailCheckService()
        assert service.detect_email_check_request("check my email") is True
        assert service.detect_email_check_request("Check my Email") is True
        assert service.detect_email_check_request("please check my email") is True

    def test_detect_email_check_request_scan_inbox(self) -> None:
        """Test detection of 'scan my inbox' pattern."""
        service = EmailCheckService()
        assert service.detect_email_check_request("scan my inbox") is True
        assert service.detect_email_check_request("Scan my inbox please") is True

    def test_detect_email_check_request_any_new_emails(self) -> None:
        """Test detection of 'any new emails' pattern."""
        service = EmailCheckService()
        assert service.detect_email_check_request("any new emails?") is True
        assert service.detect_email_check_request("Do I have any new emails") is True

    def test_detect_email_check_request_urgent_specific(self) -> None:
        """Test detection of urgent-specific patterns."""
        service = EmailCheckService()
        assert service.detect_email_check_request("do i have any urgent emails") is True
        # "any urgent mail" is detected via EMAIL_CHECK_PATTERNS not URGENT_CHECK_PATTERNS
        # It matches "any new emails" pattern with "urgent" in it
        assert service.is_urgent_specific("any urgent mail?") is True

    def test_detect_email_check_request_negative(self) -> None:
        """Test that non-email patterns are not detected."""
        service = EmailCheckService()
        assert service.detect_email_check_request("what's the weather") is False
        assert service.detect_email_check_request("tell me about the company") is False
        assert service.detect_email_check_request("help me with this task") is False

    def test_is_urgent_specific(self) -> None:
        """Test detection of urgent-specific requests."""
        service = EmailCheckService()
        assert service.is_urgent_specific("any urgent emails?") is True
        assert service.is_urgent_specific("anything urgent in my inbox") is True
        assert service.is_urgent_specific("check my email") is False

    def test_build_response_text_empty(self) -> None:
        """Test response text for empty inbox."""
        service = EmailCheckService()
        response = service._build_response_text(0, 0, [], False)
        assert "clear" in response.lower()
        assert "no new emails" in response.lower()

    def test_build_response_text_urgent_specific_none(self) -> None:
        """Test response for urgent-specific request with no urgent emails."""
        service = EmailCheckService()
        response = service._build_response_text(10, 3, [], True)
        assert "no urgent emails" in response.lower()
        assert "10" in response

    def test_build_response_text_with_urgent(self) -> None:
        """Test response when urgent emails are present."""
        from src.services.email_analyzer import EmailCategory

        service = EmailCheckService()

        # Create mock urgent email
        urgent_email = EmailCategory(
            email_id="test-1",
            thread_id="thread-1",
            sender_email="sender@example.com",
            sender_name="John Doe",
            subject="Urgent Test",
            snippet="Test snippet",
            category="NEEDS_REPLY",
            urgency="URGENT",
            topic_summary="Test topic",
            needs_draft=True,
            reason="Contains urgent keywords",
        )

        response = service._build_response_text(10, 3, [urgent_email], False)
        assert "1 urgent" in response.lower()
        assert "John Doe" in response
        assert "draft" in response.lower()


class TestUrgentNotification:
    """Tests for UrgentNotification dataclass."""

    def test_urgent_notification_creation(self) -> None:
        """Test creating an UrgentNotification."""
        notification = UrgentNotification(
            email_id="test-email-1",
            sender_name="Jane Smith",
            sender_email="jane@example.com",
            subject="Test Subject",
            urgency_reason="VIP contact",
            draft_id="draft-1",
            draft_saved=True,
            topic_summary="Test topic",
            timestamp="2026-02-14T10:00:00Z",
        )

        assert notification.email_id == "test-email-1"
        assert notification.sender_name == "Jane Smith"
        assert notification.draft_saved is True

    def test_urgent_notification_no_draft(self) -> None:
        """Test creating an UrgentNotification without a draft."""
        notification = UrgentNotification(
            email_id="test-email-2",
            sender_name="Bob Jones",
            sender_email="bob@example.com",
            subject="Another Test",
            urgency_reason="Time-sensitive content",
            draft_id=None,
            draft_saved=False,
            topic_summary="Another topic",
            timestamp="2026-02-14T11:00:00Z",
        )

        assert notification.draft_id is None
        assert notification.draft_saved is False


class TestRealtimeEmailNotifierImport:
    """Tests for RealtimeEmailNotifier module imports."""

    def test_import_notifier(self) -> None:
        """Test that the notifier can be imported."""
        from src.services.realtime_email_notifier import RealtimeEmailNotifier

        notifier = RealtimeEmailNotifier()
        assert notifier is not None
        assert notifier._draft_engine is None  # Lazily initialized

    def test_get_realtime_email_notifier_singleton(self) -> None:
        """Test the singleton getter."""
        from src.services.realtime_email_notifier import get_realtime_email_notifier

        notifier1 = get_realtime_email_notifier()
        notifier2 = get_realtime_email_notifier()
        assert notifier1 is notifier2


class TestPeriodicEmailCheckImport:
    """Tests for periodic email check job imports."""

    def test_import_job_functions(self) -> None:
        """Test that job functions can be imported."""
        from src.jobs.periodic_email_check import (
            _calculate_hours_since_last_run,
            _is_business_hours,
            run_periodic_email_check,
        )

        assert callable(run_periodic_email_check)
        assert callable(_is_business_hours)
        assert callable(_calculate_hours_since_last_run)


class TestEmailAPIRoutesImport:
    """Tests for email API route imports."""

    def test_import_email_routes(self) -> None:
        """Test that email routes can be imported."""
        from src.api.routes.email import (
            ScanInboxResponse,
            UrgentEmailInfo,
            router,
            scan_inbox_now,
        )

        assert router is not None
        assert callable(scan_inbox_now)

    def test_scan_inbox_response_model(self) -> None:
        """Test ScanInboxResponse model."""
        from src.api.routes.email import ScanInboxResponse

        response = ScanInboxResponse(
            total_emails=10,
            needs_reply=3,
            urgent=1,
            urgent_emails=[],
            scanned_at="2026-02-14T10:00:00Z",
            notifications_sent=1,
        )

        assert response.total_emails == 10
        assert response.needs_reply == 3
        assert response.urgent == 1

    def test_urgent_email_info_model(self) -> None:
        """Test UrgentEmailInfo model."""
        from src.api.routes.email import UrgentEmailInfo

        info = UrgentEmailInfo(
            email_id="email-1",
            sender="John Doe",
            sender_email="john@example.com",
            subject="Urgent Matter",
            urgency="URGENT",
            topic_summary="Test summary",
            reason="VIP contact",
            draft_id="draft-1",
        )

        assert info.email_id == "email-1"
        assert info.urgency == "URGENT"
        assert info.draft_id == "draft-1"
