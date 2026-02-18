# backend/tests/test_meeting_brief_graph.py
"""Tests for graph-enriched meeting briefs."""

from unittest.mock import MagicMock, patch

import pytest

from src.services.meeting_brief import MeetingBriefService


def _mock_db_chain(data: list | dict | None = None) -> MagicMock:
    """Build a chainable Supabase mock."""
    chain = MagicMock()
    for method in ("select", "eq", "gte", "lte", "order", "limit", "single", "insert", "update", "upsert"):
        getattr(chain, method).return_value = chain
    chain.execute.return_value = MagicMock(data=data)
    return chain


def _make_entity_context(entity_id: str) -> MagicMock:
    ctx = MagicMock()
    ctx.entity_id = entity_id
    ctx.direct_facts = [MagicMock(content=f"{entity_id} is expanding in oncology")]
    ctx.relationships = [MagicMock(content=f"{entity_id} partners with Roche")]
    ctx.recent_interactions = [MagicMock(content=f"Called {entity_id} VP last week")]
    return ctx


class TestMeetingBriefGraphIntelligence:
    """Tests that meeting briefs include graph context."""

    @pytest.mark.asyncio
    async def test_build_brief_context_includes_relationship_intelligence(self) -> None:
        """Brief context should include graph relationship data when available."""
        with patch("src.services.meeting_brief.SupabaseClient") as mock_db_cls:
            mock_db = MagicMock()
            mock_db.table.return_value = _mock_db_chain()
            mock_db_cls.get_client.return_value = mock_db

            service = MeetingBriefService()

            brief = {
                "meeting_title": "Q3 Pipeline Review",
                "meeting_time": "2026-02-20T14:00:00Z",
                "attendees": ["john@biogenix.com"],
            }
            attendee_profiles = {
                "john@biogenix.com": {
                    "name": "John Smith",
                    "title": "VP Sales",
                    "company": "BioGenix",
                },
            }
            company_signals = [
                {"company_name": "BioGenix", "headline": "New funding round"},
            ]
            graph_contexts = {
                "BioGenix": _make_entity_context("BioGenix"),
                "John Smith": _make_entity_context("John Smith"),
            }

            context = service._build_brief_context(
                brief, attendee_profiles, company_signals, graph_contexts
            )

            assert "Relationship Intelligence" in context
            assert "BioGenix" in context
            assert "partners with Roche" in context or "expanding in oncology" in context

    @pytest.mark.asyncio
    async def test_build_brief_context_works_without_graph(self) -> None:
        """Brief context should work when no graph data is available."""
        with patch("src.services.meeting_brief.SupabaseClient") as mock_db_cls:
            mock_db = MagicMock()
            mock_db.table.return_value = _mock_db_chain()
            mock_db_cls.get_client.return_value = mock_db

            service = MeetingBriefService()

            brief = {
                "meeting_title": "Sync",
                "meeting_time": "2026-02-20T14:00:00Z",
                "attendees": [],
            }

            context = service._build_brief_context(brief, {}, [], {})

            assert "Meeting Title: Sync" in context
            # Should not have graph section when no graph data
            assert "Relationship Intelligence" not in context
