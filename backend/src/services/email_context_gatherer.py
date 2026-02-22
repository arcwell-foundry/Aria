"""Email context gatherer for building complete reply context.

Aggregates context from multiple sources to provide ARIA with everything
needed to draft a contextually-aware email reply:
- Full email thread history
- Recipient research (Exa)
- Corporate memory facts
- Relationship history
- Calendar context
- CRM context

All context is persisted to draft_context table for audit and reuse.
"""

import json
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Context Models
# ---------------------------------------------------------------------------


class ThreadMessage(BaseModel):
    """A single message in an email thread."""

    sender_email: str
    sender_name: str | None = None
    body: str
    timestamp: str
    is_from_user: bool = False  # True if sent by ARIA's user


class ThreadContext(BaseModel):
    """Full thread context for drafting."""

    thread_id: str
    messages: list[ThreadMessage] = Field(default_factory=list)
    summary: str = ""  # LLM-generated summary
    message_count: int = 0


class RecipientResearch(BaseModel):
    """Research results about the email recipient."""

    sender_email: str
    sender_name: str | None = None
    sender_title: str | None = None
    sender_company: str | None = None
    linkedin_url: str | None = None
    bio: str | None = None
    web_mentions: list[dict[str, Any]] = Field(default_factory=list)
    company_description: str | None = None
    company_news: list[dict[str, Any]] = Field(default_factory=list)
    exa_sources_used: list[str] = Field(default_factory=list)


class RelationshipHistory(BaseModel):
    """History of interactions with this contact."""

    sender_email: str
    total_emails: int = 0
    last_interaction: str | None = None
    relationship_type: str = "unknown"  # colleague, client, prospect, vendor
    recent_topics: list[str] = Field(default_factory=list)
    commitments: list[str] = Field(default_factory=list)
    memory_facts: list[dict[str, Any]] = Field(default_factory=list)
    memory_fact_ids: list[str] = Field(default_factory=list)


class CalendarContext(BaseModel):
    """Calendar context related to this contact."""

    connected: bool = False
    upcoming_meetings: list[dict[str, Any]] = Field(default_factory=list)
    recent_meetings: list[dict[str, Any]] = Field(default_factory=list)


class CRMContext(BaseModel):
    """CRM context for this contact."""

    connected: bool = False
    lead_stage: str | None = None
    account_status: str | None = None
    deal_value: float | None = None
    recent_activities: list[dict[str, Any]] = Field(default_factory=list)


class RecipientWritingStyle(BaseModel):
    """Per-recipient writing style profile."""

    exists: bool = False
    formality_level: float = 0.5
    greeting_style: str = ""
    signoff_style: str = ""
    tone: str = "balanced"
    uses_emoji: bool = False
    email_count: int = 0


class CorporateMemoryContext(BaseModel):
    """Relevant facts about user's own company."""

    facts: list[dict[str, Any]] = Field(default_factory=list)
    fact_ids: list[str] = Field(default_factory=list)


class RelationshipHealthContext(BaseModel):
    """Relationship health metrics from email patterns."""

    contact_email: str = ""
    contact_name: str = ""
    total_emails: int = 0
    weekly_frequency: float = 0.0
    trend: str = "stable"  # warming, stable, cooling, new
    trend_detail: str = ""
    days_since_last: int = 0
    health_score: int = 50
    aria_note: str | None = None  # Human-readable context for drafts


class DraftContext(BaseModel):
    """Complete context package for drafting an email reply."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str
    email_id: str
    thread_id: str
    sender_email: str
    subject: str

    # FK to email_drafts (set after draft is saved)
    draft_id: str | None = None

    # All context sections
    thread_context: ThreadContext | None = None
    recipient_research: RecipientResearch | None = None
    recipient_style: RecipientWritingStyle | None = None
    relationship_history: RelationshipHistory | None = None
    relationship_health: RelationshipHealthContext | None = None
    corporate_memory: CorporateMemoryContext | None = None
    calendar_context: CalendarContext | None = None
    crm_context: CRMContext | None = None

    # Source tracking
    sources_used: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_db_dict(self) -> dict[str, Any]:
        """Serialize to database-compatible dictionary."""
        # Extract thread_summary for the separate TEXT column
        thread_summary: str | None = None
        if self.thread_context and self.thread_context.summary:
            thread_summary = self.thread_context.summary

        return {
            "id": self.id,
            "user_id": self.user_id,
            "draft_id": self.draft_id,
            "email_id": self.email_id,
            "thread_id": self.thread_id,
            "sender_email": self.sender_email,
            "subject": self.subject,
            "thread_summary": thread_summary,
            "thread_context": self.thread_context.model_dump() if self.thread_context else None,
            "recipient_research": self.recipient_research.model_dump() if self.recipient_research else None,
            "recipient_style": self.recipient_style.model_dump() if self.recipient_style else None,
            "relationship_history": self.relationship_history.model_dump() if self.relationship_history else None,
            "relationship_health": self.relationship_health.model_dump() if self.relationship_health else None,
            "corporate_memory": self.corporate_memory.model_dump() if self.corporate_memory else None,
            "calendar_context": self.calendar_context.model_dump() if self.calendar_context else None,
            "crm_context": self.crm_context.model_dump() if self.crm_context else None,
            "sources_used": self.sources_used,
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# Service Implementation
# ---------------------------------------------------------------------------


class EmailContextGatherer:
    """Gathers complete context for drafting email replies.

    Aggregates data from:
    - Composio: Full email thread
    - Exa: Recipient research
    - memory_semantic: Relationship history, corporate facts
    - recipient_writing_profiles: Per-recipient style
    - Composio Calendar: Meeting context
    - CRM: Deal/account status
    """

    # Personal/consumer email domains that should NOT trigger company research
    _PERSONAL_DOMAINS = {
        # Google
        "gmail.com", "googlemail.com",
        # Microsoft
        "outlook.com", "outlook.co.uk", "hotmail.com", "hotmail.co.uk",
        "live.com", "live.co.uk", "live.co", "live.ie", "live.ca", "live.au",
        "msn.com",
        # Yahoo
        "yahoo.com", "yahoo.co.uk", "yahoo.ca", "yahoo.au", "yahoo.ie",
        # Apple
        "icloud.com", "me.com", "mac.com",
        # AOL/Verizon
        "aol.com", "comcast.net", "verizon.net", "att.net", "cox.net",
        "sbcglobal.net", "bellsouth.net", "charter.net",
        # Privacy-focused
        "protonmail.com", "proton.me", "tutanota.com", "hey.com",
        # Other common providers
        "zoho.com", "mail.com", "gmx.com", "gmx.net", "yandex.com",
        "fastmail.com",
    }

    def __init__(self) -> None:
        """Initialize with required clients."""
        from src.db.supabase import SupabaseClient

        self._db = SupabaseClient.get_client()

    def _is_personal_email(self, email_address: str) -> bool:
        """Check if email is from a personal/consumer domain.

        Args:
            email_address: The email address to check.

        Returns:
            True if the email domain is a known personal provider.
        """
        if not email_address or "@" not in email_address:
            return False
        domain = email_address.lower().split("@")[-1]
        return domain in self._PERSONAL_DOMAINS

    async def gather_context(
        self,
        user_id: str,
        email_id: str,
        thread_id: str,
        sender_email: str,
        sender_name: str | None,
        subject: str,
    ) -> DraftContext:
        """Build complete context for drafting a reply."""
        context = DraftContext(
            user_id=user_id,
            email_id=email_id,
            thread_id=thread_id,
            sender_email=sender_email,
            subject=subject,
        )

        logger.info(
            "CONTEXT_GATHERER: Starting context gathering for email %s, user %s",
            email_id,
            user_id,
        )

        # 1. Fetch full thread
        context.thread_context = await self._fetch_thread(user_id, thread_id)
        if context.thread_context:
            context.sources_used.append("composio_thread")

        # 1b. Extract commitments from thread (needs thread messages)
        commitments: list[dict[str, Any]] = []
        if context.thread_context and context.thread_context.messages:
            commitments = await self._extract_commitments(
                user_id=user_id,
                thread_messages=context.thread_context.messages,
                sender_name=sender_name,
                sender_email=sender_email,
            )
            if commitments:
                # Store in prospective memory
                await self._store_commitments(
                    user_id=user_id,
                    commitments=commitments,
                    sender_name=sender_name,
                    sender_email=sender_email,
                    email_id=email_id,
                    thread_id=thread_id,
                )
                context.sources_used.append("commitment_extraction")

        # 2. Research recipient via memory + Exa
        context.recipient_research = await self._research_recipient(
            sender_email, sender_name, user_id=user_id
        )
        if context.recipient_research and context.recipient_research.exa_sources_used:
            context.sources_used.append("exa_research")

        # 3. Get per-recipient writing style
        context.recipient_style = await self._get_recipient_style(user_id, sender_email)
        if context.recipient_style and context.recipient_style.exists:
            context.sources_used.append("recipient_style_profile")

        # 4. Get relationship history from memory + profiles + scan log
        context.relationship_history = await self._get_relationship_history(
            user_id, sender_email
        )
        # 4b. Populate commitments into relationship history
        if context.relationship_history and commitments:
            context.relationship_history.commitments = [
                (
                    f"{'You' if c.get('who_committed') == 'user' else (sender_name or sender_email)}"
                    f" committed: {c.get('what', '')}"
                    + (f" (due: {c.get('due_date')})" if c.get("due_date") else "")
                )
                for c in commitments
            ]

        if context.relationship_history and (
            context.relationship_history.memory_facts
            or context.relationship_history.total_emails > 0
            or context.relationship_history.recent_topics
            or context.relationship_history.commitments
        ):
            context.sources_used.append("memory_semantic")

        # 4c. Get relationship health from email patterns
        context.relationship_health = await self._get_relationship_health(
            user_id, sender_email
        )
        if context.relationship_health and context.relationship_health.trend != "new":
            context.sources_used.append("relationship_health")

        # 5. Get corporate memory (search by topic AND sender's company domain)
        context.corporate_memory = await self._get_corporate_memory(
            user_id, subject, sender_email
        )
        if context.corporate_memory and context.corporate_memory.facts:
            context.sources_used.append("corporate_memory")

        # 6. Get calendar context
        context.calendar_context = await self._get_calendar_context(user_id, sender_email)
        if context.calendar_context and context.calendar_context.connected:
            context.sources_used.append("calendar")

        # 7. Get CRM context (with memory fallback if no CRM connected)
        context.crm_context = await self._get_crm_context(user_id, sender_email)
        if context.crm_context and (
            context.crm_context.connected or context.crm_context.recent_activities
        ):
            context.sources_used.append("crm")

        # 8. Persist to database
        saved = await self._save_context(context)
        if not saved:
            # Clear the ID so callers know the context row doesn't exist in DB
            context.id = ""

        # 9. Context completeness log — feeds confidence scoring
        sources_populated = []
        sources_empty = []
        for source_name, source_value in [
            ("thread_summary", context.thread_context),
            ("recipient_research", context.recipient_research and context.recipient_research.exa_sources_used),
            ("relationship_history", context.relationship_history and (
                context.relationship_history.memory_facts
                or context.relationship_history.total_emails > 0
            )),
            ("relationship_health", context.relationship_health and context.relationship_health.trend != "new"),
            ("calendar_context", context.calendar_context and context.calendar_context.connected),
            ("crm_context", context.crm_context and (
                context.crm_context.connected or context.crm_context.recent_activities
            )),
            ("corporate_memory", context.corporate_memory and context.corporate_memory.facts),
            ("recipient_style", context.recipient_style and context.recipient_style.exists),
        ]:
            if source_value:
                sources_populated.append(source_name)
            else:
                sources_empty.append(source_name)

        logger.info(
            "CONTEXT_COMPLETENESS: %d/8 sources populated: %s. Empty: %s",
            len(sources_populated),
            sources_populated,
            sources_empty,
        )

        logger.info(
            "[EMAIL_PIPELINE] Stage: context_complete | email_id=%s | saved=%s | "
            "completeness=%d/8 | sources=%s",
            email_id,
            saved,
            len(sources_populated),
            context.sources_used,
        )

        return context

    # ------------------------------------------------------------------
    # Thread Fetching (Composio)
    # ------------------------------------------------------------------

    async def _fetch_thread(
        self,
        user_id: str,
        thread_id: str,
    ) -> ThreadContext | None:
        """Fetch full email thread via Composio."""
        try:
            logger.info(
                "THREAD_FETCH: Starting for user=%s thread_id=%s",
                user_id,
                thread_id[:80] if thread_id else "NONE",
            )

            integration = await self._get_email_integration(user_id)
            if not integration:
                logger.warning(
                    "THREAD_FETCH: No email integration found for user %s",
                    user_id,
                )
                return None

            provider = integration.get("integration_type", "").lower()
            connection_id = integration.get("composio_connection_id")

            logger.info(
                "THREAD_FETCH: provider=%s connection_id=%s user_email=%s",
                provider,
                connection_id[:20] if connection_id else "NONE",
                getattr(self, "_cached_user_email", "NOT_SET"),
            )

            if not connection_id:
                logger.warning(
                    "THREAD_FETCH: No connection_id for user %s (provider=%s)",
                    user_id,
                    provider,
                )
                return None

            messages: list[ThreadMessage] = []

            if provider == "outlook":
                messages = await self._fetch_outlook_thread(
                    user_id, connection_id, thread_id
                )
            else:
                messages = await self._fetch_gmail_thread(
                    user_id, connection_id, thread_id
                )

            if not messages:
                logger.warning(
                    "THREAD_FETCH: No messages returned for thread %s (provider=%s)",
                    thread_id[:80] if thread_id else "NONE",
                    provider,
                )
                return None

            logger.info(
                "THREAD_FETCH: Got %d messages, summarizing thread %s",
                len(messages),
                thread_id[:40] if thread_id else "NONE",
            )

            summary = await self._summarize_thread(messages)

            logger.info(
                "THREAD_FETCH: Summary generated (%d chars) for thread %s",
                len(summary),
                thread_id[:40] if thread_id else "NONE",
            )

            return ThreadContext(
                thread_id=thread_id,
                messages=messages,
                summary=summary,
                message_count=len(messages),
            )

        except Exception as e:
            logger.error(
                "THREAD_FETCH: FAILED for user=%s thread=%s error=%s",
                user_id,
                thread_id[:80] if thread_id else "NONE",
                str(e),
                exc_info=True,
            )
            return None

    async def _fetch_gmail_thread(
        self,
        user_id: str,
        connection_id: str,
        thread_id: str,
    ) -> list[ThreadMessage]:
        """Fetch Gmail thread using GMAIL_FETCH_MESSAGE_BY_THREAD_ID."""
        from src.integrations.oauth import get_oauth_client

        messages: list[ThreadMessage] = []

        try:
            oauth_client = get_oauth_client()
            action = "GMAIL_FETCH_MESSAGE_BY_THREAD_ID"
            params = {"thread_id": thread_id}

            logger.info(
                "THREAD_FETCH_GMAIL: Calling action=%s params=%s connection=%s",
                action,
                params,
                connection_id[:20] if connection_id else "NONE",
            )

            response = oauth_client.execute_action_sync(
                connection_id=connection_id,
                action=action,
                params=params,
                user_id=user_id,
            )

            logger.info(
                "THREAD_FETCH_GMAIL: Response successful=%s data_keys=%s error=%s raw_preview=%s",
                response.get("successful"),
                list(response.get("data", {}).keys()) if response.get("data") else "NO_DATA",
                response.get("error"),
                str(response)[:500],
            )

            if not response.get("successful"):
                logger.error(
                    "THREAD_FETCH_GMAIL: Action failed: %s | full_response=%s",
                    response.get("error"),
                    str(response)[:1000],
                )
                return messages

            thread_data = response.get("data", {})
            thread_messages = thread_data.get("messages", [])

            logger.info(
                "THREAD_FETCH_GMAIL: Found %d messages in thread data",
                len(thread_messages),
            )

            user_email = await self._get_user_email_from_integration()

            for msg in thread_messages:
                headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
                sender = headers.get("From", "")
                sender_email = self._extract_email_address(sender)
                sender_name = self._extract_name(sender)
                body = self._extract_gmail_body(msg.get("payload", {}))

                messages.append(ThreadMessage(
                    sender_email=sender_email,
                    sender_name=sender_name,
                    body=body,
                    timestamp=msg.get("internalDate", ""),
                    is_from_user=bool(user_email and user_email.lower() in sender_email.lower()),
                ))

            logger.info(
                "THREAD_FETCH_GMAIL: Parsed %d messages from Gmail thread %s",
                len(messages),
                thread_id,
            )

        except Exception as e:
            logger.error(
                "THREAD_FETCH_GMAIL: EXCEPTION for thread=%s error=%s",
                thread_id,
                str(e),
                exc_info=True,
            )

        return messages

    async def _fetch_outlook_thread(
        self,
        user_id: str,
        connection_id: str,
        thread_id: str,
    ) -> list[ThreadMessage]:
        """Fetch Outlook conversation thread by conversationId."""
        from src.integrations.oauth import get_oauth_client

        messages: list[ThreadMessage] = []

        try:
            oauth_client = get_oauth_client()
            action = "OUTLOOK_LIST_MESSAGES"
            # Escape single quotes in conversationId for OData filter
            safe_thread_id = thread_id.replace("'", "''") if thread_id else ""
            params = {
                "$filter": f"conversationId eq '{safe_thread_id}'",
                "$orderby": "receivedDateTime asc",
                "$top": 50,
            }

            logger.info(
                "THREAD_FETCH_OUTLOOK: Calling action=%s filter=%s connection=%s",
                action,
                params["$filter"][:120],
                connection_id[:20] if connection_id else "NONE",
            )

            response = oauth_client.execute_action_sync(
                connection_id=connection_id,
                action=action,
                params=params,
                user_id=user_id,
            )

            logger.info(
                "THREAD_FETCH_OUTLOOK: Response successful=%s data_keys=%s error=%s raw_preview=%s",
                response.get("successful"),
                list(response.get("data", {}).keys()) if response.get("data") else "NO_DATA",
                response.get("error"),
                str(response)[:500],
            )

            if not response.get("successful"):
                logger.error(
                    "THREAD_FETCH_OUTLOOK: Action failed: %s | full_response=%s",
                    response.get("error"),
                    str(response)[:1000],
                )
                return messages

            messages_data = response.get("data", {}).get("value", [])
            user_email = await self._get_user_email_from_integration()

            logger.info(
                "THREAD_FETCH_OUTLOOK: Found %d messages in response",
                len(messages_data),
            )

            for msg in messages_data:
                sender = msg.get("from", {}).get("emailAddress", {})
                sender_email = sender.get("address", "")
                sender_name = sender.get("name", "")
                body_content = msg.get("body", {}).get("content", "")

                messages.append(ThreadMessage(
                    sender_email=sender_email,
                    sender_name=sender_name,
                    body=body_content,
                    timestamp=msg.get("receivedDateTime", ""),
                    is_from_user=bool(user_email and user_email.lower() in sender_email.lower()),
                ))

            logger.info(
                "THREAD_FETCH_OUTLOOK: Parsed %d messages from Outlook thread %s",
                len(messages),
                thread_id[:40] if thread_id else "NONE",
            )

        except Exception as e:
            logger.error(
                "THREAD_FETCH_OUTLOOK: EXCEPTION for thread=%s error=%s",
                thread_id[:80] if thread_id else "NONE",
                str(e),
                exc_info=True,
            )

        return messages

    def _extract_email_address(self, from_header: str) -> str:
        """Extract email address from 'Name <email@domain.com>' format."""
        import re

        match = re.search(r"<([^>]+)>", from_header)
        if match:
            return match.group(1).lower()
        return from_header.lower()

    def _extract_name(self, from_header: str) -> str | None:
        """Extract name from 'Name <email@domain.com>' format."""
        import re

        match = re.match(r"^([^<]+)<", from_header)
        if match:
            return match.group(1).strip()
        return None

    def _extract_gmail_body(self, payload: dict[str, Any]) -> str:
        """Extract body text from Gmail message payload."""
        import base64

        if payload.get("mimeType") == "text/plain":
            data = payload.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

        for part in payload.get("parts", []):
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data", "")
                if data:
                    return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

        for part in payload.get("parts", []):
            if part.get("mimeType") == "text/html":
                data = part.get("body", {}).get("data", "")
                if data:
                    import re
                    html = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                    return re.sub(r"<[^>]+>", "", html)

        return ""

    async def _get_user_email_from_integration(self) -> str:
        """Get user's email from their integration record.

        Returns the email cached during _get_email_integration(),
        or empty string if no integration was found.
        """
        return getattr(self, "_cached_user_email", "") or ""

    async def _get_email_integration(self, user_id: str) -> dict[str, Any] | None:
        """Get user's email integration (Outlook or Gmail).

        Also caches the user's email address from the integration
        metadata for use in is_from_user determination.
        """
        try:
            # Check Outlook first as it's more commonly working in enterprise
            result = (
                self._db.table("user_integrations")
                .select("*")
                .eq("user_id", user_id)
                .eq("integration_type", "outlook")
                .maybe_single()
                .execute()
            )
            if result.data:
                self._cached_user_email = result.data.get("account_email", "") or ""
                return result.data

            result = (
                self._db.table("user_integrations")
                .select("*")
                .eq("user_id", user_id)
                .eq("integration_type", "gmail")
                .maybe_single()
                .execute()
            )
            if result.data:
                self._cached_user_email = result.data.get("account_email", "") or ""
                return result.data

            return None

        except Exception as e:
            logger.warning(
                "CONTEXT_GATHERER: Failed to get email integration: %s",
                str(e),
            )
            return None

    async def _summarize_thread(self, messages: list[ThreadMessage]) -> str:
        """Generate a brief summary of the thread using LLM."""
        if not messages:
            return ""

        try:
            from src.core.llm import LLMClient

            llm = LLMClient()

            thread_text = "\n\n".join(
                f"From: {m.sender_email}\n{m.body[:500]}"
                for m in messages[-5:]
            )

            prompt = f"""Summarize this email conversation in 2-3 sentences. Focus on the main topic, any decisions made, and what action might be expected next.

Email thread:
{thread_text}

Summary:"""

            summary = await llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )

            return summary.strip()

        except Exception as e:
            logger.warning(
                "CONTEXT_GATHERER: Thread summarization failed: %s",
                str(e),
            )
            return f"Thread with {len(messages)} messages"

    # ------------------------------------------------------------------
    # Recipient Research (Exa)
    # ------------------------------------------------------------------

    async def _research_recipient(
        self,
        sender_email: str,
        sender_name: str | None,
        user_id: str | None = None,
    ) -> RecipientResearch | None:
        """Research the email sender via memory + Exa API.

        Performs:
        1. Check memory_semantic for existing facts about sender (fast, free)
        2. People search via Exa for LinkedIn profile and bio
        3. Company search ONLY if email is from a business domain (not personal)

        Args:
            sender_email: The sender's email address.
            sender_name: The sender's display name.
            user_id: The user's ID for memory lookups.

        Returns:
            RecipientResearch with gathered intelligence, or None.
        """
        research = RecipientResearch(sender_email=sender_email, sender_name=sender_name)

        # Check if this is a personal email domain - skip company research if so
        is_personal = self._is_personal_email(sender_email)

        # --- Step 1: Check memory_semantic FIRST (fast, free) ---
        memory_has_data = False
        if user_id:
            try:
                mem_result = (
                    self._db.table("memory_semantic")
                    .select("fact, confidence, source, metadata")
                    .eq("user_id", user_id)
                    .ilike("fact", f"%{sender_email}%")
                    .order("confidence", desc=True)
                    .limit(10)
                    .execute()
                )

                if mem_result.data:
                    memory_has_data = True
                    for row in mem_result.data:
                        metadata = row.get("metadata") or {}
                        # Extract structured fields from memory facts
                        if not research.sender_title and metadata.get("title"):
                            research.sender_title = metadata["title"]
                        if not research.sender_company and metadata.get("company"):
                            research.sender_company = metadata["company"]
                        if not research.bio and metadata.get("bio"):
                            research.bio = metadata["bio"]
                        if not research.linkedin_url and metadata.get("linkedin_url"):
                            research.linkedin_url = metadata["linkedin_url"]

                    # Also search by name if provided
                    if sender_name and not memory_has_data:
                        name_result = (
                            self._db.table("memory_semantic")
                            .select("fact, confidence, source, metadata")
                            .eq("user_id", user_id)
                            .ilike("fact", f"%{sender_name}%")
                            .order("confidence", desc=True)
                            .limit(5)
                            .execute()
                        )
                        if name_result.data:
                            memory_has_data = True

                    if memory_has_data:
                        research.exa_sources_used.append("memory_semantic")
                        logger.info(
                            "CONTEXT_GATHERER: Found %d memory facts for recipient %s",
                            len(mem_result.data),
                            sender_email,
                        )

            except Exception as e:
                logger.warning(
                    "CONTEXT_GATHERER: Memory lookup for recipient failed: %s",
                    str(e),
                )

        # --- Step 2: Exa research (only if memory didn't provide enough) ---
        try:
            from src.agents.capabilities.enrichment_providers.exa_provider import (
                ExaEnrichmentProvider,
            )

            exa = ExaEnrichmentProvider()

            # Extract company from email domain (only for business domains)
            domain = sender_email.split("@")[-1] if "@" in sender_email else ""
            company_from_email = "" if is_personal else domain.split(".")[0]

            # Search for person (skip if memory already found rich profile data)
            has_rich_profile = bool(
                research.sender_title and research.sender_company and research.bio
            )
            if sender_name and not has_rich_profile:
                logger.info(
                    "CONTEXT_GATHERER: Searching Exa for person: %s%s",
                    sender_name,
                    " (personal email, skipping company hint)" if is_personal else "",
                )

                person_result = await exa.search_person(
                    name=sender_name,
                    company=company_from_email,
                    role="",  # Unknown role
                )

                research.sender_name = person_result.name or sender_name
                research.sender_title = person_result.title
                research.sender_company = person_result.company or company_from_email
                research.linkedin_url = person_result.linkedin_url
                research.bio = person_result.bio

                for mention in person_result.web_mentions[:5]:
                    research.web_mentions.append({
                        "title": mention.get("title", ""),
                        "url": mention.get("url", ""),
                        "snippet": mention.get("snippet", "")[:200],
                    })
                    research.exa_sources_used.append(mention.get("url", ""))

            # Search for company ONLY if:
            # 1. This is NOT a personal email domain
            # 2. We have a company name to search for
            if is_personal:
                logger.info(
                    "SKIP_COMPANY_RESEARCH: %s is a personal email domain",
                    sender_email,
                )

            company_name = research.sender_company or company_from_email
            if company_name and not is_personal:
                logger.info(
                    "CONTEXT_GATHERER: Searching Exa for company: %s",
                    company_name,
                )

                company_result = await exa.search_company(company_name)

                research.company_description = company_result.description

                for news in company_result.recent_news[:3]:
                    research.company_news.append({
                        "title": news.get("title", ""),
                        "url": news.get("url", ""),
                        "snippet": news.get("snippet", "")[:200],
                        "date": news.get("published_date", ""),
                    })
                    research.exa_sources_used.append(news.get("url", ""))

            data_sources = []
            if memory_has_data:
                data_sources.append("memory_semantic")
            if any(s for s in research.exa_sources_used if s != "memory_semantic"):
                data_sources.append("exa_api")
            logger.info(
                "CONTEXT_GATHERER: Recipient research complete for %s | "
                "sources=%s | exa_urls=%d | company_research=%s",
                sender_email,
                data_sources,
                len([s for s in research.exa_sources_used if s != "memory_semantic"]),
                "skipped" if is_personal else "done",
            )

            return research

        except Exception as e:
            logger.error(
                "CONTEXT_GATHERER: Recipient research failed: %s",
                str(e),
                exc_info=True,
            )
            return research  # Return partial results

    # ------------------------------------------------------------------
    # Per-Recipient Writing Style
    # ------------------------------------------------------------------

    async def _get_recipient_style(
        self,
        user_id: str,
        sender_email: str,
    ) -> RecipientWritingStyle:
        """Get user's writing style profile for this recipient.

        Falls back to global digital_twin_profiles style if no
        per-recipient profile exists.

        Args:
            user_id: The user's ID.
            sender_email: The recipient's email.

        Returns:
            RecipientWritingStyle profile, global fallback, or default.
        """
        style = RecipientWritingStyle()

        # --- Try per-recipient profile first ---
        try:
            result = (
                self._db.table("recipient_writing_profiles")
                .select("*")
                .eq("user_id", user_id)
                .eq("recipient_email", sender_email.lower())
                .maybe_single()
                .execute()
            )

            if result.data:
                data = result.data
                style.exists = True
                style.formality_level = data.get("formality_level", 0.5)
                style.greeting_style = data.get("greeting_style", "")
                style.signoff_style = data.get("signoff_style", "")
                style.tone = data.get("tone", "balanced")
                style.uses_emoji = data.get("uses_emoji", False)
                style.email_count = data.get("email_count", 0)

                logger.info(
                    "CONTEXT_GATHERER: Found per-recipient style for %s (%d emails)",
                    sender_email,
                    style.email_count,
                )
                return style

        except Exception as e:
            logger.warning(
                "CONTEXT_GATHERER: Failed to get recipient style: %s",
                str(e),
            )

        # --- Fall back to global digital_twin_profiles style ---
        try:
            twin_result = (
                self._db.table("digital_twin_profiles")
                .select("tone, formality_level, writing_style, metadata")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )

            if twin_result.data:
                twin = twin_result.data
                style.exists = True
                style.tone = twin.get("tone", "balanced")

                # Map digital_twin formality (text) to numeric level
                formality_map = {
                    "casual": 0.2,
                    "business": 0.5,
                    "formal": 0.8,
                    "academic": 0.9,
                }
                style.formality_level = formality_map.get(
                    twin.get("formality_level", "business"), 0.5
                )

                # Extract greeting/signoff from metadata if available
                metadata = twin.get("metadata") or {}
                style.greeting_style = metadata.get("default_greeting", "")
                style.signoff_style = metadata.get("default_signoff", "")

                logger.info(
                    "CONTEXT_GATHERER: Using global digital twin style for %s "
                    "(tone=%s, formality=%s)",
                    sender_email,
                    style.tone,
                    style.formality_level,
                )

        except Exception as e:
            logger.warning(
                "CONTEXT_GATHERER: Failed to get digital twin fallback style: %s",
                str(e),
            )

        return style

    # ------------------------------------------------------------------
    # Relationship History (memory_semantic)
    # ------------------------------------------------------------------

    async def _get_relationship_history(
        self,
        user_id: str,
        sender_email: str,
    ) -> RelationshipHistory:
        """Get relationship history from multiple sources.

        Queries:
        1. memory_semantic for facts mentioning this contact
        2. recipient_writing_profiles for email frequency, tone, formality
        3. email_scan_log for past categorized interactions

        Args:
            user_id: The user's ID.
            sender_email: The contact's email.

        Returns:
            RelationshipHistory with memory facts, or structured "new contact"
            response if no prior history exists.
        """
        history = RelationshipHistory(sender_email=sender_email)

        # --- Source 1: memory_semantic facts ---
        try:
            result = (
                self._db.table("memory_semantic")
                .select("*")
                .eq("user_id", user_id)
                .ilike("fact", f"%{sender_email}%")
                .order("created_at", desc=True)
                .limit(20)
                .execute()
            )

            if result.data:
                for row in result.data:
                    metadata = row.get("metadata") or {}

                    history.memory_facts.append({
                        "id": row.get("id"),
                        "fact": row.get("fact"),
                        "confidence": row.get("confidence"),
                        "source": row.get("source"),
                        "created_at": row.get("created_at"),
                    })
                    history.memory_fact_ids.append(row.get("id"))

                    # Extract relationship type if present
                    rel_type = metadata.get("relationship_type")
                    if rel_type and history.relationship_type == "unknown":
                        history.relationship_type = rel_type

                # Get last interaction date
                if history.memory_facts:
                    history.last_interaction = history.memory_facts[0].get("created_at")

        except Exception as e:
            logger.warning(
                "CONTEXT_GATHERER: memory_semantic query failed for relationship: %s",
                str(e),
            )

        # --- Source 2: recipient_writing_profiles for frequency/tone ---
        try:
            profile_result = (
                self._db.table("recipient_writing_profiles")
                .select("email_count, last_email_date, relationship_type, tone")
                .eq("user_id", user_id)
                .eq("recipient_email", sender_email.lower())
                .maybe_single()
                .execute()
            )

            if profile_result.data:
                profile = profile_result.data
                history.total_emails = profile.get("email_count", 0)
                if profile.get("last_email_date"):
                    history.last_interaction = profile["last_email_date"]
                if profile.get("relationship_type") and profile["relationship_type"] != "unknown":
                    history.relationship_type = profile["relationship_type"]

        except Exception as e:
            logger.warning(
                "CONTEXT_GATHERER: recipient_writing_profiles query failed: %s",
                str(e),
            )

        # --- Source 3: email_scan_log for past interactions ---
        try:
            scan_result = (
                self._db.table("email_scan_log")
                .select("subject, category, urgency, scanned_at")
                .eq("user_id", user_id)
                .eq("sender_email", sender_email.lower())
                .order("scanned_at", desc=True)
                .limit(10)
                .execute()
            )

            if scan_result.data:
                # Count total emails from scan log if profiles didn't have count
                if history.total_emails == 0:
                    history.total_emails = len(scan_result.data)

                # Extract recent topics from subject lines
                history.recent_topics = [
                    row["subject"]
                    for row in scan_result.data
                    if row.get("subject")
                ][:5]

        except Exception as e:
            logger.warning(
                "CONTEXT_GATHERER: email_scan_log query failed: %s",
                str(e),
            )

        # --- Log result ---
        if history.memory_facts or history.total_emails > 0 or history.recent_topics:
            logger.info(
                "CONTEXT_GATHERER: Relationship history for %s — "
                "%d memory facts, %d emails, %d topics, type=%s",
                sender_email,
                len(history.memory_facts),
                history.total_emails,
                len(history.recent_topics),
                history.relationship_type,
            )
        else:
            history.relationship_type = "new_contact"
            logger.info(
                "CONTEXT_GATHERER: No prior history with %s — new contact",
                sender_email,
            )

        return history

    # ------------------------------------------------------------------
    # Relationship Health (from email patterns)
    # ------------------------------------------------------------------

    async def _get_relationship_health(
        self,
        user_id: str,
        sender_email: str,
    ) -> RelationshipHealthContext | None:
        """Get relationship health metrics from email scan patterns.

        Analyzes email frequency, recency, and trends to determine
        relationship health. Generates an ARIA note for cooling relationships.

        Args:
            user_id: The user's ID.
            sender_email: The contact's email.

        Returns:
            RelationshipHealthContext with trend and health score.
        """
        try:
            from src.services.email_relationship_health import (
                EmailRelationshipHealth,
                get_email_relationship_health,
            )

            service = get_email_relationship_health()
            health = await service.analyze_contact_health(user_id, sender_email)

            # Get ARIA note for cooling relationships
            aria_note = await service.get_aria_note(user_id, sender_email)

            context = RelationshipHealthContext(
                contact_email=health.contact_email,
                contact_name=health.contact_name,
                total_emails=health.total_emails,
                weekly_frequency=health.weekly_frequency,
                trend=health.trend,
                trend_detail=health.trend_detail,
                days_since_last=health.days_since_last,
                health_score=health.health_score,
                aria_note=aria_note,
            )

            if health.trend == "cooling":
                logger.info(
                    "CONTEXT_GATHERER: Relationship with %s is COOLING — "
                    "%d days since last contact, score=%d",
                    sender_email,
                    health.days_since_last,
                    health.health_score,
                )
            elif health.trend == "warming":
                logger.info(
                    "CONTEXT_GATHERER: Relationship with %s is WARMING — "
                    "score=%d, trend_detail=%s",
                    sender_email,
                    health.health_score,
                    health.trend_detail,
                )

            return context

        except Exception as e:
            logger.warning(
                "CONTEXT_GATHERER: Relationship health analysis failed for %s: %s",
                sender_email,
                str(e),
            )
            return None

    # ------------------------------------------------------------------
    # Corporate Memory
    # ------------------------------------------------------------------

    async def _get_corporate_memory(
        self,
        user_id: str,
        topic: str,
        sender_email: str = "",
    ) -> CorporateMemoryContext:
        """Get relevant facts about sender's company and user's company.

        Queries memory_semantic for corporate facts matching:
        1. The sender's company domain (extracted from email)
        2. The email subject/topic keywords

        Args:
            user_id: The user's ID.
            topic: The email subject/topic for relevance.
            sender_email: The sender's email for company domain extraction.

        Returns:
            CorporateMemoryContext with relevant facts.
        """
        context = CorporateMemoryContext()
        seen_ids: set[str] = set()

        # Extract sender's company from email domain
        sender_company = ""
        if sender_email and "@" in sender_email and not self._is_personal_email(sender_email):
            domain = sender_email.split("@")[-1]
            sender_company = domain.split(".")[0]

        # --- Search 1: By sender's company domain ---
        if sender_company:
            try:
                company_result = (
                    self._db.table("memory_semantic")
                    .select("id, fact, confidence, source")
                    .eq("user_id", user_id)
                    .ilike("fact", f"%{sender_company}%")
                    .order("confidence", desc=True)
                    .limit(10)
                    .execute()
                )

                if company_result.data:
                    for row in company_result.data:
                        row_id = row.get("id")
                        if row_id and row_id not in seen_ids:
                            seen_ids.add(row_id)
                            context.facts.append({
                                "id": row_id,
                                "fact": row.get("fact"),
                                "confidence": row.get("confidence"),
                                "source": row.get("source"),
                            })
                            context.fact_ids.append(row_id)

                    logger.info(
                        "CONTEXT_GATHERER: Found %d corporate facts for company '%s'",
                        len(context.facts),
                        sender_company,
                    )

            except Exception as e:
                logger.warning(
                    "CONTEXT_GATHERER: Corporate memory company search failed: %s",
                    str(e),
                )

        # --- Search 2: By email topic keywords (from corporate sources) ---
        try:
            keywords = topic.split()[:5] if topic else []
            search_terms = " | ".join(keywords) if keywords else ""

            result = (
                self._db.table("memory_semantic")
                .select("id, fact, confidence, source")
                .eq("user_id", user_id)
                .in_("source", ["company_facts", "corporate_memory", "onboarding",
                                "enrichment", "email_bootstrap"])
                .or_(f"fact.ilike.%{search_terms}%" if search_terms else "fact.ilike.%")
                .order("confidence", desc=True)
                .limit(10)
                .execute()
            )

            if result.data:
                for row in result.data:
                    row_id = row.get("id")
                    if row_id and row_id not in seen_ids:
                        seen_ids.add(row_id)
                        context.facts.append({
                            "id": row_id,
                            "fact": row.get("fact"),
                            "confidence": row.get("confidence"),
                            "source": row.get("source"),
                        })
                        context.fact_ids.append(row_id)

        except Exception as e:
            logger.warning(
                "CONTEXT_GATHERER: Corporate memory topic search failed: %s",
                str(e),
            )

        if context.facts:
            logger.info(
                "CONTEXT_GATHERER: Total %d corporate memory facts "
                "(company='%s', topic='%s')",
                len(context.facts),
                sender_company or "N/A",
                topic[:50] if topic else "N/A",
            )

        return context

    # ------------------------------------------------------------------
    # Calendar Context
    # ------------------------------------------------------------------

    async def _get_calendar_context(
        self,
        user_id: str,
        sender_email: str,
    ) -> CalendarContext:
        """Get calendar context for meetings with this contact.

        Checks for Google Calendar or Outlook Calendar integration
        and fetches recent/upcoming meetings with this person.

        Args:
            user_id: The user's ID.
            sender_email: The contact's email.

        Returns:
            CalendarContext with meeting info.
        """
        context = CalendarContext()

        try:
            calendar_integration = await self._get_calendar_integration(user_id)
            if not calendar_integration:
                return context

            context.connected = True

            from datetime import timedelta

            connection_id = calendar_integration.get("composio_connection_id")
            if not connection_id:
                logger.warning(
                    "CONTEXT_GATHERER: No connection_id for calendar integration"
                )
                return context

            now = datetime.now(UTC)
            start_date = (now - timedelta(days=30)).strftime("%Y-%m-%d")
            end_date = (now + timedelta(days=30)).strftime("%Y-%m-%d")

            provider = calendar_integration.get("integration_type", "").lower()

            if "google" in provider:
                events = await self._fetch_google_calendar_events(
                    user_id, connection_id, start_date, end_date, sender_email
                )
            else:
                events = await self._fetch_outlook_calendar_events(
                    user_id, connection_id, start_date, end_date, sender_email
                )

            for event in events:
                event_time_str = event.get("start", "")
                if event_time_str:
                    event_time = datetime.fromisoformat(
                        event_time_str.replace("Z", "+00:00")
                    )
                    if event_time < now:
                        context.recent_meetings.append(event)
                    else:
                        context.upcoming_meetings.append(event)

            logger.info(
                "CONTEXT_GATHERER: Found %d recent, %d upcoming meetings with %s",
                len(context.recent_meetings),
                len(context.upcoming_meetings),
                sender_email,
            )

        except Exception as e:
            logger.error(
                "CONTEXT_GATHERER: Calendar context failed: %s",
                str(e),
                exc_info=True,
            )

        return context

    async def _get_calendar_integration(self, user_id: str) -> dict[str, Any] | None:
        """Get user's calendar integration."""
        try:
            result = (
                self._db.table("user_integrations")
                .select("*")
                .eq("user_id", user_id)
                .eq("integration_type", "googlecalendar")
                .maybe_single()
                .execute()
            )
            if result.data:
                return result.data

            result = (
                self._db.table("user_integrations")
                .select("*")
                .eq("user_id", user_id)
                .eq("integration_type", "outlook365calendar")
                .maybe_single()
                .execute()
            )
            return result.data if result.data else None

        except Exception:
            return None

    async def _fetch_google_calendar_events(
        self,
        user_id: str,
        connection_id: str,
        start_date: str,
        end_date: str,
        sender_email: str,
    ) -> list[dict[str, Any]]:
        """Fetch Google Calendar events involving the sender."""
        from src.integrations.oauth import get_oauth_client

        events = []

        try:
            oauth_client = get_oauth_client()
            response = oauth_client.execute_action_sync(
                connection_id=connection_id,
                action="GOOGLECALENDAR_GET_EVENTS",
                params={
                    "timeMin": f"{start_date}T00:00:00Z",
                    "timeMax": f"{end_date}T23:59:59Z",
                    "maxResults": 50,
                },
                user_id=user_id,
            )

            if response.get("successful"):
                for event in response.get("data", {}).get("items", []):
                    attendees = event.get("attendees", [])
                    if any(
                        sender_email.lower() in a.get("email", "").lower()
                        for a in attendees
                    ):
                        events.append({
                            "id": event.get("id"),
                            "title": event.get("summary", ""),
                            "start": event.get("start", {}).get("dateTime", ""),
                            "end": event.get("end", {}).get("dateTime", ""),
                        })

        except Exception as e:
            logger.warning(
                "CONTEXT_GATHERER: Google Calendar fetch failed: %s",
                str(e),
            )

        return events

    async def _fetch_outlook_calendar_events(
        self,
        user_id: str,
        connection_id: str,
        start_date: str,
        end_date: str,
        sender_email: str,
    ) -> list[dict[str, Any]]:
        """Fetch Outlook Calendar events involving the sender."""
        from src.integrations.oauth import get_oauth_client

        events = []

        try:
            oauth_client = get_oauth_client()
            response = oauth_client.execute_action_sync(
                connection_id=connection_id,
                action="OUTLOOK_GET_CALENDAR_VIEW",
                params={
                    "startDateTime": f"{start_date}T00:00:00Z",
                    "endDateTime": f"{end_date}T23:59:59Z",
                    "$top": 50,
                },
                user_id=user_id,
            )

            if response.get("successful"):
                for event in response.get("data", {}).get("value", []):
                    attendees = event.get("attendees", [])
                    if any(
                        sender_email.lower() in a.get("emailAddress", {}).get("address", "").lower()
                        for a in attendees
                    ):
                        events.append({
                            "id": event.get("id"),
                            "title": event.get("subject", ""),
                            "start": event.get("start", {}).get("dateTime", ""),
                            "end": event.get("end", {}).get("dateTime", ""),
                        })

        except Exception as e:
            logger.warning(
                "CONTEXT_GATHERER: Outlook Calendar fetch failed: %s",
                str(e),
            )

        return events

    # ------------------------------------------------------------------
    # CRM Context
    # ------------------------------------------------------------------

    async def _get_crm_context(
        self,
        user_id: str,
        sender_email: str,
    ) -> CRMContext:
        """Get CRM context for this contact.

        Checks for Salesforce or HubSpot integration and fetches
        deal/account status. Falls back to memory_semantic for
        deal/pipeline data when no CRM is connected.

        Args:
            user_id: The user's ID.
            sender_email: The contact's email.

        Returns:
            CRMContext with deal/account info.
        """
        context = CRMContext()

        try:
            crm_integration = await self._get_crm_integration(user_id)
            if not crm_integration:
                # No CRM connected — fall back to memory_semantic for deal context
                logger.info(
                    "CONTEXT_GATHERER: No CRM integration for user %s, "
                    "checking memory_semantic for deal context",
                    user_id,
                )
                context = await self._get_crm_from_memory(user_id, sender_email)
                return context

            context.connected = True

            connection_id = crm_integration.get("composio_connection_id")
            if not connection_id:
                logger.warning(
                    "CONTEXT_GATHERER: No connection_id for CRM integration"
                )
                return context

            provider = crm_integration.get("integration_type", "").lower()

            if "salesforce" in provider:
                await self._fetch_salesforce_context(
                    user_id, connection_id, sender_email, context
                )
            elif "hubspot" in provider:
                await self._fetch_hubspot_context(
                    user_id, connection_id, sender_email, context
                )

            logger.info(
                "CONTEXT_GATHERER: CRM context for %s - stage: %s",
                sender_email,
                context.lead_stage or "none",
            )

        except Exception as e:
            logger.error(
                "CONTEXT_GATHERER: CRM context failed: %s",
                str(e),
                exc_info=True,
            )

        return context

    async def _get_crm_integration(self, user_id: str) -> dict[str, Any] | None:
        """Get user's CRM integration."""
        try:
            result = (
                self._db.table("user_integrations")
                .select("*")
                .eq("user_id", user_id)
                .eq("integration_type", "salesforce")
                .maybe_single()
                .execute()
            )
            if result.data:
                return result.data

            result = (
                self._db.table("user_integrations")
                .select("*")
                .eq("user_id", user_id)
                .eq("integration_type", "hubspot")
                .maybe_single()
                .execute()
            )
            return result.data if result.data else None

        except Exception:
            return None

    async def _fetch_salesforce_context(
        self,
        user_id: str,
        connection_id: str,
        sender_email: str,
        context: CRMContext,
    ) -> None:
        """Fetch Salesforce context for contact."""
        from src.integrations.oauth import get_oauth_client

        try:
            oauth_client = get_oauth_client()
            response = oauth_client.execute_action_sync(
                connection_id=connection_id,
                action="SALESFORCE_SEARCH_RECORDS",
                params={
                    "search_string": sender_email,
                },
                user_id=user_id,
            )

            if response.get("successful"):
                records = response.get("data", {}).get("searchRecords", [])

                for record in records:
                    if record.get("attributes", {}).get("type") == "Contact":
                        contact_id = record.get("Id")

                        opp_response = oauth_client.execute_action_sync(
                            connection_id=connection_id,
                            action="SALESFORCE_QUERY",
                            params={
                                "query": f"SELECT StageName, Amount FROM Opportunity WHERE ContactId = '{contact_id}' LIMIT 1",
                            },
                            user_id=user_id,
                        )

                        if opp_response.get("successful"):
                            opps = opp_response.get("data", {}).get("records", [])
                            if opps:
                                context.lead_stage = opps[0].get("StageName")
                                context.deal_value = opps[0].get("Amount")

                        break

        except Exception as e:
            logger.warning(
                "CONTEXT_GATHERER: Salesforce context failed: %s",
                str(e),
            )

    async def _fetch_hubspot_context(
        self,
        user_id: str,
        connection_id: str,
        sender_email: str,
        context: CRMContext,
    ) -> None:
        """Fetch HubSpot context for contact."""
        from src.integrations.oauth import get_oauth_client

        try:
            oauth_client = get_oauth_client()
            response = oauth_client.execute_action_sync(
                connection_id=connection_id,
                action="HUBSPOT_SEARCH_CONTACTS",
                params={
                    "query": sender_email,
                    "limit": 1,
                },
                user_id=user_id,
            )

            if response.get("successful"):
                contacts = response.get("data", {}).get("results", [])

                if contacts:
                    contact = contacts[0]
                    properties = contact.get("properties", {})

                    context.lead_stage = properties.get("lifecycle_stage")
                    context.account_status = properties.get("hubspot_owner_id")

        except Exception as e:
            logger.warning(
                "CONTEXT_GATHERER: HubSpot context failed: %s",
                str(e),
            )

    async def _get_crm_from_memory(
        self,
        user_id: str,
        sender_email: str,
    ) -> CRMContext:
        """Fall back to memory_semantic for deal/pipeline data when no CRM.

        Searches for facts about deals, pipelines, or opportunities
        related to the sender's company domain.

        Args:
            user_id: The user's ID.
            sender_email: The contact's email.

        Returns:
            CRMContext with memory-derived deal context.
        """
        context = CRMContext()

        try:
            # Extract company name from email domain
            domain = sender_email.split("@")[-1] if "@" in sender_email else ""
            company_hint = domain.split(".")[0] if domain else ""

            if not company_hint or self._is_personal_email(sender_email):
                return context

            # Search memory for deal/pipeline/opportunity facts
            result = (
                self._db.table("memory_semantic")
                .select("fact, confidence, source, metadata")
                .eq("user_id", user_id)
                .ilike("fact", f"%{company_hint}%")
                .order("confidence", desc=True)
                .limit(10)
                .execute()
            )

            if result.data:
                deal_keywords = {"deal", "pipeline", "opportunity", "stage",
                                 "prospect", "revenue", "contract", "proposal"}
                for row in result.data:
                    fact_lower = (row.get("fact") or "").lower()
                    if any(kw in fact_lower for kw in deal_keywords):
                        context.recent_activities.append({
                            "source": "memory_semantic",
                            "fact": row.get("fact"),
                            "confidence": row.get("confidence"),
                        })

                        # Try to extract stage from metadata
                        metadata = row.get("metadata") or {}
                        if not context.lead_stage and metadata.get("stage"):
                            context.lead_stage = metadata["stage"]

                if context.recent_activities:
                    logger.info(
                        "CONTEXT_GATHERER: Found %d deal-related memory facts for %s",
                        len(context.recent_activities),
                        company_hint,
                    )

        except Exception as e:
            logger.warning(
                "CONTEXT_GATHERER: Memory CRM fallback failed: %s",
                str(e),
            )

        return context

    # ------------------------------------------------------------------
    # Commitment Extraction
    # ------------------------------------------------------------------

    async def _extract_commitments(
        self,
        user_id: str,
        thread_messages: list[ThreadMessage],
        sender_name: str | None,
        sender_email: str,
    ) -> list[dict[str, Any]]:
        """Extract commitments and follow-ups from an email thread.

        Uses LLM to analyze thread messages for promises, action items,
        and follow-up needs from both the user and the sender.

        Args:
            user_id: The user's ID (the email account owner).
            thread_messages: List of ThreadMessage objects from the thread.
            sender_name: The sender's display name.
            sender_email: The sender's email address.

        Returns:
            List of commitment dicts with keys: who_committed, what,
            due_date, status, urgency.
        """
        if not thread_messages:
            return []

        try:
            from src.core.llm import LLMClient

            llm = LLMClient()

            # Build thread text from last 10 messages (recent context)
            recent = thread_messages[-10:]
            thread_text = "\n\n".join(
                f"From: {m.sender_name or m.sender_email} ({m.timestamp})\n"
                f"{m.body[:800]}"
                for m in recent
            )

            contact = sender_name or sender_email
            prompt = f"""Analyze this email thread and extract ALL commitments, \
promises, action items, and follow-up needs.

For each commitment found, provide:
- who_committed: "user" (the email account owner) or "sender" ({contact})
- what: specific action promised
- due_date: if mentioned (exact date or relative like "next week", "by Friday")
- status: "pending" (not yet done) or "completed" (if thread shows it was done)
- urgency: "high" (explicit deadline) or "normal" (implied follow-up)

EMAIL THREAD:
{thread_text}

Return as JSON array. If no commitments found, return [].
Example:
[
  {{"who_committed": "user", "what": "Send pricing proposal", "due_date": "2026-02-28", "status": "pending", "urgency": "high"}},
  {{"who_committed": "sender", "what": "Get internal budget approval", "due_date": "next week", "status": "pending", "urgency": "normal"}}
]

Return ONLY the JSON array, nothing else."""

            result = await llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1500,
                temperature=0.0,
            )

            try:
                commitments = json.loads(result.strip())
            except json.JSONDecodeError:
                match = re.search(r"\[.*\]", result, re.DOTALL)
                if match:
                    commitments = json.loads(match.group())
                else:
                    commitments = []

            if not isinstance(commitments, list):
                commitments = []

            # Filter to pending commitments only
            commitments = [
                c for c in commitments
                if isinstance(c, dict) and c.get("status") != "completed"
            ]

            logger.info(
                "COMMITMENT_EXTRACT: Found %d pending commitments in thread "
                "for user=%s sender=%s",
                len(commitments),
                user_id,
                sender_email,
            )

            return commitments

        except Exception as e:
            logger.warning(
                "COMMITMENT_EXTRACT: Failed for user=%s sender=%s error=%s",
                user_id,
                sender_email,
                str(e),
            )
            return []

    def _parse_due_date(self, due_date_str: str | None) -> str | None:
        """Parse a due date string into an ISO timestamp.

        Handles both absolute dates (2026-02-28) and relative dates
        (next week, by Friday, end of month).

        Args:
            due_date_str: The due date string from LLM extraction.

        Returns:
            ISO format datetime string, or None if unparseable.
        """
        if not due_date_str:
            return None

        due_date_str = due_date_str.strip().lower()

        # Try parsing as ISO date directly
        try:
            dt = datetime.fromisoformat(due_date_str)
            return dt.replace(tzinfo=UTC).isoformat()
        except (ValueError, TypeError):
            pass

        now = datetime.now(UTC)

        # Relative date patterns
        if "tomorrow" in due_date_str:
            return (now + timedelta(days=1)).isoformat()
        if "next week" in due_date_str:
            return (now + timedelta(weeks=1)).isoformat()
        if "next month" in due_date_str:
            return (now + timedelta(days=30)).isoformat()
        if "end of week" in due_date_str:
            days_until_friday = (4 - now.weekday()) % 7 or 7
            return (now + timedelta(days=days_until_friday)).isoformat()
        if "end of month" in due_date_str:
            if now.month == 12:
                eom = now.replace(year=now.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                eom = now.replace(month=now.month + 1, day=1) - timedelta(days=1)
            return eom.isoformat()

        # "by Friday", "by Monday", etc.
        day_names = {
            "monday": 0, "tuesday": 1, "wednesday": 2,
            "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
        }
        for day_name, day_num in day_names.items():
            if day_name in due_date_str:
                days_ahead = (day_num - now.weekday()) % 7 or 7
                return (now + timedelta(days=days_ahead)).isoformat()

        # Try a lenient parse for "March 1", "Feb 28", etc.
        for fmt in ("%B %d", "%b %d", "%B %d, %Y", "%b %d, %Y"):
            try:
                dt = datetime.strptime(due_date_str, fmt)
                dt = dt.replace(year=now.year, tzinfo=UTC)
                if dt < now:
                    dt = dt.replace(year=now.year + 1)
                return dt.isoformat()
            except ValueError:
                continue

        # If nothing matched, default to 1 week from now
        logger.debug(
            "COMMITMENT_EXTRACT: Could not parse due date '%s', "
            "defaulting to 1 week",
            due_date_str,
        )
        return (now + timedelta(weeks=1)).isoformat()

    async def _store_commitments(
        self,
        user_id: str,
        commitments: list[dict[str, Any]],
        sender_name: str | None,
        sender_email: str,
        email_id: str,
        thread_id: str,
    ) -> int:
        """Store extracted commitments as prospective memory tasks.

        Args:
            user_id: The user's ID.
            commitments: List of commitment dicts from _extract_commitments().
            sender_name: The sender's display name.
            sender_email: The sender's email address.
            email_id: The source email ID.
            thread_id: The source thread ID.

        Returns:
            Number of commitments successfully stored.
        """
        if not commitments:
            return 0

        from src.memory.prospective import (
            ProspectiveMemory,
            ProspectiveTask,
            TaskPriority,
            TaskStatus,
            TriggerType,
        )

        memory = ProspectiveMemory()
        stored = 0
        contact = sender_name or sender_email

        for commitment in commitments:
            try:
                who = commitment.get("who_committed", "unknown")
                what = commitment.get("what", "")
                if not what:
                    continue

                # Build description
                if who == "user":
                    description = f"You committed: {what}"
                    task_label = f"Follow up: {what}"
                else:
                    description = f"{contact} committed: {what}"
                    task_label = f"Track: {contact} — {what}"

                # Parse priority
                urgency = commitment.get("urgency", "normal")
                priority = (
                    TaskPriority.HIGH if urgency == "high" else TaskPriority.MEDIUM
                )

                # Parse due date into trigger config
                due_date_iso = self._parse_due_date(commitment.get("due_date"))
                trigger_config: dict[str, Any] = {}
                if due_date_iso:
                    trigger_config["due_at"] = due_date_iso

                # Build metadata for proactive follow-up engine
                commitment_metadata: dict[str, Any] = {
                    "source": "email_commitment",
                    "sender_email": sender_email,
                    "sender_name": sender_name or "",
                    "who": who,  # "user" or "sender"
                    "thread_id": thread_id,
                    "email_id": email_id,
                }

                task = ProspectiveTask(
                    id=str(uuid4()),
                    user_id=user_id,
                    task=task_label[:500],
                    description=description[:2000],
                    trigger_type=TriggerType.TIME,
                    trigger_config=trigger_config,
                    status=TaskStatus.PENDING,
                    priority=priority,
                    related_goal_id=None,
                    related_lead_id=None,
                    completed_at=None,
                    created_at=datetime.now(UTC),
                    metadata=commitment_metadata,
                )

                await memory.create_task(task)
                stored += 1

            except Exception as e:
                logger.warning(
                    "COMMITMENT_STORE: Failed to store commitment '%s': %s",
                    commitment.get("what", "?")[:80],
                    str(e),
                )
                continue

        logger.info(
            "COMMITMENT_STORE: Stored %d/%d commitments for user=%s thread=%s",
            stored,
            len(commitments),
            user_id,
            thread_id[:40] if thread_id else "NONE",
        )

        return stored

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def _save_context(self, context: DraftContext) -> bool:
        """Persist context to draft_context table.

        Args:
            context: The DraftContext to save.

        Returns:
            True if the context was saved successfully, False otherwise.
        """
        try:
            self._db.table("draft_context").insert(
                context.to_db_dict()
            ).execute()

            logger.info(
                "[EMAIL_PIPELINE] Stage: context_saved | context_id=%s | email_id=%s",
                context.id,
                context.email_id,
            )
            return True

        except Exception as e:
            logger.error(
                "[EMAIL_PIPELINE] Stage: context_save_failed | context_id=%s | email_id=%s | error=%s",
                context.id,
                context.email_id,
                str(e),
                exc_info=True,
            )
            return False

    async def update_draft_id(self, context_id: str, draft_id: str) -> bool:
        """Update the draft_id FK in draft_context after draft is saved.

        This is called by AutonomousDraftEngine after the draft is created,
        since the draft doesn't exist when context is initially gathered.

        Args:
            context_id: The ID of the draft_context row to update.
            draft_id: The ID of the newly created email_draft.

        Returns:
            True if update succeeded, False otherwise.
        """
        try:
            self._db.table("draft_context").update(
                {"draft_id": draft_id}
            ).eq("id", context_id).execute()

            logger.info(
                "[EMAIL_PIPELINE] Stage: context_draft_id_set | context_id=%s | draft_id=%s",
                context_id,
                draft_id,
            )
            return True

        except Exception as e:
            logger.error(
                "[EMAIL_PIPELINE] Stage: context_draft_id_update_failed | context_id=%s | draft_id=%s | error=%s",
                context_id,
                draft_id,
                str(e),
                exc_info=True,
            )
            return False

    async def get_existing_context(
        self,
        user_id: str,
        thread_id: str,
    ) -> DraftContext | None:
        """Get existing context for a thread if recently created.

        Useful for avoiding re-fetching context for multiple drafts
        in the same thread.

        Args:
            user_id: The user's ID.
            thread_id: The thread ID.

        Returns:
            DraftContext if found and recent, None otherwise.
        """
        try:
            from datetime import timedelta

            cutoff = (datetime.now(UTC) - timedelta(hours=24)).isoformat()

            result = (
                self._db.table("draft_context")
                .select("*")
                .eq("user_id", user_id)
                .eq("thread_id", thread_id)
                .gte("created_at", cutoff)
                .order("created_at", desc=True)
                .limit(1)
                .maybe_single()
                .execute()
            )

            if result.data:
                return self._row_to_context(result.data)

        except Exception as e:
            logger.warning(
                "CONTEXT_GATHERER: Failed to get existing context: %s",
                str(e),
            )

        return None

    def _row_to_context(self, row: dict[str, Any]) -> DraftContext:
        """Convert database row to DraftContext object."""
        context = DraftContext(
            id=row.get("id"),
            user_id=row.get("user_id"),
            draft_id=row.get("draft_id"),
            email_id=row.get("email_id"),
            thread_id=row.get("thread_id"),
            sender_email=row.get("sender_email"),
            subject=row.get("subject"),
            sources_used=row.get("sources_used", []),
            created_at=row.get("created_at"),
        )

        # Reconstruct nested objects
        if row.get("thread_context"):
            context.thread_context = ThreadContext(**row["thread_context"])
        if row.get("recipient_research"):
            context.recipient_research = RecipientResearch(**row["recipient_research"])
        if row.get("recipient_style"):
            context.recipient_style = RecipientWritingStyle(**row["recipient_style"])
        if row.get("relationship_history"):
            context.relationship_history = RelationshipHistory(**row["relationship_history"])
        if row.get("corporate_memory"):
            context.corporate_memory = CorporateMemoryContext(**row["corporate_memory"])
        if row.get("calendar_context"):
            context.calendar_context = CalendarContext(**row["calendar_context"])
        if row.get("crm_context"):
            context.crm_context = CRMContext(**row["crm_context"])

        return context


# ---------------------------------------------------------------------------
# Singleton Access
# ---------------------------------------------------------------------------

_gatherer: EmailContextGatherer | None = None


def get_email_context_gatherer() -> EmailContextGatherer:
    """Get or create the EmailContextGatherer singleton.

    Returns:
        The EmailContextGatherer singleton instance.
    """
    global _gatherer
    if _gatherer is None:
        _gatherer = EmailContextGatherer()
    return _gatherer
