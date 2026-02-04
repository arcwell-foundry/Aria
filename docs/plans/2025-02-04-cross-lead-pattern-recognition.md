# Cross-Lead Pattern Recognition Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement US-516 Cross-Lead Pattern Recognition to detect patterns across all leads and apply learnings to current leads.

**Architecture:** The `LeadPatternDetector` service analyzes leads across the company to detect sales patterns (time-to-close, objections, engagement). Detected patterns are stored in Corporate Memory via Graphiti for company-wide sharing. Privacy is enforced by stripping user-identifiable data before storage.

**Tech Stack:** Python 3.11, Supabase, Graphiti (Neo4j), pytest

---

## Task 1: Create LeadPatternDetector skeleton with tests

**Files:**
- Create: `backend/src/memory/lead_patterns.py`
- Create: `backend/tests/test_lead_patterns.py`

**Step 1: Write the failing test for LeadPatternDetector import**

```python
# backend/tests/test_lead_patterns.py
"""Tests for Lead Pattern Detection module (US-516)."""

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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_lead_patterns.py::TestLeadPatternDetectorImport -v`
Expected: FAIL with "ModuleNotFoundError" or "ImportError"

**Step 3: Write minimal implementation**

```python
# backend/src/memory/lead_patterns.py
"""Lead pattern detection for cross-lead learning.

This module analyzes patterns across all leads to extract actionable insights:
- Average time to close by segment
- Common objection patterns
- Successful engagement patterns
- Silent/inactive leads detection

Patterns are stored in Corporate Memory (Graphiti) with privacy protections -
no user-identifiable data is stored in patterns.

Usage:
    ```python
    from src.db.supabase import SupabaseClient
    from src.memory.lead_patterns import LeadPatternDetector

    client = SupabaseClient.get_client()
    detector = LeadPatternDetector(db_client=client)

    # Detect closing time patterns by segment
    patterns = await detector.avg_time_to_close_by_segment(company_id="...")

    # Find silent leads (inactive 14+ days)
    silent = await detector.find_silent_leads(user_id="...", inactive_days=14)
    ```
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from supabase import Client

logger = logging.getLogger(__name__)


@dataclass
class ClosingTimePattern:
    """Pattern for average time to close by segment.

    Attributes:
        segment: The lead segment (e.g., "enterprise", "smb", "healthcare").
        avg_days_to_close: Average days from first touch to close.
        sample_size: Number of leads used to calculate.
        calculated_at: When pattern was calculated.
    """

    segment: str
    avg_days_to_close: float
    sample_size: int
    calculated_at: datetime


@dataclass
class ObjectionPattern:
    """Pattern for common objections across leads.

    Attributes:
        objection_text: The normalized objection content.
        frequency: Number of leads with this objection.
        resolution_rate: Percentage of leads where objection was addressed.
        calculated_at: When pattern was calculated.
    """

    objection_text: str
    frequency: int
    resolution_rate: float
    calculated_at: datetime


@dataclass
class EngagementPattern:
    """Pattern for successful engagement strategies.

    Attributes:
        pattern_type: Type of engagement (e.g., "response_time", "touchpoint_frequency").
        description: Human-readable description of the pattern.
        success_correlation: Correlation with deal success (0.0 to 1.0).
        sample_size: Number of leads analyzed.
        calculated_at: When pattern was calculated.
    """

    pattern_type: str
    description: str
    success_correlation: float
    sample_size: int
    calculated_at: datetime


@dataclass
class SilentLead:
    """A lead that has been inactive for a specified period.

    Attributes:
        lead_id: The lead memory ID.
        company_name: Name of the company (not user-identifiable).
        days_inactive: Number of days since last activity.
        last_activity_at: When the lead was last active.
        health_score: Current health score.
    """

    lead_id: str
    company_name: str
    days_inactive: int
    last_activity_at: datetime
    health_score: int


class LeadPatternDetector:
    """Service for detecting patterns across leads.

    Analyzes lead data to extract company-wide patterns that can be
    applied to current leads. Stores patterns in Corporate Memory
    with privacy protections.
    """

    def __init__(self, db_client: Client) -> None:
        """Initialize the pattern detector.

        Args:
            db_client: Supabase client for database operations.
        """
        self.db = db_client
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_lead_patterns.py::TestLeadPatternDetectorImport -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/lead_patterns.py backend/tests/test_lead_patterns.py
git commit -m "feat(lead-patterns): add LeadPatternDetector skeleton and types

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Implement avg_time_to_close_by_segment

**Files:**
- Modify: `backend/src/memory/lead_patterns.py`
- Modify: `backend/tests/test_lead_patterns.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_lead_patterns.py`:

```python
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch


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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_lead_patterns.py::TestAvgTimeToCloseBySegment -v`
Expected: FAIL with "AttributeError: 'LeadPatternDetector' object has no attribute 'avg_time_to_close_by_segment'"

**Step 3: Write minimal implementation**

Add to `LeadPatternDetector` class in `backend/src/memory/lead_patterns.py`:

```python
    async def avg_time_to_close_by_segment(
        self,
        company_id: str,
    ) -> list[ClosingTimePattern]:
        """Calculate average time to close deals by segment.

        Analyzes all closed/won leads to determine average closing time
        for each segment (based on tags). Privacy-safe: only aggregated
        data is returned, no user-identifiable information.

        Args:
            company_id: The company to analyze leads for.

        Returns:
            List of ClosingTimePattern, one per segment found.

        Raises:
            DatabaseError: If query fails.
        """
        from datetime import UTC

        from src.core.exceptions import DatabaseError

        try:
            # Query closed/won leads
            response = (
                self.db.table("lead_memories")
                .select("id, first_touch_at, updated_at, tags")
                .eq("company_id", company_id)
                .eq("status", "won")
                .execute()
            )

            if not response.data:
                return []

            now = datetime.now(UTC)

            # Group by segment (first tag or "untagged")
            segment_data: dict[str, list[float]] = {}
            for lead in response.data:
                tags = lead.get("tags", []) or []
                segment = tags[0] if tags else "untagged"

                first_touch = datetime.fromisoformat(lead["first_touch_at"])
                closed_at = datetime.fromisoformat(lead["updated_at"])
                days_to_close = (closed_at - first_touch).days

                if segment not in segment_data:
                    segment_data[segment] = []
                segment_data[segment].append(float(days_to_close))

            # Calculate averages
            patterns = []
            for segment, days_list in segment_data.items():
                avg_days = sum(days_list) / len(days_list)
                patterns.append(
                    ClosingTimePattern(
                        segment=segment,
                        avg_days_to_close=avg_days,
                        sample_size=len(days_list),
                        calculated_at=now,
                    )
                )

            logger.info(
                "Calculated closing time patterns",
                extra={
                    "company_id": company_id,
                    "segment_count": len(patterns),
                },
            )

            return patterns

        except Exception as e:
            logger.exception("Failed to calculate closing time patterns")
            raise DatabaseError(f"Failed to calculate closing time patterns: {e}") from e
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_lead_patterns.py::TestAvgTimeToCloseBySegment -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/lead_patterns.py backend/tests/test_lead_patterns.py
git commit -m "feat(lead-patterns): add avg_time_to_close_by_segment

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Implement common_objection_patterns

**Files:**
- Modify: `backend/src/memory/lead_patterns.py`
- Modify: `backend/tests/test_lead_patterns.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_lead_patterns.py`:

```python
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
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = (
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
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = (
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
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = (
            mock_response
        )

        detector = LeadPatternDetector(db_client=mock_supabase)
        patterns = await detector.common_objection_patterns(company_id="company-123")

        assert patterns[0].objection_text == "Common objection"
        assert patterns[0].frequency == 3
        assert patterns[1].frequency == 1
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_lead_patterns.py::TestCommonObjectionPatterns -v`
Expected: FAIL with "AttributeError: 'LeadPatternDetector' object has no attribute 'common_objection_patterns'"

**Step 3: Write minimal implementation**

Add to `LeadPatternDetector` class in `backend/src/memory/lead_patterns.py`:

```python
    async def common_objection_patterns(
        self,
        company_id: str,
        min_frequency: int = 1,
    ) -> list[ObjectionPattern]:
        """Detect common objection patterns across leads.

        Analyzes objection-type insights from all leads to identify
        recurring objection patterns and their resolution rates.
        Privacy-safe: only aggregated patterns returned.

        Args:
            company_id: The company to analyze.
            min_frequency: Minimum occurrences to include (default 1).

        Returns:
            List of ObjectionPattern ordered by frequency descending.

        Raises:
            DatabaseError: If query fails.
        """
        from datetime import UTC

        from src.core.exceptions import DatabaseError

        try:
            # Query objection insights
            # Join through lead_memories to filter by company
            response = (
                self.db.table("lead_memory_insights")
                .select("id, content, addressed_at")
                .eq("insight_type", "objection")
                .eq("lead_memories.company_id", company_id)
                .execute()
            )

            if not response.data:
                return []

            now = datetime.now(UTC)

            # Group by content
            objection_data: dict[str, dict[str, Any]] = {}
            for insight in response.data:
                content = insight["content"]
                if content not in objection_data:
                    objection_data[content] = {"total": 0, "resolved": 0}

                objection_data[content]["total"] += 1
                if insight.get("addressed_at"):
                    objection_data[content]["resolved"] += 1

            # Create patterns
            patterns = []
            for content, data in objection_data.items():
                if data["total"] >= min_frequency:
                    resolution_rate = data["resolved"] / data["total"] if data["total"] > 0 else 0.0
                    patterns.append(
                        ObjectionPattern(
                            objection_text=content,
                            frequency=data["total"],
                            resolution_rate=resolution_rate,
                            calculated_at=now,
                        )
                    )

            # Sort by frequency descending
            patterns.sort(key=lambda p: p.frequency, reverse=True)

            logger.info(
                "Detected objection patterns",
                extra={
                    "company_id": company_id,
                    "pattern_count": len(patterns),
                },
            )

            return patterns

        except Exception as e:
            logger.exception("Failed to detect objection patterns")
            raise DatabaseError(f"Failed to detect objection patterns: {e}") from e
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_lead_patterns.py::TestCommonObjectionPatterns -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/lead_patterns.py backend/tests/test_lead_patterns.py
git commit -m "feat(lead-patterns): add common_objection_patterns

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Implement successful_engagement_patterns

**Files:**
- Modify: `backend/src/memory/lead_patterns.py`
- Modify: `backend/tests/test_lead_patterns.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_lead_patterns.py`:

```python
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

        now = datetime.now(UTC)

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
        patterns = await detector.successful_engagement_patterns(company_id="company-123")

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
        patterns = await detector.successful_engagement_patterns(company_id="company-123")

        freq_pattern = next(
            (p for p in patterns if p.pattern_type == "touchpoint_frequency"), None
        )
        assert freq_pattern is not None
        assert freq_pattern.success_correlation > 0.5
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_lead_patterns.py::TestSuccessfulEngagementPatterns -v`
Expected: FAIL with "AttributeError"

**Step 3: Write minimal implementation**

Add to `LeadPatternDetector` class in `backend/src/memory/lead_patterns.py`:

```python
    async def successful_engagement_patterns(
        self,
        company_id: str,
        min_sample_size: int = 5,
    ) -> list[EngagementPattern]:
        """Detect engagement patterns correlated with deal success.

        Analyzes health score components of won vs lost deals to identify
        which engagement factors correlate most strongly with success.
        Privacy-safe: only aggregated patterns returned.

        Args:
            company_id: The company to analyze.
            min_sample_size: Minimum closed deals required (default 5).

        Returns:
            List of EngagementPattern sorted by correlation strength.

        Raises:
            DatabaseError: If query fails.
        """
        from datetime import UTC

        from src.core.exceptions import DatabaseError

        try:
            # Query closed leads (won and lost)
            leads_response = (
                self.db.table("lead_memories")
                .select("id, status")
                .eq("company_id", company_id)
                .execute()
            )

            if not leads_response.data:
                return []

            # Filter to closed leads
            closed_leads = [
                l for l in leads_response.data if l["status"] in ("won", "lost")
            ]

            if len(closed_leads) < min_sample_size:
                return []

            lead_ids = [l["id"] for l in closed_leads]
            lead_status_map = {l["id"]: l["status"] for l in closed_leads}

            # Get health score history with component scores
            history_response = (
                self.db.table("health_score_history")
                .select(
                    "lead_memory_id, component_frequency, component_response_time, "
                    "component_sentiment, component_breadth, component_velocity"
                )
                .in_("lead_memory_id", lead_ids)
                .execute()
            )

            if not history_response.data:
                return []

            now = datetime.now(UTC)

            # Calculate correlation for each component
            components = [
                ("touchpoint_frequency", "component_frequency", "Frequent communication correlates with success"),
                ("response_time", "component_response_time", "Fast response time correlates with success"),
                ("sentiment", "component_sentiment", "Positive sentiment correlates with success"),
                ("stakeholder_breadth", "component_breadth", "Multi-stakeholder engagement correlates with success"),
                ("stage_velocity", "component_velocity", "Fast stage progression correlates with success"),
            ]

            patterns = []
            for pattern_type, component_field, description in components:
                # Get average component score for won vs lost
                won_scores = []
                lost_scores = []

                for record in history_response.data:
                    lead_id = record["lead_memory_id"]
                    score = record.get(component_field, 0) or 0

                    if lead_status_map.get(lead_id) == "won":
                        won_scores.append(score)
                    elif lead_status_map.get(lead_id) == "lost":
                        lost_scores.append(score)

                if not won_scores or not lost_scores:
                    continue

                avg_won = sum(won_scores) / len(won_scores)
                avg_lost = sum(lost_scores) / len(lost_scores)

                # Simple correlation: how much higher is won vs lost
                # Normalize to 0-1 range
                if avg_won > avg_lost:
                    correlation = min((avg_won - avg_lost) / max(avg_won, 0.01), 1.0)
                else:
                    correlation = 0.0

                patterns.append(
                    EngagementPattern(
                        pattern_type=pattern_type,
                        description=description,
                        success_correlation=correlation,
                        sample_size=len(won_scores) + len(lost_scores),
                        calculated_at=now,
                    )
                )

            # Sort by correlation strength
            patterns.sort(key=lambda p: p.success_correlation, reverse=True)

            logger.info(
                "Detected engagement patterns",
                extra={
                    "company_id": company_id,
                    "pattern_count": len(patterns),
                },
            )

            return patterns

        except Exception as e:
            logger.exception("Failed to detect engagement patterns")
            raise DatabaseError(f"Failed to detect engagement patterns: {e}") from e
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_lead_patterns.py::TestSuccessfulEngagementPatterns -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/lead_patterns.py backend/tests/test_lead_patterns.py
git commit -m "feat(lead-patterns): add successful_engagement_patterns

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Implement find_silent_leads

**Files:**
- Modify: `backend/src/memory/lead_patterns.py`
- Modify: `backend/tests/test_lead_patterns.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_lead_patterns.py`:

```python
class TestFindSilentLeads:
    """Tests for find_silent_leads method."""

    @pytest.fixture
    def mock_supabase(self) -> MagicMock:
        """Create a mocked Supabase client."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_silent_leads(
        self, mock_supabase: MagicMock
    ) -> None:
        """Test returns empty list when all leads are active."""
        from src.memory.lead_patterns import LeadPatternDetector

        mock_response = MagicMock()
        mock_response.data = []
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.lt.return_value.order.return_value.execute.return_value = (
            mock_response
        )

        detector = LeadPatternDetector(db_client=mock_supabase)
        silent = await detector.find_silent_leads(user_id="user-123")

        assert silent == []

    @pytest.mark.asyncio
    async def test_finds_leads_inactive_for_default_14_days(
        self, mock_supabase: MagicMock
    ) -> None:
        """Test finds leads inactive for 14+ days by default."""
        from src.memory.lead_patterns import LeadPatternDetector

        now = datetime.now(UTC)
        mock_response = MagicMock()
        mock_response.data = [
            {
                "id": "lead-1",
                "company_name": "Stale Corp",
                "last_activity_at": (now - timedelta(days=20)).isoformat(),
                "health_score": 45,
            },
            {
                "id": "lead-2",
                "company_name": "Dormant Inc",
                "last_activity_at": (now - timedelta(days=30)).isoformat(),
                "health_score": 30,
            },
        ]
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.lt.return_value.order.return_value.execute.return_value = (
            mock_response
        )

        detector = LeadPatternDetector(db_client=mock_supabase)
        silent = await detector.find_silent_leads(user_id="user-123")

        assert len(silent) == 2
        assert silent[0].company_name == "Stale Corp"
        assert silent[0].days_inactive >= 20
        assert silent[1].days_inactive >= 30

    @pytest.mark.asyncio
    async def test_custom_inactive_days_threshold(
        self, mock_supabase: MagicMock
    ) -> None:
        """Test custom inactive_days parameter."""
        from src.memory.lead_patterns import LeadPatternDetector

        now = datetime.now(UTC)
        mock_response = MagicMock()
        mock_response.data = [
            {
                "id": "lead-1",
                "company_name": "Recent Quiet",
                "last_activity_at": (now - timedelta(days=8)).isoformat(),
                "health_score": 60,
            },
        ]
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.lt.return_value.order.return_value.execute.return_value = (
            mock_response
        )

        detector = LeadPatternDetector(db_client=mock_supabase)
        # Find leads inactive for 7+ days
        silent = await detector.find_silent_leads(user_id="user-123", inactive_days=7)

        assert len(silent) == 1
        assert silent[0].days_inactive >= 7

    @pytest.mark.asyncio
    async def test_only_returns_active_status_leads(
        self, mock_supabase: MagicMock
    ) -> None:
        """Test only active leads are returned, not won/lost."""
        from src.memory.lead_patterns import LeadPatternDetector

        detector = LeadPatternDetector(db_client=mock_supabase)
        await detector.find_silent_leads(user_id="user-123")

        # Verify query filters by status=active
        mock_supabase.table.return_value.select.return_value.eq.assert_any_call(
            "status", "active"
        )
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_lead_patterns.py::TestFindSilentLeads -v`
Expected: FAIL with "AttributeError"

**Step 3: Write minimal implementation**

Add to `LeadPatternDetector` class in `backend/src/memory/lead_patterns.py`:

```python
    async def find_silent_leads(
        self,
        user_id: str,
        inactive_days: int = 14,
        limit: int = 50,
    ) -> list[SilentLead]:
        """Find leads that have been inactive for a specified period.

        Identifies leads with no activity for the given number of days.
        Only returns active leads (not won/lost).

        Args:
            user_id: The user to find silent leads for.
            inactive_days: Days of inactivity to be considered silent (default 14).
            limit: Maximum number of leads to return (default 50).

        Returns:
            List of SilentLead ordered by days inactive descending.

        Raises:
            DatabaseError: If query fails.
        """
        from datetime import UTC

        from src.core.exceptions import DatabaseError

        try:
            now = datetime.now(UTC)
            cutoff = now - timedelta(days=inactive_days)

            response = (
                self.db.table("lead_memories")
                .select("id, company_name, last_activity_at, health_score")
                .eq("user_id", user_id)
                .eq("status", "active")
                .lt("last_activity_at", cutoff.isoformat())
                .order("last_activity_at", desc=False)  # Oldest first
                .execute()
            )

            if not response.data:
                return []

            silent_leads = []
            for lead in response.data[:limit]:
                last_activity = datetime.fromisoformat(lead["last_activity_at"])
                days_inactive = (now - last_activity).days

                silent_leads.append(
                    SilentLead(
                        lead_id=lead["id"],
                        company_name=lead["company_name"],
                        days_inactive=days_inactive,
                        last_activity_at=last_activity,
                        health_score=lead["health_score"],
                    )
                )

            logger.info(
                "Found silent leads",
                extra={
                    "user_id": user_id,
                    "inactive_days": inactive_days,
                    "count": len(silent_leads),
                },
            )

            return silent_leads

        except Exception as e:
            logger.exception("Failed to find silent leads")
            raise DatabaseError(f"Failed to find silent leads: {e}") from e
```

Also add import at top of file:

```python
from datetime import datetime, timedelta
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_lead_patterns.py::TestFindSilentLeads -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/lead_patterns.py backend/tests/test_lead_patterns.py
git commit -m "feat(lead-patterns): add find_silent_leads

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Implement apply_warnings_to_lead

**Files:**
- Modify: `backend/src/memory/lead_patterns.py`
- Modify: `backend/tests/test_lead_patterns.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_lead_patterns.py`:

```python
class TestApplyWarningsToLead:
    """Tests for apply_warnings_to_lead method."""

    @pytest.fixture
    def mock_supabase(self) -> MagicMock:
        """Create a mocked Supabase client."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_patterns_match(
        self, mock_supabase: MagicMock
    ) -> None:
        """Test returns empty list when lead doesn't match negative patterns."""
        from src.memory.lead_patterns import LeadPatternDetector, LeadWarning

        # Mock lead data with good metrics
        mock_lead_response = MagicMock()
        mock_lead_response.data = {
            "id": "lead-1",
            "company_name": "Healthy Corp",
            "last_activity_at": datetime.now(UTC).isoformat(),
            "health_score": 85,
            "tags": ["enterprise"],
        }

        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = (
            mock_lead_response
        )

        # Mock empty objection patterns
        mock_patterns_response = MagicMock()
        mock_patterns_response.data = []
        mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = (
            mock_patterns_response
        )

        detector = LeadPatternDetector(db_client=mock_supabase)
        warnings = await detector.apply_warnings_to_lead(
            user_id="user-123",
            lead_id="lead-1",
        )

        assert warnings == []

    @pytest.mark.asyncio
    async def test_warns_on_unresolved_objection_pattern(
        self, mock_supabase: MagicMock
    ) -> None:
        """Test warns when lead has unresolved objection matching a low-resolution pattern."""
        from src.memory.lead_patterns import LeadPatternDetector

        now = datetime.now(UTC)

        # Mock lead data
        mock_lead_response = MagicMock()
        mock_lead_response.data = {
            "id": "lead-1",
            "company_name": "At Risk Corp",
            "last_activity_at": (now - timedelta(days=10)).isoformat(),
            "health_score": 55,
            "tags": ["enterprise"],
        }

        # Mock unresolved objection for this lead
        mock_insight_response = MagicMock()
        mock_insight_response.data = [
            {"content": "Budget constraints", "addressed_at": None},
        ]

        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table

        # Setup chain for lead query
        mock_table.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = (
            mock_lead_response
        )

        # Setup chain for insights query
        mock_table.select.return_value.eq.return_value.eq.return_value.is_.return_value.execute.return_value = (
            mock_insight_response
        )

        detector = LeadPatternDetector(db_client=mock_supabase)

        # Inject a known low-resolution objection pattern
        with patch.object(
            detector,
            "common_objection_patterns",
            return_value=[
                ObjectionPattern(
                    objection_text="Budget constraints",
                    frequency=10,
                    resolution_rate=0.2,  # Only 20% resolved - bad pattern
                    calculated_at=now,
                )
            ],
        ):
            warnings = await detector.apply_warnings_to_lead(
                user_id="user-123",
                lead_id="lead-1",
                company_id="company-123",
            )

        assert len(warnings) >= 1
        budget_warning = next(
            (w for w in warnings if "Budget" in w.message), None
        )
        assert budget_warning is not None
        assert budget_warning.severity == "high"

    @pytest.mark.asyncio
    async def test_warns_on_silent_lead(
        self, mock_supabase: MagicMock
    ) -> None:
        """Test warns when lead has been silent."""
        from src.memory.lead_patterns import LeadPatternDetector

        now = datetime.now(UTC)

        mock_lead_response = MagicMock()
        mock_lead_response.data = {
            "id": "lead-1",
            "company_name": "Silent Corp",
            "last_activity_at": (now - timedelta(days=20)).isoformat(),
            "health_score": 40,
            "tags": [],
        }

        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = (
            mock_lead_response
        )

        # Empty insights
        mock_insight_response = MagicMock()
        mock_insight_response.data = []
        mock_table.select.return_value.eq.return_value.eq.return_value.is_.return_value.execute.return_value = (
            mock_insight_response
        )

        detector = LeadPatternDetector(db_client=mock_supabase)

        with patch.object(detector, "common_objection_patterns", return_value=[]):
            warnings = await detector.apply_warnings_to_lead(
                user_id="user-123",
                lead_id="lead-1",
            )

        silent_warning = next(
            (w for w in warnings if "inactive" in w.message.lower()), None
        )
        assert silent_warning is not None
```

First, add the `LeadWarning` dataclass after the other dataclasses:

```python
@dataclass
class LeadWarning:
    """A warning applied to a lead based on negative pattern matching.

    Attributes:
        lead_id: The lead this warning applies to.
        warning_type: Type of warning (e.g., "objection_pattern", "silent_lead").
        message: Human-readable warning message.
        severity: Warning severity ("low", "medium", "high").
        pattern_source: Description of the pattern that triggered this warning.
        created_at: When the warning was generated.
    """

    lead_id: str
    warning_type: str
    message: str
    severity: str
    pattern_source: str
    created_at: datetime
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_lead_patterns.py::TestApplyWarningsToLead -v`
Expected: FAIL with "AttributeError" or "ImportError"

**Step 3: Write minimal implementation**

Add to `LeadPatternDetector` class in `backend/src/memory/lead_patterns.py`:

```python
    async def apply_warnings_to_lead(
        self,
        user_id: str,
        lead_id: str,
        company_id: str | None = None,
        inactive_threshold_days: int = 14,
        low_resolution_threshold: float = 0.3,
    ) -> list[LeadWarning]:
        """Apply warnings to a lead based on negative pattern matching.

        Checks if the lead matches any concerning patterns:
        - Unresolved objections that historically have low resolution rates
        - Inactivity beyond threshold
        - Other negative patterns

        Args:
            user_id: The user who owns the lead.
            lead_id: The lead to check.
            company_id: Optional company ID for pattern matching.
            inactive_threshold_days: Days inactive to trigger warning (default 14).
            low_resolution_threshold: Resolution rate below which to warn (default 0.3).

        Returns:
            List of LeadWarning for any matching patterns.

        Raises:
            DatabaseError: If query fails.
        """
        from datetime import UTC

        from src.core.exceptions import DatabaseError

        warnings: list[LeadWarning] = []
        now = datetime.now(UTC)

        try:
            # Get lead data
            lead_response = (
                self.db.table("lead_memories")
                .select("id, company_name, last_activity_at, health_score, tags")
                .eq("id", lead_id)
                .eq("user_id", user_id)
                .single()
                .execute()
            )

            if not lead_response.data:
                return []

            lead = lead_response.data
            last_activity = datetime.fromisoformat(lead["last_activity_at"])
            days_inactive = (now - last_activity).days

            # Check for silent lead warning
            if days_inactive >= inactive_threshold_days:
                warnings.append(
                    LeadWarning(
                        lead_id=lead_id,
                        warning_type="silent_lead",
                        message=f"Lead has been inactive for {days_inactive} days",
                        severity="medium" if days_inactive < 21 else "high",
                        pattern_source=f"Inactivity threshold: {inactive_threshold_days} days",
                        created_at=now,
                    )
                )

            # Get unresolved objections for this lead
            objections_response = (
                self.db.table("lead_memory_insights")
                .select("content")
                .eq("lead_memory_id", lead_id)
                .eq("insight_type", "objection")
                .is_("addressed_at", "null")
                .execute()
            )

            unresolved_objections = [o["content"] for o in (objections_response.data or [])]

            # If company_id provided, check against objection patterns
            if company_id and unresolved_objections:
                patterns = await self.common_objection_patterns(company_id=company_id)

                for pattern in patterns:
                    if pattern.resolution_rate < low_resolution_threshold:
                        # Check if lead has this objection
                        for objection in unresolved_objections:
                            if pattern.objection_text.lower() in objection.lower():
                                warnings.append(
                                    LeadWarning(
                                        lead_id=lead_id,
                                        warning_type="objection_pattern",
                                        message=f"Unresolved objection '{objection}' matches pattern with only {pattern.resolution_rate:.0%} resolution rate",
                                        severity="high",
                                        pattern_source=f"Pattern: {pattern.objection_text} (n={pattern.frequency})",
                                        created_at=now,
                                    )
                                )
                                break

            logger.info(
                "Applied warnings to lead",
                extra={
                    "user_id": user_id,
                    "lead_id": lead_id,
                    "warning_count": len(warnings),
                },
            )

            return warnings

        except Exception as e:
            logger.exception("Failed to apply warnings to lead")
            raise DatabaseError(f"Failed to apply warnings to lead: {e}") from e
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_lead_patterns.py::TestApplyWarningsToLead -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/lead_patterns.py backend/tests/test_lead_patterns.py
git commit -m "feat(lead-patterns): add apply_warnings_to_lead

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Implement store_patterns_to_corporate_memory

**Files:**
- Modify: `backend/src/memory/lead_patterns.py`
- Modify: `backend/tests/test_lead_patterns.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_lead_patterns.py`:

```python
from unittest.mock import AsyncMock


class TestStorePatternsToCorporateMemory:
    """Tests for store_patterns_to_corporate_memory method."""

    @pytest.fixture
    def mock_supabase(self) -> MagicMock:
        """Create a mocked Supabase client."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_stores_closing_time_patterns(
        self, mock_supabase: MagicMock
    ) -> None:
        """Test stores closing time patterns to corporate memory."""
        from src.memory.lead_patterns import ClosingTimePattern, LeadPatternDetector

        now = datetime.now(UTC)
        patterns = [
            ClosingTimePattern(
                segment="enterprise",
                avg_days_to_close=45.0,
                sample_size=10,
                calculated_at=now,
            ),
        ]

        detector = LeadPatternDetector(db_client=mock_supabase)

        with patch("src.memory.lead_patterns.CorporateMemory") as mock_corp_mem:
            mock_instance = MagicMock()
            mock_instance.add_fact = AsyncMock(return_value="fact-123")
            mock_corp_mem.return_value = mock_instance

            result = await detector.store_patterns_to_corporate_memory(
                company_id="company-123",
                closing_patterns=patterns,
            )

            mock_instance.add_fact.assert_called_once()
            call_args = mock_instance.add_fact.call_args
            fact = call_args.kwargs.get("fact") or call_args.args[0]
            assert fact.predicate == "avg_closing_time"
            assert fact.subject == "segment:enterprise"
            assert "45" in fact.object

    @pytest.mark.asyncio
    async def test_stores_objection_patterns(
        self, mock_supabase: MagicMock
    ) -> None:
        """Test stores objection patterns to corporate memory."""
        from src.memory.lead_patterns import LeadPatternDetector, ObjectionPattern

        now = datetime.now(UTC)
        patterns = [
            ObjectionPattern(
                objection_text="Budget constraints",
                frequency=15,
                resolution_rate=0.4,
                calculated_at=now,
            ),
        ]

        detector = LeadPatternDetector(db_client=mock_supabase)

        with patch("src.memory.lead_patterns.CorporateMemory") as mock_corp_mem:
            mock_instance = MagicMock()
            mock_instance.add_fact = AsyncMock(return_value="fact-456")
            mock_corp_mem.return_value = mock_instance

            await detector.store_patterns_to_corporate_memory(
                company_id="company-123",
                objection_patterns=patterns,
            )

            mock_instance.add_fact.assert_called_once()
            call_args = mock_instance.add_fact.call_args
            fact = call_args.kwargs.get("fact") or call_args.args[0]
            assert fact.predicate == "common_objection"
            assert "Budget" in fact.object

    @pytest.mark.asyncio
    async def test_privacy_no_user_data_in_patterns(
        self, mock_supabase: MagicMock
    ) -> None:
        """Test no user-identifiable data is stored in patterns."""
        from src.memory.lead_patterns import EngagementPattern, LeadPatternDetector

        now = datetime.now(UTC)
        patterns = [
            EngagementPattern(
                pattern_type="response_time",
                description="Fast response correlates with success",
                success_correlation=0.8,
                sample_size=20,
                calculated_at=now,
            ),
        ]

        detector = LeadPatternDetector(db_client=mock_supabase)

        with patch("src.memory.lead_patterns.CorporateMemory") as mock_corp_mem:
            mock_instance = MagicMock()
            mock_instance.add_fact = AsyncMock(return_value="fact-789")
            mock_corp_mem.return_value = mock_instance

            await detector.store_patterns_to_corporate_memory(
                company_id="company-123",
                engagement_patterns=patterns,
            )

            call_args = mock_instance.add_fact.call_args
            fact = call_args.kwargs.get("fact") or call_args.args[0]

            # Verify no user_id in fact
            assert "user" not in fact.subject.lower()
            assert "user" not in fact.object.lower()
            # created_by should be None (system-generated)
            assert fact.created_by is None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_lead_patterns.py::TestStorePatternsToCorporateMemory -v`
Expected: FAIL with "AttributeError"

**Step 3: Write minimal implementation**

Add to `LeadPatternDetector` class in `backend/src/memory/lead_patterns.py`:

```python
    async def store_patterns_to_corporate_memory(
        self,
        company_id: str,
        closing_patterns: list[ClosingTimePattern] | None = None,
        objection_patterns: list[ObjectionPattern] | None = None,
        engagement_patterns: list[EngagementPattern] | None = None,
    ) -> list[str]:
        """Store detected patterns to Corporate Memory via Graphiti.

        Patterns are stored as company-level facts that can be shared
        across all users. Privacy is enforced: no user-identifiable
        data is included in stored patterns.

        Args:
            company_id: The company to store patterns for.
            closing_patterns: Optional closing time patterns to store.
            objection_patterns: Optional objection patterns to store.
            engagement_patterns: Optional engagement patterns to store.

        Returns:
            List of created fact IDs.

        Raises:
            CorporateMemoryError: If storage fails.
        """
        import uuid
        from datetime import UTC

        from src.memory.corporate import CorporateFact, CorporateFactSource, CorporateMemory

        fact_ids: list[str] = []
        now = datetime.now(UTC)
        corp_memory = CorporateMemory()

        # Store closing time patterns
        if closing_patterns:
            for pattern in closing_patterns:
                fact = CorporateFact(
                    id=str(uuid.uuid4()),
                    company_id=company_id,
                    subject=f"segment:{pattern.segment}",
                    predicate="avg_closing_time",
                    object=f"{pattern.avg_days_to_close:.1f} days (n={pattern.sample_size})",
                    confidence=min(0.5 + (pattern.sample_size / 100), 0.95),
                    source=CorporateFactSource.AGGREGATED,
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                    created_by=None,  # System-generated, no user
                )
                fact_id = await corp_memory.add_fact(fact=fact)
                fact_ids.append(fact_id)

        # Store objection patterns
        if objection_patterns:
            for pattern in objection_patterns:
                fact = CorporateFact(
                    id=str(uuid.uuid4()),
                    company_id=company_id,
                    subject="lead_objections",
                    predicate="common_objection",
                    object=f"{pattern.objection_text} (freq={pattern.frequency}, resolution={pattern.resolution_rate:.0%})",
                    confidence=min(0.5 + (pattern.frequency / 50), 0.90),
                    source=CorporateFactSource.AGGREGATED,
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                    created_by=None,
                )
                fact_id = await corp_memory.add_fact(fact=fact)
                fact_ids.append(fact_id)

        # Store engagement patterns
        if engagement_patterns:
            for pattern in engagement_patterns:
                fact = CorporateFact(
                    id=str(uuid.uuid4()),
                    company_id=company_id,
                    subject=f"engagement:{pattern.pattern_type}",
                    predicate="success_correlation",
                    object=f"{pattern.description} (r={pattern.success_correlation:.2f}, n={pattern.sample_size})",
                    confidence=pattern.success_correlation,
                    source=CorporateFactSource.AGGREGATED,
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                    created_by=None,
                )
                fact_id = await corp_memory.add_fact(fact=fact)
                fact_ids.append(fact_id)

        logger.info(
            "Stored patterns to corporate memory",
            extra={
                "company_id": company_id,
                "fact_count": len(fact_ids),
            },
        )

        return fact_ids
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_lead_patterns.py::TestStorePatternsToCorporateMemory -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/lead_patterns.py backend/tests/test_lead_patterns.py
git commit -m "feat(lead-patterns): add store_patterns_to_corporate_memory

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Add module exports and run full test suite

**Files:**
- Modify: `backend/src/memory/__init__.py`
- Modify: `backend/tests/test_lead_patterns.py`

**Step 1: Write the failing test for module exports**

Add to `backend/tests/test_lead_patterns.py`:

```python
class TestLeadPatternsModuleExports:
    """Tests for module exports."""

    def test_lead_pattern_detector_exported_from_memory_module(self) -> None:
        """Test LeadPatternDetector is exported from memory module."""
        from src.memory import LeadPatternDetector

        assert LeadPatternDetector is not None

    def test_pattern_types_exported_from_memory_module(self) -> None:
        """Test pattern types are exported from memory module."""
        from src.memory import (
            ClosingTimePattern,
            EngagementPattern,
            LeadWarning,
            ObjectionPattern,
            SilentLead,
        )

        assert ClosingTimePattern is not None
        assert ObjectionPattern is not None
        assert EngagementPattern is not None
        assert SilentLead is not None
        assert LeadWarning is not None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_lead_patterns.py::TestLeadPatternsModuleExports -v`
Expected: FAIL with "ImportError"

**Step 3: Write minimal implementation**

Update `backend/src/memory/__init__.py` to add the imports:

After the existing imports, add:

```python
from src.memory.lead_patterns import (
    ClosingTimePattern,
    EngagementPattern,
    LeadPatternDetector,
    LeadWarning,
    ObjectionPattern,
    SilentLead,
)
```

Add to the `__all__` list:

```python
    # Lead Pattern Detection
    "LeadPatternDetector",
    "ClosingTimePattern",
    "ObjectionPattern",
    "EngagementPattern",
    "SilentLead",
    "LeadWarning",
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_lead_patterns.py::TestLeadPatternsModuleExports -v`
Expected: PASS

**Step 5: Run full test suite for lead patterns**

Run: `cd backend && python -m pytest tests/test_lead_patterns.py -v`
Expected: All tests PASS

**Step 6: Run linting**

Run: `cd backend && ruff check src/memory/lead_patterns.py && ruff format src/memory/lead_patterns.py`
Expected: No errors

**Step 7: Run type checking**

Run: `cd backend && mypy src/memory/lead_patterns.py --strict`
Expected: No errors (or only expected ones from Supabase client)

**Step 8: Commit**

```bash
git add backend/src/memory/__init__.py backend/src/memory/lead_patterns.py backend/tests/test_lead_patterns.py
git commit -m "feat(lead-patterns): export LeadPatternDetector from memory module

Completes US-516: Cross-Lead Pattern Recognition

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Final verification and cleanup

**Step 1: Run all related tests**

Run: `cd backend && python -m pytest tests/test_lead_patterns.py tests/test_lead_memory.py tests/test_corporate_memory.py -v`
Expected: All tests PASS

**Step 2: Run full backend test suite**

Run: `cd backend && python -m pytest tests/ -v --ignore=tests/integration/`
Expected: All tests PASS

**Step 3: Verify git status**

Run: `git status`
Expected: Clean working tree

**Step 4: Create summary of completed work**

The US-516 implementation is complete with:
- `LeadPatternDetector` class with 5 core methods
- `avg_time_to_close_by_segment()` - analyzes closing times by tag/segment
- `common_objection_patterns()` - detects recurring objection patterns
- `successful_engagement_patterns()` - correlates engagement with success
- `find_silent_leads()` - identifies inactive leads (14+ days default)
- `apply_warnings_to_lead()` - flags leads matching negative patterns
- `store_patterns_to_corporate_memory()` - persists to Graphiti with privacy
- Full unit test coverage
- Privacy-safe: no user-identifiable data in stored patterns
