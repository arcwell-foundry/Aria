"""Pre-meeting context service.

Enriches upcoming calendar events with email context so the Communications page
can surface "You have a meeting with X in N hours — here's your latest email
thread" banners.

100% DYNAMIC — no hardcoded meetings, contacts, or calendar event IDs.
Everything derived from each user's live data at query time.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from src.db.supabase import SupabaseClient
from src.utils.email_pipeline_linker import get_pipeline_context_for_email

logger = logging.getLogger(__name__)


def _format_time_until(meeting_time: datetime) -> str:
    """Return a human-readable string like '2 hours' or '35 minutes'.

    Args:
        meeting_time: The meeting start time (must be in UTC).

    Returns:
        Human-readable relative time string.
    """
    now = datetime.now(UTC)
    delta = meeting_time - now
    total_minutes = max(int(delta.total_seconds() / 60), 0)

    if total_minutes < 1:
        return "now"
    if total_minutes < 60:
        return f"{total_minutes} minute{'s' if total_minutes != 1 else ''}"
    hours = total_minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''}"
    days = hours // 24
    return f"{days} day{'s' if days != 1 else ''}"


def _format_relative_date(iso_date: str) -> str:
    """Return a relative date string like '5d ago' or '2h ago'.

    Args:
        iso_date: ISO-format datetime string.

    Returns:
        Short relative date string.
    """
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        now = datetime.now(UTC)
        delta = now - dt
        total_minutes = int(delta.total_seconds() / 60)

        if total_minutes < 1:
            return "just now"
        if total_minutes < 60:
            return f"{total_minutes}m ago"
        hours = total_minutes // 60
        if hours < 24:
            return f"{hours}h ago"
        days = hours // 24
        if days < 30:
            return f"{days}d ago"
        return dt.strftime("%b %d")
    except (ValueError, TypeError):
        return ""


class PreMeetingContextService:
    """Enriches upcoming calendar events with email communication context."""

    def __init__(self) -> None:
        self._db = SupabaseClient.get_client()

    async def get_upcoming_meetings_with_context(
        self,
        user_id: str,
        hours_ahead: int = 24,
        user_email: str | None = None,
    ) -> list[dict[str, Any]]:
        """Find meetings in the next N hours and enrich with email context.

        For each upcoming meeting:
        1. Get calendar events from calendar_events table
        2. Extract attendee emails (excluding the user's own email)
        3. Match against email_scan_log and email_drafts
        4. Enrich with pipeline context

        Only returns meetings where ARIA can add value (i.e., there is email
        context for at least one external attendee).

        Args:
            user_id: The user's UUID.
            hours_ahead: How many hours ahead to look for meetings.
            user_email: The authenticated user's email (from auth token).

        Returns:
            List of enriched meeting dicts with email context.
            Empty list if no calendar data or no email context found.
        """
        # Step 1: Get upcoming calendar events
        events = await self._get_upcoming_events(user_id, hours_ahead)
        if not events:
            return []

        # Build set of user's emails to exclude from attendee matching.
        # Primary source: the auth token email passed from the route handler.
        # Supplementary: any connected integration emails.
        user_emails = await self._get_user_emails(user_id, user_email)
        logger.info(
            "[MEETING-CONTEXT] user_id=%s, user_emails_to_exclude=%s",
            user_id,
            user_emails,
        )

        # Step 2-4: Enrich each event with email context
        enriched: list[dict[str, Any]] = []
        for event in events:
            meeting_result = await self._enrich_event(user_id, event, user_emails)
            if meeting_result is not None:
                enriched.append(meeting_result)

        return enriched

    async def _get_user_emails(
        self,
        user_id: str,
        user_email: str | None = None,
    ) -> set[str]:
        """Get the authenticated user's email addresses to exclude from attendee matching.

        Primary source is the auth token email passed from the route handler.
        Supplementary source is connected integration emails.

        Args:
            user_id: The user's UUID.
            user_email: The user's email from the auth token (most reliable).

        Returns:
            Set of lowercase email addresses belonging to the user.
        """
        emails: set[str] = set()

        # Primary: use the email from the auth token (always available)
        if user_email:
            emails.add(user_email.lower().strip())

        # Supplementary: check user_integrations for connected email accounts
        try:
            integrations = (
                self._db.table("user_integrations")
                .select("metadata")
                .eq("user_id", user_id)
                .in_("integration_type", ["gmail", "outlook"])
                .eq("status", "active")
                .execute()
            )
            for row in integrations.data or []:
                meta = row.get("metadata") or {}
                if isinstance(meta, dict) and meta.get("email"):
                    emails.add(str(meta["email"]).lower().strip())
        except Exception:
            logger.debug("Failed to get integration emails for attendee filtering", exc_info=True)

        return emails

    async def _get_upcoming_events(
        self,
        user_id: str,
        hours_ahead: int,
    ) -> list[dict[str, Any]]:
        """Fetch upcoming calendar events within the lookahead window.

        Args:
            user_id: The user's UUID.
            hours_ahead: Hours to look ahead.

        Returns:
            List of raw calendar event rows.
        """
        now = datetime.now(UTC)
        cutoff = now + timedelta(hours=hours_ahead)

        try:
            result = (
                self._db.table("calendar_events")
                .select("id, title, start_time, end_time, attendees, source, metadata")
                .eq("user_id", user_id)
                .gte("start_time", now.isoformat())
                .lte("start_time", cutoff.isoformat())
                .order("start_time", desc=False)
                .limit(20)
                .execute()
            )
            return result.data or []
        except Exception:
            logger.exception(
                "Failed to fetch upcoming calendar events",
                extra={"user_id": user_id},
            )
            return []

    async def _enrich_event(
        self,
        user_id: str,
        event: dict[str, Any],
        user_emails: set[str] | None = None,
    ) -> dict[str, Any] | None:
        """Enrich a single calendar event with email context.

        Returns None if no email context is available for any external attendee
        (i.e., ARIA can't add value for this meeting).

        Args:
            user_id: The user's UUID.
            event: Raw calendar event row.
            user_emails: Set of the user's own email addresses to exclude
                from attendee matching. If None, no filtering is applied.

        Returns:
            Enriched meeting dict or None.
        """
        attendees_raw = event.get("attendees") or []
        if not attendees_raw:
            return None

        # Attendees are stored as a list of email strings
        attendee_emails: list[str] = []
        for att in attendees_raw:
            if isinstance(att, str) and "@" in att:
                attendee_emails.append(att.lower().strip())
            elif isinstance(att, dict) and att.get("email"):
                attendee_emails.append(str(att["email"]).lower().strip())

        if not attendee_emails:
            return None

        # Exclude the user's own email(s) from attendee matching.
        # This prevents the user's email from dominating the email context
        # (since it matches ALL meetings and has the most email history).
        if user_emails:
            external_emails = [e for e in attendee_emails if e not in user_emails]
        else:
            external_emails = list(attendee_emails)

        # Parse meeting time
        start_time_str = event.get("start_time", "")
        try:
            meeting_time = datetime.fromisoformat(
                start_time_str.replace("Z", "+00:00")
            )
        except (ValueError, TypeError):
            return None

        # Build attendee context — find email history for each EXTERNAL attendee
        attendees_with_context: list[dict[str, Any]] = []
        best_email_context: dict[str, Any] | None = None

        for email in external_emails:
            email_ctx = await self._get_email_context_for_contact(user_id, email)
            if email_ctx is not None:
                name = email_ctx.pop("contact_name", None) or email.split("@")[0]
                attendee_info: dict[str, Any] = {"name": name, "email": email}
                attendees_with_context.append(attendee_info)

                # Keep the richest email context (most emails)
                if best_email_context is None or (
                    email_ctx.get("total_emails", 0)
                    > best_email_context.get("total_emails", 0)
                ):
                    best_email_context = email_ctx

        meeting_title = event.get("title") or "Meeting"
        best_contact = best_email_context.get("contact_email") if best_email_context else None
        best_count = best_email_context.get("total_emails", 0) if best_email_context else 0
        logger.info(
            "[MEETING-CONTEXT] Meeting '%s': attendees=%s, external_attendees=%s, best_contact=%s, email_count=%d",
            meeting_title,
            attendee_emails,
            external_emails,
            best_contact,
            best_count,
        )

        # Only return meetings where we have email context for external attendees
        if best_email_context is None:
            return None

        # Include all attendees (including user) for display, but email context
        # is from external attendees only
        all_attendees = attendees_with_context or [
            {"name": e.split("@")[0], "email": e} for e in external_emails
        ]

        return {
            "meeting_id": event.get("id"),
            "meeting_title": event.get("title") or "Meeting",
            "meeting_time": start_time_str,
            "time_until": _format_time_until(meeting_time),
            "attendees": all_attendees,
            "email_context": best_email_context,
        }

    async def _get_email_context_for_contact(
        self,
        user_id: str,
        contact_email: str,
    ) -> dict[str, Any] | None:
        """Get email communication context for a specific contact.

        Checks:
        1. email_scan_log for received emails from this contact
        2. email_drafts for pending/sent drafts to this contact
        3. Pipeline context from email_pipeline_linker

        Args:
            user_id: The user's UUID.
            contact_email: The contact's email address.

        Returns:
            Dict with email context or None if no communications found.
        """
        contact_email_lower = contact_email.lower().strip()
        total_emails = 0
        latest_subject: str | None = None
        latest_date: str | None = None
        latest_date_relative: str | None = None
        contact_name: str | None = None

        # 1. Check email_scan_log for received emails
        try:
            scan_result = (
                self._db.table("email_scan_log")
                .select("subject, scanned_at, sender_email")
                .eq("user_id", user_id)
                .eq("sender_email", contact_email_lower)
                .order("scanned_at", desc=True)
                .limit(10)
                .execute()
            )
            if scan_result.data:
                total_emails += len(scan_result.data)
                latest = scan_result.data[0]
                latest_subject = latest.get("subject")
                latest_date = latest.get("scanned_at")
                latest_date_relative = _format_relative_date(latest_date) if latest_date else None
        except Exception:
            logger.debug(
                "email_scan_log query failed for %s", contact_email_lower,
                exc_info=True,
            )

        # 2. Check email_drafts for drafts/sent to this contact
        has_pending_draft = False
        pending_draft_id: str | None = None

        try:
            drafts_result = (
                self._db.table("email_drafts")
                .select("id, subject, status, created_at, recipient_name")
                .eq("user_id", user_id)
                .eq("recipient_email", contact_email_lower)
                .order("created_at", desc=True)
                .limit(10)
                .execute()
            )
            if drafts_result.data:
                total_emails += len(drafts_result.data)

                # Check for pending drafts
                for draft in drafts_result.data:
                    if draft.get("status") in (
                        "draft",
                        "pending_review",
                    ):
                        has_pending_draft = True
                        pending_draft_id = draft.get("id")
                        break

                # Get contact name from draft if available
                first_draft = drafts_result.data[0]
                if first_draft.get("recipient_name"):
                    contact_name = first_draft["recipient_name"]

                # Check if draft is more recent than scan log entry
                draft_date = first_draft.get("created_at")
                if draft_date and (
                    latest_date is None or draft_date > latest_date
                ):
                    latest_subject = first_draft.get("subject") or latest_subject
                    latest_date = draft_date
                    latest_date_relative = _format_relative_date(draft_date)
        except Exception:
            logger.debug(
                "email_drafts query failed for %s", contact_email_lower,
                exc_info=True,
            )

        if total_emails == 0:
            return None

        # 3. Get pipeline context
        pipeline_context: dict[str, Any] | None = None
        try:
            pipeline_context = await get_pipeline_context_for_email(
                db=self._db,
                user_id=user_id,
                contact_email=contact_email_lower,
            )
        except Exception:
            logger.debug(
                "Pipeline context lookup failed for %s", contact_email_lower,
                exc_info=True,
            )

        return {
            "contact_name": contact_name,
            "contact_email": contact_email_lower,
            "total_emails": total_emails,
            "latest_subject": latest_subject,
            "latest_date": latest_date,
            "latest_date_relative": latest_date_relative,
            "has_pending_draft": has_pending_draft,
            "draft_id": pending_draft_id,
            "pipeline_context": pipeline_context,
        }
