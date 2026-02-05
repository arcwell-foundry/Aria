"""Tests for LeadProactiveBehaviors service.

Tests the proactive lead monitoring behaviors:
- Silent lead detection and notification
- Health score drop detection and notification
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.memory.lead_patterns import SilentLead


class TestCheckSilentLeads:
    """Tests for check_silent_leads method."""

    @pytest.mark.asyncio
    async def test_check_silent_leads_sends_notifications(self):
        """Test that silent leads trigger notifications."""
        from src.behaviors.lead_proactive import LeadProactiveBehaviors
        from src.models.notification import NotificationType

        mock_db = MagicMock()
        service = LeadProactiveBehaviors(db_client=mock_db)

        now = datetime.now(UTC)
        silent_leads = [
            SilentLead(
                lead_id="lead-123",
                company_name="Acme Corp",
                days_inactive=21,
                last_activity_at=now - timedelta(days=21),
                health_score=45,
            ),
            SilentLead(
                lead_id="lead-456",
                company_name="Beta Inc",
                days_inactive=14,
                last_activity_at=now - timedelta(days=14),
                health_score=60,
            ),
        ]

        with patch.object(
            service, "_pattern_detector"
        ) as mock_detector, patch(
            "src.behaviors.lead_proactive.NotificationService"
        ) as mock_notification_service:
            mock_detector.find_silent_leads = AsyncMock(return_value=silent_leads)
            mock_notification_service.create_notification = AsyncMock()

            result = await service.check_silent_leads(user_id="user-abc")

            assert result == 2
            assert mock_notification_service.create_notification.call_count == 2

            # Check first notification
            first_call = mock_notification_service.create_notification.call_args_list[0]
            assert first_call.kwargs["user_id"] == "user-abc"
            assert first_call.kwargs["type"] == NotificationType.LEAD_SILENT
            assert "Acme Corp" in first_call.kwargs["title"]
            assert "21 days" in first_call.kwargs["message"]

    @pytest.mark.asyncio
    async def test_check_silent_leads_no_results(self):
        """Test check_silent_leads with no silent leads."""
        from src.behaviors.lead_proactive import LeadProactiveBehaviors

        mock_db = MagicMock()
        service = LeadProactiveBehaviors(db_client=mock_db)

        with patch.object(
            service, "_pattern_detector"
        ) as mock_detector, patch(
            "src.behaviors.lead_proactive.NotificationService"
        ) as mock_notification_service:
            mock_detector.find_silent_leads = AsyncMock(return_value=[])
            mock_notification_service.create_notification = AsyncMock()

            result = await service.check_silent_leads(user_id="user-abc")

            assert result == 0
            mock_notification_service.create_notification.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_silent_leads_custom_threshold(self):
        """Test check_silent_leads with custom inactive days threshold."""
        from src.behaviors.lead_proactive import LeadProactiveBehaviors

        mock_db = MagicMock()
        service = LeadProactiveBehaviors(db_client=mock_db)

        with patch.object(
            service, "_pattern_detector"
        ) as mock_detector, patch(
            "src.behaviors.lead_proactive.NotificationService"
        ):
            mock_detector.find_silent_leads = AsyncMock(return_value=[])

            await service.check_silent_leads(user_id="user-abc", inactive_days=7)

            mock_detector.find_silent_leads.assert_called_once_with(
                user_id="user-abc",
                inactive_days=7,
            )
