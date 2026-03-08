"""Service for detecting stale email threads that need follow-up."""

import logging
from typing import Any

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


class StaleThread:
    """A stale thread that needs follow-up."""

    def __init__(
        self,
        draft_id: str,
        recipient_name: str | None,
        recipient_email: str,
        subject: str,
        sent_at: str,
        days_since_sent: int,
        urgency: str,
        thread_id: str | None,
    ):
        self.draft_id = draft_id
        self.recipient_name = recipient_name
        self.recipient_email = recipient_email
        self.subject = subject
        self.sent_at = sent_at
        self.days_since_sent = days_since_sent
        self.urgency = urgency
        self.thread_id = thread_id

    @property
    def suggested_action(self) -> str:
        """Generate a human-readable suggested action."""
        if self.urgency == "URGENT":
            return "Follow up urgently"
        elif self.urgency == "LOW":
            return "Check in when convenient"
        return "Consider a gentle follow-up"

    def to_dict(self) -> dict[str, Any]:
        return {
            "draft_id": self.draft_id,
            "recipient_name": self.recipient_name,
            "recipient_email": self.recipient_email,
            "subject": self.subject,
            "sent_at": self.sent_at,
            "days_since_sent": self.days_since_sent,
            "urgency": self.urgency,
            "thread_id": self.thread_id,
            "suggested_action": self.suggested_action,
        }


class FollowupTracker:
    """Detects stale email threads that need follow-up."""

    # Configurable thresholds (days)
    THRESHOLDS = {
        "URGENT": 3,
        "NORMAL": 5,
        "LOW": 7,
    }
    DEFAULT_THRESHOLD_DAYS = 5
    MINIMUM_THRESHOLD_DAYS = 3  # Don't show anything younger than this

    async def get_stale_threads(self, user_id: str) -> list[StaleThread]:
        """Find sent drafts where recipient hasn't replied within threshold.

        Args:
            user_id: The user ID to check stale threads for.

        Returns:
            List of StaleThread objects sorted by days_since_sent DESC.
        """
        try:
            client = SupabaseClient.get_client()

            # Query sent drafts older than minimum threshold with no reply
            # Uses LEFT JOIN to get original email urgency from email_scan_log
            result = client.rpc(
                "get_stale_threads",
                {"p_user_id": user_id}
            ).execute()

            if not result.data:
                return []

            threads = []
            for row in result.data:
                threads.append(StaleThread(
                    draft_id=row["draft_id"],
                    recipient_name=row.get("recipient_name"),
                    recipient_email=row["recipient_email"],
                    subject=row["subject"],
                    sent_at=row["sent_at"],
                    days_since_sent=row["days_since_sent"],
                    urgency=row.get("urgency", "NORMAL"),
                    thread_id=row.get("thread_id"),
                ))

            # Filter by urgency-specific threshold
            filtered = []
            for thread in threads:
                threshold = self.THRESHOLDS.get(thread.urgency, self.DEFAULT_THRESHOLD_DAYS)
                if thread.days_since_sent >= threshold:
                    filtered.append(thread)

            # Sort by days_since_sent DESC
            filtered.sort(key=lambda t: t.days_since_sent, reverse=True)

            logger.info(
                "Found %d stale threads for user %s",
                len(filtered),
                user_id,
            )
            return filtered

        except Exception:
            logger.exception("Failed to get stale threads for user %s", user_id)
            return []


# Singleton instance
_followup_tracker: FollowupTracker | None = None


def get_followup_tracker() -> FollowupTracker:
    """Get or create FollowupTracker singleton."""
    global _followup_tracker
    if _followup_tracker is None:
        _followup_tracker = FollowupTracker()
    return _followup_tracker
