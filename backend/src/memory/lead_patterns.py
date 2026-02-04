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
from typing import TYPE_CHECKING

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
