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

import logging
from datetime import UTC, datetime
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


class DraftContext(BaseModel):
    """Complete context package for drafting an email reply."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str
    email_id: str
    thread_id: str
    sender_email: str
    subject: str

    # All context sections
    thread_context: ThreadContext | None = None
    recipient_research: RecipientResearch | None = None
    recipient_style: RecipientWritingStyle | None = None
    relationship_history: RelationshipHistory | None = None
    corporate_memory: CorporateMemoryContext | None = None
    calendar_context: CalendarContext | None = None
    crm_context: CRMContext | None = None

    # Source tracking
    sources_used: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_db_dict(self) -> dict[str, Any]:
        """Serialize to database-compatible dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "email_id": self.email_id,
            "thread_id": self.thread_id,
            "sender_email": self.sender_email,
            "subject": self.subject,
            "thread_context": self.thread_context.model_dump() if self.thread_context else None,
            "recipient_research": self.recipient_research.model_dump() if self.recipient_research else None,
            "recipient_style": self.recipient_style.model_dump() if self.recipient_style else None,
            "relationship_history": self.relationship_history.model_dump() if self.relationship_history else None,
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

    def __init__(self) -> None:
        """Initialize with required clients."""
        from src.db.supabase import SupabaseClient

        self._db = SupabaseClient.get_client()

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

        # 2. Research recipient via Exa
        context.recipient_research = await self._research_recipient(
            sender_email, sender_name
        )
        if context.recipient_research and context.recipient_research.exa_sources_used:
            context.sources_used.append("exa_research")

        # 3. Get per-recipient writing style
        context.recipient_style = await self._get_recipient_style(user_id, sender_email)
        if context.recipient_style and context.recipient_style.exists:
            context.sources_used.append("recipient_style_profile")

        # 4. Get relationship history from memory
        context.relationship_history = await self._get_relationship_history(
            user_id, sender_email
        )
        if context.relationship_history and context.relationship_history.memory_facts:
            context.sources_used.append("memory_semantic")

        # 5. Get corporate memory
        context.corporate_memory = await self._get_corporate_memory(
            user_id, subject
        )
        if context.corporate_memory and context.corporate_memory.facts:
            context.sources_used.append("corporate_memory")

        # 6. Get calendar context
        context.calendar_context = await self._get_calendar_context(user_id, sender_email)
        if context.calendar_context and context.calendar_context.connected:
            context.sources_used.append("calendar")

        # 7. Get CRM context
        context.crm_context = await self._get_crm_context(user_id, sender_email)
        if context.crm_context and context.crm_context.connected:
            context.sources_used.append("crm")

        # 8. Persist to database
        await self._save_context(context)

        logger.info(
            "CONTEXT_GATHERER: Completed for email %s, sources used: %s",
            email_id,
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
            from composio import ComposioToolSet

            toolset = ComposioToolSet()
            entity = toolset.get_entity(id=user_id)

            integration = await self._get_email_integration(user_id)
            if not integration:
                logger.warning(
                    "CONTEXT_GATHERER: No email integration for user %s",
                    user_id,
                )
                return None

            provider = integration.get("integration_type", "").lower()
            messages: list[ThreadMessage] = []

            if provider == "outlook":
                messages = await self._fetch_outlook_thread(entity, thread_id)
            else:
                messages = await self._fetch_gmail_thread(entity, thread_id)

            if not messages:
                logger.warning(
                    "CONTEXT_GATHERER: No messages found for thread %s",
                    thread_id,
                )
                return None

            summary = await self._summarize_thread(messages)

            return ThreadContext(
                thread_id=thread_id,
                messages=messages,
                summary=summary,
                message_count=len(messages),
            )

        except Exception as e:
            logger.error(
                "CONTEXT_GATHERER: Thread fetch failed: %s",
                str(e),
                exc_info=True,
            )
            return None

    async def _fetch_gmail_thread(
        self,
        entity: Any,
        thread_id: str,
    ) -> list[ThreadMessage]:
        """Fetch Gmail thread using GMAIL_GET_THREAD."""
        messages: list[ThreadMessage] = []

        try:
            response = entity.execute(
                action="GMAIL_GET_THREAD",
                params={"thread_id": thread_id},
            )

            if not response or not response.get("success"):
                logger.error(
                    "CONTEXT_GATHERER: GMAIL_GET_THREAD failed: %s",
                    response.get("error", "Unknown error") if response else "No response",
                )
                return messages

            thread_data = response.get("data", {})
            thread_messages = thread_data.get("messages", [])

            for msg in thread_messages:
                headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
                sender = headers.get("From", "")
                sender_email = self._extract_email_address(sender)
                sender_name = self._extract_name(sender)
                body = self._extract_gmail_body(msg.get("payload", {}))
                user_email = await self._get_user_email_from_integration()

                messages.append(ThreadMessage(
                    sender_email=sender_email,
                    sender_name=sender_name,
                    body=body,
                    timestamp=msg.get("internalDate", ""),
                    is_from_user=user_email.lower() in sender_email.lower(),
                ))

            logger.info(
                "CONTEXT_GATHERER: Fetched %d messages from Gmail thread %s",
                len(messages),
                thread_id,
            )

        except Exception as e:
            logger.error(
                "CONTEXT_GATHERER: Gmail thread fetch error: %s",
                str(e),
                exc_info=True,
            )

        return messages

    async def _fetch_outlook_thread(
        self,
        entity: Any,
        thread_id: str,
    ) -> list[ThreadMessage]:
        """Fetch Outlook conversation thread."""
        messages: list[ThreadMessage] = []

        try:
            response = entity.execute(
                action="OUTLOOK365_LIST_MESSAGES",
                params={
                    "filter": f"conversationId eq '{thread_id}'",
                    "orderby": "receivedDateTime asc",
                    "top": 50,
                },
            )

            if not response or not response.get("success"):
                logger.error(
                    "CONTEXT_GATHERER: OUTLOOK365_LIST_MESSAGES failed: %s",
                    response.get("error", "Unknown error") if response else "No response",
                )
                return messages

            messages_data = response.get("data", {}).get("value", [])
            user_email = await self._get_user_email_from_integration()

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
                    is_from_user=user_email.lower() in sender_email.lower(),
                ))

            logger.info(
                "CONTEXT_GATHERER: Fetched %d messages from Outlook thread %s",
                len(messages),
                thread_id,
            )

        except Exception as e:
            logger.error(
                "CONTEXT_GATHERER: Outlook thread fetch error: %s",
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
        """Get user's email from their integration record."""
        return getattr(self, "_cached_user_email", "")

    async def _get_email_integration(self, user_id: str) -> dict[str, Any] | None:
        """Get user's email integration (Gmail or Outlook)."""
        try:
            result = (
                self._db.table("user_integrations")
                .select("*")
                .eq("user_id", user_id)
                .eq("integration_type", "gmail")
                .maybe_single()
                .execute()
            )
            if result.data:
                return result.data

            result = (
                self._db.table("user_integrations")
                .select("*")
                .eq("user_id", user_id)
                .eq("integration_type", "outlook")
                .maybe_single()
                .execute()
            )
            return result.data if result.data else None

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
    ) -> RecipientResearch | None:
        """Research the email sender via Exa API.

        Performs:
        1. People search for LinkedIn profile and bio
        2. Company search if company can be inferred

        Args:
            sender_email: The sender's email address.
            sender_name: The sender's display name.

        Returns:
            RecipientResearch with gathered intelligence, or None.
        """
        research = RecipientResearch(sender_email=sender_email, sender_name=sender_name)

        try:
            from src.agents.capabilities.enrichment_providers.exa_provider import (
                ExaEnrichmentProvider,
            )

            exa = ExaEnrichmentProvider()

            # Extract name parts for search
            name_parts = (sender_name or "").split()
            first_name = name_parts[0] if name_parts else ""
            last_name = name_parts[-1] if len(name_parts) > 1 else ""

            # Extract company from email domain
            domain = sender_email.split("@")[-1] if "@" in sender_email else ""
            # Skip common email providers
            common_providers = {"gmail.com", "outlook.com", "yahoo.com", "hotmail.com"}
            company_from_email = "" if domain in common_providers else domain.split(".")[0]

            # Search for person
            if sender_name:
                logger.info(
                    "CONTEXT_GATHERER: Searching Exa for person: %s",
                    sender_name,
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

            # Search for company if we have one
            company_name = research.sender_company or company_from_email
            if company_name:
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

            logger.info(
                "CONTEXT_GATHERER: Recipient research complete for %s, %d sources",
                sender_email,
                len(research.exa_sources_used),
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

        Args:
            user_id: The user's ID.
            sender_email: The recipient's email.

        Returns:
            RecipientWritingStyle profile or default.
        """
        style = RecipientWritingStyle()

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
                    "CONTEXT_GATHERER: Found style profile for %s (%d prior emails)",
                    sender_email,
                    style.email_count,
                )

        except Exception as e:
            logger.warning(
                "CONTEXT_GATHERER: Failed to get recipient style: %s",
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
        """Get relationship history from semantic memory.

        Queries memory_semantic for facts mentioning this contact,
        including interaction count, relationship type, and topics.

        Args:
            user_id: The user's ID.
            sender_email: The contact's email.

        Returns:
            RelationshipHistory with memory facts.
        """
        history = RelationshipHistory(sender_email=sender_email)

        try:
            # Query facts about this contact
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
                    # Parse metadata for structured data
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

                # Count interactions from email bootstrap data
                history.total_emails = len([
                    f for f in history.memory_facts
                    if f.get("source") == "email_bootstrap"
                ])

                # Get last interaction date
                if history.memory_facts:
                    history.last_interaction = history.memory_facts[0].get("created_at")

                logger.info(
                    "CONTEXT_GATHERER: Found %d memory facts for %s",
                    len(history.memory_facts),
                    sender_email,
                )

        except Exception as e:
            logger.warning(
                "CONTEXT_GATHERER: Failed to get relationship history: %s",
                str(e),
            )

        return history

    # ------------------------------------------------------------------
    # Corporate Memory
    # ------------------------------------------------------------------

    async def _get_corporate_memory(
        self,
        user_id: str,
        topic: str,
    ) -> CorporateMemoryContext:
        """Get relevant facts about user's own company.

        Queries memory_semantic for corporate facts that might be
        relevant to the email topic (products, partnerships, etc.).

        Args:
            user_id: The user's ID.
            topic: The email subject/topic for relevance.

        Returns:
            CorporateMemoryContext with relevant facts.
        """
        context = CorporateMemoryContext()

        try:
            # Search for corporate facts with topic keywords
            keywords = topic.split()[:5] if topic else []
            search_terms = " | ".join(keywords) if keywords else ""

            result = (
                self._db.table("memory_semantic")
                .select("*")
                .eq("user_id", user_id)
                .in_("source", ["company_facts", "corporate_memory", "onboarding"])
                .or_(f"fact.ilike.%{search_terms}%" if search_terms else "fact.ilike.%")
                .order("confidence", desc=True)
                .limit(10)
                .execute()
            )

            if result.data:
                for row in result.data:
                    context.facts.append({
                        "id": row.get("id"),
                        "fact": row.get("fact"),
                        "confidence": row.get("confidence"),
                        "source": row.get("source"),
                    })
                    context.fact_ids.append(row.get("id"))

                logger.info(
                    "CONTEXT_GATHERER: Found %d corporate memory facts for topic '%s'",
                    len(context.facts),
                    topic[:50],
                )

        except Exception as e:
            logger.warning(
                "CONTEXT_GATHERER: Failed to get corporate memory: %s",
                str(e),
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

            from composio import ComposioToolSet
            from datetime import timedelta

            toolset = ComposioToolSet()
            entity = toolset.get_entity(id=user_id)

            now = datetime.now(UTC)
            start_date = (now - timedelta(days=30)).strftime("%Y-%m-%d")
            end_date = (now + timedelta(days=30)).strftime("%Y-%m-%d")

            provider = calendar_integration.get("integration_type", "").lower()

            if "google" in provider:
                events = await self._fetch_google_calendar_events(
                    entity, start_date, end_date, sender_email
                )
            else:
                events = await self._fetch_outlook_calendar_events(
                    entity, start_date, end_date, sender_email
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
        entity: Any,
        start_date: str,
        end_date: str,
        sender_email: str,
    ) -> list[dict[str, Any]]:
        """Fetch Google Calendar events involving the sender."""
        events = []

        try:
            response = entity.execute(
                action="GOOGLECALENDAR_GET_EVENTS",
                params={
                    "timeMin": f"{start_date}T00:00:00Z",
                    "timeMax": f"{end_date}T23:59:59Z",
                    "maxResults": 50,
                },
            )

            if response and response.get("success"):
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
        entity: Any,
        start_date: str,
        end_date: str,
        sender_email: str,
    ) -> list[dict[str, Any]]:
        """Fetch Outlook Calendar events involving the sender."""
        events = []

        try:
            response = entity.execute(
                action="OUTLOOK365_CALENDAR_VIEW",
                params={
                    "startDateTime": f"{start_date}T00:00:00Z",
                    "endDateTime": f"{end_date}T23:59:59Z",
                    "top": 50,
                },
            )

            if response and response.get("success"):
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
        deal/account status and recent activities.

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
                return context

            context.connected = True

            from composio import ComposioToolSet

            toolset = ComposioToolSet()
            entity = toolset.get_entity(id=user_id)

            provider = crm_integration.get("integration_type", "").lower()

            if "salesforce" in provider:
                await self._fetch_salesforce_context(entity, sender_email, context)
            elif "hubspot" in provider:
                await self._fetch_hubspot_context(entity, sender_email, context)

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
        entity: Any,
        sender_email: str,
        context: CRMContext,
    ) -> None:
        """Fetch Salesforce context for contact."""
        try:
            response = entity.execute(
                action="SALESFORCE_SEARCH_RECORDS",
                params={
                    "search_string": sender_email,
                },
            )

            if response and response.get("success"):
                records = response.get("data", {}).get("searchRecords", [])

                for record in records:
                    if record.get("attributes", {}).get("type") == "Contact":
                        contact_id = record.get("Id")

                        opp_response = entity.execute(
                            action="SALESFORCE_QUERY",
                            params={
                                "query": f"SELECT StageName, Amount FROM Opportunity WHERE ContactId = '{contact_id}' LIMIT 1",
                            },
                        )

                        if opp_response and opp_response.get("success"):
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
        entity: Any,
        sender_email: str,
        context: CRMContext,
    ) -> None:
        """Fetch HubSpot context for contact."""
        try:
            response = entity.execute(
                action="HUBSPOT_SEARCH_CONTACTS",
                params={
                    "query": sender_email,
                    "limit": 1,
                },
            )

            if response and response.get("success"):
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

    async def _save_context(self, context: DraftContext) -> None:
        """Placeholder - implemented in Task 7."""
        pass
