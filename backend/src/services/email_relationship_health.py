"""Email relationship health tracking from scan patterns.

Analyzes email_scan_log data to detect relationship patterns per contact:
- Frequency trends (warming, stable, cooling)
- Response patterns
- Engagement shifts
- Days since last contact

This data feeds into:
- Draft context (ARIA mentions cooling relationships in drafts)
- Intelligence panel (relationship health dashboard)
- Proactive alerts (contacts going cold)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


@dataclass
class ContactHealth:
    """Health metrics for a single contact relationship."""

    contact_email: str
    contact_name: str = ""
    total_emails: int = 0
    weekly_frequency: float = 0.0
    trend: str = "stable"  # warming, stable, cooling, new
    trend_detail: str = ""
    last_email_date: str | None = None
    days_since_last: int = 0
    needs_reply_count: int = 0
    urgent_count: int = 0
    health_score: int = 50  # 0-100, starts neutral

    # Period comparisons
    recent_count: int = 0  # Last 7 days
    prior_count: int = 0  # 7-14 days ago

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "contact_email": self.contact_email,
            "contact_name": self.contact_name,
            "total_emails": self.total_emails,
            "weekly_frequency": round(self.weekly_frequency, 1),
            "trend": self.trend,
            "trend_detail": self.trend_detail,
            "last_email_date": self.last_email_date,
            "days_since_last": self.days_since_last,
            "needs_reply_count": self.needs_reply_count,
            "urgent_count": self.urgent_count,
            "health_score": self.health_score,
            "recent_count": self.recent_count,
            "prior_count": self.prior_count,
        }


class EmailRelationshipHealth:
    """Analyze and track email relationship health per contact.

    Uses email_scan_log patterns to detect:
    - Communication frequency trends
    - Response behavior
    - Engagement changes

    Example:
        ```python
        service = EmailRelationshipHealth()

        # Analyze single contact
        health = await service.analyze_contact_health(
            user_id="...",
            contact_email="john@example.com"
        )
        print(health.trend)  # "warming", "stable", "cooling", "new"

        # Get all contacts
        all_health = await service.get_all_contact_health(user_id="...")
        for h in all_health:
            print(f"{h.contact_email}: {h.trend} ({h.health_score})")
        ```
    """

    # Thresholds for trend detection
    WARMING_THRESHOLD = 1.5  # 50% increase = warming
    COOLING_DAYS = 14  # No contact for 14+ days = cooling
    COOLING_PRIOR_MIN = 2  # Must have had 2+ emails before to be "cooling"

    # Health score weights
    SCORE_FREQUENCY = 30  # Up to 30 points for frequency
    SCORE_RECENCY = 40  # Up to 40 points for recency
    SCORE_TREND = 30  # Up to 30 points for positive trend

    def __init__(self) -> None:
        """Initialize with database client."""
        self._db = SupabaseClient.get_client()

    async def analyze_contact_health(
        self,
        user_id: str,
        contact_email: str,
    ) -> ContactHealth:
        """Analyze email relationship health for a specific contact.

        Args:
            user_id: The user's ID.
            contact_email: The contact's email address.

        Returns:
            ContactHealth with trend analysis and health score.
        """
        health = ContactHealth(contact_email=contact_email)

        try:
            # Get all scan log entries for this contact
            result = (
                self._db.table("email_scan_log")
                .select("*")
                .eq("user_id", user_id)
                .eq("sender_email", contact_email.lower())
                .order("scanned_at", desc=True)
                .execute()
            )

            if not result.data:
                health.trend = "new"
                health.trend_detail = "No prior email history with this contact"
                return health

            entries = result.data
            health.total_emails = len(entries)
            health.contact_name = entries[0].get("sender_name", "") or ""

            # Parse timestamps
            now = datetime.now(UTC)
            first_email = entries[-1]["scanned_at"]
            last_email = entries[0]["scanned_at"]

            health.last_email_date = last_email

            # Parse dates safely
            try:
                first_dt = self._parse_timestamp(first_email)
                last_dt = self._parse_timestamp(last_email)
                health.days_since_last = (now - last_dt).days

                # Calculate frequency
                days_span = max((last_dt - first_dt).days, 1)
                if days_span >= 7:
                    health.weekly_frequency = health.total_emails / (days_span / 7)
                else:
                    health.weekly_frequency = health.total_emails

            except (ValueError, TypeError) as e:
                logger.warning(
                    "RELATIONSHIP_HEALTH: Failed to parse dates for %s: %s",
                    contact_email,
                    str(e),
                )
                health.days_since_last = 0

            # Count categories
            health.needs_reply_count = sum(
                1 for e in entries if e.get("category") == "NEEDS_REPLY"
            )
            health.urgent_count = sum(
                1 for e in entries if e.get("urgency") == "URGENT"
            )

            # Period comparison: recent (0-7 days) vs prior (7-14 days)
            recent_cutoff = (now - timedelta(days=7)).isoformat()
            prior_cutoff = (now - timedelta(days=14)).isoformat()

            health.recent_count = sum(
                1 for e in entries if e.get("scanned_at", "") >= recent_cutoff
            )
            health.prior_count = sum(
                1
                for e in entries
                if prior_cutoff <= e.get("scanned_at", "") < recent_cutoff
            )

            # Trend detection
            health.trend, health.trend_detail = self._detect_trend(health)

            # Calculate health score
            health.health_score = self._calculate_health_score(health)

            logger.debug(
                "RELATIONSHIP_HEALTH: %s — %d emails, %.1f/week, trend=%s, score=%d",
                contact_email,
                health.total_emails,
                health.weekly_frequency,
                health.trend,
                health.health_score,
            )

        except Exception as e:
            logger.error(
                "RELATIONSHIP_HEALTH: Failed to analyze %s: %s",
                contact_email,
                str(e),
                exc_info=True,
            )

        return health

    def _parse_timestamp(self, ts: str) -> datetime:
        """Parse ISO timestamp to datetime."""
        # Handle various ISO formats
        ts = ts.replace("Z", "+00:00")
        if "+" not in ts and "-" not in ts[-6:]:
            ts += "+00:00"
        return datetime.fromisoformat(ts)

    def _detect_trend(self, health: ContactHealth) -> tuple[str, str]:
        """Detect relationship trend from period comparison.

        Args:
            health: ContactHealth with populated counts.

        Returns:
            Tuple of (trend, detail_message).
        """
        # New contact: very few emails
        if health.total_emails <= 2:
            return "new", f"Just {health.total_emails} email(s) — relationship starting"

        # Cooling: no recent emails but had prior activity
        if health.recent_count == 0 and health.prior_count >= self.COOLING_PRIOR_MIN:
            return (
                "cooling",
                f"No emails in 7 days — previously {health.prior_count}/week",
            )

        # Also cooling if long gap since last email
        if health.days_since_last >= self.COOLING_DAYS and health.total_emails > 3:
            return (
                "cooling",
                f"No contact for {health.days_since_last} days",
            )

        # Warming: significant increase in recent activity
        if health.prior_count > 0:
            ratio = health.recent_count / health.prior_count
            if ratio >= self.WARMING_THRESHOLD:
                return (
                    "warming",
                    f"Communication up {int((ratio - 1) * 100)}% — "
                    f"{health.recent_count} vs {health.prior_count} prior",
                )

        # Active warming: high recent activity with new contact
        if health.recent_count >= 3 and health.total_emails <= 5:
            return "warming", f"{health.recent_count} emails this week — new active contact"

        # Stable: consistent or no clear pattern
        if health.weekly_frequency >= 1:
            return "stable", f"Consistent ~{health.weekly_frequency:.1f} emails/week"
        else:
            return "stable", f"Occasional contact ({health.total_emails} total)"

    def _calculate_health_score(self, health: ContactHealth) -> int:
        """Calculate overall health score (0-100).

        Components:
        - Frequency (30 pts): Higher frequency = higher score
        - Recency (40 pts): Recent contact = higher score
        - Trend (30 pts): Warming = bonus, cooling = penalty

        Args:
            health: ContactHealth with trend data.

        Returns:
            Health score 0-100.
        """
        score = 50  # Start neutral

        # Frequency component (up to 30 points)
        if health.weekly_frequency >= 3:
            score += 30  # Very active
        elif health.weekly_frequency >= 1:
            score += 20  # Regular
        elif health.weekly_frequency >= 0.5:
            score += 10  # Occasional
        # else: no bonus for rare contact

        # Recency component (up to 40 points, can go negative)
        if health.days_since_last <= 2:
            score += 40  # Very recent
        elif health.days_since_last <= 7:
            score += 30  # This week
        elif health.days_since_last <= 14:
            score += 15  # Within 2 weeks
        elif health.days_since_last <= 30:
            score -= 10  # Getting cold
        else:
            score -= 30  # Cold

        # Trend component (up to 30 points, can go negative)
        if health.trend == "warming":
            score += 30
        elif health.trend == "stable" and health.weekly_frequency >= 1:
            score += 15
        elif health.trend == "cooling":
            score -= 20
        # new or sparse stable = no change

        # Clamp to 0-100
        return max(0, min(100, score))

    async def get_all_contact_health(
        self,
        user_id: str,
        limit: int = 50,
    ) -> list[ContactHealth]:
        """Get health summary for all contacts.

        Args:
            user_id: The user's ID.
            limit: Maximum contacts to return.

        Returns:
            List of ContactHealth objects sorted by total emails.
        """
        results: list[ContactHealth] = []

        try:
            # Get unique contacts from scan log
            result = (
                self._db.table("email_scan_log")
                .select("sender_email, sender_name")
                .eq("user_id", user_id)
                .execute()
            )

            if not result.data:
                return results

            # Get unique emails
            unique_contacts: dict[str, str] = {}
            for row in result.data:
                email = row.get("sender_email", "")
                if email and email not in unique_contacts:
                    unique_contacts[email] = row.get("sender_name", "") or ""

            # Analyze each contact
            for email, name in unique_contacts.items():
                health = await self.analyze_contact_health(user_id, email)
                results.append(health)

                if len(results) >= limit:
                    break

            # Sort by health score (lowest first — needs attention)
            results.sort(key=lambda h: h.health_score)

        except Exception as e:
            logger.error(
                "RELATIONSHIP_HEALTH: Failed to get all contacts for %s: %s",
                user_id,
                str(e),
                exc_info=True,
            )

        return results

    async def get_cooling_contacts(
        self,
        user_id: str,
        min_prior_emails: int = 3,
    ) -> list[ContactHealth]:
        """Get contacts that are cooling (need attention).

        Args:
            user_id: The user's ID.
            min_prior_emails: Minimum prior emails to consider "cooling".

        Returns:
            List of ContactHealth objects for cooling relationships.
        """
        all_health = await self.get_all_contact_health(user_id)

        cooling = [
            h
            for h in all_health
            if h.trend == "cooling" and h.total_emails >= min_prior_emails
        ]

        logger.info(
            "RELATIONSHIP_HEALTH: Found %d cooling contacts for user %s",
            len(cooling),
            user_id,
        )

        return cooling

    async def get_aria_note(self, user_id: str, contact_email: str) -> str | None:
        """Generate an ARIA-style note about relationship health.

        Used in draft generation to add context about the relationship.

        Args:
            user_id: The user's ID.
            contact_email: The contact's email.

        Returns:
            Human-readable note or None if no special context.
        """
        health = await self.analyze_contact_health(user_id, contact_email)

        if health.trend == "cooling":
            name = health.contact_name or contact_email.split("@")[0]
            return (
                f"{name} hasn't emailed in {health.days_since_last} days "
                f"(usually weekly). I kept the tone warm and suggested reconnecting."
            )

        if health.trend == "warming":
            return (
                f"Communication is heating up — {health.recent_count} emails "
                f"this week vs {health.prior_count} prior."
            )

        if health.needs_reply_count > 2:
            return (
                f"There are {health.needs_reply_count} emails from this contact "
                f"awaiting replies."
            )

        return None


# ---------------------------------------------------------------------------
# Singleton Access
# ---------------------------------------------------------------------------

_service: EmailRelationshipHealth | None = None


def get_email_relationship_health() -> EmailRelationshipHealth:
    """Get or create the EmailRelationshipHealth singleton.

    Returns:
        The EmailRelationshipHealth singleton instance.
    """
    global _service
    if _service is None:
        _service = EmailRelationshipHealth()
    return _service
