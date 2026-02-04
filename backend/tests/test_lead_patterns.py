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


class TestCommonObjectionPatterns:
    """Tests for common_objection_patterns method."""

    @pytest.fixture
    def mock_supabase(self) -> MagicMock:
        """Create a mocked Supabase client."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_objections(
        self, mock_supabase: MagicMock
    ) -> None:
        """Test returns empty list when no objections exist."""
        from src.memory.lead_patterns import LeadPatternDetector

        mock_response = MagicMock()
        mock_response.data = []
        # Only one .eq() call now (insight_type filter only)
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = (
            mock_response
        )

        detector = LeadPatternDetector(db_client=mock_supabase)
        patterns = await detector.common_objection_patterns(company_id="company-123")

        assert patterns == []

    @pytest.mark.asyncio
    async def test_groups_similar_objections(
        self, mock_supabase: MagicMock
    ) -> None:
        """Test groups similar objections together."""
        from src.memory.lead_patterns import LeadPatternDetector

        now = datetime.now(UTC)
        mock_response = MagicMock()
        mock_response.data = [
            {"id": "i1", "content": "Budget constraints", "addressed_at": None},
            {"id": "i2", "content": "Budget constraints", "addressed_at": now.isoformat()},
            {"id": "i3", "content": "Timeline concerns", "addressed_at": None},
        ]
        # Only one .eq() call now (insight_type filter only)
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = (
            mock_response
        )

        detector = LeadPatternDetector(db_client=mock_supabase)
        patterns = await detector.common_objection_patterns(company_id="company-123")

        assert len(patterns) == 2
        budget = next(p for p in patterns if "Budget" in p.objection_text)
        assert budget.frequency == 2
        assert budget.resolution_rate == 0.5  # 1 out of 2 resolved

    @pytest.mark.asyncio
    async def test_orders_by_frequency(
        self, mock_supabase: MagicMock
    ) -> None:
        """Test patterns are ordered by frequency descending."""
        from src.memory.lead_patterns import LeadPatternDetector

        mock_response = MagicMock()
        mock_response.data = [
            {"id": "i1", "content": "Rare objection", "addressed_at": None},
            {"id": "i2", "content": "Common objection", "addressed_at": None},
            {"id": "i3", "content": "Common objection", "addressed_at": None},
            {"id": "i4", "content": "Common objection", "addressed_at": None},
        ]
        # Only one .eq() call now (insight_type filter only)
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = (
            mock_response
        )

        detector = LeadPatternDetector(db_client=mock_supabase)
        patterns = await detector.common_objection_patterns(company_id="company-123")

        assert patterns[0].objection_text == "Common objection"
        assert patterns[0].frequency == 3
        assert patterns[1].frequency == 1


class TestSuccessfulEngagementPatterns:
    """Tests for successful_engagement_patterns method."""

    @pytest.fixture
    def mock_supabase(self) -> MagicMock:
        """Create a mocked Supabase client."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_returns_empty_when_insufficient_data(
        self, mock_supabase: MagicMock
    ) -> None:
        """Test returns empty list when not enough closed leads."""
        from src.memory.lead_patterns import LeadPatternDetector

        mock_response = MagicMock()
        mock_response.data = []
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = (
            mock_response
        )

        detector = LeadPatternDetector(db_client=mock_supabase)
        patterns = await detector.successful_engagement_patterns(company_id="company-123")

        assert patterns == []

    @pytest.mark.asyncio
    async def test_detects_response_time_pattern(
        self, mock_supabase: MagicMock
    ) -> None:
        """Test detects fast response time correlation with success."""
        from src.memory.lead_patterns import LeadPatternDetector

        # Setup mock for lead query
        mock_lead_response = MagicMock()
        mock_lead_response.data = [
            {"id": "lead-1", "status": "won"},
            {"id": "lead-2", "status": "won"},
            {"id": "lead-3", "status": "lost"},
        ]

        # Setup mock for health score history with response time component
        mock_history_response = MagicMock()
        mock_history_response.data = [
            {"lead_memory_id": "lead-1", "component_response_time": 0.9},
            {"lead_memory_id": "lead-2", "component_response_time": 0.85},
            {"lead_memory_id": "lead-3", "component_response_time": 0.3},
        ]

        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table

        # Chain for leads query
        mock_table.select.return_value.eq.return_value.execute.return_value = mock_lead_response

        # Chain for health score history query
        mock_table.select.return_value.in_.return_value.execute.return_value = mock_history_response

        detector = LeadPatternDetector(db_client=mock_supabase)
        patterns = await detector.successful_engagement_patterns(
            company_id="company-123", min_sample_size=3
        )

        # Should detect response time as a success factor
        response_pattern = next(
            (p for p in patterns if p.pattern_type == "response_time"), None
        )
        assert response_pattern is not None
        assert response_pattern.success_correlation > 0.5

    @pytest.mark.asyncio
    async def test_detects_frequency_pattern(
        self, mock_supabase: MagicMock
    ) -> None:
        """Test detects touchpoint frequency correlation with success."""
        from src.memory.lead_patterns import LeadPatternDetector

        mock_lead_response = MagicMock()
        mock_lead_response.data = [
            {"id": "lead-1", "status": "won"},
            {"id": "lead-2", "status": "won"},
            {"id": "lead-3", "status": "lost"},
        ]

        mock_history_response = MagicMock()
        mock_history_response.data = [
            {"lead_memory_id": "lead-1", "component_frequency": 0.95},
            {"lead_memory_id": "lead-2", "component_frequency": 0.90},
            {"lead_memory_id": "lead-3", "component_frequency": 0.2},
        ]

        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.select.return_value.eq.return_value.execute.return_value = mock_lead_response
        mock_table.select.return_value.in_.return_value.execute.return_value = mock_history_response

        detector = LeadPatternDetector(db_client=mock_supabase)
        patterns = await detector.successful_engagement_patterns(
            company_id="company-123", min_sample_size=3
        )

        freq_pattern = next(
            (p for p in patterns if p.pattern_type == "touchpoint_frequency"), None
        )
        assert freq_pattern is not None
        assert freq_pattern.success_correlation > 0.5
