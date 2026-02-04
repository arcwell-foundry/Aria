"""Tests for Lead Pattern Detection module (US-516)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest


class TestLeadPatternDetectorImport:
    """Tests for module imports."""

    def test_lead_pattern_detector_can_be_imported(self) -> None:
        """Test LeadPatternDetector class is importable."""
        from src.memory.lead_patterns import LeadPatternDetector

        assert LeadPatternDetector is not None

    def test_lead_pattern_types_can_be_imported(self) -> None:
        """Test pattern type dataclasses are importable."""
        from src.memory.lead_patterns import (
            ClosingTimePattern,
            EngagementPattern,
            ObjectionPattern,
            SilentLead,
        )

        assert ClosingTimePattern is not None
        assert ObjectionPattern is not None
        assert EngagementPattern is not None
        assert SilentLead is not None


class TestAvgTimeToCloseBySegment:
    """Tests for avg_time_to_close_by_segment method."""

    @pytest.fixture
    def mock_supabase(self) -> MagicMock:
        """Create a mocked Supabase client."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_closed_leads(
        self, mock_supabase: MagicMock
    ) -> None:
        """Test returns empty list when no closed leads exist."""
        from src.memory.lead_patterns import LeadPatternDetector

        mock_response = MagicMock()
        mock_response.data = []
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = (
            mock_response
        )

        detector = LeadPatternDetector(db_client=mock_supabase)
        patterns = await detector.avg_time_to_close_by_segment(company_id="company-123")

        assert patterns == []

    @pytest.mark.asyncio
    async def test_calculates_avg_time_by_segment(
        self, mock_supabase: MagicMock
    ) -> None:
        """Test correctly calculates average time to close by segment."""
        from src.memory.lead_patterns import LeadPatternDetector

        now = datetime.now(UTC)
        # Two enterprise leads: 30 days and 60 days to close
        mock_response = MagicMock()
        mock_response.data = [
            {
                "id": "lead-1",
                "first_touch_at": (now - timedelta(days=30)).isoformat(),
                "updated_at": now.isoformat(),
                "tags": ["enterprise"],
            },
            {
                "id": "lead-2",
                "first_touch_at": (now - timedelta(days=60)).isoformat(),
                "updated_at": now.isoformat(),
                "tags": ["enterprise"],
            },
            {
                "id": "lead-3",
                "first_touch_at": (now - timedelta(days=14)).isoformat(),
                "updated_at": now.isoformat(),
                "tags": ["smb"],
            },
        ]
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = (
            mock_response
        )

        detector = LeadPatternDetector(db_client=mock_supabase)
        patterns = await detector.avg_time_to_close_by_segment(company_id="company-123")

        assert len(patterns) == 2
        enterprise = next(p for p in patterns if p.segment == "enterprise")
        smb = next(p for p in patterns if p.segment == "smb")
        assert enterprise.avg_days_to_close == 45.0  # (30 + 60) / 2
        assert enterprise.sample_size == 2
        assert smb.avg_days_to_close == 14.0
        assert smb.sample_size == 1

    @pytest.mark.asyncio
    async def test_handles_leads_without_tags(
        self, mock_supabase: MagicMock
    ) -> None:
        """Test leads without tags are grouped as 'untagged'."""
        from src.memory.lead_patterns import LeadPatternDetector

        now = datetime.now(UTC)
        mock_response = MagicMock()
        mock_response.data = [
            {
                "id": "lead-1",
                "first_touch_at": (now - timedelta(days=20)).isoformat(),
                "updated_at": now.isoformat(),
                "tags": [],
            },
        ]
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = (
            mock_response
        )

        detector = LeadPatternDetector(db_client=mock_supabase)
        patterns = await detector.avg_time_to_close_by_segment(company_id="company-123")

        assert len(patterns) == 1
        assert patterns[0].segment == "untagged"
        assert patterns[0].avg_days_to_close == 20.0
