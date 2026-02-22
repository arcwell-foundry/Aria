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
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from src.core.llm import LLMClient
from src.db.supabase import SupabaseClient
from src.memory.digital_twin import DigitalTwin
from src.onboarding.personality_calibrator import PersonalityCalibrator
from src.services.activity_service import ActivityService
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
    emails_needs_reply: int = 0
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

    _FALLBACK_REPLY_PROMPT = (
        "You are drafting an email reply on behalf of the user. "
        "You must match their exact writing style — they should not be able "
        "to tell this wasn't written by them. Write naturally, not like an AI."
    )

    _REPLY_TASK_INSTRUCTIONS = """
IMPORTANT: Your response MUST be valid JSON with exactly these fields:
{
  "subject": "The reply subject line (usually Re: original subject)",
  "body": "The full email body with greeting and signature"
}

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
        self._activity_service = ActivityService()

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

        # Clean up any orphaned runs from previous crashes
        await self._cleanup_stale_runs(user_id)

        # Create processing run record
        await self._create_processing_run(run_id, user_id, started_at)

        try:
            logger.info(
                "[EMAIL_PIPELINE] Stage: inbox_processing_started | user_id=%s | since_hours=%d | run_id=%s",
                user_id,
                since_hours,
                run_id,
            )

            # 1. Scan inbox via EmailAnalyzer
            scan_result = await self._email_analyzer.scan_inbox(user_id, since_hours)
            result.emails_scanned = scan_result.total_emails
            result.emails_needs_reply = len(scan_result.needs_reply)

            logger.info(
                "[EMAIL_PIPELINE] Stage: scan_complete | emails_scanned=%d | needs_reply=%d | fyi=%d | skipped=%d | run_id=%s",
                result.emails_scanned,
                result.emails_needs_reply,
                len(scan_result.fyi),
                len(scan_result.skipped),
                run_id,
            )

            # Log inbox scan to activity feed (non-blocking)
            try:
                await self._activity_service.record(
                    user_id=user_id,
                    agent="scout",
                    activity_type="inbox_scanned",
                    title=f"Inbox scanned: {result.emails_scanned} emails",
                    description=f"{result.emails_needs_reply} need attention, {len(scan_result.fyi)} FYI, {len(scan_result.skipped)} filtered",
                    confidence=0.95,
                    metadata={
                        "emails_scanned": result.emails_scanned,
                        "needs_reply": result.emails_needs_reply,
                        "fyi_count": len(scan_result.fyi),
                        "filtered_count": len(scan_result.skipped),
                    },
                )
            except Exception as e:
                logger.warning(
                    "DRAFT_ENGINE: Failed to log inbox scan activity: %s",
                    e,
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

                if not top_contacts:
                    logger.warning(
                        "DRAFT_ENGINE: No top contacts in learning mode for user %s. "
                        "This is expected for new users - will populate after first email interactions. "
                        "Processing first 3 emails anyway to bootstrap.",
                        user_id,
                    )

            # 3. Group emails by thread and deduplicate
            grouped_emails = await self._group_emails_by_thread(scan_result.needs_reply)

            # 3b. Pre-fetch sent thread IDs (one API call for dedup)
            sent_thread_ids = await self._fetch_sent_thread_ids(user_id, since_hours)

            emails_processed = 0
            emails_skipped_learning_mode = 0
            emails_skipped_existing_draft = 0
            emails_skipped_already_replied = 0
            emails_deferred_active_conversation = 0

            for thread_id, thread_emails in grouped_emails.items():
                # Collect email_ids for cross-run dedup check
                thread_email_ids = [e.email_id for e in thread_emails]

                # Check for existing draft first (across ALL processing runs)
                existing_draft_id = await self._check_existing_draft(
                    user_id, thread_id, thread_email_ids
                )
                if existing_draft_id:
                    logger.info(
                        "SKIP_DUPLICATE: Draft already exists for thread_id=%s, draft_id=%s",
                        thread_id,
                        existing_draft_id,
                    )
                    await self._log_skip_decision(user_id, thread_id, "existing_draft")
                    emails_skipped_existing_draft += 1
                    continue

                # Check if user already replied to this thread
                if await self._user_already_replied(user_id, thread_id, sent_thread_ids):
                    logger.info(
                        "SKIP_ALREADY_REPLIED: User already replied in thread_id=%s",
                        thread_id,
                    )
                    await self._log_skip_decision(
                        user_id, thread_id, "already_replied",
                        thread_emails[0].email_id if thread_emails else None,
                    )
                    emails_skipped_already_replied += 1
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
                # If no top contacts yet, process first 3 emails to bootstrap
                if is_learning_mode and top_contacts:
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
                    logger.info(
                        "[EMAIL_PIPELINE] Stage: processing_email | email_id=%s | sender=%s | subject=%s | run_id=%s",
                        email.email_id,
                        email.sender_email,
                        email.subject,
                        run_id,
                    )
                    draft = await self._process_single_email(
                        user_id, user_name, email, is_learning_mode, run_id
                    )
                    result.drafts.append(draft)
                    if draft.success:
                        result.drafts_generated += 1
                        logger.info(
                            "[EMAIL_PIPELINE] Stage: draft_generated | draft_id=%s | email_id=%s | confidence=%.2f | run_id=%s",
                            draft.draft_id,
                            email.email_id,
                            draft.confidence_level,
                            run_id,
                        )
                    else:
                        result.drafts_failed += 1
                        logger.warning(
                            "[EMAIL_PIPELINE] Stage: draft_failed | email_id=%s | error=%s | run_id=%s",
                            email.email_id,
                            draft.error,
                            run_id,
                        )
                except Exception as e:
                    logger.error(
                        "[EMAIL_PIPELINE] Stage: draft_exception | email_id=%s | error=%s | run_id=%s",
                        email.email_id,
                        e,
                        run_id,
                        exc_info=True,
                    )
                    result.drafts_failed += 1

            # Determine final status
            if result.drafts_failed == 0:
                result.status = "completed"
            elif result.drafts_generated > 0:
                result.status = "partial_failure"
            else:
                if result.emails_needs_reply == 0:
                    result.status = "completed"
                else:
                    result.status = "failed"

            logger.info(
                "[EMAIL_PIPELINE] Stage: run_complete | run_id=%s | "
                "drafts_generated=%d | drafts_failed=%d | "
                "skipped_existing=%d | skipped_already_replied=%d | "
                "deferred_active=%d | skipped_learning=%d | status=%s",
                run_id,
                result.drafts_generated,
                result.drafts_failed,
                emails_skipped_existing_draft,
                emails_skipped_already_replied,
                emails_deferred_active_conversation,
                emails_skipped_learning_mode,
                result.status,
            )

        except Exception as e:
            logger.error(
                "[EMAIL_PIPELINE] Stage: run_failed | run_id=%s | user_id=%s | error=%s",
                run_id,
                user_id,
                e,
                exc_info=True,
            )
            result.status = "failed"
            result.error_message = str(e)
        finally:
            # Always finalize the processing run, even on failure
            result.completed_at = datetime.now(UTC)
            await self._update_processing_run(result)

        return result

    # ------------------------------------------------------------------
    # On-Demand Draft (from Chat)
    # ------------------------------------------------------------------

    async def draft_reply_on_demand(
        self,
        user_id: str,
        email_data: dict[str, Any],
        special_instructions: str | None = None,
    ) -> dict[str, Any]:
        """Draft a reply to a specific email on demand (triggered from chat).

        Uses the full drafting pipeline: context gathering, style matching,
        LLM generation, confidence scoring, and email client save.

        Args:
            user_id: The user's ID.
            email_data: Dict with email_id, thread_id, sender_email,
                        sender_name, subject, body, snippet, urgency.
            special_instructions: Optional user instructions for the draft.

        Returns:
            Dict with draft details for chat display.
        """
        email = SimpleNamespace(**email_data)
        user_name = await self._get_user_name(user_id)

        try:
            # a. Gather context (with fallback on error)
            try:
                context = await self._context_gatherer.gather_context(
                    user_id=user_id,
                    email_id=email.email_id,
                    thread_id=email.thread_id,
                    sender_email=email.sender_email,
                    sender_name=email.sender_name,
                    subject=email.subject,
                )
            except Exception as e:
                logger.error(
                    "ON_DEMAND_DRAFT: Context gathering failed: %s", e, exc_info=True,
                )
                context = DraftContext(
                    user_id=user_id,
                    email_id=email.email_id,
                    thread_id=email.thread_id,
                    sender_email=email.sender_email,
                    subject=email.subject or "(no subject)",
                    sources_used=["fallback_minimal"],
                )

            # b. Get style guidelines
            style_guidelines = await self._digital_twin.get_style_guidelines(user_id)

            # c. Get personality calibration
            calibration = await self._personality_calibrator.get_calibration(user_id)
            tone_guidance = calibration.tone_guidance if calibration else ""

            # d. Generate draft via LLM
            draft_content = await self._generate_reply_draft(
                user_id, user_name, email, context,
                style_guidelines, tone_guidance,
                special_instructions=special_instructions,
            )

            # e. Score style match
            style_score = await self._digital_twin.score_style_match(
                user_id, draft_content.body,
            )

            # f. Calculate confidence
            confidence = self._calculate_confidence(context)

            # g. Generate ARIA notes
            aria_notes = await self._generate_aria_notes(
                email, context, style_score, confidence,
            )

            # h. Save draft with metadata
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

            # Update draft_context FK
            if context.id:
                await self._context_gatherer.update_draft_id(context.id, draft_id)

            # i. Save to email client (non-fatal)
            saved_to_client = False
            try:
                client_result = await self._client_writer.save_draft_to_client(
                    user_id=user_id,
                    draft_id=draft_id,
                )
                saved_to_client = bool(
                    client_result.get("success") and not client_result.get("already_saved")
                )
            except Exception as e:
                logger.warning("ON_DEMAND_DRAFT: Client save failed (non-fatal): %s", e)

            # j. Log activity
            try:
                await self._activity_service.record(
                    user_id=user_id,
                    agent="scribe",
                    activity_type="email_drafted",
                    title=f"Drafted reply to {email.sender_name or email.sender_email}",
                    description=f"Re: {draft_content.subject} (on-demand via chat)",
                    reasoning=aria_notes,
                    confidence=confidence,
                    related_entity_type="email_draft",
                    related_entity_id=draft_id,
                    metadata={
                        "recipient_email": email.sender_email,
                        "style_match_score": style_score,
                        "confidence_level": confidence,
                        "original_email_id": email.email_id,
                        "thread_id": email.thread_id,
                        "trigger": "chat_request",
                    },
                )
            except Exception as e:
                logger.warning("ON_DEMAND_DRAFT: Activity log failed: %s", e)

            sender_label = email.sender_name or email.sender_email
            client_msg = (
                "saved it to your drafts folder"
                if saved_to_client
                else "saved it in ARIA"
            )
            return {
                "draft_id": draft_id,
                "to": email.sender_email,
                "to_name": email.sender_name,
                "subject": draft_content.subject,
                "body": draft_content.body,
                "aria_notes": aria_notes,
                "confidence": confidence,
                "style_match": style_score,
                "saved_to_client": saved_to_client,
                "message": (
                    f"I've drafted a reply to {sender_label}'s email "
                    f'about "{email.subject}" and {client_msg}.'
                ),
            }

        except Exception as e:
            logger.error("ON_DEMAND_DRAFT: Failed: %s", e, exc_info=True)
            return {
                "error": f"Failed to generate draft: {e}",
                "email_subject": email_data.get("subject", ""),
            }

    # ------------------------------------------------------------------
    # Single Email Processing
    # ------------------------------------------------------------------

    async def _process_single_email(
        self,
        user_id: str,
        user_name: str,
        email: Any,  # EmailCategory from email_analyzer
        is_learning_mode: bool = False,
        run_id: str | None = None,
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
                "[EMAIL_PIPELINE] Stage: gathering_context | email_id=%s | sender=%s | subject=%s",
                email.email_id,
                email.sender_email,
                email.subject,
            )

            # a. Gather context (with fallback on error)
            try:
                context = await self._context_gatherer.gather_context(
                    user_id=user_id,
                    email_id=email.email_id,
                    thread_id=email.thread_id,
                    sender_email=email.sender_email,
                    sender_name=email.sender_name,
                    subject=email.subject,
                )
                logger.info(
                    "[EMAIL_PIPELINE] Stage: context_gathered | email_id=%s | context_id=%s | sources=%s",
                    email.email_id,
                    context.id,
                    context.sources_used,
                )
            except Exception as e:
                logger.error(
                    "[EMAIL_PIPELINE] Stage: context_gathering_failed | email_id=%s | error=%s",
                    email.email_id,
                    e,
                    exc_info=True,
                )
                # Create minimal fallback context
                context = DraftContext(
                    user_id=user_id,
                    email_id=email.email_id,
                    thread_id=email.thread_id,
                    sender_email=email.sender_email,
                    subject=email.subject or "(no subject)",
                    sources_used=["fallback_minimal"],
                )
                logger.info(
                    "DRAFT_ENGINE: Using fallback context for email %s",
                    email.email_id,
                )

            # b. Get style guidelines
            style_guidelines = await self._digital_twin.get_style_guidelines(user_id)

            # c. Get personality calibration
            calibration = await self._personality_calibrator.get_calibration(user_id)
            tone_guidance = calibration.tone_guidance if calibration else ""

            # d. Generate draft via LLM
            logger.info(
                "[EMAIL_PIPELINE] Stage: generating_draft | email_id=%s",
                email.email_id,
            )
            draft_content = await self._generate_reply_draft(
                user_id, user_name, email, context, style_guidelines, tone_guidance
            )

            # e. Score style match
            style_score = await self._digital_twin.score_style_match(user_id, draft_content.body)

            # f. Calculate confidence
            confidence = self._calculate_confidence(context)

            logger.info(
                "[EMAIL_PIPELINE] Stage: draft_scored | email_id=%s | style_score=%.2f | confidence=%.2f",
                email.email_id,
                style_score,
                confidence,
            )

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
                processing_run_id=run_id,
            )

            # h2. Update draft_context.draft_id FK now that draft exists
            if context.id:
                await self._context_gatherer.update_draft_id(context.id, draft_id)

            logger.info(
                "[EMAIL_PIPELINE] Stage: draft_saved_to_db | draft_id=%s | email_id=%s",
                draft_id,
                email.email_id,
            )

            # i. Auto-save to email client (Gmail/Outlook)
            # Non-fatal: draft stays in ARIA database even if client save fails
            try:
                logger.info(
                    "[EMAIL_PIPELINE] Stage: saving_to_client_attempt | draft_id=%s | user_id=%s",
                    draft_id,
                    user_id,
                )
                client_result = await self._client_writer.save_draft_to_client(
                    user_id=user_id,
                    draft_id=draft_id,
                )
                if client_result.get("success") and not client_result.get("already_saved"):
                    logger.info(
                        "[EMAIL_PIPELINE] Stage: saved_to_client_success | draft_id=%s | provider=%s | client_draft_id=%s",
                        draft_id,
                        client_result.get("provider"),
                        client_result.get("client_draft_id"),
                    )
                elif client_result.get("already_saved"):
                    logger.info(
                        "[EMAIL_PIPELINE] Stage: client_save_skipped_already_saved | draft_id=%s",
                        draft_id,
                    )
                else:
                    logger.warning(
                        "[EMAIL_PIPELINE] Stage: client_save_returned_failure | draft_id=%s | result=%s",
                        draft_id,
                        client_result,
                    )
            except DraftSaveError as e:
                logger.error(
                    "[EMAIL_PIPELINE] Stage: client_save_failed | draft_id=%s | error=%s | provider=%s",
                    draft_id,
                    e,
                    getattr(e, "provider", "unknown"),
                    exc_info=True,
                )
            except Exception as e:
                logger.error(
                    "[EMAIL_PIPELINE] Stage: client_save_unexpected_error | draft_id=%s | error=%s",
                    draft_id,
                    e,
                    exc_info=True,
                )

            logger.info(
                "[EMAIL_PIPELINE] Stage: email_processed | draft_id=%s | confidence=%.2f | style_score=%.2f",
                draft_id,
                confidence,
                style_score,
            )

            # Determine confidence label for activity log
            confidence_label = (
                "HIGH" if confidence >= 0.75 else "MEDIUM" if confidence >= 0.5 else "LOW"
            )

            # Log draft generation to activity feed (non-blocking)
            try:
                await self._activity_service.record(
                    user_id=user_id,
                    agent="scribe",
                    activity_type="email_drafted",
                    title=f"Drafted reply to {email.sender_name or email.sender_email}",
                    description=f"Re: {draft_content.subject} - {confidence_label} confidence, {style_score:.0%} style match",
                    reasoning=aria_notes,
                    confidence=confidence,
                    related_entity_type="email_draft",
                    related_entity_id=draft_id,
                    metadata={
                        "recipient_email": email.sender_email,
                        "style_match_score": style_score,
                        "confidence_level": confidence,
                        "original_email_id": email.email_id,
                        "thread_id": email.thread_id,
                    },
                )
            except Exception as e:
                logger.warning(
                    "DRAFT_ENGINE: Failed to log draft activity: %s",
                    e,
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
        user_id: str,
        user_name: str,
        email: Any,
        context: DraftContext,
        style_guidelines: str,
        tone_guidance: str,
        special_instructions: str | None = None,
    ) -> ReplyDraftContent:
        """Generate reply draft via LLM with full context.

        Args:
            user_id: User ID (for PersonaBuilder and logging).
            user_name: User's name for signature.
            email: Original email (EmailCategory).
            context: Full context from EmailContextGatherer.
            style_guidelines: Style guidelines from DigitalTwin.
            tone_guidance: Tone guidance from PersonalityCalibrator.
            special_instructions: Optional user instructions for the draft.

        Returns:
            ReplyDraftContent with subject and body.
        """
        prompt = self._build_reply_prompt(
            user_name, email, context, style_guidelines, tone_guidance,
            special_instructions=special_instructions,
        )

        # Primary: PersonaBuilder for system prompt
        system_prompt = self._FALLBACK_REPLY_PROMPT + "\n\n" + self._REPLY_TASK_INSTRUCTIONS
        try:
            from src.core.persona import PersonaRequest, get_persona_builder

            builder = get_persona_builder()
            ctx = await builder.build(PersonaRequest(
                user_id=user_id,
                agent_name="draft_engine",
                agent_role_description="Drafting an email reply on behalf of the user",
                task_description=f"Reply to email from {email.sender_email} re: {email.subject}",
                output_format="json",
            ))
            system_prompt = ctx.to_system_prompt() + "\n\n" + self._REPLY_TASK_INSTRUCTIONS
        except Exception as e:
            logger.warning("PersonaBuilder unavailable, using fallback: %s", e)

        response = await self._llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=system_prompt,
            temperature=0.4,
            max_tokens=1200,
            user_id=user_id,
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
        special_instructions: str | None = None,
    ) -> str:
        """Build comprehensive reply generation prompt.

        Assembles all context sections into a structured prompt
        with full voice matching, strategic guardrails, and all
        available context sources.
        """
        sections: list[str] = []

        # Identity and voice matching (top of prompt for emphasis)
        sections.append(f"""You are drafting an email reply AS {user_name}.
You must match their exact writing style — they should not be able to tell
this wasn't written by them. Do NOT sound like an AI assistant.""")

        # User's writing style guide
        sections.append(f"""## Writing Style Guide
{style_guidelines}""")

        # Recipient-specific writing style
        if context.recipient_style and context.recipient_style.exists:
            rs = context.recipient_style
            recipient_label = email.sender_name or email.sender_email
            style_lines = [
                f"## How {user_name} writes to {recipient_label}",
                f"- Greeting style: {rs.greeting_style or 'Use global style above'}",
                f"- Signoff style: {rs.signoff_style or 'Use global style above'}",
                f"- Formality: {rs.formality_level:.1f}/1.0",
                f"- Tone: {rs.tone}",
                f"- Uses emoji: {'Yes' if rs.uses_emoji else 'No'}",
                f"- Emails exchanged: {rs.email_count}",
            ]
            sections.append("\n".join(style_lines))

        # Tone guidance from personality calibrator
        if tone_guidance:
            sections.append(f"""## Tone Guidance
{tone_guidance}""")

        # The original email being replied to
        email_body = getattr(email, "body", None) or email.snippet
        sections.append(f"""## The email you're replying to
From: {email.sender_name or 'Unknown'} <{email.sender_email}>
Subject: {email.subject}
Urgency: {email.urgency}

{email_body}""")

        # Full conversation thread
        if context.thread_context and context.thread_context.messages:
            thread_summary = (
                context.thread_context.summary
                or f"{context.thread_context.message_count} messages in thread"
            )
            recent_messages = context.thread_context.messages[-5:]
            recent = "\n".join(
                f"- {m.sender_name or m.sender_email}: "
                f"{m.body[:300]}{'...' if len(m.body) > 300 else ''}"
                for m in recent_messages
            )
            sections.append(f"""## Full conversation thread (chronological)
Summary: {thread_summary}
Recent messages:
{recent}""")
        else:
            sections.append(
                "## Full conversation thread\nNo prior thread — this is a first reply."
            )

        # Recipient research
        if context.recipient_research:
            r = context.recipient_research
            info = []
            if r.sender_name:
                info.append(f"Name: {r.sender_name}")
            if r.sender_title:
                info.append(f"Title: {r.sender_title}")
            if r.sender_company:
                info.append(f"Company: {r.sender_company}")
            if r.company_description:
                desc = r.company_description[:300]
                info.append(f"Company info: {desc}")
            if r.bio:
                bio = r.bio[:400] + ("..." if len(r.bio) > 400 else "")
                info.append(f"Bio: {bio}")
            if info:
                sections.append("## Context about the recipient\n" + "\n".join(info))
            else:
                sections.append("## Context about the recipient\nNo research available.")
        else:
            sections.append("## Context about the recipient\nNo research available.")

        # Relationship history
        if context.relationship_history and context.relationship_history.total_emails > 0:
            rh = context.relationship_history
            lines = [f"Total emails: {rh.total_emails}"]
            if rh.relationship_type and rh.relationship_type != "unknown":
                lines.append(f"Relationship: {rh.relationship_type}")
            if rh.last_interaction:
                lines.append(f"Last interaction: {rh.last_interaction}")
            if rh.recent_topics:
                lines.append(f"Recent topics: {', '.join(rh.recent_topics[:5])}")
            if rh.memory_facts:
                facts = rh.memory_facts[:5]
                fact_lines = "\n".join(
                    f"- {f.get('fact', str(f))}" for f in facts
                )
                lines.append(f"Key facts:\n{fact_lines}")
            sections.append(
                "## Your relationship with this person\n" + "\n".join(lines)
            )
        else:
            sections.append(
                "## Your relationship with this person\n"
                "New contact — no prior interaction history."
            )

        # Outstanding commitments in this thread
        if (
            context.relationship_history
            and context.relationship_history.commitments
        ):
            commitment_lines = "\n".join(
                f"- {c}" for c in context.relationship_history.commitments[:5]
            )
            sections.append(
                f"## Outstanding commitments in this thread\n"
                f"{commitment_lines}\n\n"
                f"Reference these naturally if relevant to the reply — "
                f"e.g. acknowledge a promise you made or remind about "
                f"something the sender committed to."
            )
        else:
            sections.append(
                "## Outstanding commitments in this thread\n"
                "No commitments detected."
            )

        # Calendar context
        if context.calendar_context and (
            context.calendar_context.upcoming_meetings
            or context.calendar_context.recent_meetings
        ):
            cal_lines = []
            if context.calendar_context.upcoming_meetings:
                for m in context.calendar_context.upcoming_meetings[:3]:
                    cal_lines.append(
                        f"- UPCOMING: {m.get('summary', 'Meeting')} "
                        f"on {m.get('start', 'TBD')}"
                    )
            if context.calendar_context.recent_meetings:
                for m in context.calendar_context.recent_meetings[:2]:
                    cal_lines.append(
                        f"- RECENT: {m.get('summary', 'Meeting')} "
                        f"on {m.get('start', 'TBD')}"
                    )
            sections.append(
                "## Upcoming/recent meetings with this person\n"
                + "\n".join(cal_lines)
            )
        else:
            sections.append(
                "## Upcoming/recent meetings with this person\n"
                "No calendar data available."
            )

        # CRM context
        if context.crm_context and context.crm_context.connected:
            crm_lines = []
            if context.crm_context.lead_stage:
                crm_lines.append(f"Lead stage: {context.crm_context.lead_stage}")
            if context.crm_context.account_status:
                crm_lines.append(f"Account status: {context.crm_context.account_status}")
            if context.crm_context.deal_value:
                crm_lines.append(
                    f"Deal value: ${context.crm_context.deal_value:,.0f}"
                )
            if context.crm_context.recent_activities:
                for act in context.crm_context.recent_activities[:2]:
                    crm_lines.append(f"- {act.get('description', str(act))}")
            if crm_lines:
                sections.append(
                    "## Deal/pipeline context\n" + "\n".join(crm_lines)
                )
            else:
                sections.append("## Deal/pipeline context\nNo CRM data.")
        else:
            sections.append("## Deal/pipeline context\nNo CRM data.")

        # Corporate memory
        if context.corporate_memory and context.corporate_memory.facts:
            fact_lines = "\n".join(
                f"- {f.get('fact', str(f))}"
                for f in context.corporate_memory.facts[:5]
            )
            sections.append(f"## Relevant company knowledge\n{fact_lines}")
        else:
            sections.append(
                "## Relevant company knowledge\n"
                "No corporate memory for this company."
            )

        # Special instructions from user (on-demand drafts)
        if special_instructions:
            sections.append(
                f"## Special Instructions from User\n{special_instructions}"
            )

        # Strategic guardrails
        sections.append("""## Strategic guardrails
- Do NOT commit to specific pricing unless pricing was already discussed
- Do NOT make promises about timelines without checking context
- Do NOT agree to meetings without checking calendar
- If unsure about something, be warm but non-committal and suggest a call
- Keep the response proportional to the incoming email length""")

        # Final instructions
        sections.append(f"""## Instructions
Write a reply that:
1. Addresses everything the sender raised
2. Sounds EXACTLY like {user_name} — same greeting, tone, length, signoff
3. References relevant context naturally (don't dump everything you know)
4. Is ready to send with minimal editing

Sign off as {user_name}.
Write ONLY the email body (no metadata).

Respond with JSON: {{"subject": "Re: ...", "body": "..."}}""")

        return "\n\n".join(sections)

    # ------------------------------------------------------------------
    # Confidence Calculation
    # ------------------------------------------------------------------

    def _calculate_confidence(
        self,
        context: DraftContext,
    ) -> float:
        """Calculate confidence level (0.0-1.0) from context richness.

        Confidence varies per-draft based on:
        - Context richness (how many of 7 context sources are available)
        - Known contact (has per-recipient writing profile)
        - Thread depth (message count in conversation)
        """
        available_sources = 0
        if context.thread_context and context.thread_context.summary:
            available_sources += 1
        if context.recipient_research:
            available_sources += 1
        if context.relationship_history and context.relationship_history.total_emails > 0:
            available_sources += 1
        if context.calendar_context and context.calendar_context.connected:
            available_sources += 1
        if context.crm_context and context.crm_context.connected:
            available_sources += 1
        if context.corporate_memory and context.corporate_memory.facts:
            available_sources += 1
        if context.recipient_style and context.recipient_style.exists:
            available_sources += 1

        # Base 0.4 + up to 0.42 from context + up to 0.1 from known contact + 0.08 thread depth
        base = 0.4
        context_score = (available_sources / 7) * 0.42
        known_contact = 0.1 if (context.recipient_style and context.recipient_style.exists) else 0.0
        msg_count = context.thread_context.message_count if context.thread_context else 1
        thread_depth = min(msg_count * 0.02, 0.08)

        return round(min(base + context_score + known_contact + thread_depth, 1.0), 3)

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

        These notes help the user understand why ARIA drafted what it did,
        which context sources were used, and what was missing.
        """
        notes: list[str] = []

        # Add learning mode note first if applicable
        if is_learning_mode:
            notes.append(self._learning_mode.get_learning_mode_note())

        # Context sources available vs missing
        available: list[str] = []
        missing: list[str] = []

        if context.thread_context and context.thread_context.summary:
            msg_count = context.thread_context.message_count
            available.append(f"thread ({msg_count} msgs)")
        else:
            missing.append("thread history")

        if context.recipient_research and (
            context.recipient_research.sender_title
            or context.recipient_research.bio
        ):
            available.append("recipient research")
        else:
            missing.append("recipient research")

        if context.relationship_history and context.relationship_history.total_emails > 0:
            available.append(
                f"relationship ({context.relationship_history.total_emails} emails)"
            )
        else:
            missing.append("relationship history")

        if context.recipient_style and context.recipient_style.exists:
            available.append("per-recipient style")
        else:
            missing.append("per-recipient style")

        if context.calendar_context and context.calendar_context.connected:
            available.append("calendar")
        else:
            missing.append("calendar")

        if context.crm_context and context.crm_context.connected:
            available.append("CRM")
        else:
            missing.append("CRM")

        if context.corporate_memory and context.corporate_memory.facts:
            available.append(f"corporate memory ({len(context.corporate_memory.facts)} facts)")
        else:
            missing.append("corporate memory")

        if available:
            notes.append(f"Used: {', '.join(available)}")
        if missing:
            notes.append(f"Missing: {', '.join(missing)}")

        # Style match quality
        if style_score >= 0.8:
            notes.append(f"Style match: strong ({style_score:.0%})")
        elif style_score >= 0.7:
            notes.append(f"Style match: good ({style_score:.0%})")
        else:
            notes.append(f"Style match: LOW ({style_score:.0%}) — review recommended")

        # Urgency flag
        if email.urgency == "URGENT":
            notes.append("URGENT — review carefully before sending")

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
        context_id: str | None,
        style_match_score: float,
        confidence_level: float,
        aria_notes: str,
        urgency: str,
        learning_mode_draft: bool = False,
        processing_run_id: str | None = None,
    ) -> str:
        """Save draft with all metadata to email_drafts table."""
        draft_id = str(uuid4())

        # Safety: only reference draft_context_id if the context was actually saved
        safe_context_id = context_id if context_id else None

        insert_data = {
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
            "draft_context_id": safe_context_id,
            "style_match_score": style_match_score,
            "confidence_level": confidence_level,
            "aria_notes": aria_notes,
            "status": "draft",
            "learning_mode_draft": learning_mode_draft,
            "processing_run_id": processing_run_id,
        }

        try:
            result = self._db.table("email_drafts").insert(insert_data).execute()
            if not result.data:
                logger.error(
                    "[EMAIL_PIPELINE] Stage: draft_insert_empty | draft_id=%s",
                    draft_id,
                )
        except Exception as e:
            logger.error(
                "[EMAIL_PIPELINE] Stage: draft_insert_failed | draft_id=%s | user_id=%s | recipient=%s | error=%s",
                draft_id,
                user_id,
                recipient_email,
                e,
                exc_info=True,
            )
            raise

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

    async def _cleanup_stale_runs(self, user_id: str, timeout_minutes: int = 30) -> None:
        """Mark zombie processing runs stuck in 'running' as failed."""
        try:
            cutoff = (datetime.now(UTC) - timedelta(minutes=timeout_minutes)).isoformat()
            result = self._db.table("email_processing_runs").update(
                {
                    "status": "failed",
                    "completed_at": datetime.now(UTC).isoformat(),
                    "error_message": f"Timed out after {timeout_minutes} minutes",
                }
            ).eq("user_id", user_id).eq("status", "running").lt(
                "started_at", cutoff
            ).execute()
            if result.data:
                logger.warning(
                    "ZOMBIE_CLEANUP: Marked %d stale runs as failed for user %s",
                    len(result.data),
                    user_id,
                )
        except Exception as e:
            logger.warning("DRAFT_ENGINE: Failed to cleanup stale runs: %s", e)

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
                    "emails_scanned": 0,
                    "emails_needs_reply": 0,
                    "drafts_generated": 0,
                    "drafts_failed": 0,
                }
            ).execute()
            logger.info(
                "[EMAIL_PIPELINE] Stage: run_created | run_id=%s | user_id=%s",
                run_id,
                user_id,
            )
        except Exception as e:
            logger.error(
                "[EMAIL_PIPELINE] Stage: run_create_failed | run_id=%s | error=%s",
                run_id,
                e,
                exc_info=True,
            )

    async def _update_processing_run(self, result: ProcessingRunResult) -> None:
        """Update processing run with final status.

        This is called from a finally block, so it always executes
        even when draft generation fails partway through.
        """
        try:
            processing_time_ms = None
            if result.completed_at and result.started_at:
                delta = result.completed_at - result.started_at
                processing_time_ms = int(delta.total_seconds() * 1000)

            update_data = {
                "completed_at": (
                    result.completed_at.isoformat() if result.completed_at else datetime.now(UTC).isoformat()
                ),
                "emails_scanned": result.emails_scanned,
                "emails_needs_reply": result.emails_needs_reply,
                "drafts_generated": result.drafts_generated,
                "drafts_failed": result.drafts_failed,
                "status": result.status,
                "error_message": result.error_message,
                "processing_time_ms": processing_time_ms,
            }

            self._db.table("email_processing_runs").update(
                update_data
            ).eq("id", result.run_id).execute()

            logger.info(
                "[EMAIL_PIPELINE] Stage: run_finalized | run_id=%s | status=%s | "
                "emails_scanned=%d | drafts_generated=%d | drafts_failed=%d | time_ms=%s",
                result.run_id,
                result.status,
                result.emails_scanned,
                result.drafts_generated,
                result.drafts_failed,
                processing_time_ms,
            )
        except Exception as e:
            logger.error(
                "[EMAIL_PIPELINE] Stage: run_finalize_failed | run_id=%s | error=%s",
                result.run_id,
                e,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Deduplication Methods
    # ------------------------------------------------------------------

    async def _get_email_integration(
        self, user_id: str
    ) -> tuple[str | None, str | None]:
        """Get the email provider and connection_id for a user.

        Prefers Outlook, falls back to Gmail.

        Args:
            user_id: The user ID.

        Returns:
            Tuple of (provider, connection_id) or (None, None).
        """
        try:
            result = (
                self._db.table("user_integrations")
                .select("integration_type, composio_connection_id")
                .eq("user_id", user_id)
                .eq("integration_type", "outlook")
                .limit(1)
                .execute()
            )

            if not result.data:
                result = (
                    self._db.table("user_integrations")
                    .select("integration_type, composio_connection_id")
                    .eq("user_id", user_id)
                    .eq("integration_type", "gmail")
                    .limit(1)
                    .execute()
                )

            if result and result.data:
                integration = result.data[0]
                return (
                    integration.get("integration_type"),
                    integration.get("composio_connection_id"),
                )

            return None, None
        except Exception:
            return None, None

    async def _fetch_sent_thread_ids(
        self,
        user_id: str,
        since_hours: int = 24,
    ) -> set[str]:
        """Fetch thread IDs from the user's sent folder.

        Makes a single Composio API call to list sent messages for the
        time window, then extracts thread/conversation IDs into a set
        for O(1) lookup during the main processing loop.

        Args:
            user_id: The user whose sent folder to check.
            since_hours: How far back to look.

        Returns:
            Set of thread IDs found in the sent folder.
        """
        try:
            provider, connection_id = await self._get_email_integration(user_id)
            if not provider or not connection_id:
                return set()

            from src.integrations.oauth import get_oauth_client

            oauth_client = get_oauth_client()
            since_date = (datetime.now(UTC) - timedelta(hours=since_hours)).isoformat()

            if provider == "outlook":
                response = oauth_client.execute_action_sync(
                    connection_id=connection_id,
                    action="OUTLOOK_LIST_MAIL_FOLDER_MESSAGES",
                    params={
                        "mail_folder_id": "sentitems",
                        "$top": 200,
                        "$orderby": "sentDateTime desc",
                        "$filter": f"sentDateTime ge {since_date}",
                        "$select": "conversationId",
                    },
                    user_id=user_id,
                )
                if response.get("successful") and response.get("data"):
                    messages = response["data"].get("value", [])
                    return {
                        msg.get("conversationId")
                        for msg in messages
                        if msg.get("conversationId")
                    }
            else:
                response = oauth_client.execute_action_sync(
                    connection_id=connection_id,
                    action="GMAIL_FETCH_EMAILS",
                    params={
                        "label": "SENT",
                        "max_results": 200,
                    },
                    user_id=user_id,
                )
                if response.get("successful") and response.get("data"):
                    messages = response["data"].get("emails", [])
                    return {
                        msg.get("thread_id")
                        for msg in messages
                        if msg.get("thread_id")
                    }

            return set()

        except Exception as e:
            logger.warning(
                "DRAFT_ENGINE: Failed to fetch sent thread IDs for user %s: %s",
                user_id,
                e,
            )
            return set()

    async def _user_already_replied(
        self,
        user_id: str,
        thread_id: str,
        sent_thread_ids: set[str],
    ) -> bool:
        """Check if the user already replied to this thread.

        Two-tier check:
        1. Fast: thread_id in pre-fetched sent folder thread IDs
        2. Fallback: email_drafts has an approved/edited draft for this thread

        Args:
            user_id: The user's ID.
            thread_id: The email thread/conversation ID.
            sent_thread_ids: Pre-fetched set of thread IDs from sent folder.

        Returns:
            True if user already replied, False otherwise.
        """
        if not thread_id:
            return False

        # Tier 1: Check pre-fetched sent folder thread IDs
        if thread_id in sent_thread_ids:
            return True

        # Tier 2: Check email_drafts for drafts the user sent via ARIA
        try:
            result = (
                self._db.table("email_drafts")
                .select("id")
                .eq("user_id", user_id)
                .eq("thread_id", thread_id)
                .in_("user_action", ["approved", "edited"])
                .limit(1)
                .execute()
            )
            if result.data:
                return True
        except Exception as e:
            logger.warning(
                "DRAFT_ENGINE: DB check for already-replied failed for thread %s: %s",
                thread_id,
                e,
            )

        return False

    async def _check_existing_draft(
        self,
        user_id: str,
        thread_id: str,
        email_ids: list[str] | None = None,
    ) -> str | None:
        """Check if a non-rejected draft already exists for this thread or emails.

        Checks across ALL processing runs (not just the current one) by matching
        on thread_id OR original_email_id.  Finds any draft regardless of status,
        excluding only explicitly rejected drafts.  Uses limit(1) instead of
        maybe_single() so that pre-existing duplicates don't throw and
        snowball into more duplicates.

        Args:
            user_id: The user's ID.
            thread_id: The email thread/conversation ID.
            email_ids: Optional list of email IDs in this thread to also match
                       against original_email_id.

        Returns:
            The existing draft ID if one exists, None otherwise.
        """
        try:
            # Build OR condition: thread_id matches OR original_email_id matches
            or_parts = [f"thread_id.eq.{thread_id}"]
            if email_ids:
                escaped = ",".join(email_ids)
                or_parts.append(f"original_email_id.in.({escaped})")
            or_filter = ",".join(or_parts)

            result = (
                self._db.table("email_drafts")
                .select("id")
                .eq("user_id", user_id)
                .neq("user_action", "rejected")
                .or_(or_filter)
                .limit(1)
                .execute()
            )
            if result.data:
                return result.data[0]["id"]
            return None
        except Exception as e:
            logger.warning(
                "DRAFT_ENGINE: Failed to check existing draft for thread %s: %s",
                thread_id,
                e,
            )
            return None

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
