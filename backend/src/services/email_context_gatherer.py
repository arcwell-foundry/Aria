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
