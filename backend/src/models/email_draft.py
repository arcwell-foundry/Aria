"""Pydantic models for email drafts."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class EmailDraftPurpose(str, Enum):
    """Purpose categories for email drafts."""

    INTRO = "intro"
    FOLLOW_UP = "follow_up"
    PROPOSAL = "proposal"
    THANK_YOU = "thank_you"
    CHECK_IN = "check_in"
    REPLY = "reply"
    OTHER = "other"


class EmailDraftTone(str, Enum):
    """Tone options for email drafts."""

    FORMAL = "formal"
    FRIENDLY = "friendly"
    URGENT = "urgent"


class EmailDraftStatus(str, Enum):
    """Status of an email draft."""

    DRAFT = "draft"
    SENT = "sent"
    FAILED = "failed"


class DraftUserAction(str, Enum):
    """User action on an ARIA-generated draft for learning mode."""

    PENDING = "pending"
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"
    IGNORED = "ignored"


class EmailDraftCreate(BaseModel):
    """Request model for creating an email draft."""

    recipient_email: EmailStr = Field(..., description="Recipient's email address")
    recipient_name: str | None = Field(None, description="Recipient's name for personalization")
    subject_hint: str | None = Field(None, description="Optional hint for subject line generation")
    purpose: EmailDraftPurpose = Field(..., description="Purpose of the email")
    context: str | None = Field(None, description="Additional context for draft generation")
    tone: EmailDraftTone = Field(EmailDraftTone.FRIENDLY, description="Desired tone")
    lead_memory_id: str | None = Field(None, description="Optional lead memory ID for context")


class EmailDraftUpdate(BaseModel):
    """Request model for updating an email draft."""

    recipient_email: EmailStr | None = Field(None, description="Updated recipient email")
    recipient_name: str | None = Field(None, description="Updated recipient name")
    subject: str | None = Field(None, description="Updated subject line")
    body: str | None = Field(None, description="Updated email body")
    tone: EmailDraftTone | None = Field(None, description="Updated tone")


class EmailDraftResponse(BaseModel):
    """Response model for an email draft."""

    id: str = Field(..., description="Draft ID")
    user_id: str = Field(..., description="Owner user ID")
    recipient_email: str = Field(..., description="Recipient's email address")
    recipient_name: str | None = Field(None, description="Recipient's name")
    subject: str = Field(..., description="Email subject line")
    body: str = Field(..., description="Email body content")
    purpose: EmailDraftPurpose = Field(..., description="Purpose of the email")
    tone: EmailDraftTone = Field(..., description="Tone of the email")
    context: dict[str, Any] | None = Field(None, description="Context used for generation")
    lead_memory_id: str | None = Field(None, description="Associated lead memory ID")
    style_match_score: float | None = Field(
        None, ge=0.0, le=1.0, description="How well the draft matches user's style"
    )
    status: EmailDraftStatus = Field(..., description="Current status of the draft")
    sent_at: datetime | None = Field(None, description="When the email was sent")
    error_message: str | None = Field(None, description="Error message if sending failed")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    # Fields for autonomous reply drafts
    original_email_id: str | None = Field(None, description="ID of original email this replies to")
    thread_id: str | None = Field(None, description="Email thread ID")
    confidence_level: float | None = Field(
        None, ge=0.0, le=1.0, description="ARIA confidence in draft quality"
    )
    aria_notes: str | None = Field(None, description="Internal ARIA reasoning notes")
    draft_context_id: str | None = Field(None, description="Reference to full context used")
    # Fields for email client sync (Gmail/Outlook)
    client_draft_id: str | None = Field(None, description="ID of draft in Gmail/Outlook")
    client_provider: str | None = Field(
        None, description="Email client where draft is saved (gmail or outlook)"
    )
    saved_to_client_at: datetime | None = Field(None, description="When saved to client")
    in_reply_to: str | None = Field(
        None, description="Message-ID of email being replied to (for threading)"
    )
    # Fields for learning mode and feedback tracking
    user_action: DraftUserAction | None = Field(
        None, description="User action on draft: pending/approved/edited/rejected/ignored"
    )
    user_edited_body: str | None = Field(
        None, description="If edited, stores the user-modified version"
    )
    edit_distance: float | None = Field(
        None, ge=0.0, le=1.0, description="Levenshtein ratio between original and edited draft"
    )
    action_detected_at: datetime | None = Field(
        None, description="When the user action was detected"
    )
    learning_mode_draft: bool | None = Field(
        None, description="Whether this draft was created during learning mode period"
    )
    confidence_tier: str | None = Field(
        None, description="Confidence tier: HIGH, MEDIUM, LOW, or MINIMAL"
    )
    # Fields for staleness detection
    is_stale: bool | None = Field(
        None, description="Whether the draft is stale (thread evolved after creation)"
    )
    stale_reason: str | None = Field(
        None, description="Human-readable explanation of why the draft is stale"
    )


class EmailDraftListResponse(BaseModel):
    """Response model for listing email drafts."""

    id: str
    recipient_email: str
    recipient_name: str | None
    subject: str
    purpose: EmailDraftPurpose
    tone: EmailDraftTone
    status: EmailDraftStatus
    style_match_score: float | None
    confidence_tier: str | None = None
    created_at: datetime


class EmailRegenerateRequest(BaseModel):
    """Request model for regenerating an email draft."""

    tone: EmailDraftTone | None = Field(None, description="New tone for regeneration")
    additional_context: str | None = Field(None, description="Additional context for regeneration")


class EmailSendResponse(BaseModel):
    """Response model for sending an email."""

    id: str = Field(..., description="Draft ID")
    status: EmailDraftStatus = Field(..., description="New status after send attempt")
    sent_at: datetime | None = Field(None, description="When email was sent")
    error_message: str | None = Field(None, description="Error if send failed")
