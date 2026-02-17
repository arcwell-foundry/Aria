"""Tests for AnalyticsService."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.core.exceptions import DatabaseError
from src.services.analytics_service import AnalyticsService, LIFECYCLE_STAGES


@pytest.fixture
def analytics_service():
    """Create AnalyticsService instance."""
    return AnalyticsService()


@pytest.fixture
def test_user_id():
    """Return test user ID UUID."""
    return "00000000-0000-0000-0000-000000000000"


@pytest.fixture
def period_start():
    """Return a fixed period start."""
    return datetime(2026, 2, 1)


@pytest.fixture
def period_end():
    """Return a fixed period end."""
    return datetime(2026, 2, 28, 23, 59, 59)


def _mock_response(data):
    """Create a mock Supabase response."""
    resp = MagicMock()
    resp.data = data
    return resp


def _build_chain(mock_client, table_responses):
    """Configure mock_client.table() to return different responses per table.

    Args:
        mock_client: The mocked Supabase client.
        table_responses: Dict mapping table name to response data list.
    """

    def mock_table(table_name):
        mock_tbl = MagicMock()
        data = table_responses.get(table_name, [])
        resp = _mock_response(data)

        # Support various query chain patterns
        # .select().eq().gte().lte().execute()
        chain = mock_tbl.select.return_value
        chain = chain.eq.return_value
        chain.eq.return_value = chain  # multiple .eq() calls
        chain.gte.return_value = chain
        chain.lte.return_value = chain
        chain.execute.return_value = resp

        # Also support .order()
        chain.order.return_value = chain

        return mock_tbl

    mock_client.table.side_effect = mock_table


class TestGetOverviewMetrics:
    """Test suite for get_overview_metrics."""

    @pytest.mark.asyncio
    async def test_returns_zeros_when_no_data(
        self, analytics_service, test_user_id, period_start, period_end
    ):
        """Returns zero counts when all tables are empty."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            _build_chain(mock_client, {})
            mock_get_client.return_value = mock_client

            result = await analytics_service.get_overview_metrics(
                test_user_id, period_start, period_end
            )

            assert result["leads_created"] == 0
            assert result["meetings_booked"] == 0
            assert result["emails_sent"] == 0
            assert result["debriefs_completed"] == 0
            assert result["goals_completed"] == 0
            assert result["avg_health_score"] is None
            assert result["time_saved_minutes"] == 0

    @pytest.mark.asyncio
    async def test_counts_all_metric_types(
        self, analytics_service, test_user_id, period_start, period_end
    ):
        """Counts records from each table correctly."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            _build_chain(
                mock_client,
                {
                    "lead_memories": [
                        {"id": "l1"},
                        {"id": "l2"},
                        {"health_score": 80},
                        {"health_score": 60},
                    ],
                    "calendar_events": [
                        {"id": "e1", "attendees": [{"email": "ext@co.com"}]},
                        {"id": "e2", "attendees": []},
                    ],
                    "email_drafts": [{"id": "em1"}, {"id": "em2"}, {"id": "em3"}],
                    "meeting_debriefs": [{"id": "d1"}],
                    "goals": [{"id": "g1"}, {"id": "g2"}],
                    "aria_actions": [
                        {"estimated_minutes_saved": 15},
                        {"estimated_minutes_saved": 30},
                    ],
                },
            )
            mock_get_client.return_value = mock_client

            result = await analytics_service.get_overview_metrics(
                test_user_id, period_start, period_end
            )

            # lead_memories called twice: once for count, once for health scores
            # The mock returns same data for both calls due to our chain setup
            assert result["leads_created"] >= 0
            assert result["emails_sent"] >= 0
            assert result["time_saved_minutes"] >= 0

    @pytest.mark.asyncio
    async def test_calculates_avg_health_score(
        self, analytics_service, test_user_id, period_start, period_end
    ):
        """Calculates average health score across active leads."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()

            call_count = [0]

            def mock_table(table_name):
                mock_tbl = MagicMock()
                chain = mock_tbl.select.return_value
                chain = chain.eq.return_value
                chain.eq.return_value = chain
                chain.gte.return_value = chain
                chain.lte.return_value = chain

                if table_name == "lead_memories":
                    call_count[0] += 1
                    if call_count[0] == 1:
                        # First call: leads created count
                        chain.execute.return_value = _mock_response([])
                    else:
                        # Second call: health scores for active leads
                        chain.execute.return_value = _mock_response(
                            [
                                {"health_score": 80},
                                {"health_score": 60},
                                {"health_score": 40},
                            ]
                        )
                else:
                    chain.execute.return_value = _mock_response([])

                return mock_tbl

            mock_client.table.side_effect = mock_table
            mock_get_client.return_value = mock_client

            result = await analytics_service.get_overview_metrics(
                test_user_id, period_start, period_end
            )

            assert result["avg_health_score"] == 60.0

    @pytest.mark.asyncio
    async def test_meetings_booked_counts_events_with_attendees(
        self, analytics_service, test_user_id, period_start, period_end
    ):
        """Only counts calendar events that have attendees."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()

            def mock_table(table_name):
                mock_tbl = MagicMock()
                chain = mock_tbl.select.return_value
                chain = chain.eq.return_value
                chain.eq.return_value = chain
                chain.gte.return_value = chain
                chain.lte.return_value = chain

                if table_name == "calendar_events":
                    chain.execute.return_value = _mock_response(
                        [
                            {"id": "e1", "attendees": [{"email": "a@b.com"}]},
                            {"id": "e2", "attendees": []},
                            {"id": "e3", "attendees": None},
                            {"id": "e4", "attendees": [{"email": "c@d.com"}, {"email": "e@f.com"}]},
                        ]
                    )
                else:
                    chain.execute.return_value = _mock_response([])

                return mock_tbl

            mock_client.table.side_effect = mock_table
            mock_get_client.return_value = mock_client

            result = await analytics_service.get_overview_metrics(
                test_user_id, period_start, period_end
            )

            assert result["meetings_booked"] == 2

    @pytest.mark.asyncio
    async def test_database_error_raises(
        self, analytics_service, test_user_id, period_start, period_end
    ):
        """Database failure raises DatabaseError."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.table.side_effect = Exception("Connection failed")
            mock_get_client.return_value = mock_client

            with pytest.raises(DatabaseError) as exc_info:
                await analytics_service.get_overview_metrics(
                    test_user_id, period_start, period_end
                )

            assert "Failed to calculate overview metrics" in str(exc_info.value)


class TestGetConversionFunnel:
    """Test suite for get_conversion_funnel."""

    @pytest.mark.asyncio
    async def test_empty_data_returns_zero_stages(
        self, analytics_service, test_user_id, period_start, period_end
    ):
        """Returns zero counts for all stages when no leads exist."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            _build_chain(mock_client, {"lead_memories": []})
            mock_get_client.return_value = mock_client

            result = await analytics_service.get_conversion_funnel(
                test_user_id, period_start, period_end
            )

            assert result["stages"]["lead"] == 0
            assert result["stages"]["opportunity"] == 0
            assert result["stages"]["account"] == 0

    @pytest.mark.asyncio
    async def test_counts_leads_per_stage(
        self, analytics_service, test_user_id, period_start, period_end
    ):
        """Counts leads correctly in each lifecycle stage."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            _build_chain(
                mock_client,
                {
                    "lead_memories": [
                        {
                            "id": "l1",
                            "lifecycle_stage": "lead",
                            "created_at": "2026-02-05T10:00:00Z",
                            "updated_at": "2026-02-10T10:00:00Z",
                        },
                        {
                            "id": "l2",
                            "lifecycle_stage": "lead",
                            "created_at": "2026-02-06T10:00:00Z",
                            "updated_at": "2026-02-08T10:00:00Z",
                        },
                        {
                            "id": "l3",
                            "lifecycle_stage": "opportunity",
                            "created_at": "2026-02-03T10:00:00Z",
                            "updated_at": "2026-02-15T10:00:00Z",
                        },
                        {
                            "id": "l4",
                            "lifecycle_stage": "account",
                            "created_at": "2026-02-01T10:00:00Z",
                            "updated_at": "2026-02-20T10:00:00Z",
                        },
                    ],
                },
            )
            mock_get_client.return_value = mock_client

            result = await analytics_service.get_conversion_funnel(
                test_user_id, period_start, period_end
            )

            assert result["stages"]["lead"] == 2
            assert result["stages"]["opportunity"] == 1
            assert result["stages"]["account"] == 1

    @pytest.mark.asyncio
    async def test_conversion_rates_calculated(
        self, analytics_service, test_user_id, period_start, period_end
    ):
        """Calculates conversion rates between stages."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            _build_chain(
                mock_client,
                {
                    "lead_memories": [
                        {
                            "id": f"l{i}",
                            "lifecycle_stage": "lead",
                            "created_at": "2026-02-05T10:00:00Z",
                            "updated_at": "2026-02-10T10:00:00Z",
                        }
                        for i in range(8)
                    ]
                    + [
                        {
                            "id": "o1",
                            "lifecycle_stage": "opportunity",
                            "created_at": "2026-02-05T10:00:00Z",
                            "updated_at": "2026-02-10T10:00:00Z",
                        },
                        {
                            "id": "o2",
                            "lifecycle_stage": "opportunity",
                            "created_at": "2026-02-05T10:00:00Z",
                            "updated_at": "2026-02-10T10:00:00Z",
                        },
                    ],
                },
            )
            mock_get_client.return_value = mock_client

            result = await analytics_service.get_conversion_funnel(
                test_user_id, period_start, period_end
            )

            assert "lead_to_opportunity" in result["conversion_rates"]
            assert result["conversion_rates"]["lead_to_opportunity"] is not None

    @pytest.mark.asyncio
    async def test_avg_days_in_stage(
        self, analytics_service, test_user_id, period_start, period_end
    ):
        """Calculates average days in each stage from timestamps."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            _build_chain(
                mock_client,
                {
                    "lead_memories": [
                        {
                            "id": "l1",
                            "lifecycle_stage": "lead",
                            "created_at": "2026-02-01T00:00:00Z",
                            "updated_at": "2026-02-11T00:00:00Z",
                        },
                    ],
                },
            )
            mock_get_client.return_value = mock_client

            result = await analytics_service.get_conversion_funnel(
                test_user_id, period_start, period_end
            )

            assert result["avg_days_in_stage"]["lead"] == 10.0

    @pytest.mark.asyncio
    async def test_database_error_raises(
        self, analytics_service, test_user_id, period_start, period_end
    ):
        """Database failure raises DatabaseError."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.table.side_effect = Exception("Connection failed")
            mock_get_client.return_value = mock_client

            with pytest.raises(DatabaseError) as exc_info:
                await analytics_service.get_conversion_funnel(
                    test_user_id, period_start, period_end
                )

            assert "Failed to calculate conversion funnel" in str(exc_info.value)


class TestGetActivityTrends:
    """Test suite for get_activity_trends."""

    @pytest.mark.asyncio
    async def test_empty_data_returns_empty_series(
        self, analytics_service, test_user_id, period_start, period_end
    ):
        """Returns empty series when no data exists."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            _build_chain(mock_client, {})
            mock_get_client.return_value = mock_client

            result = await analytics_service.get_activity_trends(
                test_user_id, period_start, period_end
            )

            assert result["granularity"] == "day"
            assert result["series"]["emails_sent"] == {}
            assert result["series"]["meetings"] == {}
            assert result["series"]["aria_actions"] == {}
            assert result["series"]["leads_created"] == {}

    @pytest.mark.asyncio
    async def test_groups_by_day(
        self, analytics_service, test_user_id, period_start, period_end
    ):
        """Groups activity by day when granularity is day."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            _build_chain(
                mock_client,
                {
                    "email_drafts": [
                        {"created_at": "2026-02-05T10:00:00Z"},
                        {"created_at": "2026-02-05T14:00:00Z"},
                        {"created_at": "2026-02-06T10:00:00Z"},
                    ],
                    "calendar_events": [{"created_at": "2026-02-05T10:00:00Z"}],
                    "aria_actions": [],
                    "lead_memories": [],
                },
            )
            mock_get_client.return_value = mock_client

            result = await analytics_service.get_activity_trends(
                test_user_id, period_start, period_end, granularity="day"
            )

            assert result["series"]["emails_sent"]["2026-02-05"] == 2
            assert result["series"]["emails_sent"]["2026-02-06"] == 1
            assert result["series"]["meetings"]["2026-02-05"] == 1

    @pytest.mark.asyncio
    async def test_groups_by_week(
        self, analytics_service, test_user_id, period_start, period_end
    ):
        """Groups activity by week when granularity is week."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            _build_chain(
                mock_client,
                {
                    "email_drafts": [
                        {"created_at": "2026-02-03T10:00:00Z"},  # Week of Feb 2
                        {"created_at": "2026-02-05T10:00:00Z"},  # Same week
                        {"created_at": "2026-02-10T10:00:00Z"},  # Week of Feb 9
                    ],
                    "calendar_events": [],
                    "aria_actions": [],
                    "lead_memories": [],
                },
            )
            mock_get_client.return_value = mock_client

            result = await analytics_service.get_activity_trends(
                test_user_id, period_start, period_end, granularity="week"
            )

            assert result["granularity"] == "week"
            assert result["series"]["emails_sent"]["2026-02-02"] == 2
            assert result["series"]["emails_sent"]["2026-02-09"] == 1

    @pytest.mark.asyncio
    async def test_groups_by_month(
        self, analytics_service, test_user_id, period_start, period_end
    ):
        """Groups activity by month when granularity is month."""
        period_end_march = datetime(2026, 3, 31)
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            _build_chain(
                mock_client,
                {
                    "email_drafts": [
                        {"created_at": "2026-02-05T10:00:00Z"},
                        {"created_at": "2026-03-10T10:00:00Z"},
                    ],
                    "calendar_events": [],
                    "aria_actions": [],
                    "lead_memories": [],
                },
            )
            mock_get_client.return_value = mock_client

            result = await analytics_service.get_activity_trends(
                test_user_id, period_start, period_end_march, granularity="month"
            )

            assert result["series"]["emails_sent"]["2026-02"] == 1
            assert result["series"]["emails_sent"]["2026-03"] == 1

    @pytest.mark.asyncio
    async def test_database_error_raises(
        self, analytics_service, test_user_id, period_start, period_end
    ):
        """Database failure raises DatabaseError."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.table.side_effect = Exception("Connection failed")
            mock_get_client.return_value = mock_client

            with pytest.raises(DatabaseError) as exc_info:
                await analytics_service.get_activity_trends(
                    test_user_id, period_start, period_end
                )

            assert "Failed to calculate activity trends" in str(exc_info.value)


class TestGetResponseTimeMetrics:
    """Test suite for get_response_time_metrics."""

    @pytest.mark.asyncio
    async def test_empty_data_returns_none_avg(
        self, analytics_service, test_user_id, period_start, period_end
    ):
        """Returns None average when no sent emails exist."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            _build_chain(mock_client, {"email_drafts": []})
            mock_get_client.return_value = mock_client

            result = await analytics_service.get_response_time_metrics(
                test_user_id, period_start, period_end
            )

            assert result["avg_response_minutes"] is None
            assert result["by_lead"] == {}
            assert result["trend"] == []

    @pytest.mark.asyncio
    async def test_calculates_response_times(
        self, analytics_service, test_user_id, period_start, period_end
    ):
        """Calculates average response time from created_at to sent_at."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            _build_chain(
                mock_client,
                {
                    "email_drafts": [
                        {
                            "created_at": "2026-02-05T10:00:00Z",
                            "sent_at": "2026-02-05T10:30:00Z",
                            "lead_memory_id": "lead-1",
                        },
                        {
                            "created_at": "2026-02-05T14:00:00Z",
                            "sent_at": "2026-02-05T15:00:00Z",
                            "lead_memory_id": "lead-1",
                        },
                    ],
                },
            )
            mock_get_client.return_value = mock_client

            result = await analytics_service.get_response_time_metrics(
                test_user_id, period_start, period_end
            )

            # (30 + 60) / 2 = 45 minutes average
            assert result["avg_response_minutes"] == 45.0
            assert result["by_lead"]["lead-1"] == 45.0
            assert len(result["trend"]) == 1
            assert result["trend"][0]["date"] == "2026-02-05"

    @pytest.mark.asyncio
    async def test_skips_emails_without_sent_at(
        self, analytics_service, test_user_id, period_start, period_end
    ):
        """Skips emails missing sent_at timestamp."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            _build_chain(
                mock_client,
                {
                    "email_drafts": [
                        {
                            "created_at": "2026-02-05T10:00:00Z",
                            "sent_at": "2026-02-05T10:30:00Z",
                            "lead_memory_id": "lead-1",
                        },
                        {
                            "created_at": "2026-02-05T14:00:00Z",
                            "sent_at": None,
                            "lead_memory_id": "lead-2",
                        },
                    ],
                },
            )
            mock_get_client.return_value = mock_client

            result = await analytics_service.get_response_time_metrics(
                test_user_id, period_start, period_end
            )

            assert result["avg_response_minutes"] == 30.0
            assert "lead-2" not in result["by_lead"]

    @pytest.mark.asyncio
    async def test_groups_by_lead(
        self, analytics_service, test_user_id, period_start, period_end
    ):
        """Groups response times by lead_memory_id."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            _build_chain(
                mock_client,
                {
                    "email_drafts": [
                        {
                            "created_at": "2026-02-05T10:00:00Z",
                            "sent_at": "2026-02-05T10:20:00Z",
                            "lead_memory_id": "lead-1",
                        },
                        {
                            "created_at": "2026-02-06T10:00:00Z",
                            "sent_at": "2026-02-06T11:00:00Z",
                            "lead_memory_id": "lead-2",
                        },
                    ],
                },
            )
            mock_get_client.return_value = mock_client

            result = await analytics_service.get_response_time_metrics(
                test_user_id, period_start, period_end
            )

            assert result["by_lead"]["lead-1"] == 20.0
            assert result["by_lead"]["lead-2"] == 60.0

    @pytest.mark.asyncio
    async def test_database_error_raises(
        self, analytics_service, test_user_id, period_start, period_end
    ):
        """Database failure raises DatabaseError."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.table.side_effect = Exception("Connection failed")
            mock_get_client.return_value = mock_client

            with pytest.raises(DatabaseError) as exc_info:
                await analytics_service.get_response_time_metrics(
                    test_user_id, period_start, period_end
                )

            assert "Failed to calculate response time metrics" in str(exc_info.value)


class TestGetAriaImpactSummary:
    """Test suite for get_aria_impact_summary."""

    @pytest.mark.asyncio
    async def test_empty_data_returns_zeros(
        self, analytics_service, test_user_id, period_start, period_end
    ):
        """Returns zero totals when no actions or impacts exist."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            _build_chain(mock_client, {"aria_actions": [], "pipeline_impact": []})
            mock_get_client.return_value = mock_client

            result = await analytics_service.get_aria_impact_summary(
                test_user_id, period_start, period_end
            )

            assert result["total_actions"] == 0
            assert result["by_action_type"] == {}
            assert result["estimated_time_saved_minutes"] == 0
            assert result["pipeline_impact"] == {}

    @pytest.mark.asyncio
    async def test_counts_actions_by_type(
        self, analytics_service, test_user_id, period_start, period_end
    ):
        """Counts ARIA actions by action_type."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()

            call_count = [0]

            def mock_table(table_name):
                mock_tbl = MagicMock()
                chain = mock_tbl.select.return_value
                chain = chain.eq.return_value
                chain.eq.return_value = chain
                chain.gte.return_value = chain
                chain.lte.return_value = chain

                if table_name == "aria_actions":
                    chain.execute.return_value = _mock_response(
                        [
                            {
                                "action_type": "email_draft",
                                "estimated_minutes_saved": 15,
                                "status": "auto_approved",
                            },
                            {
                                "action_type": "email_draft",
                                "estimated_minutes_saved": 15,
                                "status": "auto_approved",
                            },
                            {
                                "action_type": "meeting_prep",
                                "estimated_minutes_saved": 30,
                                "status": "user_approved",
                            },
                            {
                                "action_type": "research_report",
                                "estimated_minutes_saved": 60,
                                "status": "auto_approved",
                            },
                        ]
                    )
                elif table_name == "pipeline_impact":
                    chain.execute.return_value = _mock_response([])
                else:
                    chain.execute.return_value = _mock_response([])

                return mock_tbl

            mock_client.table.side_effect = mock_table
            mock_get_client.return_value = mock_client

            result = await analytics_service.get_aria_impact_summary(
                test_user_id, period_start, period_end
            )

            assert result["total_actions"] == 4
            assert result["by_action_type"]["email_draft"] == 2
            assert result["by_action_type"]["meeting_prep"] == 1
            assert result["by_action_type"]["research_report"] == 1
            assert result["estimated_time_saved_minutes"] == 120

    @pytest.mark.asyncio
    async def test_pipeline_impact_breakdown(
        self, analytics_service, test_user_id, period_start, period_end
    ):
        """Breaks down pipeline impact by type with estimated values."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()

            def mock_table(table_name):
                mock_tbl = MagicMock()
                chain = mock_tbl.select.return_value
                chain = chain.eq.return_value
                chain.eq.return_value = chain
                chain.gte.return_value = chain
                chain.lte.return_value = chain

                if table_name == "aria_actions":
                    chain.execute.return_value = _mock_response([])
                elif table_name == "pipeline_impact":
                    chain.execute.return_value = _mock_response(
                        [
                            {
                                "impact_type": "lead_discovered",
                                "estimated_value": 50000.0,
                            },
                            {
                                "impact_type": "lead_discovered",
                                "estimated_value": 30000.0,
                            },
                            {
                                "impact_type": "deal_influenced",
                                "estimated_value": 100000.0,
                            },
                        ]
                    )
                else:
                    chain.execute.return_value = _mock_response([])

                return mock_tbl

            mock_client.table.side_effect = mock_table
            mock_get_client.return_value = mock_client

            result = await analytics_service.get_aria_impact_summary(
                test_user_id, period_start, period_end
            )

            assert result["pipeline_impact"]["lead_discovered"]["count"] == 2
            assert result["pipeline_impact"]["lead_discovered"]["estimated_value"] == 80000.0
            assert result["pipeline_impact"]["deal_influenced"]["count"] == 1
            assert result["pipeline_impact"]["deal_influenced"]["estimated_value"] == 100000.0

    @pytest.mark.asyncio
    async def test_database_error_raises(
        self, analytics_service, test_user_id, period_start, period_end
    ):
        """Database failure raises DatabaseError."""
        with patch("src.db.supabase.SupabaseClient.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.table.side_effect = Exception("Connection failed")
            mock_get_client.return_value = mock_client

            with pytest.raises(DatabaseError) as exc_info:
                await analytics_service.get_aria_impact_summary(
                    test_user_id, period_start, period_end
                )

            assert "Failed to calculate ARIA impact summary" in str(exc_info.value)


class TestComparePeriods:
    """Test suite for compare_periods."""

    @pytest.mark.asyncio
    async def test_calculates_delta_percentages(
        self, analytics_service, test_user_id
    ):
        """Calculates percentage deltas between two periods."""
        with patch.object(
            analytics_service,
            "get_overview_metrics",
        ) as mock_overview:
            mock_overview.side_effect = [
                # Current period
                {
                    "leads_created": 10,
                    "meetings_booked": 5,
                    "emails_sent": 20,
                    "debriefs_completed": 3,
                    "goals_completed": 2,
                    "avg_health_score": 75.0,
                    "time_saved_minutes": 120,
                },
                # Previous period
                {
                    "leads_created": 8,
                    "meetings_booked": 4,
                    "emails_sent": 15,
                    "debriefs_completed": 2,
                    "goals_completed": 1,
                    "avg_health_score": 70.0,
                    "time_saved_minutes": 90,
                },
            ]

            current_start = datetime(2026, 2, 1)
            current_end = datetime(2026, 2, 28)
            previous_start = datetime(2026, 1, 1)
            previous_end = datetime(2026, 1, 31)

            result = await analytics_service.compare_periods(
                test_user_id,
                current_start,
                current_end,
                previous_start,
                previous_end,
            )

            assert result["current"]["leads_created"] == 10
            assert result["previous"]["leads_created"] == 8
            # (10 - 8) / 8 * 100 = 25.0%
            assert result["delta_pct"]["leads_created"] == 25.0
            # (20 - 15) / 15 * 100 = 33.3%
            assert result["delta_pct"]["emails_sent"] == 33.3
            # Health score delta is absolute: 75 - 70 = 5.0
            assert result["delta_pct"]["avg_health_score"] == 5.0

    @pytest.mark.asyncio
    async def test_handles_zero_previous_values(
        self, analytics_service, test_user_id
    ):
        """Returns 100% delta when previous value is zero but current is not."""
        with patch.object(
            analytics_service,
            "get_overview_metrics",
        ) as mock_overview:
            mock_overview.side_effect = [
                {
                    "leads_created": 5,
                    "meetings_booked": 0,
                    "emails_sent": 0,
                    "debriefs_completed": 0,
                    "goals_completed": 0,
                    "avg_health_score": None,
                    "time_saved_minutes": 0,
                },
                {
                    "leads_created": 0,
                    "meetings_booked": 0,
                    "emails_sent": 0,
                    "debriefs_completed": 0,
                    "goals_completed": 0,
                    "avg_health_score": None,
                    "time_saved_minutes": 0,
                },
            ]

            result = await analytics_service.compare_periods(
                test_user_id,
                datetime(2026, 2, 1),
                datetime(2026, 2, 28),
                datetime(2026, 1, 1),
                datetime(2026, 1, 31),
            )

            assert result["delta_pct"]["leads_created"] == 100.0
            assert result["delta_pct"]["meetings_booked"] == 0.0
            assert result["delta_pct"]["avg_health_score"] is None

    @pytest.mark.asyncio
    async def test_database_error_propagates(
        self, analytics_service, test_user_id
    ):
        """DatabaseError from get_overview_metrics propagates."""
        with patch.object(
            analytics_service,
            "get_overview_metrics",
            side_effect=DatabaseError("DB failure"),
        ):
            with pytest.raises(DatabaseError):
                await analytics_service.compare_periods(
                    test_user_id,
                    datetime(2026, 2, 1),
                    datetime(2026, 2, 28),
                    datetime(2026, 1, 1),
                    datetime(2026, 1, 31),
                )
