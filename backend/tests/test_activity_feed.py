"""Tests for US-940 Activity Feed / Command Center."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.models.activity import (
    ActivityCreate,
    ActivityFilter,
    ActivityItem,
)

# ------------------------------------------------------------------ #
# Model tests                                                         #
# ------------------------------------------------------------------ #


class TestActivityModels:
    """Test Pydantic model validation."""

    def test_activity_create_valid(self) -> None:
        ac = ActivityCreate(
            agent="hunter",
            activity_type="research_complete",
            title="Researched Acme Bio",
            description="Found 3 key contacts",
            reasoning="Company matched ICP criteria",
            confidence=0.85,
            related_entity_type="lead",
            related_entity_id="abc-123",
            metadata={"source": "web"},
        )
        assert ac.agent == "hunter"
        assert ac.activity_type == "research_complete"
        assert ac.title == "Researched Acme Bio"
        assert ac.confidence == 0.85
        assert ac.metadata == {"source": "web"}

    def test_activity_create_minimal(self) -> None:
        ac = ActivityCreate(activity_type="note", title="Quick note")
        assert ac.agent is None
        assert ac.description == ""
        assert ac.reasoning == ""
        assert ac.confidence == 0.5
        assert ac.related_entity_type is None
        assert ac.related_entity_id is None
        assert ac.metadata == {}

    def test_activity_create_rejects_empty_title(self) -> None:
        with pytest.raises(ValueError):
            ActivityCreate(activity_type="note", title="")

    def test_activity_create_rejects_empty_type(self) -> None:
        with pytest.raises(ValueError):
            ActivityCreate(activity_type="", title="Some title")

    def test_activity_create_clamps_confidence(self) -> None:
        with pytest.raises(ValueError):
            ActivityCreate(activity_type="note", title="Test", confidence=1.5)
        with pytest.raises(ValueError):
            ActivityCreate(activity_type="note", title="Test", confidence=-0.1)

    def test_activity_filter_defaults(self) -> None:
        af = ActivityFilter()
        assert af.agent is None
        assert af.activity_type is None
        assert af.date_start is None
        assert af.date_end is None
        assert af.search is None
        assert af.limit == 50
        assert af.offset == 0

    def test_activity_filter_validates_limit(self) -> None:
        with pytest.raises(ValueError):
            ActivityFilter(limit=0)
        with pytest.raises(ValueError):
            ActivityFilter(limit=201)

    def test_activity_item_full(self) -> None:
        item = ActivityItem(
            id="act-1",
            user_id="user-1",
            agent="analyst",
            activity_type="insight_generated",
            title="Market Analysis Complete",
            description="Analyzed 5 competitors",
            reasoning="Used public financial data",
            confidence=0.9,
            related_entity_type="company",
            related_entity_id="comp-1",
            metadata={"competitors": 5},
            created_at="2026-02-08T00:00:00Z",
        )
        assert item.id == "act-1"
        assert item.agent == "analyst"
        assert item.confidence == 0.9
        assert item.metadata == {"competitors": 5}


# ------------------------------------------------------------------ #
# Service tests                                                       #
# ------------------------------------------------------------------ #


def _mock_db() -> MagicMock:
    """Create a mock Supabase client."""
    return MagicMock()


def _chain(mock: MagicMock, data: list[dict[str, Any]]) -> MagicMock:
    """Make a fluent mock chain return data on .execute()."""
    execute_result = MagicMock()
    execute_result.data = data
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
        "or_",
    ):
        getattr(mock, method, lambda *a, **kw: mock).return_value = mock  # noqa: ARG005
    mock.execute.return_value = execute_result
    return mock


class TestActivityServiceRecord:
    """Test ActivityService.record."""

    @pytest.mark.asyncio
    async def test_record_activity(self) -> None:
        from src.services.activity_service import ActivityService

        db = _mock_db()
        mock_table = MagicMock()
        inserted = {
            "id": "act-1",
            "user_id": "user-1",
            "agent": "hunter",
            "activity_type": "research_complete",
            "title": "Researched Acme",
            "description": "Found contacts",
            "reasoning": "ICP match",
            "confidence": 0.85,
            "related_entity_type": "lead",
            "related_entity_id": "lead-1",
            "metadata": {},
            "created_at": "2026-02-08T00:00:00Z",
        }
        _chain(mock_table, [inserted])
        db.table = lambda _: mock_table

        with patch("src.services.activity_service.SupabaseClient") as mock_sb:
            mock_sb.get_client.return_value = db
            service = ActivityService()
            service._db = db

            result = await service.record(
                user_id="user-1",
                agent="hunter",
                activity_type="research_complete",
                title="Researched Acme",
                description="Found contacts",
                reasoning="ICP match",
                confidence=0.85,
                related_entity_type="lead",
                related_entity_id="lead-1",
            )

        assert result["id"] == "act-1"
        assert result["agent"] == "hunter"
        assert result["activity_type"] == "research_complete"


class TestActivityServiceGetFeed:
    """Test ActivityService.get_feed."""

    @pytest.mark.asyncio
    async def test_get_feed_returns_data(self) -> None:
        from src.services.activity_service import ActivityService

        db = _mock_db()
        mock_table = MagicMock()
        feed_data = [
            {
                "id": "act-2",
                "user_id": "user-1",
                "agent": "analyst",
                "activity_type": "insight_generated",
                "title": "Market Analysis",
                "description": "Completed analysis",
                "reasoning": "",
                "confidence": 0.7,
                "related_entity_type": None,
                "related_entity_id": None,
                "metadata": {},
                "created_at": "2026-02-08T01:00:00Z",
            },
            {
                "id": "act-1",
                "user_id": "user-1",
                "agent": "hunter",
                "activity_type": "research_complete",
                "title": "Researched Acme",
                "description": "",
                "reasoning": "",
                "confidence": 0.85,
                "related_entity_type": "lead",
                "related_entity_id": "lead-1",
                "metadata": {},
                "created_at": "2026-02-08T00:00:00Z",
            },
        ]
        _chain(mock_table, feed_data)
        db.table = lambda _: mock_table

        with patch("src.services.activity_service.SupabaseClient"):
            service = ActivityService()
            service._db = db

            result = await service.get_feed("user-1")

        assert len(result) == 2
        assert result[0]["id"] == "act-2"
        assert result[1]["id"] == "act-1"

    @pytest.mark.asyncio
    async def test_get_feed_empty(self) -> None:
        from src.services.activity_service import ActivityService

        db = _mock_db()
        mock_table = MagicMock()
        _chain(mock_table, [])
        db.table = lambda _: mock_table

        with patch("src.services.activity_service.SupabaseClient"):
            service = ActivityService()
            service._db = db

            result = await service.get_feed("user-1")

        assert result == []


class TestActivityServiceAgentStatus:
    """Test ActivityService.get_agent_status."""

    @pytest.mark.asyncio
    async def test_agent_status_with_activity(self) -> None:
        from src.services.activity_service import ActivityService

        db = _mock_db()
        mock_table = MagicMock()
        rows = [
            {
                "agent": "hunter",
                "activity_type": "research_complete",
                "title": "Researched Acme",
                "created_at": "2026-02-08T01:00:00Z",
            },
            {
                "agent": "hunter",
                "activity_type": "lead_scored",
                "title": "Scored lead",
                "created_at": "2026-02-08T00:30:00Z",
            },
            {
                "agent": "analyst",
                "activity_type": "insight_generated",
                "title": "Market insight",
                "created_at": "2026-02-08T00:00:00Z",
            },
        ]
        _chain(mock_table, rows)
        db.table = lambda _: mock_table

        with patch("src.services.activity_service.SupabaseClient"):
            service = ActivityService()
            service._db = db

            result = await service.get_agent_status("user-1")

        # Hunter should have latest activity
        assert result["hunter"]["last_activity"] == "Researched Acme"
        assert result["hunter"]["last_activity_type"] == "research_complete"
        assert result["hunter"]["status"] == "idle"

        # Analyst should have its own latest
        assert result["analyst"]["last_activity"] == "Market insight"

        # All known agents should be present
        for agent_name in ("hunter", "analyst", "strategist", "scribe", "operator", "scout"):
            assert agent_name in result

        # Agents without activity should have None last_activity
        assert result["strategist"]["last_activity"] is None
        assert result["strategist"]["last_time"] is None
