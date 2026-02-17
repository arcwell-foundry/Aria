"""Tests for ActivityFeedService.

Tests cover:
- get_activity_feed: paginated feed with entity detail enrichment
- get_real_time_updates: polling-based updates since timestamp
- create_activity: standardized activity type recording
- get_activity_stats: summary counts by type and period
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_USER_ID = "user-abc-123"

ACTIVITY_TYPES = [
    "email_drafted",
    "meeting_prepped",
    "lead_discovered",
    "goal_updated",
    "signal_detected",
    "debrief_processed",
    "briefing_generated",
    "score_calculated",
]


def _mock_db() -> MagicMock:
    """Create a mock Supabase client."""
    return MagicMock()


def _chain(mock: MagicMock, data: list[dict[str, Any]]) -> MagicMock:
    """Make a fluent mock chain return data on .execute()."""
    execute_result = MagicMock()
    execute_result.data = data
    execute_result.count = len(data)
    mock.execute.return_value = execute_result
    for method in (
        "select",
        "eq",
        "in_",
        "order",
        "limit",
        "offset",
        "insert",
        "update",
        "upsert",
        "maybe_single",
        "single",
        "gte",
        "lte",
        "gt",
        "or_",
        "range",
    ):
        getattr(mock, method, lambda *a, **kw: mock).return_value = mock  # noqa: ARG005
    mock.execute.return_value = execute_result
    return mock


def _make_activity(
    activity_id: str = "act-1",
    activity_type: str = "email_drafted",
    agent: str = "scribe",
    title: str = "Drafted email to John",
    related_entity_type: str | None = None,
    related_entity_id: str | None = None,
    created_at: str = "2026-02-17T10:00:00Z",
) -> dict[str, Any]:
    return {
        "id": activity_id,
        "user_id": SAMPLE_USER_ID,
        "agent": agent,
        "activity_type": activity_type,
        "title": title,
        "description": "Some description",
        "reasoning": "Because it was needed",
        "confidence": 0.8,
        "related_entity_type": related_entity_type,
        "related_entity_id": related_entity_id,
        "metadata": {},
        "created_at": created_at,
    }


def _make_service(db: MagicMock) -> Any:
    """Create an ActivityFeedService with a mocked DB."""
    from src.services.activity_feed_service import ActivityFeedService

    with patch("src.services.activity_feed_service.SupabaseClient") as mock_sb:
        mock_sb.get_client.return_value = db
        service = ActivityFeedService()
        service._db = db
    return service


# ---------------------------------------------------------------------------
# get_activity_feed tests
# ---------------------------------------------------------------------------


class TestGetActivityFeed:
    """Test ActivityFeedService.get_activity_feed."""

    @pytest.mark.asyncio
    async def test_returns_paginated_results(self) -> None:
        db = _mock_db()
        mock_table = MagicMock()
        activities = [
            _make_activity("act-1", created_at="2026-02-17T10:00:00Z"),
            _make_activity("act-2", created_at="2026-02-17T09:00:00Z"),
        ]
        _chain(mock_table, activities)
        db.table = lambda _: mock_table

        service = _make_service(db)
        result = await service.get_activity_feed(
            user_id=SAMPLE_USER_ID,
            page=1,
            page_size=20,
        )

        assert "activities" in result
        assert "total_count" in result
        assert "page" in result
        assert "page_size" in result
        assert len(result["activities"]) == 2
        assert result["page"] == 1
        assert result["page_size"] == 20

    @pytest.mark.asyncio
    async def test_filters_by_activity_type(self) -> None:
        db = _mock_db()
        mock_table = MagicMock()
        activities = [_make_activity(activity_type="email_drafted")]
        _chain(mock_table, activities)
        db.table = lambda _: mock_table

        service = _make_service(db)
        result = await service.get_activity_feed(
            user_id=SAMPLE_USER_ID,
            filters={"activity_type": "email_drafted"},
        )

        assert len(result["activities"]) == 1
        assert result["activities"][0]["activity_type"] == "email_drafted"

    @pytest.mark.asyncio
    async def test_filters_by_agent(self) -> None:
        db = _mock_db()
        mock_table = MagicMock()
        activities = [_make_activity(agent="hunter")]
        _chain(mock_table, activities)
        db.table = lambda _: mock_table

        service = _make_service(db)
        result = await service.get_activity_feed(
            user_id=SAMPLE_USER_ID,
            filters={"agent": "hunter"},
        )

        assert len(result["activities"]) == 1
        assert result["activities"][0]["agent"] == "hunter"

    @pytest.mark.asyncio
    async def test_filters_by_related_entity_type(self) -> None:
        db = _mock_db()
        mock_table = MagicMock()
        activities = [
            _make_activity(related_entity_type="lead", related_entity_id="lead-1")
        ]
        _chain(mock_table, activities)
        db.table = lambda _: mock_table

        service = _make_service(db)
        result = await service.get_activity_feed(
            user_id=SAMPLE_USER_ID,
            filters={"related_entity_type": "lead"},
        )

        assert len(result["activities"]) == 1
        assert result["activities"][0]["related_entity_type"] == "lead"

    @pytest.mark.asyncio
    async def test_filters_by_date_range(self) -> None:
        db = _mock_db()
        mock_table = MagicMock()
        activities = [_make_activity(created_at="2026-02-17T10:00:00Z")]
        _chain(mock_table, activities)
        db.table = lambda _: mock_table

        service = _make_service(db)
        result = await service.get_activity_feed(
            user_id=SAMPLE_USER_ID,
            filters={
                "date_start": "2026-02-17T00:00:00Z",
                "date_end": "2026-02-17T23:59:59Z",
            },
        )

        assert len(result["activities"]) == 1

    @pytest.mark.asyncio
    async def test_empty_feed(self) -> None:
        db = _mock_db()
        mock_table = MagicMock()
        _chain(mock_table, [])
        db.table = lambda _: mock_table

        service = _make_service(db)
        result = await service.get_activity_feed(user_id=SAMPLE_USER_ID)

        assert result["activities"] == []
        assert result["total_count"] == 0

    @pytest.mark.asyncio
    async def test_pagination_offset_calculation(self) -> None:
        """Page 2 with page_size 10 should offset by 10."""
        db = _mock_db()
        mock_table = MagicMock()
        activities = [_make_activity("act-11")]
        _chain(mock_table, activities)
        db.table = lambda _: mock_table

        service = _make_service(db)
        result = await service.get_activity_feed(
            user_id=SAMPLE_USER_ID,
            page=2,
            page_size=10,
        )

        assert result["page"] == 2
        assert result["page_size"] == 10
        # The service should have called .range(10, 19) for page 2
        mock_table.range.assert_called_with(10, 19)

    @pytest.mark.asyncio
    async def test_enriches_entity_details_for_leads(self) -> None:
        """Activities with related_entity_type=lead should include lead name."""
        db = _mock_db()

        # Activity table mock
        activity_table = MagicMock()
        activities = [
            _make_activity(
                related_entity_type="lead",
                related_entity_id="lead-1",
            )
        ]
        _chain(activity_table, activities)

        # Lead lookup mock
        lead_table = MagicMock()
        lead_result = MagicMock()
        lead_result.data = {"id": "lead-1", "company_name": "Acme Bio"}
        lead_table.select.return_value = lead_table
        lead_table.eq.return_value = lead_table
        lead_table.maybe_single.return_value = lead_table
        lead_table.execute.return_value = lead_result

        def table_router(name: str) -> MagicMock:
            if name == "lead_memory":
                return lead_table
            return activity_table

        db.table = table_router

        service = _make_service(db)
        result = await service.get_activity_feed(user_id=SAMPLE_USER_ID)

        assert result["activities"][0]["entity_details"] == {
            "entity_name": "Acme Bio",
        }

    @pytest.mark.asyncio
    async def test_enriches_entity_details_for_goals(self) -> None:
        """Activities with related_entity_type=goal should include goal title."""
        db = _mock_db()

        activity_table = MagicMock()
        activities = [
            _make_activity(
                related_entity_type="goal",
                related_entity_id="goal-1",
            )
        ]
        _chain(activity_table, activities)

        goal_table = MagicMock()
        goal_result = MagicMock()
        goal_result.data = {"id": "goal-1", "title": "Close Lonza deal"}
        goal_table.select.return_value = goal_table
        goal_table.eq.return_value = goal_table
        goal_table.maybe_single.return_value = goal_table
        goal_table.execute.return_value = goal_result

        def table_router(name: str) -> MagicMock:
            if name == "goals":
                return goal_table
            return activity_table

        db.table = table_router

        service = _make_service(db)
        result = await service.get_activity_feed(user_id=SAMPLE_USER_ID)

        assert result["activities"][0]["entity_details"] == {
            "entity_name": "Close Lonza deal",
        }


# ---------------------------------------------------------------------------
# get_real_time_updates tests
# ---------------------------------------------------------------------------


class TestGetRealTimeUpdates:
    """Test ActivityFeedService.get_real_time_updates."""

    @pytest.mark.asyncio
    async def test_returns_activities_since_timestamp(self) -> None:
        db = _mock_db()
        mock_table = MagicMock()
        since = "2026-02-17T09:00:00Z"
        activities = [
            _make_activity("act-new", created_at="2026-02-17T09:30:00Z"),
        ]
        _chain(mock_table, activities)
        db.table = lambda _: mock_table

        service = _make_service(db)
        result = await service.get_real_time_updates(
            user_id=SAMPLE_USER_ID,
            since_timestamp=since,
        )

        assert len(result) == 1
        assert result[0]["id"] == "act-new"
        # Should use gt (greater than) on created_at
        mock_table.gt.assert_called_with("created_at", since)

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_new_activities(self) -> None:
        db = _mock_db()
        mock_table = MagicMock()
        _chain(mock_table, [])
        db.table = lambda _: mock_table

        service = _make_service(db)
        result = await service.get_real_time_updates(
            user_id=SAMPLE_USER_ID,
            since_timestamp="2026-02-17T12:00:00Z",
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_orders_by_created_at_ascending(self) -> None:
        """Real-time updates should be in chronological order (oldest first)."""
        db = _mock_db()
        mock_table = MagicMock()
        activities = [
            _make_activity("act-1", created_at="2026-02-17T09:10:00Z"),
            _make_activity("act-2", created_at="2026-02-17T09:20:00Z"),
        ]
        _chain(mock_table, activities)
        db.table = lambda _: mock_table

        service = _make_service(db)
        result = await service.get_real_time_updates(
            user_id=SAMPLE_USER_ID,
            since_timestamp="2026-02-17T09:00:00Z",
        )

        assert len(result) == 2
        # Verify ascending order was requested
        mock_table.order.assert_called_with("created_at", desc=False)

    @pytest.mark.asyncio
    async def test_limits_results(self) -> None:
        """Should cap results to prevent excessive data transfer."""
        db = _mock_db()
        mock_table = MagicMock()
        _chain(mock_table, [])
        db.table = lambda _: mock_table

        service = _make_service(db)
        await service.get_real_time_updates(
            user_id=SAMPLE_USER_ID,
            since_timestamp="2026-02-17T09:00:00Z",
        )

        mock_table.limit.assert_called_with(100)


# ---------------------------------------------------------------------------
# create_activity tests
# ---------------------------------------------------------------------------


class TestCreateActivity:
    """Test ActivityFeedService.create_activity."""

    @pytest.mark.asyncio
    async def test_creates_activity_record(self) -> None:
        db = _mock_db()
        mock_table = MagicMock()
        created = _make_activity(
            activity_type="email_drafted",
            agent="scribe",
            title="Drafted follow-up to Dr. Smith",
        )
        _chain(mock_table, [created])
        db.table = lambda _: mock_table

        service = _make_service(db)
        result = await service.create_activity(
            user_id=SAMPLE_USER_ID,
            activity_type="email_drafted",
            title="Drafted follow-up to Dr. Smith",
            description="Follow-up after conference",
            agent="scribe",
        )

        assert result["id"] == "act-1"
        assert result["activity_type"] == "email_drafted"
        mock_table.insert.assert_called_once()

    @pytest.mark.asyncio
    async def test_creates_with_related_entity(self) -> None:
        db = _mock_db()
        mock_table = MagicMock()
        created = _make_activity(
            related_entity_type="lead",
            related_entity_id="lead-1",
        )
        _chain(mock_table, [created])
        db.table = lambda _: mock_table

        service = _make_service(db)
        result = await service.create_activity(
            user_id=SAMPLE_USER_ID,
            activity_type="lead_discovered",
            title="Discovered new lead: Acme Bio",
            agent="hunter",
            related_entity_type="lead",
            related_entity_id="lead-1",
        )

        assert result["related_entity_type"] == "lead"
        assert result["related_entity_id"] == "lead-1"

    @pytest.mark.asyncio
    async def test_creates_with_metadata(self) -> None:
        db = _mock_db()
        mock_table = MagicMock()
        created = _make_activity()
        created["metadata"] = {"score": 85.5}
        _chain(mock_table, [created])
        db.table = lambda _: mock_table

        service = _make_service(db)
        result = await service.create_activity(
            user_id=SAMPLE_USER_ID,
            activity_type="score_calculated",
            title="Scored lead",
            agent="analyst",
            metadata={"score": 85.5},
        )

        assert result["metadata"] == {"score": 85.5}

    @pytest.mark.asyncio
    async def test_standardized_activity_types_are_defined(self) -> None:
        """The service should define STANDARD_ACTIVITY_TYPES."""
        from src.services.activity_feed_service import STANDARD_ACTIVITY_TYPES

        for activity_type in ACTIVITY_TYPES:
            assert activity_type in STANDARD_ACTIVITY_TYPES


# ---------------------------------------------------------------------------
# get_activity_stats tests
# ---------------------------------------------------------------------------


class TestGetActivityStats:
    """Test ActivityFeedService.get_activity_stats."""

    @pytest.mark.asyncio
    async def test_returns_counts_by_type(self) -> None:
        db = _mock_db()
        mock_table = MagicMock()
        activities = [
            _make_activity("a1", activity_type="email_drafted"),
            _make_activity("a2", activity_type="email_drafted"),
            _make_activity("a3", activity_type="lead_discovered"),
            _make_activity("a4", activity_type="signal_detected"),
        ]
        _chain(mock_table, activities)
        db.table = lambda _: mock_table

        service = _make_service(db)
        result = await service.get_activity_stats(
            user_id=SAMPLE_USER_ID,
            period="day",
        )

        assert "by_type" in result
        assert result["by_type"]["email_drafted"] == 2
        assert result["by_type"]["lead_discovered"] == 1
        assert result["by_type"]["signal_detected"] == 1

    @pytest.mark.asyncio
    async def test_returns_total_count(self) -> None:
        db = _mock_db()
        mock_table = MagicMock()
        activities = [
            _make_activity("a1"),
            _make_activity("a2"),
            _make_activity("a3"),
        ]
        _chain(mock_table, activities)
        db.table = lambda _: mock_table

        service = _make_service(db)
        result = await service.get_activity_stats(
            user_id=SAMPLE_USER_ID,
            period="day",
        )

        assert result["total"] == 3

    @pytest.mark.asyncio
    async def test_returns_counts_by_agent(self) -> None:
        db = _mock_db()
        mock_table = MagicMock()
        activities = [
            _make_activity("a1", agent="hunter"),
            _make_activity("a2", agent="hunter"),
            _make_activity("a3", agent="scribe"),
        ]
        _chain(mock_table, activities)
        db.table = lambda _: mock_table

        service = _make_service(db)
        result = await service.get_activity_stats(
            user_id=SAMPLE_USER_ID,
            period="day",
        )

        assert "by_agent" in result
        assert result["by_agent"]["hunter"] == 2
        assert result["by_agent"]["scribe"] == 1

    @pytest.mark.asyncio
    async def test_period_day_filters_last_24_hours(self) -> None:
        db = _mock_db()
        mock_table = MagicMock()
        _chain(mock_table, [])
        db.table = lambda _: mock_table

        service = _make_service(db)
        await service.get_activity_stats(
            user_id=SAMPLE_USER_ID,
            period="day",
        )

        # Should have called gte with a timestamp ~24h ago
        mock_table.gte.assert_called_once()
        call_args = mock_table.gte.call_args
        assert call_args[0][0] == "created_at"

    @pytest.mark.asyncio
    async def test_period_week_filters_last_7_days(self) -> None:
        db = _mock_db()
        mock_table = MagicMock()
        _chain(mock_table, [])
        db.table = lambda _: mock_table

        service = _make_service(db)
        await service.get_activity_stats(
            user_id=SAMPLE_USER_ID,
            period="week",
        )

        mock_table.gte.assert_called_once()
        call_args = mock_table.gte.call_args
        assert call_args[0][0] == "created_at"

    @pytest.mark.asyncio
    async def test_period_month_filters_last_30_days(self) -> None:
        db = _mock_db()
        mock_table = MagicMock()
        _chain(mock_table, [])
        db.table = lambda _: mock_table

        service = _make_service(db)
        await service.get_activity_stats(
            user_id=SAMPLE_USER_ID,
            period="month",
        )

        mock_table.gte.assert_called_once()
        call_args = mock_table.gte.call_args
        assert call_args[0][0] == "created_at"

    @pytest.mark.asyncio
    async def test_empty_stats(self) -> None:
        db = _mock_db()
        mock_table = MagicMock()
        _chain(mock_table, [])
        db.table = lambda _: mock_table

        service = _make_service(db)
        result = await service.get_activity_stats(
            user_id=SAMPLE_USER_ID,
            period="day",
        )

        assert result["total"] == 0
        assert result["by_type"] == {}
        assert result["by_agent"] == {}
        assert "period" in result
