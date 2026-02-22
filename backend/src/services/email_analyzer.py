"""Email inbox analyzer for categorizing and triaging incoming emails.

Scans a user's inbox via Composio (Gmail or Outlook), categorizes each email
using rule-based fast-path checks and LLM classification, detects urgency,
and logs every decision to email_scan_log for full transparency.

Callable as a service from:
- Scheduled jobs (nightly / hourly)
- Morning briefing generation
- User request ("ARIA, check my email")
"""

import json
import logging
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from src.core.llm import LLMClient
from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class EmailCategory(BaseModel):
    """A categorized email with classification metadata."""

    email_id: str
    thread_id: str
    sender_email: str
    sender_name: str
    subject: str
    snippet: str  # first 200 chars of body
    category: str  # NEEDS_REPLY, FYI, SKIP
    urgency: str  # URGENT, NORMAL, LOW
    topic_summary: str
    sender_relationship: dict[str, Any] | None = None  # from memory_semantic
    needs_draft: bool = False
    reason: str  # why this categorization


class EmailScanResult(BaseModel):
    """Summary of an inbox scan run."""

    scan_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    total_emails: int = 0
    needs_reply: list[EmailCategory] = Field(default_factory=list)
    fyi: list[EmailCategory] = Field(default_factory=list)
    skipped: list[EmailCategory] = Field(default_factory=list)
    urgent: list[EmailCategory] = Field(default_factory=list)  # subset of needs_reply


# Automated / no-reply sender patterns
_NOREPLY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^no[-_.]?reply@", re.IGNORECASE),
    re.compile(r"^do[-_.]?not[-_.]?reply@", re.IGNORECASE),
    re.compile(r"^notifications?@", re.IGNORECASE),
    re.compile(r"^mailer[-_.]?daemon@", re.IGNORECASE),
    re.compile(r"^postmaster@", re.IGNORECASE),
    re.compile(r"^bounce[s]?@", re.IGNORECASE),
    re.compile(r"^auto[-_.]?confirm@", re.IGNORECASE),
]

# Newsletter / mailing-list header indicators
_LIST_HEADERS = {"list-unsubscribe", "list-id", "x-mailchimp-id", "x-campaign-id"}

# Calendar response subject patterns
_CALENDAR_SUBJECT_PATTERNS = [
    "accepted:", "declined:", "tentative:", "canceled:", "cancelled:",
    "updated invitation:", "invitation:", "reminder:",
    "meeting request:", "meeting response:",
]

# Junk/spam notification patterns
_JUNK_PATTERNS = [
    "not junk:", "junk email:", "spam notification:",
    "quarantine notification:", "message blocked:",
    "delivery status notification", "undeliverable:",
    "mail delivery failed", "failure notice",
    "returned mail:", "mailer-daemon",
]

# Bounce/undeliverable indicators
_BOUNCE_INDICATORS = [
    "undeliverable", "delivery failed", "returned mail",
    "failure notice", "delivery status", "mail delivery subsystem",
]

# Read/delivery receipt patterns
_RECEIPT_PATTERNS = [
    "read:", "read receipt:", "delivery receipt:", "disposition-notification",
]


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class EmailAnalyzer:
    """Analyzes inbox emails for categorization, urgency, and draft needs.

    Fetches real emails via Composio OAuth, classifies with LLM, respects
    privacy exclusions, and logs every decision to email_scan_log.
    """

    def __init__(self) -> None:
        """Initialize with database and LLM clients."""
        self._db = SupabaseClient.get_client()
        self._llm = LLMClient()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def scan_inbox(
        self,
        user_id: str,
        since_hours: int = 24,
    ) -> EmailScanResult:
        """Scan inbox for new emails since last check.

        Args:
            user_id: The authenticated user's ID.
            since_hours: How far back to look for emails (default 24h).

        Returns:
            EmailScanResult with categorized lists.
        """
        result = EmailScanResult()

        logger.info(
            "EMAIL_ANALYZER: Starting inbox scan for user %s (last %d hours)",
            user_id,
            since_hours,
        )

        try:
            # 1. Load privacy exclusions
            exclusions = await self._load_exclusions(user_id)
            logger.info(
                "EMAIL_ANALYZER: Loaded %d privacy exclusions for user %s",
                len(exclusions),
                user_id,
            )

            # 2. Fetch inbox emails
            emails = await self._fetch_inbox_emails(user_id, since_hours=since_hours)
            result.total_emails = len(emails)
            logger.info(
                "EMAIL_ANALYZER: Fetched %d inbox emails for user %s",
                len(emails),
                user_id,
            )

            if not emails:
                logger.info("EMAIL_ANALYZER: No emails found for user %s", user_id)
                return result

            # 3. Categorize each email
            for email in emails:
                try:
                    categorized = await self.categorize_email(email, user_id, exclusions)

                    # Route to appropriate bucket
                    if categorized.category == "NEEDS_REPLY":
                        result.needs_reply.append(categorized)
                        if categorized.urgency == "URGENT":
                            result.urgent.append(categorized)
                    elif categorized.category == "FYI":
                        result.fyi.append(categorized)
                    else:
                        result.skipped.append(categorized)

                    # 4. Log decision to email_scan_log
                    await self._log_scan_decision(user_id, categorized)

                except Exception as e:
                    logger.warning(
                        "EMAIL_ANALYZER: Failed to categorize email %s: %s",
                        email.get("id", "unknown"),
                        e,
                    )

            logger.info(
                "EMAIL_ANALYZER: Scan complete for user %s — "
                "%d needs_reply (%d urgent), %d fyi, %d skipped",
                user_id,
                len(result.needs_reply),
                len(result.urgent),
                len(result.fyi),
                len(result.skipped),
            )

            return result

        except Exception as e:
            logger.error(
                "EMAIL_ANALYZER: Inbox scan failed for user %s: %s",
                user_id,
                e,
                exc_info=True,
            )
            return result

    async def categorize_email(
        self,
        email: dict[str, Any],
        user_id: str,
        exclusions: list[dict[str, Any]] | None = None,
    ) -> EmailCategory:
        """Categorize a single email using rules + LLM.

        Args:
            email: Raw email dict from Composio.
            user_id: The user's ID.
            exclusions: Pre-loaded privacy exclusions (loaded if None).

        Returns:
            EmailCategory with classification and reasoning.
        """
        sender_email = self._extract_sender_email(email)
        sender_name = self._extract_sender_name(email)
        subject = email.get("subject", "(no subject)")
        body = email.get("body", email.get("snippet", ""))
        snippet = body[:200] if body else ""
        email_id = email.get("id", email.get("message_id", str(uuid.uuid4())))
        thread_id = email.get("thread_id", email.get("conversationId", email_id))

        # Load exclusions if not provided
        if exclusions is None:
            exclusions = await self._load_exclusions(user_id)

        # ---- Rule-based fast path (no LLM needed) ----

        # Privacy exclusion check
        if self._is_excluded(sender_email, exclusions):
            return EmailCategory(
                email_id=email_id,
                thread_id=thread_id,
                sender_email=sender_email,
                sender_name=sender_name,
                subject=subject,
                snippet=snippet,
                category="SKIP",
                urgency="LOW",
                topic_summary="Privacy-excluded sender",
                needs_draft=False,
                reason=f"Sender {sender_email} matches privacy exclusion rules",
            )

        # No-reply / automated sender check
        if self._is_noreply(sender_email):
            return EmailCategory(
                email_id=email_id,
                thread_id=thread_id,
                sender_email=sender_email,
                sender_name=sender_name,
                subject=subject,
                snippet=snippet,
                category="SKIP",
                urgency="LOW",
                topic_summary="Automated / no-reply sender",
                needs_draft=False,
                reason=f"Sender {sender_email} is an automated no-reply address",
            )

        # Newsletter / mailing list check
        headers = email.get("headers", {})
        if isinstance(headers, dict) and any(
            h in {k.lower() for k in headers} for h in _LIST_HEADERS
        ):
            return EmailCategory(
                email_id=email_id,
                thread_id=thread_id,
                sender_email=sender_email,
                sender_name=sender_name,
                subject=subject,
                snippet=snippet,
                category="FYI",
                urgency="LOW",
                topic_summary="Newsletter / mailing list",
                needs_draft=False,
                reason="Email contains mailing list headers (List-Unsubscribe or similar)",
            )

        # User is only CC'd check
        user_email = await self._get_user_email(user_id)
        if user_email and self._is_only_cc(email, user_email):
            return EmailCategory(
                email_id=email_id,
                thread_id=thread_id,
                sender_email=sender_email,
                sender_name=sender_name,
                subject=subject,
                snippet=snippet,
                category="FYI",
                urgency="LOW",
                topic_summary="CC'd — not directly addressed",
                needs_draft=False,
                reason="User is only CC'd, not a direct recipient",
            )

        # ---- Additional rule-based filters (Filters 5-10) ----

        # Filter 5: Self-sent detection
        if await self._is_self_sent(email, user_id):
            return EmailCategory(
                email_id=email_id,
                thread_id=thread_id,
                sender_email=sender_email,
                sender_name=sender_name,
                subject=subject,
                snippet=snippet,
                category="SKIP",
                urgency="LOW",
                topic_summary="Self-sent email",
                needs_draft=False,
                reason="Email sent by user to themselves",
            )

        # Filter 6: Calendar responses
        if self._is_calendar_response(email):
            return EmailCategory(
                email_id=email_id,
                thread_id=thread_id,
                sender_email=sender_email,
                sender_name=sender_name,
                subject=subject,
                snippet=snippet,
                category="SKIP",
                urgency="LOW",
                topic_summary="Calendar notification",
                needs_draft=False,
                reason="Automated calendar response/notification",
            )

        # Filter 7: Junk/spam notifications
        if self._is_system_junk_notification(email):
            return EmailCategory(
                email_id=email_id,
                thread_id=thread_id,
                sender_email=sender_email,
                sender_name=sender_name,
                subject=subject,
                snippet=snippet,
                category="SKIP",
                urgency="LOW",
                topic_summary="System junk notification",
                needs_draft=False,
                reason="System junk/spam notification",
            )

        # Filter 8: Bounce/undeliverable
        if self._is_bounce(email):
            return EmailCategory(
                email_id=email_id,
                thread_id=thread_id,
                sender_email=sender_email,
                sender_name=sender_name,
                subject=subject,
                snippet=snippet,
                category="SKIP",
                urgency="LOW",
                topic_summary="Bounce/delivery failure",
                needs_draft=False,
                reason="Delivery failure notification",
            )

        # Filter 9: Read receipts
        if self._is_read_receipt(email):
            return EmailCategory(
                email_id=email_id,
                thread_id=thread_id,
                sender_email=sender_email,
                sender_name=sender_name,
                subject=subject,
                snippet=snippet,
                category="SKIP",
                urgency="LOW",
                topic_summary="Read/delivery receipt",
                needs_draft=False,
                reason="Automated read/delivery receipt",
            )

        # Filter 10: Auto-generated messages
        if self._is_auto_generated(email):
            return EmailCategory(
                email_id=email_id,
                thread_id=thread_id,
                sender_email=sender_email,
                sender_name=sender_name,
                subject=subject,
                snippet=snippet,
                category="SKIP",
                urgency="LOW",
                topic_summary="Auto-generated message",
                needs_draft=False,
                reason="Auto-generated message (rules, forwards, notifications)",
            )

        # ---- LLM classification for remaining emails ----

        # Look up sender in semantic memory
        sender_relationship = await self._lookup_sender_relationship(
            user_id, sender_email
        )

        classification = await self._llm_classify(
            email=email,
            sender_email=sender_email,
            sender_name=sender_name,
            subject=subject,
            body=body,
            sender_relationship=sender_relationship,
        )

        category = classification.get("category", "FYI")
        urgency_from_llm = classification.get("urgency", "NORMAL")
        topic_summary = classification.get("topic_summary", subject)
        needs_draft = classification.get("needs_draft", False)
        reason = classification.get("reason", "LLM classification")

        # Override urgency with signal-based detection
        urgency = await self.detect_urgency(email, user_id)
        # Take the more urgent of LLM vs signal-based
        urgency_rank = {"URGENT": 3, "NORMAL": 2, "LOW": 1}
        if urgency_rank.get(urgency, 0) < urgency_rank.get(urgency_from_llm, 0):
            urgency = urgency_from_llm

        return EmailCategory(
            email_id=email_id,
            thread_id=thread_id,
            sender_email=sender_email,
            sender_name=sender_name,
            subject=subject,
            snippet=snippet,
            category=category,
            urgency=urgency,
            topic_summary=topic_summary,
            sender_relationship=sender_relationship,
            needs_draft=needs_draft,
            reason=reason,
        )

    async def detect_urgency(
        self,
        email: dict[str, Any],
        user_id: str,
    ) -> str:
        """Detect time-sensitive emails that need immediate attention.

        Checks keyword signals, VIP contacts, calendar proximity,
        overdue responses, and rapid thread activity.

        Args:
            email: Raw email dict.
            user_id: The user's ID.

        Returns:
            Urgency level: URGENT, NORMAL, or LOW.
        """
        subject = email.get("subject", "")
        body = email.get("body", email.get("snippet", ""))
        text = f"{subject} {body}".lower()
        sender_email = self._extract_sender_email(email)

        # Keyword urgency signals
        urgent_keywords = [
            "urgent",
            "asap",
            "by eod",
            "end of day",
            "deadline",
            "immediately",
            "time-sensitive",
            "time sensitive",
            "critical",
            "action required",
            "action needed",
            "response needed",
            "please respond",
            "by tomorrow",
            "by end of week",
            "within the hour",
            "right away",
        ]

        if any(kw in text for kw in urgent_keywords):
            return "URGENT"

        # VIP sender check
        if await self._is_vip_sender(user_id, sender_email):
            return "URGENT"

        # NEW: Calendar proximity check (meeting with sender in next 2 hours)
        if await self._is_sender_in_upcoming_meeting(user_id, sender_email):
            return "URGENT"

        # NEW: Overdue response check (reply to user's email >48 hours ago)
        if await self._is_overdue_response(user_id, email):
            return "URGENT"

        # NEW: Rapid thread activity (3+ rapid back-and-forth in last hour)
        thread_id = email.get("thread_id", email.get("conversationId", ""))
        if thread_id and await self._is_rapid_thread(user_id, thread_id):
            return "URGENT"

        return "NORMAL"

    async def _is_sender_in_upcoming_meeting(
        self,
        user_id: str,
        sender_email: str,
    ) -> bool:
        """Check if sender is in a meeting with user in the next 2 hours.

        Args:
            user_id: The user's ID.
            sender_email: The sender's email address.

        Returns:
            True if sender is in an upcoming meeting within 2 hours.
        """
        try:
            from datetime import timedelta

            now = datetime.now(UTC)
            two_hours_from_now = now + timedelta(hours=2)

            # Query calendar_events for upcoming meetings
            result = (
                self._db.table("calendar_events")
                .select("attendees, start_time")
                .eq("user_id", user_id)
                .gte("start_time", now.isoformat())
                .lte("start_time", two_hours_from_now.isoformat())
                .execute()
            )

            if not result.data:
                return False

            sender_lower = sender_email.lower()

            for event in result.data:
                attendees = event.get("attendees", [])
                if isinstance(attendees, list):
                    for attendee in attendees:
                        if isinstance(attendee, dict):
                            attendee_email = attendee.get("email", "").lower()
                        elif isinstance(attendee, str):
                            attendee_email = attendee.lower()
                        else:
                            continue
                        if sender_lower in attendee_email or attendee_email in sender_lower:
                            logger.info(
                                "EMAIL_ANALYZER: Urgency detected - sender %s in upcoming meeting",
                                sender_email,
                            )
                            return True

            return False

        except Exception as e:
            logger.warning(
                "EMAIL_ANALYZER: Calendar proximity check failed for %s: %s",
                sender_email,
                e,
            )
            return False

    async def _is_overdue_response(
        self,
        user_id: str,
        email: dict[str, Any],
    ) -> bool:
        """Check if this is a reply to user's email sent >48 hours ago.

        Args:
            user_id: The user's ID.
            email: The incoming email dict.

        Returns:
            True if this is an overdue response to user's email.
        """
        try:
            from datetime import timedelta

            # Check if this email is a reply (has In-Reply-To or References header)
            headers = email.get("headers", {})
            if isinstance(headers, dict):
                in_reply_to = headers.get("In-Reply-To", "") or headers.get("References", "")
                if not in_reply_to:
                    return False

            # Look up the original email in email_scan_log
            # Find emails FROM user that this might be a reply to
            user_email = await self._get_user_email(user_id)
            if not user_email:
                return False

            # Check email date
            email_date_str = email.get("date", email.get("received_at", ""))
            if not email_date_str:
                return False

            try:
                # Parse the incoming email date
                if isinstance(email_date_str, str):
                    # Handle ISO format or RFC 2822
                    email_date = datetime.fromisoformat(
                        email_date_str.replace("Z", "+00:00")
                    )
                else:
                    return False
            except (ValueError, TypeError):
                return False

            # Look for a sent email from user >48 hours before this reply
            cutoff_date = email_date - timedelta(hours=48)

            result = (
                self._db.table("email_scan_log")
                .select("created_at, sender_email")
                .eq("user_id", user_id)
                .eq("sender_email", user_email.lower())
                .lte("created_at", cutoff_date.isoformat())
                .order("created_at", desc=True)
                .limit(5)
                .execute()
            )

            if result.data:
                logger.info(
                    "EMAIL_ANALYZER: Urgency detected - overdue response to user's email"
                )
                return True

            return False

        except Exception as e:
            logger.warning(
                "EMAIL_ANALYZER: Overdue response check failed: %s",
                e,
            )
            return False

    async def _is_rapid_thread(
        self,
        user_id: str,
        thread_id: str,
    ) -> bool:
        """Check if there's rapid back-and-forth activity (3+ messages in last hour).

        Args:
            user_id: The user's ID.
            thread_id: The email thread/conversation ID.

        Returns:
            True if 3+ messages in the last hour with different senders.
        """
        try:
            from datetime import timedelta

            one_hour_ago = datetime.now(UTC) - timedelta(hours=1)

            # Query email_scan_log for messages in this thread
            result = (
                self._db.table("email_scan_log")
                .select("sender_email, scanned_at")
                .eq("user_id", user_id)
                .eq("thread_id", thread_id)
                .gte("scanned_at", one_hour_ago.isoformat())
                .order("scanned_at", desc=True)
                .execute()
            )

            if not result.data or len(result.data) < 3:
                return False

            # Check if there are at least 2 different senders (back-and-forth)
            unique_senders = {msg["sender_email"].lower() for msg in result.data}

            if len(unique_senders) >= 2 and len(result.data) >= 3:
                logger.info(
                    "EMAIL_ANALYZER: Urgency detected - rapid thread activity (%d messages, %d senders)",
                    len(result.data),
                    len(unique_senders),
                )
                return True

            return False

        except Exception as e:
            logger.warning(
                "EMAIL_ANALYZER: Rapid thread check failed for thread %s: %s",
                thread_id,
                e,
            )
            return False

    # ------------------------------------------------------------------
    # Email fetching
    # ------------------------------------------------------------------

    async def _fetch_inbox_emails(
        self,
        user_id: str,
        since_hours: int = 24,
    ) -> list[dict[str, Any]]:
        """Fetch inbox emails via Composio.

        Detects the user's email provider (Gmail or Outlook) from
        user_integrations and uses the appropriate Composio action.

        Args:
            user_id: The user whose inbox to fetch.
            since_hours: How many hours of history to fetch.

        Returns:
            List of email dicts.
        """
        try:
            # Get the email integration with connection_id
            # Prefer Outlook as it's more commonly working in enterprise
            # First try Outlook, then fall back to Gmail
            result = (
                self._db.table("user_integrations")
                .select("integration_type, composio_connection_id")
                .eq("user_id", user_id)
                .eq("integration_type", "outlook")
                .limit(1)
                .execute()
            )

            if not result.data:
                # Fall back to Gmail
                result = (
                    self._db.table("user_integrations")
                    .select("integration_type, composio_connection_id")
                    .eq("user_id", user_id)
                    .eq("integration_type", "gmail")
                    .limit(1)
                    .execute()
                )

            if not result or not result.data:
                logger.warning(
                    "EMAIL_ANALYZER: No email integration found for user %s",
                    user_id,
                )
                return []

            integration = result.data[0]
            provider = integration.get("integration_type", "").lower()
            connection_id = integration.get("composio_connection_id")

            if not connection_id:
                logger.warning(
                    "EMAIL_ANALYZER: No connection_id for user %s provider %s",
                    user_id,
                    provider,
                )
                return []

            logger.info(
                "EMAIL_ANALYZER: Detected email provider '%s' for user %s (connection: %s)",
                provider,
                user_id,
                connection_id[:12] + "...",
            )

            from src.integrations.oauth import get_oauth_client

            oauth_client = get_oauth_client()

            since_date = (datetime.now(UTC) - timedelta(hours=since_hours)).isoformat()

            if provider == "outlook":
                logger.info(
                    "EMAIL_ANALYZER: Using OUTLOOK_GET_MAIL_DELTA for user %s",
                    user_id,
                )
                response = oauth_client.execute_action_sync(
                    connection_id=connection_id,
                    action="OUTLOOK_GET_MAIL_DELTA",
                    params={
                        "$top": 200,
                    },
                    user_id=user_id,
                )
                # Outlook returns messages in 'data.value'
                if response.get("successful") and response.get("data"):
                    raw_emails = response["data"].get("value", [])
                    # Normalize Outlook format to match Gmail-style dict
                    emails = []
                    for msg in raw_emails:
                        from_addr = msg.get("from", {}).get("emailAddress", {})
                        body_content = msg.get("body", {}).get("content", "")
                        emails.append({
                            "id": msg.get("id"),
                            "message_id": msg.get("internetMessageId"),
                            "thread_id": msg.get("conversationId"),
                            "subject": msg.get("subject", "(no subject)"),
                            "body": body_content,
                            "snippet": msg.get("bodyPreview", body_content[:200] if body_content else ""),
                            "sender_email": from_addr.get("address", ""),
                            "sender_name": from_addr.get("name", ""),
                            "date": msg.get("receivedDateTime", ""),
                        })
                else:
                    logger.warning(
                        "EMAIL_ANALYZER: Outlook fetch failed: %s",
                        response.get("error"),
                    )
                    emails = []
            else:
                # Default to Gmail
                logger.info(
                    "EMAIL_ANALYZER: Using GMAIL_FETCH_EMAILS for user %s",
                    user_id,
                )
                response = oauth_client.execute_action_sync(
                    connection_id=connection_id,
                    action="GMAIL_FETCH_EMAILS",
                    params={
                        "label": "INBOX",
                        "max_results": 200,
                    },
                    user_id=user_id,
                )
                # Gmail returns emails in 'data.emails'
                if response.get("successful") and response.get("data"):
                    emails = response["data"].get("emails", [])
                else:
                    logger.warning(
                        "EMAIL_ANALYZER: Gmail fetch failed: %s",
                        response.get("error"),
                    )
                    emails = []

            logger.info(
                "EMAIL_ANALYZER: Composio returned %d inbox emails for user %s",
                len(emails),
                user_id,
            )
            return emails

        except Exception as e:
            logger.error(
                "EMAIL_ANALYZER: Inbox fetch failed for user %s: %s",
                user_id,
                e,
                exc_info=True,
            )
            return []

    # ------------------------------------------------------------------
    # Privacy exclusions
    # ------------------------------------------------------------------

    async def _load_exclusions(self, user_id: str) -> list[dict[str, Any]]:
        """Load privacy exclusions from user settings.

        Args:
            user_id: The user whose exclusions to load.

        Returns:
            List of exclusion dicts with 'type' and 'value' keys.
        """
        result = (
            self._db.table("user_settings")
            .select("integrations")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if result and result.data:
            data: dict[str, Any] = result.data  # type: ignore[assignment]
            email_config = data.get("integrations", {}).get("email", {})
            return email_config.get("privacy_exclusions", [])
        return []

    def _is_excluded(
        self,
        sender_email: str,
        exclusions: list[dict[str, Any]],
    ) -> bool:
        """Check if a sender matches any privacy exclusion.

        Args:
            sender_email: The sender's email address.
            exclusions: The user's privacy exclusion rules.

        Returns:
            True if the sender should be excluded.
        """
        addr = sender_email.lower()
        domain = addr.split("@")[-1] if "@" in addr else ""

        for exc in exclusions:
            exc_type = exc.get("type", "")
            exc_value = exc.get("value", "").lower()

            if exc_type == "sender" and addr == exc_value:
                return True
            if exc_type == "domain" and domain == exc_value:
                return True

        return False

    # ------------------------------------------------------------------
    # Rule-based helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_noreply(sender_email: str) -> bool:
        """Check if sender is an automated no-reply address."""
        return any(p.match(sender_email) for p in _NOREPLY_PATTERNS)

    @staticmethod
    def _is_only_cc(email: dict[str, Any], user_email: str) -> bool:
        """Check if the user is only CC'd, not a direct recipient.

        Args:
            email: Raw email dict.
            user_email: The user's own email address.

        Returns:
            True if user appears in CC but not in To.
        """
        to_addrs = email.get("to", [])
        cc_addrs = email.get("cc", [])

        user_lower = user_email.lower()

        def _in_list(addr_list: Any, target: str) -> bool:
            if not addr_list:
                return False
            for r in addr_list:
                addr = r.lower() if isinstance(r, str) else r.get("email", "").lower()
                if addr == target:
                    return True
            return False

        in_to = _in_list(to_addrs, user_lower)
        in_cc = _in_list(cc_addrs, user_lower)

        return not in_to and in_cc

    # ------------------------------------------------------------------
    # Additional rule-based filters (Filters 5-10)
    # ------------------------------------------------------------------

    async def _is_self_sent(self, email: dict[str, Any], user_id: str) -> bool:
        """Skip emails sent by the user themselves.

        Args:
            email: Raw email dict.
            user_id: The user's ID.

        Returns:
            True if the email is from the user to themselves.
        """
        sender = self._extract_sender_email(email)
        if not sender:
            return False

        # Get user's own email addresses from user_integrations
        try:
            integrations = (
                self._db.table("user_integrations")
                .select("account_email")
                .eq("user_id", user_id)
                .execute()
            )
            user_emails = {
                i["account_email"].lower()
                for i in integrations.data
                if i.get("account_email")
            }

            # Also check the user_profiles table for primary email
            profile = (
                self._db.table("user_profiles")
                .select("email")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
            if profile.data and profile.data.get("email"):
                user_emails.add(profile.data["email"].lower())

            # Also check auth email
            auth_email = await self._get_user_email(user_id)
            if auth_email:
                user_emails.add(auth_email.lower())

            if sender in user_emails:
                logger.info(
                    "SKIP_SELF_SENT: %s from %s",
                    email.get("id", "unknown"),
                    sender,
                )
                return True

        except Exception as e:
            logger.warning(
                "EMAIL_ANALYZER: Self-sent check failed for %s: %s",
                sender,
                e,
            )

        return False

    def _is_calendar_response(self, email: dict[str, Any]) -> bool:
        """Skip automated calendar notifications.

        Args:
            email: Raw email dict.

        Returns:
            True if the email is a calendar response/notification.
        """
        subject = (email.get("subject") or "").lower().strip()

        # Check subject line patterns
        for pattern in _CALENDAR_SUBJECT_PATTERNS:
            if subject.startswith(pattern):
                logger.info(
                    "SKIP_CALENDAR: %s subject=%s",
                    email.get("id", "unknown"),
                    subject,
                )
                return True

        # Check content-type for text/calendar
        content_type = email.get("contentType", "") or email.get("content_type", "")
        if "calendar" in content_type.lower():
            logger.info(
                "SKIP_CALENDAR: %s (calendar content-type)",
                email.get("id", "unknown"),
            )
            return True

        # Check for iCalendar attachment indicators in body
        body = email.get("body", "")
        if isinstance(body, dict):
            body = body.get("content", "")
        if "BEGIN:VCALENDAR" in body:
            logger.info(
                "SKIP_CALENDAR: %s (iCalendar content)",
                email.get("id", "unknown"),
            )
            return True

        return False

    def _is_system_junk_notification(self, email: dict[str, Any]) -> bool:
        """Skip Outlook/Gmail junk reclassification and spam notifications.

        Args:
            email: Raw email dict.

        Returns:
            True if the email is a junk/spam system notification.
        """
        subject = (email.get("subject") or "").lower()
        sender = self._extract_sender_email(email)

        for pattern in _JUNK_PATTERNS:
            if pattern in subject:
                logger.info(
                    "SKIP_JUNK_NOTIFICATION: %s subject=%s",
                    email.get("id", "unknown"),
                    subject,
                )
                return True

        # Common system senders
        system_senders = [
            "postmaster@",
            "mailer-daemon@",
            "no-reply@microsoft.com",
            "noreply@google.com",
            "outlook-noreply@",
        ]
        for sys_sender in system_senders:
            if sender.startswith(sys_sender) or sys_sender in sender:
                logger.info(
                    "SKIP_JUNK_NOTIFICATION: %s from system sender %s",
                    email.get("id", "unknown"),
                    sender,
                )
                return True

        return False

    def _is_bounce(self, email: dict[str, Any]) -> bool:
        """Skip delivery failure notifications.

        Args:
            email: Raw email dict.

        Returns:
            True if the email is a bounce/delivery failure.
        """
        subject = (email.get("subject") or "").lower()
        sender = self._extract_sender_email(email)

        is_bounce = (
            any(b in subject for b in _BOUNCE_INDICATORS)
            or "mailer-daemon" in sender
            or "postmaster" in sender
        )

        if is_bounce:
            logger.info(
                "SKIP_BOUNCE: %s subject=%s sender=%s",
                email.get("id", "unknown"),
                subject,
                sender,
            )

        return is_bounce

    def _is_read_receipt(self, email: dict[str, Any]) -> bool:
        """Skip read/delivery receipts.

        Args:
            email: Raw email dict.

        Returns:
            True if the email is a read/delivery receipt.
        """
        subject = (email.get("subject") or "").lower()

        for pattern in _RECEIPT_PATTERNS:
            if pattern in subject:
                logger.info(
                    "SKIP_READ_RECEIPT: %s subject=%s",
                    email.get("id", "unknown"),
                    subject,
                )
                return True

        return False

    def _is_auto_generated(self, email: dict[str, Any]) -> bool:
        """Skip auto-generated emails (rules, forwards, notifications).

        Args:
            email: Raw email dict.

        Returns:
            True if the email is auto-generated.
        """
        # Check internetMessageHeaders (Outlook format)
        headers = email.get("internetMessageHeaders", [])
        if headers:
            for header in headers:
                name = (header.get("name") or "").lower()
                value = (header.get("value") or "").lower()
                if name == "auto-submitted" and value != "no":
                    logger.info(
                        "SKIP_AUTO_GENERATED: %s (auto-submitted header)",
                        email.get("id", "unknown"),
                    )
                    return True
                if name == "x-auto-response-suppress":
                    logger.info(
                        "SKIP_AUTO_GENERATED: %s (x-auto-response-suppress header)",
                        email.get("id", "unknown"),
                    )
                    return True
                if name == "precedence" and value in ("bulk", "junk", "list"):
                    logger.info(
                        "SKIP_AUTO_GENERATED: %s (precedence=%s)",
                        email.get("id", "unknown"),
                        value,
                    )
                    return True

        # Also check standard headers dict (Gmail format)
        headers_dict = email.get("headers", {})
        if isinstance(headers_dict, dict):
            for name, value in headers_dict.items():
                name_lower = name.lower()
                value_lower = (value or "").lower()
                if name_lower == "auto-submitted" and value_lower != "no":
                    logger.info(
                        "SKIP_AUTO_GENERATED: %s (auto-submitted header)",
                        email.get("id", "unknown"),
                    )
                    return True
                if name_lower == "x-auto-response-suppress":
                    logger.info(
                        "SKIP_AUTO_GENERATED: %s (x-auto-response-suppress header)",
                        email.get("id", "unknown"),
                    )
                    return True
                if name_lower == "precedence" and value_lower in ("bulk", "junk", "list"):
                    logger.info(
                        "SKIP_AUTO_GENERATED: %s (precedence=%s)",
                        email.get("id", "unknown"),
                        value_lower,
                    )
                    return True

        return False

    async def _get_user_email(self, user_id: str) -> str | None:
        """Get the user's email address from Supabase Auth.

        Args:
            user_id: The user's ID.

        Returns:
            The user's email address, or None if not found.
        """
        try:
            result = self._db.auth.admin.get_user_by_id(user_id)
            if result.user and result.user.email:
                return result.user.email
        except Exception as e:
            logger.warning(
                "EMAIL_ANALYZER: Failed to get user email for %s: %s", user_id, e
            )
        return None

    # ------------------------------------------------------------------
    # Sender memory lookup
    # ------------------------------------------------------------------

    async def _lookup_sender_relationship(
        self,
        user_id: str,
        sender_email: str,
    ) -> dict[str, Any] | None:
        """Look up sender in semantic memory for existing relationship context.

        Args:
            user_id: The user's ID.
            sender_email: The sender's email address.

        Returns:
            Relationship dict if found, None otherwise.
        """
        try:
            result = (
                self._db.table("memory_semantic")
                .select("fact, confidence, metadata")
                .eq("user_id", user_id)
                .ilike("fact", f"%{sender_email}%")
                .limit(5)
                .execute()
            )

            if result and result.data:
                # Return the most relevant match
                for row in result.data:
                    metadata_raw = row.get("metadata")
                    if metadata_raw:
                        metadata = (
                            json.loads(metadata_raw)
                            if isinstance(metadata_raw, str)
                            else metadata_raw
                        )
                        if metadata.get("email", "").lower() == sender_email.lower():
                            return {
                                "fact": row.get("fact"),
                                "confidence": row.get("confidence"),
                                "relationship_type": metadata.get("relationship_type"),
                                "company": metadata.get("company"),
                                "title": metadata.get("title"),
                                "interaction_count": metadata.get("interaction_count"),
                            }

                # If no exact email match, return first partial match
                first = result.data[0]
                return {
                    "fact": first.get("fact"),
                    "confidence": first.get("confidence"),
                }

        except Exception as e:
            logger.warning(
                "EMAIL_ANALYZER: Sender lookup failed for %s: %s", sender_email, e
            )

        return None

    # ------------------------------------------------------------------
    # VIP detection
    # ------------------------------------------------------------------

    async def _is_vip_sender(self, user_id: str, sender_email: str) -> bool:
        """Check if a sender is a VIP based on user settings or top contacts.

        Args:
            user_id: The user's ID.
            sender_email: The sender's email address.

        Returns:
            True if the sender is a VIP.
        """
        try:
            # Check user_settings for VIP list
            result = (
                self._db.table("user_settings")
                .select("preferences")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
            if result and result.data:
                prefs = result.data.get("preferences", {})
                if isinstance(prefs, dict):
                    vip_contacts = prefs.get("vip_contacts", [])
                    if sender_email.lower() in [
                        v.lower() for v in vip_contacts if isinstance(v, str)
                    ]:
                        return True

            # Check if sender is a high-interaction contact from semantic memory
            relationship = await self._lookup_sender_relationship(
                user_id, sender_email
            )
            if relationship and relationship.get("interaction_count", 0) >= 10:
                return True

        except Exception as e:
            logger.warning(
                "EMAIL_ANALYZER: VIP check failed for %s: %s", sender_email, e
            )

        return False

    # ------------------------------------------------------------------
    # LLM classification
    # ------------------------------------------------------------------

    async def _llm_classify(
        self,
        email: dict[str, Any],
        sender_email: str,
        sender_name: str,
        subject: str,
        body: str,
        sender_relationship: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Use LLM to classify an email.

        Args:
            email: Raw email dict.
            sender_email: Extracted sender email.
            sender_name: Extracted sender name.
            subject: Email subject.
            body: Email body text.
            sender_relationship: Known relationship context (or None).

        Returns:
            Dict with category, urgency, topic_summary, needs_draft, reason.
        """
        # Truncate body for prompt efficiency
        body_truncated = body[:2000] if body else "(empty body)"

        relationship_context = ""
        if sender_relationship:
            rel_type = sender_relationship.get("relationship_type", "unknown")
            company = sender_relationship.get("company", "unknown")
            interactions = sender_relationship.get("interaction_count", 0)
            relationship_context = (
                f"\nKnown relationship: {rel_type} at {company}, "
                f"{interactions} prior interactions."
            )

        # Check if user is in To or CC
        to_list = email.get("to", [])
        cc_list = email.get("cc", [])
        recipient_context = f"To: {to_list}, CC: {cc_list}"

        prompt = (
            "Classify this email for a life sciences commercial professional.\n\n"
            f"From: {sender_name} <{sender_email}>\n"
            f"Subject: {subject}\n"
            f"Recipients: {recipient_context}\n"
            f"{relationship_context}\n\n"
            f"Body:\n{body_truncated}\n\n"
            "Classify as exactly one JSON object with these fields:\n"
            "{\n"
            '  "category": "NEEDS_REPLY" | "FYI" | "SKIP",\n'
            '  "urgency": "URGENT" | "NORMAL" | "LOW",\n'
            '  "topic_summary": "1-sentence summary of what this email is about",\n'
            '  "needs_draft": true/false (should ARIA draft a reply?),\n'
            '  "reason": "1-sentence explanation of why this classification"\n'
            "}\n\n"
            "Classification guidelines:\n"
            "- NEEDS_REPLY: Direct question, action requested, from a real person, "
            "part of active thread, meeting follow-up, deal discussion\n"
            "- FYI: Informational, no action needed, internal announcements, "
            "status updates, newsletters\n"
            "- SKIP: Spam, automated notifications, promotional, "
            "system-generated alerts\n"
            "- needs_draft=true only if NEEDS_REPLY and a substantive response is expected\n"
            "- URGENT only for time-sensitive items with explicit deadlines or critical asks\n\n"
            "Return ONLY the JSON object, no other text."
        )

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.0,
            )

            # Parse JSON from response (handle markdown code blocks)
            cleaned = response.strip()
            if cleaned.startswith("```"):
                # Strip markdown code fences
                lines = cleaned.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                cleaned = "\n".join(lines)

            classification: dict[str, Any] = json.loads(cleaned)

            # Validate required fields
            if "category" not in classification:
                classification["category"] = "FYI"
            if classification["category"] not in ("NEEDS_REPLY", "FYI", "SKIP"):
                classification["category"] = "FYI"
            if "urgency" not in classification:
                classification["urgency"] = "NORMAL"
            if classification["urgency"] not in ("URGENT", "NORMAL", "LOW"):
                classification["urgency"] = "NORMAL"
            if "topic_summary" not in classification:
                classification["topic_summary"] = subject
            if "needs_draft" not in classification:
                classification["needs_draft"] = False
            if "reason" not in classification:
                classification["reason"] = "LLM classification"

            return classification

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(
                "EMAIL_ANALYZER: LLM classification parse failed for %s: %s",
                subject,
                e,
            )
            # Fallback: conservative FYI classification
            return {
                "category": "FYI",
                "urgency": "NORMAL",
                "topic_summary": subject,
                "needs_draft": False,
                "reason": f"LLM response parse failed ({e}), defaulting to FYI",
            }

    # ------------------------------------------------------------------
    # Decision logging
    # ------------------------------------------------------------------

    async def _log_scan_decision(
        self,
        user_id: str,
        categorized: EmailCategory,
    ) -> None:
        """Log a categorization decision to email_scan_log.

        Args:
            user_id: The user's ID.
            categorized: The categorized email.
        """
        try:
            self._db.table("email_scan_log").insert(
                {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "email_id": categorized.email_id,
                    "thread_id": categorized.thread_id,
                    "sender_email": categorized.sender_email,
                    "sender_name": categorized.sender_name,
                    "subject": categorized.subject[:500],
                    "category": categorized.category,
                    "urgency": categorized.urgency,
                    "needs_draft": categorized.needs_draft,
                    "reason": categorized.reason,
                    "scanned_at": datetime.now(UTC).isoformat(),
                }
            ).execute()
        except Exception as e:
            logger.warning(
                "EMAIL_ANALYZER: Failed to log scan decision for email %s: %s",
                categorized.email_id,
                e,
            )

    # ------------------------------------------------------------------
    # Email field extraction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_sender_email(email: dict[str, Any]) -> str:
        """Extract sender email address from various email dict formats.

        Outlook normalization stores the address in 'sender_email', while
        Gmail uses 'from' or 'sender'.  Check all known keys.

        Args:
            email: Raw email dict.

        Returns:
            The sender's email address (lowercased).
        """
        # Check these keys in order — covers Gmail ('from'/'sender')
        # and Outlook-normalized ('sender_email'/'from_email') formats
        for key in ("from", "sender", "sender_email", "from_email"):
            value = email.get(key)
            if not value:
                continue
            if isinstance(value, dict):
                addr = value.get("email", value.get("address", ""))
                if addr:
                    return addr.lower()
            if isinstance(value, str) and value.strip():
                # Handle "Name <email>" format
                match = re.search(r"<([^>]+)>", value)
                if match:
                    return match.group(1).lower()
                return value.strip().lower()
        return ""

    @staticmethod
    def _extract_sender_name(email: dict[str, Any]) -> str:
        """Extract sender display name from various email dict formats.

        Args:
            email: Raw email dict.

        Returns:
            The sender's display name.
        """
        # Check pre-extracted field first (Outlook normalization sets this)
        if email.get("sender_name"):
            return email["sender_name"]
        sender = email.get("from", email.get("sender", ""))
        if isinstance(sender, dict):
            return sender.get("name", sender.get("email", ""))
        if isinstance(sender, str):
            # Handle "Name <email>" format
            match = re.match(r"^([^<]+)<", sender)
            if match:
                return match.group(1).strip()
            return sender
        return ""
