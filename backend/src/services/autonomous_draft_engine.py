"""Autonomous email reply drafting engine.

Orchestrates inbox scanning, context gathering, and LLM-powered
draft generation with style matching and confidence scoring.

This is an ORCHESTRATION service that composes:
- EmailAnalyzer: Inbox scanning and categorization
- EmailContextGatherer: 7-source context aggregation
- DigitalTwin: Style matching and scoring
- PersonalityCalibrator: Tone guidance

It does NOT extend DraftService - it uses composition, not inheritance.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from src.core.llm import LLMClient
from src.db.supabase import SupabaseClient
from src.memory.digital_twin import DigitalTwin
from src.onboarding.personality_calibrator import PersonalityCalibrator
from src.services.email_analyzer import EmailAnalyzer
from src.services.email_context_gatherer import (
    DraftContext,
    EmailContextGatherer,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


@dataclass
class DraftResult:
    """Result of processing a single email into a draft."""

    draft_id: str
    recipient_email: str
    recipient_name: str | None
    subject: str
    body: str
    style_match_score: float
    confidence_level: float
    aria_notes: str
    original_email_id: str
    thread_id: str
    context_id: str
    success: bool = True
    error: str | None = None


@dataclass
class ProcessingRunResult:
    """Result of a full inbox processing run."""

    run_id: str
    user_id: str
    started_at: datetime
    completed_at: datetime | None = None
    emails_scanned: int = 0
    emails_needing_reply: int = 0
    drafts: list[DraftResult] = field(default_factory=list)
    drafts_generated: int = 0
    drafts_failed: int = 0
    status: str = "running"
    error_message: str | None = None


# ---------------------------------------------------------------------------
# LLM Response Models
# ---------------------------------------------------------------------------


class ReplyDraftContent(BaseModel):
    """LLM response model for reply draft content."""

    subject: str
    body: str


# ---------------------------------------------------------------------------
# Service Implementation
# ---------------------------------------------------------------------------


class AutonomousDraftEngine:
    """Orchestrates autonomous inbox processing and reply drafting.

    This engine:
    1. Scans inbox via EmailAnalyzer
    2. For each NEEDS_REPLY email, gathers context via EmailContextGatherer
    3. Generates style-matched draft via LLM
    4. Scores style match via DigitalTwin
    5. Calculates confidence based on context richness
    6. Generates ARIA notes explaining reasoning
    7. Saves draft with all metadata
    8. Tracks processing run in email_processing_runs table
    """

    REPLY_SYSTEM_PROMPT = """You are ARIA, an AI assistant drafting an email reply.

IMPORTANT: Your response MUST be valid JSON with exactly these fields:
{
  "subject": "The reply subject line (usually Re: original subject)",
  "body": "The full email body with greeting and signature"
}

Guidelines:
1. Start with an appropriate greeting based on the relationship
2. Acknowledge the sender's message specifically
3. Address any questions or requests directly
4. Be concise but thorough - match the sender's detail level
5. End with an appropriate sign-off
6. Sign as the user (use their provided name)

Do not include any text outside the JSON object."""

    def __init__(self) -> None:
        """Initialize with all required service dependencies."""
        self._db = SupabaseClient.get_client()
        self._llm = LLMClient()
        self._email_analyzer = EmailAnalyzer()
        self._context_gatherer = EmailContextGatherer()
        self._digital_twin = DigitalTwin()
        self._personality_calibrator = PersonalityCalibrator()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process_inbox(
        self,
        user_id: str,
        since_hours: int = 24,
    ) -> ProcessingRunResult:
        """Full autonomous email processing pipeline.

        Args:
            user_id: The user whose inbox to process.
            since_hours: How many hours back to scan.

        Returns:
            ProcessingRunResult with all draft results and statistics.
        """
        run_id = str(uuid4())
        started_at = datetime.now(UTC)

        result = ProcessingRunResult(
            run_id=run_id,
            user_id=user_id,
            started_at=started_at,
        )

        # Create processing run record
        await self._create_processing_run(run_id, user_id, started_at)

        try:
            logger.info(
                "DRAFT_ENGINE: Starting inbox processing for user %s (since %d hours)",
                user_id,
                since_hours,
            )

            # 1. Scan inbox via EmailAnalyzer
            scan_result = await self._email_analyzer.scan_inbox(user_id, since_hours)
            result.emails_scanned = scan_result.total_emails
            result.emails_needing_reply = len(scan_result.needs_reply)

            logger.info(
                "DRAFT_ENGINE: Scanned %d emails, %d need replies",
                result.emails_scanned,
                result.emails_needing_reply,
            )

            # Get user info for signature
            user_name = await self._get_user_name(user_id)

            # 2. Process each email needing reply
            for email in scan_result.needs_reply:
                try:
                    draft = await self._process_single_email(
                        user_id, user_name, email
                    )
                    result.drafts.append(draft)
                    if draft.success:
                        result.drafts_generated += 1
                    else:
                        result.drafts_failed += 1
                except Exception as e:
                    logger.error(
                        "DRAFT_ENGINE: Failed for %s: %s",
                        email.email_id,
                        e,
                        exc_info=True,
                    )
                    result.drafts_failed += 1

            # Determine final status
            if result.drafts_failed == 0:
                result.status = "completed"
            elif result.drafts_generated > 0:
                result.status = "partial_failure"
            else:
                result.status = "failed"

            logger.info(
                "DRAFT_ENGINE: Processing complete. %d drafts generated, %d failed",
                result.drafts_generated,
                result.drafts_failed,
            )

        except Exception as e:
            logger.error(
                "DRAFT_ENGINE: Processing failed for %s: %s",
                user_id,
                e,
                exc_info=True,
            )
            result.status = "failed"
            result.error_message = str(e)

        result.completed_at = datetime.now(UTC)
        await self._update_processing_run(result)

        return result

    # ------------------------------------------------------------------
    # Single Email Processing
    # ------------------------------------------------------------------

    async def _process_single_email(
        self,
        user_id: str,
        user_name: str,
        email: Any,  # EmailCategory from email_analyzer
    ) -> DraftResult:
        """Process a single email and generate a reply draft.

        Steps:
        a. Gather context via EmailContextGatherer
        b. Get style guidelines via DigitalTwin
        c. Get personality calibration
        d. Generate draft via LLM
        e. Score style match
        f. Calculate confidence level
        g. Generate ARIA notes
        h. Save draft with all metadata
        """
        try:
            logger.info(
                "DRAFT_ENGINE: Processing email %s from %s",
                email.email_id,
                email.sender_email,
            )

            # a. Gather context
            context = await self._context_gatherer.gather_context(
                user_id=user_id,
                email_id=email.email_id,
                thread_id=email.thread_id,
                sender_email=email.sender_email,
                sender_name=email.sender_name,
                subject=email.subject,
            )

            # b. Get style guidelines
            style_guidelines = await self._digital_twin.get_style_guidelines(user_id)

            # c. Get personality calibration
            calibration = await self._personality_calibrator.get_calibration(user_id)
            tone_guidance = calibration.tone_guidance if calibration else ""

            # d. Generate draft via LLM
            draft_content = await self._generate_reply_draft(
                user_name, email, context, style_guidelines, tone_guidance
            )

            # e. Score style match
            style_score = await self._digital_twin.score_style_match(
                user_id, draft_content.body
            )

            # f. Calculate confidence
            confidence = self._calculate_confidence(context, style_score)

            # g. Generate ARIA notes
            aria_notes = await self._generate_aria_notes(
                email, context, style_score, confidence
            )

            # h. Save draft with all metadata
            draft_id = await self._save_draft_with_metadata(
                user_id=user_id,
                recipient_email=email.sender_email,
                recipient_name=email.sender_name,
                subject=draft_content.subject,
                body=draft_content.body,
                original_email_id=email.email_id,
                thread_id=email.thread_id,
                context_id=context.id,
                style_match_score=style_score,
                confidence_level=confidence,
                aria_notes=aria_notes,
                urgency=email.urgency,
            )

            logger.info(
                "DRAFT_ENGINE: Draft %s created (confidence: %.2f, style: %.2f)",
                draft_id,
                confidence,
                style_score,
            )

            return DraftResult(
                draft_id=draft_id,
                recipient_email=email.sender_email,
                recipient_name=email.sender_name,
                subject=draft_content.subject,
                body=draft_content.body,
                style_match_score=style_score,
                confidence_level=confidence,
                aria_notes=aria_notes,
                original_email_id=email.email_id,
                thread_id=email.thread_id,
                context_id=context.id,
                success=True,
            )

        except Exception as e:
            logger.error(
                "DRAFT_ENGINE: Failed to process email %s: %s",
                email.email_id,
                e,
                exc_info=True,
            )
            return DraftResult(
                draft_id="",
                recipient_email=email.sender_email,
                recipient_name=email.sender_name,
                subject="",
                body="",
                style_match_score=0.0,
                confidence_level=0.0,
                aria_notes=f"Failed: {e}",
                original_email_id=email.email_id,
                thread_id=email.thread_id,
                context_id="",
                success=False,
                error=str(e),
            )

    # ------------------------------------------------------------------
    # LLM Draft Generation
    # ------------------------------------------------------------------

    async def _generate_reply_draft(
        self,
        user_name: str,
        email: Any,
        context: DraftContext,
        style_guidelines: str,
        tone_guidance: str,
    ) -> ReplyDraftContent:
        """Generate reply draft via LLM with full context.

        Args:
            user_id: User ID (for logging).
            user_name: User's name for signature.
            email: Original email (EmailCategory).
            context: Full context from EmailContextGatherer.
            style_guidelines: Style guidelines from DigitalTwin.
            tone_guidance: Tone guidance from PersonalityCalibrator.

        Returns:
            ReplyDraftContent with subject and body.
        """
        prompt = self._build_reply_prompt(
            user_name, email, context, style_guidelines, tone_guidance
        )

        response = await self._llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=self.REPLY_SYSTEM_PROMPT,
            temperature=0.7,
        )

        # Parse JSON response
        try:
            data = json.loads(response.strip())
            return ReplyDraftContent(
                subject=data.get("subject", f"Re: {email.subject}"),
                body=data.get("body", response),
            )
        except json.JSONDecodeError:
            # Fallback: use raw response as body
            logger.warning(
                "DRAFT_ENGINE: LLM returned non-JSON for email %s, using fallback",
                email.email_id,
            )
            return ReplyDraftContent(
                subject=f"Re: {email.subject}",
                body=response,
            )

    def _build_reply_prompt(
        self,
        user_name: str,
        email: Any,
        context: DraftContext,
        style_guidelines: str,
        tone_guidance: str,
    ) -> str:
        """Build comprehensive reply generation prompt.

        Assembles all context sections into a structured prompt.
        """
        sections: list[str] = []

        # Original email
        sections.append(f"""=== ORIGINAL EMAIL ===
From: {email.sender_name} <{email.sender_email}>
Subject: {email.subject}
Urgency: {email.urgency}
Body: {email.snippet}""")

        # Thread context
        if context.thread_context and context.thread_context.messages:
            thread_summary = context.thread_context.summary or f"{context.thread_context.message_count} messages"
            recent_messages = context.thread_context.messages[-3:]
            recent = "\n".join(
                f"- {m.sender_name}: {m.body[:200]}{'...' if len(m.body) > 200 else ''}"
                for m in recent_messages
            )
            sections.append(f"""=== CONVERSATION THREAD ===
Summary: {thread_summary}
Recent messages:
{recent}""")

        # Recipient research
        if context.recipient_research:
            r = context.recipient_research
            info = []
            if r.sender_title:
                info.append(f"Title: {r.sender_title}")
            if r.sender_company:
                info.append(f"Company: {r.sender_company}")
            if r.bio:
                info.append(f"Bio: {r.bio[:300]}{'...' if len(r.bio) > 300 else ''}")
            if info:
                sections.append("=== ABOUT THE RECIPIENT ===\n" + "\n".join(info))

        # Relationship history
        if context.relationship_history and context.relationship_history.memory_facts:
            facts = context.relationship_history.memory_facts[:3]
            fact_lines = "\n".join(
                f"- {f.get('fact', str(f))}" for f in facts
            )
            sections.append(f"""=== RELATIONSHIP HISTORY ===
Total interactions: {context.relationship_history.total_emails}
Key facts:
{fact_lines}""")

        # Recipient style
        if context.recipient_style and context.recipient_style.exists:
            sections.append(f"""=== RECIPIENT'S COMMUNICATION STYLE ===
Formality: {context.recipient_style.formality_level:.1f}/1.0
Tone: {context.recipient_style.tone}
Uses emoji: {'Yes' if context.recipient_style.uses_emoji else 'No'}""")

        # User's style
        sections.append(f"""=== YOUR WRITING STYLE (MATCH THIS) ===
{style_guidelines}""")

        # Tone guidance
        if tone_guidance:
            sections.append(f"""=== TONE GUIDANCE ===
{tone_guidance}""")

        # Calendar context
        if context.calendar_context and context.calendar_context.upcoming_meetings:
            meetings = context.calendar_context.upcoming_meetings[:2]
            meeting_lines = "\n".join(
                f"- {m.get('summary', 'Meeting')} on {m.get('start', 'TBD')}"
                for m in meetings
            )
            sections.append(f"""=== UPCOMING MEETINGS ===
{meeting_lines}""")

        # CRM context
        if context.crm_context and context.crm_context.connected:
            crm_info = []
            if context.crm_context.lead_stage:
                crm_info.append(f"Lead stage: {context.crm_context.lead_stage}")
            if context.crm_context.deal_value:
                crm_info.append(f"Deal value: ${context.crm_context.deal_value:,.0f}")
            if crm_info:
                sections.append("=== CRM STATUS ===\n" + "\n".join(crm_info))

        # User info and task
        sections.append(f"""=== YOUR INFO ===
Your name: {user_name}

=== TASK ===
Write a reply to this email. Match the writing style exactly.

Respond with JSON: {{"subject": "...", "body": "..."}}""")

        return "\n\n".join(sections)

    # ------------------------------------------------------------------
    # Confidence Calculation
    # ------------------------------------------------------------------

    def _calculate_confidence(
        self,
        context: DraftContext,
        style_score: float,
    ) -> float:
        """Calculate confidence level (0.0-1.0).

        Confidence is based on:
        - Context richness (number of sources used)
        - Thread history depth
        - Recipient research availability
        - Relationship history depth
        - Style match score
        """
        score = 0.5  # Base confidence

        # Context richness
        num_sources = len(context.sources_used)
        if num_sources >= 5:
            score += 0.15
        elif num_sources >= 3:
            score += 0.10
        elif num_sources >= 1:
            score += 0.05

        # Thread history
        if context.thread_context and context.thread_context.message_count > 0:
            score += 0.10
            if context.thread_context.message_count >= 3:
                score += 0.05

        # Recipient research
        if context.recipient_research:
            if context.recipient_research.bio:
                score += 0.05
            if context.recipient_research.company_description:
                score += 0.05

        # Relationship history
        if context.relationship_history:
            if context.relationship_history.total_emails >= 5:
                score += 0.10
            elif context.relationship_history.total_emails >= 2:
                score += 0.05

        # Style match contribution
        score += 0.15 * style_score

        return max(0.0, min(1.0, score))

    # ------------------------------------------------------------------
    # ARIA Notes Generation
    # ------------------------------------------------------------------

    async def _generate_aria_notes(
        self,
        email: Any,
        context: DraftContext,
        style_score: float,
        confidence: float,
    ) -> str:
        """Generate internal notes explaining ARIA's reasoning.

        These notes help the user understand why ARIA drafted what it did.
        """
        notes: list[str] = []

        # Context sources used
        if context.sources_used:
            notes.append(f"Context sources: {', '.join(context.sources_used)}")

        # Relationship context
        if context.relationship_history and context.relationship_history.total_emails > 0:
            notes.append(f"Prior relationship: {context.relationship_history.total_emails} emails")
        else:
            notes.append("New contact - no prior relationship data")

        # Style warning
        if style_score < 0.7:
            notes.append(f"WARNING: Style match is low ({style_score:.2f}). Review recommended.")

        # Urgency flag
        if email.urgency == "URGENT":
            notes.append("URGENT: User should review carefully before sending.")

        # Confidence level
        confidence_label = (
            "HIGH" if confidence >= 0.75
            else "MEDIUM" if confidence >= 0.5
            else "LOW"
        )
        notes.append(f"Confidence: {confidence_label} ({confidence:.2f})")

        return " | ".join(notes)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def _save_draft_with_metadata(
        self,
        user_id: str,
        recipient_email: str,
        recipient_name: str | None,
        subject: str,
        body: str,
        original_email_id: str,
        thread_id: str,
        context_id: str,
        style_match_score: float,
        confidence_level: float,
        aria_notes: str,
        urgency: str,
    ) -> str:
        """Save draft with all metadata to email_drafts table."""
        draft_id = str(uuid4())

        self._db.table("email_drafts").insert({
            "id": draft_id,
            "user_id": user_id,
            "recipient_email": recipient_email,
            "recipient_name": recipient_name,
            "subject": subject,
            "body": body,
            "purpose": "reply",
            "tone": "urgent" if urgency == "URGENT" else "friendly",
            "original_email_id": original_email_id,
            "thread_id": thread_id,
            "draft_context_id": context_id,
            "style_match_score": style_match_score,
            "confidence_level": confidence_level,
            "aria_notes": aria_notes,
            "status": "draft",
        }).execute()

        return draft_id

    async def _get_user_name(self, user_id: str) -> str:
        """Get user's full name from profile."""
        try:
            result = (
                self._db.table("user_profiles")
                .select("full_name")
                .eq("id", user_id)
                .maybe_single()
                .execute()
            )

            if result and result.data:
                return result.data.get("full_name", "there")
        except Exception as e:
            logger.warning("DRAFT_ENGINE: Failed to get user name: %s", e)

        return "there"

    async def _create_processing_run(
        self,
        run_id: str,
        user_id: str,
        started_at: datetime,
    ) -> None:
        """Create processing run record."""
        try:
            self._db.table("email_processing_runs").insert({
                "id": run_id,
                "user_id": user_id,
                "started_at": started_at.isoformat(),
                "status": "running",
            }).execute()
        except Exception as e:
            logger.error("DRAFT_ENGINE: Failed to create processing run: %s", e)

    async def _update_processing_run(self, result: ProcessingRunResult) -> None:
        """Update processing run with final status."""
        try:
            processing_time_ms = None
            if result.completed_at and result.started_at:
                delta = result.completed_at - result.started_at
                processing_time_ms = int(delta.total_seconds() * 1000)

            self._db.table("email_processing_runs").update({
                "completed_at": (
                    result.completed_at.isoformat() if result.completed_at else None
                ),
                "emails_scanned": result.emails_scanned,
                "emails_needing_reply": result.emails_needing_reply,
                "drafts_generated": result.drafts_generated,
                "drafts_failed": result.drafts_failed,
                "status": result.status,
                "error_message": result.error_message,
                "processing_time_ms": processing_time_ms,
            }).eq("id", result.run_id).execute()
        except Exception as e:
            logger.error("DRAFT_ENGINE: Failed to update processing run: %s", e)


# ---------------------------------------------------------------------------
# Singleton Access
# ---------------------------------------------------------------------------

_engine: AutonomousDraftEngine | None = None


def get_autonomous_draft_engine() -> AutonomousDraftEngine:
    """Get the singleton AutonomousDraftEngine instance."""
    global _engine
    if _engine is None:
        _engine = AutonomousDraftEngine()
    return _engine
