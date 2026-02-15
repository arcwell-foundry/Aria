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
from src.services.email_client_writer import DraftSaveError, EmailClientWriter
from src.services.email_context_gatherer import (
    DraftContext,
    EmailContextGatherer,
)
from src.services.learning_mode_service import get_learning_mode_service

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
        self._client_writer = EmailClientWriter()
        self._learning_mode = get_learning_mode_service()

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

            # 2. Check learning mode status
            is_learning_mode = await self._learning_mode.is_learning_mode_active(user_id)
            top_contacts: list[str] = []

            if is_learning_mode:
                top_contacts = await self._learning_mode.get_top_contacts(user_id)
                logger.info(
                    "DRAFT_ENGINE: Learning mode ACTIVE for user %s. "
                    "Limiting to %d top contacts.",
                    user_id,
                    len(top_contacts),
                )

            # 3. Group emails by thread and deduplicate
            grouped_emails = await self._group_emails_by_thread(scan_result.needs_reply)

            emails_processed = 0
            emails_skipped_learning_mode = 0
            emails_skipped_existing_draft = 0
            emails_deferred_active_conversation = 0

            for thread_id, thread_emails in grouped_emails.items():
                # Check for existing draft first
                if await self._check_existing_draft(user_id, thread_id):
                    logger.info(
                        "DRAFT_ENGINE: Skipped: existing draft already generated for thread %s",
                        thread_id,
                    )
                    await self._log_skip_decision(user_id, thread_id, "existing_draft")
                    emails_skipped_existing_draft += 1
                    continue

                # Get only the latest email in thread
                email = await self._get_latest_email_in_thread(thread_emails)

                # Check for active conversation (rapid-fire)
                if await self._is_active_conversation(user_id, thread_id):
                    logger.info(
                        "DRAFT_ENGINE: Deferred: active conversation in thread %s",
                        thread_id,
                    )
                    await self._defer_draft(user_id, thread_id, email, "active_conversation")
                    await self._log_skip_decision(
                        user_id, thread_id, "active_conversation", email.email_id
                    )
                    emails_deferred_active_conversation += 1
                    continue

                # Apply learning mode filter
                if is_learning_mode:
                    sender_email = email.sender_email.lower().strip()
                    is_top_contact = any(
                        c.lower().strip() == sender_email for c in top_contacts
                    )

                    if not is_top_contact:
                        logger.debug(
                            "DRAFT_ENGINE: Skipping email from %s - not in top contacts (learning mode)",
                            email.sender_email,
                        )
                        emails_skipped_learning_mode += 1
                        continue

                # Increment interaction count for learning mode
                if is_learning_mode:
                    await self._learning_mode.increment_draft_interaction(user_id)

                emails_processed += 1
                try:
                    draft = await self._process_single_email(
                        user_id, user_name, email, is_learning_mode
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
                "DRAFT_ENGINE: Processing complete. %d drafts generated, %d failed, "
                "%d skipped (existing draft), %d deferred (active conversation), "
                "%d skipped (learning mode)",
                result.drafts_generated,
                result.drafts_failed,
                emails_skipped_existing_draft,
                emails_deferred_active_conversation,
                emails_skipped_learning_mode,
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
        is_learning_mode: bool = False,
    ) -> DraftResult:
        """Process a single email and generate a reply draft.

        Steps:
        a. Gather context via EmailContextGatherer
        b. Get style guidelines via DigitalTwin
        c. Get personality calibration
        d. Generate draft via LLM
        e. Score style match
        f. Calculate confidence level
        g. Generate ARIA notes (with learning mode note if applicable)
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
            style_score = await self._digital_twin.score_style_match(user_id, draft_content.body)

            # f. Calculate confidence
            confidence = self._calculate_confidence(context, style_score)

            # g. Generate ARIA notes (add learning mode note if applicable)
            aria_notes = await self._generate_aria_notes(
                email, context, style_score, confidence, is_learning_mode
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
                learning_mode_draft=is_learning_mode,
            )

            # i. Auto-save to email client (Gmail/Outlook)
            # Non-fatal: draft stays in ARIA database even if client save fails
            try:
                client_result = await self._client_writer.save_draft_to_client(
                    user_id=user_id,
                    draft_id=draft_id,
                )
                if client_result.get("success") and not client_result.get("already_saved"):
                    logger.info(
                        "DRAFT_ENGINE: Auto-saved draft %s to %s",
                        draft_id,
                        client_result.get("provider"),
                    )
            except DraftSaveError as e:
                logger.warning(
                    "DRAFT_ENGINE: Could not auto-save draft %s to client: %s",
                    draft_id,
                    e,
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
            error_notes = f"Failed: {e}"
            if is_learning_mode:
                error_notes = f"{self._learning_mode.get_learning_mode_note()} | {error_notes}"
            return DraftResult(
                draft_id="",
                recipient_email=email.sender_email,
                recipient_name=email.sender_name,
                subject="",
                body="",
                style_match_score=0.0,
                confidence_level=0.0,
                aria_notes=error_notes,
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
            thread_summary = (
                context.thread_context.summary or f"{context.thread_context.message_count} messages"
            )
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
            fact_lines = "\n".join(f"- {f.get('fact', str(f))}" for f in facts)
            sections.append(f"""=== RELATIONSHIP HISTORY ===
Total interactions: {context.relationship_history.total_emails}
Key facts:
{fact_lines}""")

        # Recipient style
        if context.recipient_style and context.recipient_style.exists:
            sections.append(f"""=== RECIPIENT'S COMMUNICATION STYLE ===
Formality: {context.recipient_style.formality_level:.1f}/1.0
Tone: {context.recipient_style.tone}
Uses emoji: {"Yes" if context.recipient_style.uses_emoji else "No"}""")

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
                f"- {m.get('summary', 'Meeting')} on {m.get('start', 'TBD')}" for m in meetings
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
        is_learning_mode: bool = False,
    ) -> str:
        """Generate internal notes explaining ARIA's reasoning.

        These notes help the user understand why ARIA drafted what it did.
        """
        notes: list[str] = []

        # Add learning mode note first if applicable
        if is_learning_mode:
            notes.append(self._learning_mode.get_learning_mode_note())

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
            "HIGH" if confidence >= 0.75 else "MEDIUM" if confidence >= 0.5 else "LOW"
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
        learning_mode_draft: bool = False,
    ) -> str:
        """Save draft with all metadata to email_drafts table."""
        draft_id = str(uuid4())

        self._db.table("email_drafts").insert(
            {
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
                "learning_mode_draft": learning_mode_draft,
            }
        ).execute()

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
            self._db.table("email_processing_runs").insert(
                {
                    "id": run_id,
                    "user_id": user_id,
                    "started_at": started_at.isoformat(),
                    "status": "running",
                }
            ).execute()
        except Exception as e:
            logger.error("DRAFT_ENGINE: Failed to create processing run: %s", e)

    async def _update_processing_run(self, result: ProcessingRunResult) -> None:
        """Update processing run with final status."""
        try:
            processing_time_ms = None
            if result.completed_at and result.started_at:
                delta = result.completed_at - result.started_at
                processing_time_ms = int(delta.total_seconds() * 1000)

            self._db.table("email_processing_runs").update(
                {
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
                }
            ).eq("id", result.run_id).execute()
        except Exception as e:
            logger.error("DRAFT_ENGINE: Failed to update processing run: %s", e)

    # ------------------------------------------------------------------
    # Deduplication Methods
    # ------------------------------------------------------------------

    async def _check_existing_draft(self, user_id: str, thread_id: str) -> bool:
        """Check if a draft already exists for this thread.

        Args:
            user_id: The user's ID.
            thread_id: The email thread/conversation ID.

        Returns:
            True if a draft exists, False otherwise.
        """
        try:
            result = (
                self._db.table("email_drafts")
                .select("id")
                .eq("user_id", user_id)
                .eq("thread_id", thread_id)
                .in_("status", ["draft", "saved_to_client"])
                .maybe_single()
                .execute()
            )
            return result.data is not None
        except Exception as e:
            logger.warning(
                "DRAFT_ENGINE: Failed to check existing draft for thread %s: %s",
                thread_id,
                e,
            )
            return False

    async def _group_emails_by_thread(self, emails: list[Any]) -> dict[str, list[Any]]:
        """Group emails by thread_id for deduplication.

        Args:
            emails: List of EmailCategory objects.

        Returns:
            Dict mapping thread_id to list of emails in that thread.
        """
        grouped: dict[str, list[Any]] = {}
        for email in emails:
            # Use thread_id if available, fallback to email_id
            tid = email.thread_id or email.email_id
            if tid not in grouped:
                grouped[tid] = []
            grouped[tid].append(email)
        return grouped

    async def _get_latest_email_in_thread(self, emails: list[Any]) -> Any:
        """Get the most recent email from a thread group.

        Args:
            emails: List of emails in the same thread.

        Returns:
            The most recent email (by scanned_at or email_id as fallback).
        """
        if len(emails) == 1:
            return emails[0]

        # Sort by scanned_at if available, otherwise by email_id
        def sort_key(email: Any) -> Any:
            if hasattr(email, "scanned_at") and email.scanned_at:
                return email.scanned_at
            return email.email_id

        return max(emails, key=sort_key)

    async def _is_active_conversation(self, user_id: str, thread_id: str) -> bool:
        """Check if thread has rapid back-and-forth activity (3+ messages in last hour).

        Reuses the logic from EmailAnalyzer._is_rapid_thread().

        Args:
            user_id: The user's ID.
            thread_id: The email thread/conversation ID.

        Returns:
            True if active conversation detected, False otherwise.
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
                    "DRAFT_ENGINE: Active conversation detected in thread %s (%d messages, %d senders)",
                    thread_id,
                    len(result.data),
                    len(unique_senders),
                )
                return True

            return False

        except Exception as e:
            logger.warning(
                "DRAFT_ENGINE: Active conversation check failed for thread %s: %s",
                thread_id,
                e,
            )
            return False

    async def _defer_draft(
        self,
        user_id: str,
        thread_id: str,
        email: Any,
        reason: str,
    ) -> str:
        """Add thread to deferred queue for later processing.

        Args:
            user_id: The user's ID.
            thread_id: The email thread/conversation ID.
            email: The email object with details to store.
            reason: The deferral reason ('active_conversation', etc.).

        Returns:
            The ID of the deferred draft record.
        """
        from datetime import timedelta

        deferred_id = str(uuid4())
        deferred_until = datetime.now(UTC) + timedelta(minutes=30)

        try:
            self._db.table("deferred_email_drafts").insert(
                {
                    "id": deferred_id,
                    "user_id": user_id,
                    "thread_id": thread_id,
                    "latest_email_id": email.email_id,
                    "subject": email.subject,
                    "sender_email": email.sender_email,
                    "deferred_until": deferred_until.isoformat(),
                    "reason": reason,
                    "status": "pending",
                }
            ).execute()

            logger.info(
                "DRAFT_ENGINE: Deferred thread %s until %s (reason: %s)",
                thread_id,
                deferred_until.isoformat(),
                reason,
            )

        except Exception as e:
            logger.error(
                "DRAFT_ENGINE: Failed to defer draft for thread %s: %s",
                thread_id,
                e,
            )

        return deferred_id

    async def _log_skip_decision(
        self,
        user_id: str,
        thread_id: str,
        reason: str,
        email_id: str | None = None,
    ) -> None:
        """Log skip/defer decision to email_scan_log for transparency.

        This enables the "why didn't ARIA draft?" feature.

        Args:
            user_id: The user's ID.
            thread_id: The email thread/conversation ID.
            reason: The skip reason ('existing_draft', 'active_conversation', etc.).
            email_id: Optional email ID (uses thread prefix if not provided).
        """
        try:
            log_id = str(uuid4())
            self._db.table("email_scan_log").insert(
                {
                    "id": log_id,
                    "user_id": user_id,
                    "email_id": email_id or f"thread:{thread_id}",
                    "thread_id": thread_id,
                    "sender_email": "system",
                    "subject": f"Draft skipped: {reason}",
                    "category": "SKIP",
                    "urgency": "LOW",
                    "needs_draft": False,
                    "reason": reason,
                    "scanned_at": datetime.now(UTC).isoformat(),
                }
            ).execute()
        except Exception as e:
            logger.warning(
                "DRAFT_ENGINE: Failed to log skip decision for thread %s: %s",
                thread_id,
                e,
            )


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
