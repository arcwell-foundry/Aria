"""Tests for ROI Service (US-943 Task 10)."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.core.exceptions import ARIAException, DatabaseError
from src.services.roi_service import ROIService, TIME_SAVED_MINUTES


@pytest.fixture
def roi_service():
    """Create ROIService instance."""
    return ROIService()


@pytest.fixture
def test_user_id():
    """Return test user ID UUID."""
    return "00000000-0000-0000-0000-000000000000"


@pytest.fixture
def sample_aria_actions():
    """Sample aria_actions data."""
    return [
        {
            "id": "action-1",
            "user_id": "00000000-0000-0000-0000-000000000000",
            "action_type": "email_draft",
            "estimated_minutes_saved": 15,
            "status": "auto_approved",
            "created_at": "2026-02-01T10:00:00Z",
        },
        {
            "id": "action-2",
            "user_id": "00000000-0000-0000-0000-000000000000",
            "action_type": "meeting_prep",
            "estimated_minutes_saved": 30,
            "status": "user_approved",
            "created_at": "2026-02-02T14:00:00Z",
        },
        {
            "id": "action-3",
            "user_id": "00000000-0000-0000-0000-000000000000",
            "action_type": "research_report",
            "estimated_minutes_saved": 60,
            "status": "auto_approved",
            "created_at": "2026-02-03T09:00:00Z",
        },
        {
            "id": "action-4",
            "user_id": "00000000-0000-0000-0000-000000000000",
            "action_type": "crm_update",
            "estimated_minutes_saved": 5,
            "status": "rejected",
            "created_at": "2026-02-04T16:00:00Z",
        },
        {
            "id": "action-5",
            "user_id": "00000000-0000-0000-0000-000000000000",
            "action_type": "email_draft",
            "estimated_minutes_saved": 15,
            "status": "pending",
            "created_at": "2026-02-05T11:00:00Z",
        },
    ]


@pytest.fixture
def sample_intelligence_delivered():
    """Sample intelligence_delivered data."""
    return [
        {
            "id": "intel-1",
            "user_id": "00000000-0000-0000-0000-000000000000",
            "intelligence_type": "fact",
            "delivered_at": "2026-02-01T10:00:00Z",
        },
        {
            "id": "intel-2",
            "user_id": "00000000-0000-0000-0000-000000000000",
            "intelligence_type": "signal",
            "delivered_at": "2026-02-02T14:00:00Z",
        },
        {
            "id": "intel-3",
            "user_id": "00000000-0000-0000-0000-000000000000",
            "intelligence_type": "gap_filled",
            "delivered_at": "2026-02-03T09:00:00Z",
        },
        {
            "id": "intel-4",
            "user_id": "00000000-0000-0000-0000-000000000000",
            "intelligence_type": "briefing",
            "delivered_at": "2026-02-04T16:00:00Z",
        },
    ]


@pytest.fixture
def sample_pipeline_impact():
    """Sample pipeline_impact data."""
    return [
        {
            "id": "impact-1",
            "user_id": "00000000-0000-0000-0000-000000000000",
            "impact_type": "lead_discovered",
            "created_at": "2026-02-01T10:00:00Z",
        },
        {
            "id": "impact-2",
            "user_id": "00000000-0000-0000-0000-000000000000",
            "impact_type": "meeting_prepped",
            "created_at": "2026-02-02T14:00:00Z",
        },
        {
            "id": "impact-3",
            "user_id": "00000000-0000-0000-0000-000000000000",
            "impact_type": "follow_up_sent",
            "created_at": "2026-02-03T09:00:00Z",
        },
    ]


class TestGetPeriodStart:
    """Test suite for _get_period_start method."""

    def test_7d_period_returns_7_days_ago(self, roi_service):
        """7d period returns datetime 7 days ago."""
        result = roi_service._get_period_start("7d")
        expected = datetime.utcnow() - timedelta(days=7)
        # Allow 1 second tolerance for test execution time
        assert abs((result - expected).total_seconds()) < 1

    def test_30d_period_returns_30_days_ago(self, roi_service):
        """30d period returns datetime 30 days ago."""
        result = roi_service._get_period_start("30d")
        expected = datetime.utcnow() - timedelta(days=30)
        # Allow 1 second tolerance for test execution time
        assert abs((result - expected).total_seconds()) < 1

    def test_90d_period_returns_90_days_ago(self, roi_service):
        """90d period returns datetime 90 days ago."""
        result = roi_service._get_period_start("90d")
        expected = datetime.utcnow() - timedelta(days=90)
        # Allow 1 second tolerance for test execution time
        assert abs((result - expected).total_seconds()) < 1

    def test_all_period_returns_2020_start_date(self, roi_service):
        """all period returns January 1, 2020."""
        result = roi_service._get_period_start("all")
        expected = datetime(2020, 1, 1)
        assert result == expected

    def test_invalid_period_raises_value_error(self, roi_service):
        """Invalid period raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            roi_service._get_period_start("invalid")

        assert "Invalid period" in str(exc_info.value)
        assert "invalid" in str(exc_info.value)
        assert "7d, 30d, 90d, all" in str(exc_info.value)


class TestGetTimeSavedMetrics:
    """Test suite for get_time_saved_metrics method."""

    @pytest.mark.asyncio
    async def test_empty_data_returns_zeros(self, roi_service, test_user_id):
        """Empty aria_actions data returns zero metrics."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.data = []
            mock_client.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = mock_response
            mock_get_client.return_value = mock_client

            period_start = datetime.utcnow() - timedelta(days=30)
            result = await roi_service.get_time_saved_metrics(test_user_id, period_start)

            assert result["hours"] == 0
            assert result["breakdown"]["email_drafts"]["count"] == 0
            assert result["breakdown"]["email_drafts"]["estimated_hours"] == 0.0
            assert result["breakdown"]["meeting_prep"]["count"] == 0
            assert result["breakdown"]["meeting_prep"]["estimated_hours"] == 0.0
            assert result["breakdown"]["research_reports"]["count"] == 0
            assert result["breakdown"]["research_reports"]["estimated_hours"] == 0.0
            assert result["breakdown"]["crm_updates"]["count"] == 0
            assert result["breakdown"]["crm_updates"]["estimated_hours"] == 0.0

    @pytest.mark.asyncio
    async def test_calculates_time_saved_from_actions(
        self, roi_service, test_user_id, sample_aria_actions
    ):
        """Calculates time saved correctly from action data."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.data = sample_aria_actions
            mock_client.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = mock_response
            mock_get_client.return_value = mock_client

            period_start = datetime.utcnow() - timedelta(days=30)
            result = await roi_service.get_time_saved_metrics(test_user_id, period_start)

            # Total: 15 + 30 + 60 + 5 + 15 = 125 minutes = 2.08 hours
            assert result["hours"] == 2.08
            # 2 email drafts: 15 + 15 = 30 minutes = 0.5 hours
            assert result["breakdown"]["email_drafts"]["count"] == 2
            assert result["breakdown"]["email_drafts"]["estimated_hours"] == 0.5
            # 1 meeting prep: 30 minutes = 0.5 hours
            assert result["breakdown"]["meeting_prep"]["count"] == 1
            assert result["breakdown"]["meeting_prep"]["estimated_hours"] == 0.5
            # 1 research report: 60 minutes = 1 hour
            assert result["breakdown"]["research_reports"]["count"] == 1
            assert result["breakdown"]["research_reports"]["estimated_hours"] == 1.0
            # 1 CRM update: 5 minutes = 0.08 hours
            assert result["breakdown"]["crm_updates"]["count"] == 1
            assert result["breakdown"]["crm_updates"]["estimated_hours"] == 0.08

    @pytest.mark.asyncio
    async def test_uses_constant_minutes_when_saved_not_provided(
        self, roi_service, test_user_id
    ):
        """Uses TIME_SAVED_MINUTES constant when estimated_minutes_saved is missing."""
        actions_without_saved = [
            {
                "id": "action-1",
                "user_id": test_user_id,
                "action_type": "email_draft",
                "created_at": "2026-02-01T10:00:00Z",
            },
        ]

        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.data = actions_without_saved
            mock_client.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = mock_response
            mock_get_client.return_value = mock_client

            period_start = datetime.utcnow() - timedelta(days=30)
            result = await roi_service.get_time_saved_metrics(test_user_id, period_start)

            # Should use TIME_SAVED_MINUTES["email_draft"] = 15
            assert result["hours"] == 0.25  # 15 minutes = 0.25 hours

    @pytest.mark.asyncio
    async def test_skips_unknown_action_types(self, roi_service, test_user_id):
        """Skips action types not in TIME_SAVED_MINUTES."""
        actions_with_unknown = [
            {
                "id": "action-1",
                "user_id": test_user_id,
                "action_type": "unknown_type",
                "estimated_minutes_saved": 100,
                "created_at": "2026-02-01T10:00:00Z",
            },
        ]

        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.data = actions_with_unknown
            mock_client.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = mock_response
            mock_get_client.return_value = mock_client

            period_start = datetime.utcnow() - timedelta(days=30)
            result = await roi_service.get_time_saved_metrics(test_user_id, period_start)

            # Unknown action type should be skipped
            assert result["hours"] == 0

    @pytest.mark.asyncio
    async def test_database_error_raises_database_error(self, roi_service, test_user_id):
        """Database operation failure raises DatabaseError."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.side_effect = Exception("Database connection failed")
            mock_get_client.return_value = mock_client

            period_start = datetime.utcnow() - timedelta(days=30)

            with pytest.raises(DatabaseError) as exc_info:
                await roi_service.get_time_saved_metrics(test_user_id, period_start)

            assert "Failed to calculate time saved metrics" in str(exc_info.value)


class TestGetIntelligenceMetrics:
    """Test suite for get_intelligence_metrics method."""

    @pytest.mark.asyncio
    async def test_empty_data_returns_zeros(self, roi_service, test_user_id):
        """Empty intelligence_delivered data returns zero metrics."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.data = []
            mock_client.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = mock_response
            mock_get_client.return_value = mock_client

            period_start = datetime.utcnow() - timedelta(days=30)
            result = await roi_service.get_intelligence_metrics(test_user_id, period_start)

            assert result["facts_discovered"] == 0
            assert result["signals_detected"] == 0
            assert result["gaps_filled"] == 0
            assert result["briefings_generated"] == 0

    @pytest.mark.asyncio
    async def test_counts_intelligence_by_type(
        self, roi_service, test_user_id, sample_intelligence_delivered
    ):
        """Counts intelligence records by type."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.data = sample_intelligence_delivered
            mock_client.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = mock_response
            mock_get_client.return_value = mock_client

            period_start = datetime.utcnow() - timedelta(days=30)
            result = await roi_service.get_intelligence_metrics(test_user_id, period_start)

            assert result["facts_discovered"] == 1
            assert result["signals_detected"] == 1
            assert result["gaps_filled"] == 1
            assert result["briefings_generated"] == 1

    @pytest.mark.asyncio
    async def test_multiple_of_same_type(self, roi_service, test_user_id):
        """Counts multiple intelligence records of the same type."""
        multiple_facts = [
            {
                "id": "intel-1",
                "user_id": test_user_id,
                "intelligence_type": "fact",
                "delivered_at": "2026-02-01T10:00:00Z",
            },
            {
                "id": "intel-2",
                "user_id": test_user_id,
                "intelligence_type": "fact",
                "delivered_at": "2026-02-02T10:00:00Z",
            },
            {
                "id": "intel-3",
                "user_id": test_user_id,
                "intelligence_type": "fact",
                "delivered_at": "2026-02-03T10:00:00Z",
            },
        ]

        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.data = multiple_facts
            mock_client.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = mock_response
            mock_get_client.return_value = mock_client

            period_start = datetime.utcnow() - timedelta(days=30)
            result = await roi_service.get_intelligence_metrics(test_user_id, period_start)

            assert result["facts_discovered"] == 3

    @pytest.mark.asyncio
    async def test_database_error_raises_database_error(self, roi_service, test_user_id):
        """Database operation failure raises DatabaseError."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.side_effect = Exception("Database connection failed")
            mock_get_client.return_value = mock_client

            period_start = datetime.utcnow() - timedelta(days=30)

            with pytest.raises(DatabaseError) as exc_info:
                await roi_service.get_intelligence_metrics(test_user_id, period_start)

            assert "Failed to calculate intelligence metrics" in str(exc_info.value)


class TestGetActionsMetrics:
    """Test suite for get_actions_metrics method."""

    @pytest.mark.asyncio
    async def test_empty_data_returns_zeros(self, roi_service, test_user_id):
        """Empty aria_actions data returns zero metrics."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.data = []
            mock_client.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = mock_response
            mock_get_client.return_value = mock_client

            period_start = datetime.utcnow() - timedelta(days=30)
            result = await roi_service.get_actions_metrics(test_user_id, period_start)

            assert result["total"] == 0
            assert result["auto_approved"] == 0
            assert result["user_approved"] == 0
            assert result["rejected"] == 0

    @pytest.mark.asyncio
    async def test_counts_actions_by_status(
        self, roi_service, test_user_id, sample_aria_actions
    ):
        """Counts actions by approval status."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.data = sample_aria_actions
            mock_client.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = mock_response
            mock_get_client.return_value = mock_client

            period_start = datetime.utcnow() - timedelta(days=30)
            result = await roi_service.get_actions_metrics(test_user_id, period_start)

            assert result["total"] == 5
            assert result["auto_approved"] == 2
            assert result["user_approved"] == 1
            assert result["rejected"] == 1
            # pending is counted in total but not tracked separately

    @pytest.mark.asyncio
    async def test_includes_pending_in_total(self, roi_service, test_user_id):
        """Pending actions are counted in total but not in approval categories."""
        pending_actions = [
            {
                "id": "action-1",
                "user_id": test_user_id,
                "status": "pending",
                "created_at": "2026-02-01T10:00:00Z",
            },
            {
                "id": "action-2",
                "user_id": test_user_id,
                "status": "pending",
                "created_at": "2026-02-02T10:00:00Z",
            },
        ]

        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.data = pending_actions
            mock_client.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = mock_response
            mock_get_client.return_value = mock_client

            period_start = datetime.utcnow() - timedelta(days=30)
            result = await roi_service.get_actions_metrics(test_user_id, period_start)

            assert result["total"] == 2
            assert result["auto_approved"] == 0
            assert result["user_approved"] == 0
            assert result["rejected"] == 0

    @pytest.mark.asyncio
    async def test_database_error_raises_database_error(self, roi_service, test_user_id):
        """Database operation failure raises DatabaseError."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.side_effect = Exception("Database connection failed")
            mock_get_client.return_value = mock_client

            period_start = datetime.utcnow() - timedelta(days=30)

            with pytest.raises(DatabaseError) as exc_info:
                await roi_service.get_actions_metrics(test_user_id, period_start)

            assert "Failed to calculate actions metrics" in str(exc_info.value)


class TestGetPipelineMetrics:
    """Test suite for get_pipeline_metrics method."""

    @pytest.mark.asyncio
    async def test_empty_data_returns_zeros(self, roi_service, test_user_id):
        """Empty pipeline_impact data returns zero metrics."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.data = []
            mock_client.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = mock_response
            mock_get_client.return_value = mock_client

            period_start = datetime.utcnow() - timedelta(days=30)
            result = await roi_service.get_pipeline_metrics(test_user_id, period_start)

            assert result["leads_discovered"] == 0
            assert result["meetings_prepped"] == 0
            assert result["follow_ups_sent"] == 0

    @pytest.mark.asyncio
    async def test_counts_pipeline_impact_by_type(
        self, roi_service, test_user_id, sample_pipeline_impact
    ):
        """Counts pipeline impacts by type."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.data = sample_pipeline_impact
            mock_client.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = mock_response
            mock_get_client.return_value = mock_client

            period_start = datetime.utcnow() - timedelta(days=30)
            result = await roi_service.get_pipeline_metrics(test_user_id, period_start)

            assert result["leads_discovered"] == 1
            assert result["meetings_prepped"] == 1
            assert result["follow_ups_sent"] == 1

    @pytest.mark.asyncio
    async def test_multiple_of_same_type(self, roi_service, test_user_id):
        """Counts multiple pipeline impacts of the same type."""
        multiple_leads = [
            {
                "id": "impact-1",
                "user_id": test_user_id,
                "impact_type": "lead_discovered",
                "created_at": "2026-02-01T10:00:00Z",
            },
            {
                "id": "impact-2",
                "user_id": test_user_id,
                "impact_type": "lead_discovered",
                "created_at": "2026-02-02T10:00:00Z",
            },
        ]

        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.data = multiple_leads
            mock_client.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = mock_response
            mock_get_client.return_value = mock_client

            period_start = datetime.utcnow() - timedelta(days=30)
            result = await roi_service.get_pipeline_metrics(test_user_id, period_start)

            assert result["leads_discovered"] == 2

    @pytest.mark.asyncio
    async def test_database_error_raises_database_error(self, roi_service, test_user_id):
        """Database operation failure raises DatabaseError."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.side_effect = Exception("Database connection failed")
            mock_get_client.return_value = mock_client

            period_start = datetime.utcnow() - timedelta(days=30)

            with pytest.raises(DatabaseError) as exc_info:
                await roi_service.get_pipeline_metrics(test_user_id, period_start)

            assert "Failed to calculate pipeline metrics" in str(exc_info.value)


class TestGetWeeklyTrend:
    """Test suite for get_weekly_trend method."""

    @pytest.mark.asyncio
    async def test_empty_data_returns_empty_list(self, roi_service, test_user_id):
        """Empty aria_actions data returns empty trend list."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.data = []
            mock_client.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.execute.return_value = mock_response
            mock_get_client.return_value = mock_client

            period_start = datetime.utcnow() - timedelta(days=30)
            result = await roi_service.get_weekly_trend(test_user_id, period_start)

            assert result == []

    @pytest.mark.asyncio
    async def test_groups_actions_by_week(self, roi_service, test_user_id):
        """Groups actions by week and sums hours saved."""
        # Actions across multiple weeks
        actions = [
            {
                "id": "action-1",
                "user_id": test_user_id,
                "action_type": "email_draft",
                "estimated_minutes_saved": 15,
                "created_at": "2026-02-03T10:00:00Z",  # Monday of week 1
            },
            {
                "id": "action-2",
                "user_id": test_user_id,
                "action_type": "email_draft",
                "estimated_minutes_saved": 15,
                "created_at": "2026-02-05T10:00:00Z",  # Wednesday of week 1
            },
            {
                "id": "action-3",
                "user_id": test_user_id,
                "action_type": "meeting_prep",
                "estimated_minutes_saved": 30,
                "created_at": "2026-02-10T10:00:00Z",  # Monday of week 2
            },
        ]

        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.data = actions
            mock_client.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.execute.return_value = mock_response
            mock_get_client.return_value = mock_client

            period_start = datetime(2026, 2, 1)
            result = await roi_service.get_weekly_trend(test_user_id, period_start)

            # Week 1 (Feb 2): 15 + 15 = 30 minutes = 0.5 hours
            # Week 2 (Feb 9): 30 minutes = 0.5 hours
            assert len(result) == 2
            assert result[0]["week_start"] == "2026-02-02"
            assert result[0]["hours_saved"] == 0.5
            assert result[1]["week_start"] == "2026-02-09"
            assert result[1]["hours_saved"] == 0.5

    @pytest.mark.asyncio
    async def test_uses_constant_minutes_when_saved_not_provided(
        self, roi_service, test_user_id
    ):
        """Uses TIME_SAVED_MINUTES constant when estimated_minutes_saved is missing."""
        actions = [
            {
                "id": "action-1",
                "user_id": test_user_id,
                "action_type": "email_draft",
                "created_at": "2026-02-03T10:00:00Z",
            },
        ]

        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.data = actions
            mock_client.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.execute.return_value = mock_response
            mock_get_client.return_value = mock_client

            period_start = datetime(2026, 2, 1)
            result = await roi_service.get_weekly_trend(test_user_id, period_start)

            # Should use TIME_SAVED_MINUTES["email_draft"] = 15 minutes = 0.25 hours
            assert len(result) == 1
            assert result[0]["hours_saved"] == 0.25

    @pytest.mark.asyncio
    async def test_skips_actions_with_invalid_created_at(self, roi_service, test_user_id):
        """Skips actions with missing or invalid created_at timestamps."""
        actions = [
            {
                "id": "action-1",
                "user_id": test_user_id,
                "action_type": "email_draft",
                "estimated_minutes_saved": 15,
                "created_at": "2026-02-03T10:00:00Z",
            },
            {
                "id": "action-2",
                "user_id": test_user_id,
                "action_type": "email_draft",
                "estimated_minutes_saved": 15,
                # Missing created_at
            },
        ]

        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.data = actions
            mock_client.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.execute.return_value = mock_response
            mock_get_client.return_value = mock_client

            period_start = datetime(2026, 2, 1)
            result = await roi_service.get_weekly_trend(test_user_id, period_start)

            # Should only count the valid action
            assert len(result) == 1
            assert result[0]["hours_saved"] == 0.25

    @pytest.mark.asyncio
    async def test_skips_unknown_action_types(self, roi_service, test_user_id):
        """Skips action types not in TIME_SAVED_MINUTES."""
        actions = [
            {
                "id": "action-1",
                "user_id": test_user_id,
                "action_type": "unknown_type",
                "estimated_minutes_saved": 100,
                "created_at": "2026-02-03T10:00:00Z",
            },
        ]

        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.data = actions
            mock_client.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.execute.return_value = mock_response
            mock_get_client.return_value = mock_client

            period_start = datetime(2026, 2, 1)
            result = await roi_service.get_weekly_trend(test_user_id, period_start)

            # Unknown action type should be skipped
            assert result == []

    @pytest.mark.asyncio
    async def test_returns_trend_sorted_by_week(self, roi_service, test_user_id):
        """Returns trend data sorted by week ascending."""
        actions = [
            {
                "id": "action-2",
                "user_id": test_user_id,
                "action_type": "meeting_prep",
                "estimated_minutes_saved": 30,
                "created_at": "2026-02-10T10:00:00Z",
            },
            {
                "id": "action-1",
                "user_id": test_user_id,
                "action_type": "email_draft",
                "estimated_minutes_saved": 15,
                "created_at": "2026-02-03T10:00:00Z",
            },
        ]

        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.data = actions
            mock_client.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.execute.return_value = mock_response
            mock_get_client.return_value = mock_client

            period_start = datetime(2026, 2, 1)
            result = await roi_service.get_weekly_trend(test_user_id, period_start)

            # Should be sorted by week
            assert len(result) == 2
            assert result[0]["week_start"] == "2026-02-02"
            assert result[1]["week_start"] == "2026-02-09"

    @pytest.mark.asyncio
    async def test_database_error_raises_database_error(self, roi_service, test_user_id):
        """Database operation failure raises DatabaseError."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.execute.side_effect = Exception("Database connection failed")
            mock_get_client.return_value = mock_client

            period_start = datetime.utcnow() - timedelta(days=30)

            with pytest.raises(DatabaseError) as exc_info:
                await roi_service.get_weekly_trend(test_user_id, period_start)

            assert "Failed to calculate weekly trend" in str(exc_info.value)


class TestGetAllMetrics:
    """Test suite for get_all_metrics method."""

    @pytest.mark.asyncio
    async def test_aggregates_all_metrics(
        self,
        roi_service,
        test_user_id,
        sample_aria_actions,
        sample_intelligence_delivered,
        sample_pipeline_impact,
    ):
        """Aggregates all metric categories for a user and period."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()

            # Create response mocks
            def create_response(data):
                response = MagicMock()
                response.data = data
                return response

            # Track table calls
            table_call_count = [0]

            def mock_table(table_name):
                table_call_count[0] += 1
                mock_tbl = MagicMock()

                if table_name == "aria_actions":
                    # Return actions data
                    mock_tbl.select.return_value.eq.return_value.gte.return_value.execute.return_value = create_response(sample_aria_actions)
                    mock_tbl.select.return_value.eq.return_value.gte.return_value.order.return_value.execute.return_value = create_response(sample_aria_actions)
                elif table_name == "intelligence_delivered":
                    mock_tbl.select.return_value.eq.return_value.gte.return_value.execute.return_value = create_response(sample_intelligence_delivered)
                elif table_name == "pipeline_impact":
                    mock_tbl.select.return_value.eq.return_value.gte.return_value.execute.return_value = create_response(sample_pipeline_impact)

                return mock_tbl

            mock_client.table.side_effect = mock_table
            mock_get_client.return_value = mock_client

            result = await roi_service.get_all_metrics(test_user_id, "30d")

            # Verify time_saved metrics
            assert "time_saved" in result
            assert result["time_saved"]["hours"] == 2.08

            # Verify intelligence_delivered metrics
            assert "intelligence_delivered" in result
            assert result["intelligence_delivered"]["facts_discovered"] == 1

            # Verify actions_taken metrics
            assert "actions_taken" in result
            assert result["actions_taken"]["total"] == 5
            assert result["actions_taken"]["auto_approved"] == 2

            # Verify pipeline_impact metrics
            assert "pipeline_impact" in result
            assert result["pipeline_impact"]["leads_discovered"] == 1

            # Verify weekly_trend
            assert "weekly_trend" in result
            assert isinstance(result["weekly_trend"], list)

            # Verify period and calculated_at
            assert result["period"] == "30d"
            assert "calculated_at" in result
            assert isinstance(result["calculated_at"], str)

    @pytest.mark.asyncio
    async def test_calculates_derived_metrics(self, roi_service, test_user_id):
        """Calculates time_saved_per_week and action_approval_rate."""
        # Actions with clear approval pattern
        actions = [
            {
                "id": "action-1",
                "user_id": test_user_id,
                "action_type": "email_draft",
                "estimated_minutes_saved": 15,
                "status": "auto_approved",
                "created_at": "2026-02-03T10:00:00Z",
            },
            {
                "id": "action-2",
                "user_id": test_user_id,
                "action_type": "email_draft",
                "estimated_minutes_saved": 15,
                "status": "user_approved",
                "created_at": "2026-03-03T10:00:00Z",  # Different week
            },
        ]

        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()

            def create_response(data):
                response = MagicMock()
                response.data = data
                return response

            def mock_table(table_name):
                mock_tbl = MagicMock()

                if table_name == "aria_actions":
                    mock_tbl.select.return_value.eq.return_value.gte.return_value.execute.return_value = create_response(actions)
                    mock_tbl.select.return_value.eq.return_value.gte.return_value.order.return_value.execute.return_value = create_response(actions)
                else:
                    # Empty data for other tables
                    mock_tbl.select.return_value.eq.return_value.gte.return_value.execute.return_value = create_response([])

                return mock_tbl

            mock_client.table.side_effect = mock_table
            mock_get_client.return_value = mock_client

            result = await roi_service.get_all_metrics(test_user_id, "30d")

            # Calculate derived metrics
            assert "time_saved_per_week" in result
            assert result["time_saved_per_week"] is not None
            # 2 actions across 2 weeks = (15+15)/60/2 = 0.25 hours per week
            assert result["time_saved_per_week"] == 0.25

            assert "action_approval_rate" in result
            assert result["action_approval_rate"] is not None
            # 2 approved out of 2 total = 1.0
            assert result["action_approval_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_action_approval_rate_none_when_no_actions(
        self, roi_service, test_user_id
    ):
        """action_approval_rate is None when there are no actions."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()

            def create_response(data):
                response = MagicMock()
                response.data = data
                return response

            def mock_table(table_name):
                mock_tbl = MagicMock()
                mock_tbl.select.return_value.eq.return_value.gte.return_value.execute.return_value = create_response([])
                mock_tbl.select.return_value.eq.return_value.gte.return_value.order.return_value.execute.return_value = create_response([])
                return mock_tbl

            mock_client.table.side_effect = mock_table
            mock_get_client.return_value = mock_client

            result = await roi_service.get_all_metrics(test_user_id, "30d")

            assert result["action_approval_rate"] is None

    @pytest.mark.asyncio
    async def test_time_saved_per_week_none_when_no_trend(
        self, roi_service, test_user_id
    ):
        """time_saved_per_week is None when there is no weekly trend."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()

            def create_response(data):
                response = MagicMock()
                response.data = data
                return response

            def mock_table(table_name):
                mock_tbl = MagicMock()
                mock_tbl.select.return_value.eq.return_value.gte.return_value.execute.return_value = create_response([])
                mock_tbl.select.return_value.eq.return_value.gte.return_value.order.return_value.execute.return_value = create_response([])
                return mock_tbl

            mock_client.table.side_effect = mock_table
            mock_get_client.return_value = mock_client

            result = await roi_service.get_all_metrics(test_user_id, "30d")

            assert result["time_saved_per_week"] is None

    @pytest.mark.asyncio
    async def test_invalid_period_raises_ar_exception(
        self, roi_service, test_user_id
    ):
        """Invalid period raises ARIAException with status 400."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()

            def create_response(data):
                response = MagicMock()
                response.data = data
                return response

            def mock_table(table_name):
                mock_tbl = MagicMock()
                mock_tbl.select.return_value.eq.return_value.gte.return_value.execute.return_value = create_response([])
                mock_tbl.select.return_value.eq.return_value.gte.return_value.order.return_value.execute.return_value = create_response([])
                return mock_tbl

            mock_client.table.side_effect = mock_table
            mock_get_client.return_value = mock_client

            with pytest.raises(ARIAException) as exc_info:
                await roi_service.get_all_metrics(test_user_id, "invalid")

            assert exc_info.value.status_code == 400
            assert "INVALID_PERIOD" in exc_info.value.code

    @pytest.mark.asyncio
    async def test_database_error_propagates(self, roi_service, test_user_id):
        """DatabaseError from metric methods propagates correctly."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.side_effect = Exception("Database connection failed")
            mock_get_client.return_value = mock_client

            with pytest.raises(DatabaseError):
                await roi_service.get_all_metrics(test_user_id, "30d")

    @pytest.mark.asyncio
    async def test_default_period_is_30d(self, roi_service, test_user_id):
        """Default period is 30d when not specified."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()

            def create_response(data):
                response = MagicMock()
                response.data = data
                return response

            def mock_table(table_name):
                mock_tbl = MagicMock()
                mock_tbl.select.return_value.eq.return_value.gte.return_value.execute.return_value = create_response([])
                mock_tbl.select.return_value.eq.return_value.gte.return_value.order.return_value.execute.return_value = create_response([])
                return mock_tbl

            mock_client.table.side_effect = mock_table
            mock_get_client.return_value = mock_client

            result = await roi_service.get_all_metrics(test_user_id)

            assert result["period"] == "30d"
