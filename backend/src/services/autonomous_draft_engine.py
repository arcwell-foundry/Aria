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
import re
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
from src.services.activity_service import ActivityService
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
    # Watermark fields for tracking which emails have been processed
    watermark_timestamp: str | None = None
    watermark_email_id: str | None = None


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

    _FALLBACK_REPLY_PROMPT = """You are ARIA, an AI assistant drafting an email reply."""

    _SCHEDULING_KEYWORDS = [
        "availability",
        "available",
        "schedule",
        "meet",
        "call",
        "time",
        "when can",
        "free",
        "calendar",
        "slot",
        "meeting",
        "book",
        "appointment",
        "discuss",
        "chat",
        "sync",
    ]

    _CALENDAR_GUARDRAIL_INSTRUCTION = """

CRITICAL SCHEDULING RULE: This email asks about scheduling but you do NOT have access to the user's calendar. You MUST NOT suggest any specific dates, times, or time slots. Instead write something like: 'Let me check my calendar and get back to you with some available times.' or 'I'll look at my schedule and send over some options shortly.' NEVER invent availability."""

    # Time patterns for post-LLM validation (code-level guardrail)
    _TIME_PATTERNS = [
        r'\d{1,2}:\d{2}\s*(AM|PM|am|pm|EST|PST|CST|MST|ET|PT|CT|MT)',  # "2:00 PM EST"
        r'\d{1,2}\s*(AM|PM|am|pm)\s*(EST|PST|CST|MST|ET|PT|CT|MT)?',    # "2 PM EST" or "2 PM"
        r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+(morning|afternoon|evening|at\s+\d)',  # "Thursday afternoon"
        r'(tomorrow|today)\s+(morning|afternoon|evening|at\s+\d)',        # "tomorrow afternoon"
        r'(before|after|around)\s+\d{1,2}\s*(AM|PM|am|pm)',              # "after 2 PM"
        r'(March|April|May|June|July|August|September|October|November|December|January|February)\s+\d{1,2}',  # "March 5th"
    ]

    # Meeting claim patterns for post-LLM validation
    _MEETING_CLAIM_PATTERNS = [
        r'(already|just)\s+(had|finished|completed|wrapped up)\s+(the|our|a)\s+(meeting|call|session)',
        r'(great|good|nice)\s+(meeting|call|chat)\s+(earlier|today|this morning|this afternoon)',
        r'(enjoyed|appreciated)\s+(our|the)\s+(meeting|call|conversation)\s+(earlier|today)',
        r'following up (on|from) (our|the) (meeting|call|conversation)',
    ]

    _REPLY_TASK_INSTRUCTIONS = """
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
        self._activity_service = ActivityService()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process_inbox(
        self,
        user_id: str,
        since_hours: int = 24,
        force_full_scan: bool = False,
    ) -> ProcessingRunResult:
        """Full autonomous email processing pipeline.

        Args:
            user_id: The user whose inbox to process.
            since_hours: How many hours back to scan (used only if no watermark or force_full_scan).
            force_full_scan: If True, ignore watermark and scan all emails within since_hours.

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

        # Global per-user lock: skip if another run is already active
        if await self._is_run_active(user_id):
            logger.info(
                "[EMAIL_PIPELINE] Stage: skipped_concurrent | user_id=%s | run_id=%s | "
                "reason=another run already active for this user",
                user_id,
                run_id,
            )
            result.status = "skipped"
            result.error_message = "Another processing run is already active"
            result.completed_at = datetime.now(UTC)
            return result

        # Create processing run record
        await self._create_processing_run(run_id, user_id, started_at)

        # Track the newest email seen for watermark
        newest_email_timestamp: str | None = None
        newest_email_id: str | None = None

        try:
            logger.info(
                "[EMAIL_PIPELINE] Stage: inbox_processing_started | user_id=%s | since_hours=%d | force_full_scan=%s | run_id=%s",
                user_id,
                since_hours,
                force_full_scan,
                run_id,
            )

            # Get watermark unless force_full_scan is True
            since_timestamp: str | None = None
            if not force_full_scan:
                watermark = await self._get_watermark(user_id)
                if watermark:
                    since_timestamp = watermark.get("watermark_timestamp")
                    logger.info(
                        "[EMAIL_PIPELINE] Stage: watermark_found | user_id=%s | since_timestamp=%s | run_id=%s",
                        user_id,
                        since_timestamp,
                        run_id,
                    )
                else:
                    logger.info(
                        "[EMAIL_PIPELINE] Stage: no_watermark | user_id=%s | using_since_hours=%d | run_id=%s",
                        user_id,
                        since_hours,
                        run_id,
                    )

            # 1. Scan inbox via EmailAnalyzer with optional watermark filter
            scan_result = await self._email_analyzer.scan_inbox(
                user_id, since_hours, since_timestamp=since_timestamp
            )
            result.emails_scanned = scan_result.total_emails
            result.emails_needs_reply = len(scan_result.needs_reply)

            # Capture watermark from scan result for saving later
            if scan_result.newest_email_timestamp:
                result.watermark_timestamp = scan_result.newest_email_timestamp
                result.watermark_email_id = scan_result.newest_email_id

            logger.info(
                "[EMAIL_PIPELINE] Stage: scan_complete | emails_scanned=%d | needs_reply=%d | fyi=%d | skipped=%d | run_id=%s | new_watermark=%s",
                result.emails_scanned,
                result.emails_needs_reply,
                len(scan_result.fyi),
                len(scan_result.skipped),
                run_id,
                result.watermark_timestamp or "none",
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

            emails_processed = 0
            emails_skipped_learning_mode = 0
            emails_skipped_existing_draft = 0
            emails_deferred_active_conversation = 0
            emails_skipped_user_replied = 0

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

                    # Handle user_already_replied as a special skip case (not generated, not failed)
                    if draft.error == "user_already_replied":
                        emails_skipped_user_replied += 1
                        logger.info(
                            "[EMAIL_PIPELINE] Stage: skipped_user_replied | email_id=%s | thread_id=%s | run_id=%s",
                            email.email_id,
                            email.thread_id,
                            run_id,
                        )
                    elif draft.success:
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
                "skipped_existing=%d | deferred_active=%d | skipped_learning=%d | skipped_user_replied=%d | status=%s",
                run_id,
                result.drafts_generated,
                result.drafts_failed,
                emails_skipped_existing_draft,
                emails_deferred_active_conversation,
                emails_skipped_learning_mode,
                emails_skipped_user_replied,
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

            # a.5 REPLY CHECK: Skip drafting if user already replied manually
            # This prevents ARIA from drafting replies to emails the user already responded to
            user_already_replied, reply_timestamp = self._check_user_already_replied(
                email, context
            )
            if user_already_replied:
                logger.info(
                    "REPLY_CHECK: User already replied to thread %s at %s, skipping draft for email_id=%s",
                    email.thread_id,
                    reply_timestamp,
                    email.email_id,
                )
                # Log skip to email_scan_log for visibility
                await self._log_skip_decision(
                    user_id, email.thread_id, "user_already_replied", email.email_id
                )
                return DraftResult(
                    draft_id="",
                    recipient_email=email.sender_email,
                    recipient_name=email.sender_name,
                    subject="",
                    body="",
                    style_match_score=0.0,
                    confidence_level=0.0,
                    aria_notes="Skipped: User already replied to this thread",
                    original_email_id=email.email_id,
                    thread_id=email.thread_id,
                    context_id="",
                    success=True,  # Not a failure - intentional skip
                    error="user_already_replied",
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

            # d.5 POST-LLM VALIDATION: Calendar guardrail (code-level enforcement)
            # This is the PRIMARY defense - validates actual text, not prompt instructions
            current_utc = datetime.now(UTC)
            is_valid, cleaned_body = self._validate_calendar_claims(
                draft_content.body, context, current_utc
            )
            if not is_valid:
                logger.info(
                    "[EMAIL_PIPELINE] Stage: calendar_guardrail_applied | email_id=%s | "
                    "original_length=%d | cleaned_length=%d",
                    email.email_id,
                    len(draft_content.body),
                    len(cleaned_body),
                )
                # Update the draft content with the cleaned body
                draft_content = ReplyDraftContent(
                    subject=draft_content.subject,
                    body=cleaned_body,
                )

            # e. Score style match
            style_score = await self._digital_twin.score_style_match(user_id, draft_content.body)

            # f. Calculate confidence
            confidence = self._calculate_confidence(context, style_score)

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

            logger.info(
                "[EMAIL_PIPELINE] Stage: draft_saved_to_db | draft_id=%s | email_id=%s",
                draft_id,
                email.email_id,
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
                        "[EMAIL_PIPELINE] Stage: saving_to_client | draft_id=%s | provider=%s",
                        draft_id,
                        client_result.get("provider"),
                    )
            except DraftSaveError as e:
                logger.warning(
                    "[EMAIL_PIPELINE] Stage: client_save_failed | draft_id=%s | error=%s",
                    draft_id,
                    e,
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
    # LLM Response Parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_draft_response(raw_llm_output: str, logger: logging.Logger) -> dict:
        """Parse LLM draft response, handling all known output formats.

        Handles: fenced JSON, raw JSON, mixed text+JSON, corrupted JSON (reject), plain text.

        Args:
            raw_llm_output: The raw response string from the LLM.
            logger: Logger instance for error reporting.

        Returns:
            Dict with keys: 'subject', 'body', 'parsed' (bool), optionally 'error'.
        """
        text = raw_llm_output.strip()

        # Step 1: Strip markdown code fences (```json ... ``` or ``` ... ```)
        if text.startswith("```"):
            # Remove opening fence (with optional language tag)
            text = re.sub(r"^```\w*\n?", "", text)
            # Remove closing fence
            text = re.sub(r"\n?```$", "", text)
            text = text.strip()

        # Step 2: Try to parse as JSON
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                body = parsed.get("body", parsed.get("content", parsed.get("message", "")))
                subject = parsed.get("subject", "")
                if body:
                    # Unescape any escaped newlines from JSON
                    body = body.replace("\\n", "\n")
                    return {"subject": subject, "body": body, "parsed": True}
        except json.JSONDecodeError:
            pass

        # Step 3: Try to extract JSON from mixed text (LLM wrote explanation + JSON)
        json_match = re.search(r'\{[^{}]*"body"\s*:\s*"[^"]*"[^{}]*\}', text, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                body = parsed.get("body", "")
                subject = parsed.get("subject", "")
                if body:
                    body = body.replace("\\n", "\n")
                    return {"subject": subject, "body": body, "parsed": True}
            except json.JSONDecodeError:
                pass

        # Step 4: If text still contains JSON artifacts, it's corrupted — don't save
        if text.startswith("{") and '"body"' in text:
            logger.error("JSON_PARSE_FAILURE: Could not extract body from JSON response")
            return {"subject": "", "body": "", "parsed": False, "error": "unparseable_json"}

        # Step 5: Plain text response — use as-is
        return {"subject": "", "body": text, "parsed": True}

    # ------------------------------------------------------------------
    # Scheduling Intent Detection
    # ------------------------------------------------------------------

    def _detect_scheduling_intent(self, email: Any) -> bool:
        """Detect if the email asks about scheduling/availability.

        Checks the email subject and body for scheduling-related keywords.

        Args:
            email: The original email (EmailCategory).

        Returns:
            True if scheduling intent detected, False otherwise.
        """
        text_to_check = f"{email.subject or ''} {email.snippet or ''}".lower()
        return any(kw in text_to_check for kw in self._SCHEDULING_KEYWORDS)

    def _has_calendar_context(self, context: DraftContext) -> bool:
        """Check if calendar data was actually gathered.

        Args:
            context: The context from EmailContextGatherer.

        Returns:
            True if calendar context is available with data, False otherwise.
        """
        # Check if calendar_context exists and has actual meeting data
        if context.calendar_context and context.calendar_context.upcoming_meetings:
            return True
        # Also check if "calendar" is in sources_used (even if empty, it was attempted)
        if "calendar" in context.sources_used:
            return True
        return False

    # ------------------------------------------------------------------
    # Post-LLM Calendar Guardrail (Code-Level Enforcement)
    # ------------------------------------------------------------------

    def _validate_calendar_claims(
        self,
        draft_body: str,
        context: DraftContext,
        current_utc_time: datetime,
    ) -> tuple[bool, str]:
        """Validate that the draft doesn't make unsupported calendar claims.

        This is the PRIMARY defense against calendar hallucination - it runs on
        the actual text produced by the LLM, not on a prompt it might ignore.

        Args:
            draft_body: The draft body text to validate.
            context: The context from EmailContextGatherer (for calendar data check).
            current_utc_time: Current UTC time for temporal validation.

        Returns:
            Tuple of (is_valid, cleaned_body_or_original).
            If is_valid is False, the second element is the cleaned body.
        """
        has_real_calendar_data = self._has_calendar_context(context)

        # Detect time-specific patterns in the draft
        has_time_claims = any(
            re.search(p, draft_body, re.IGNORECASE) for p in self._TIME_PATTERNS
        )

        # Detect meeting reference patterns
        has_meeting_claims = any(
            re.search(p, draft_body, re.IGNORECASE) for p in self._MEETING_CLAIM_PATTERNS
        )

        # CASE 1: No calendar data but draft suggests specific times → CLEAN
        if not has_real_calendar_data and has_time_claims:
            logger.warning(
                "CALENDAR_GUARDRAIL_REJECT: Draft contains time suggestions without calendar data"
            )
            cleaned = self._replace_time_claims_with_safe_language(draft_body)
            return (False, cleaned)

        # CASE 2: Draft makes claims about meetings but we can't verify → CLEAN
        if has_meeting_claims and not has_real_calendar_data:
            logger.warning(
                "CALENDAR_GUARDRAIL_REJECT: Draft references meetings without calendar verification"
            )
            cleaned = self._replace_meeting_claims_with_safe_language(draft_body)
            return (False, cleaned)

        # CASE 3: Has calendar data but need to validate temporal claims
        if has_real_calendar_data and has_meeting_claims:
            # Check if the draft claims a future meeting already happened
            if context.calendar_context and context.calendar_context.upcoming_meetings:
                for meeting in context.calendar_context.upcoming_meetings:
                    meeting_time_str = meeting.get('start_time') or meeting.get('start')
                    if meeting_time_str:
                        try:
                            # Parse the meeting time (handle ISO format)
                            if isinstance(meeting_time_str, str):
                                meeting_time = datetime.fromisoformat(
                                    meeting_time_str.replace('Z', '+00:00')
                                )
                            else:
                                meeting_time = meeting_time_str

                            if meeting_time > current_utc_time:
                                # Meeting is in the FUTURE — draft should NOT say "already had"
                                if re.search(
                                    r'(already|just)\s+(had|finished|completed)',
                                    draft_body,
                                    re.IGNORECASE
                                ):
                                    logger.warning(
                                        "CALENDAR_GUARDRAIL_REJECT: Draft says 'already had' "
                                        "meeting that's in the future"
                                    )
                                    cleaned = self._replace_meeting_claims_with_safe_language(
                                        draft_body
                                    )
                                    return (False, cleaned)
                        except (ValueError, TypeError) as e:
                            logger.warning(
                                "CALENDAR_GUARDRAIL: Could not parse meeting time %s: %s",
                                meeting_time_str,
                                e,
                            )

        return (True, draft_body)

    def _replace_time_claims_with_safe_language(self, draft_body: str) -> str:
        """Replace specific time suggestions with calendar-check language.

        Args:
            draft_body: The draft body containing time references.

        Returns:
            Cleaned draft body with safe language.
        """
        # Safe language patterns - if sentence already has these, just remove time refs
        safe_patterns = [
            r'check (my|the) calendar',
            r'get back to you',
            r'send (over |you )?(some )?available times',
            r'look at (my|the) schedule',
            r'my availability',
        ]

        def has_safe_language(text: str) -> bool:
            return any(re.search(p, text, re.IGNORECASE) for p in safe_patterns)

        def remove_time_refs_from_sentence(sentence: str) -> str:
            """Remove time references while preserving the rest of the sentence."""
            # First, try to truncate at common safe-language boundaries
            # "Let me check my calendar and get back to you with confirmation on 2pm"
            #   -> "Let me check my calendar and get back to you."
            # Find the LAST occurrence of any safe phrase and truncate there
            safe_phrases = [
                r'get back to you',
                r'send (over |you )?(some )?available times',
                r'look at (my|the) schedule',
                r'check (my|the) calendar',
            ]

            last_match_end = -1
            for phrase in safe_phrases:
                for match in re.finditer(phrase, sentence, re.IGNORECASE):
                    if match.end() > last_match_end:
                        last_match_end = match.end()

            if last_match_end > 0:
                truncated = sentence[:last_match_end].strip()
                # Ensure proper ending
                if not truncated.endswith(('.', '!', '?')):
                    truncated += '.'
                return truncated

            # If no truncation point, remove time patterns directly
            time_patterns_to_remove = [
                r'\s*(at|on|around|before|after)?\s*\d{1,2}:\d{2}\s*(AM|PM|am|pm|EST|PST|CST|MST|ET|PT|CT|MT)',
                r'\s*(at|on|around|before|after)?\s*\d{1,2}\s*(AM|PM|am|pm)\s*(EST|PST|CST|MST|ET|PT|CT|MT)?',
                r'\s*(on\s+)?(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+(morning|afternoon|evening)?',
                r'\s*(tomorrow|today)(\s+(morning|afternoon|evening))?',
                r'\s*(in\s+)?(the\s+)?(morning|afternoon|evening)',
                r'\s*(on\s+)?(March|April|May|June|July|August|September|October|November|December|January|February)\s+\d{1,2}(st|nd|rd|th)?',
            ]
            cleaned = sentence
            for pattern in time_patterns_to_remove:
                cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
            # Clean up double spaces and trailing punctuation
            cleaned = re.sub(r'\s+', ' ', cleaned).strip()
            cleaned = re.sub(r'\s+([.!?])', r'\1', cleaned)
            return cleaned

        # Process sentence by sentence
        sentences = re.split(r'(?<=[.!?])\s+', draft_body)
        cleaned_sentences = []

        for sentence in sentences:
            has_time = any(re.search(p, sentence, re.IGNORECASE) for p in self._TIME_PATTERNS)

            if has_time:
                if has_safe_language(sentence):
                    # Sentence already has safe language - just remove time refs
                    cleaned = remove_time_refs_from_sentence(sentence)
                    if cleaned and len(cleaned) > 10:  # Keep if meaningful content remains
                        cleaned_sentences.append(cleaned)
                    else:
                        # If removing time refs left nothing meaningful, use safe language
                        cleaned_sentences.append(
                            "I'll check my calendar and send over some available times shortly."
                        )
                else:
                    # No safe language - replace entire sentence
                    cleaned_sentences.append(
                        "I'll check my calendar and send over some available times shortly."
                    )
            else:
                cleaned_sentences.append(sentence)

        return ' '.join(cleaned_sentences)

    def _replace_meeting_claims_with_safe_language(self, draft_body: str) -> str:
        """Replace meeting claims with safe language.

        Args:
            draft_body: The draft body containing meeting references.

        Returns:
            Cleaned draft body with safe language.
        """
        cleaned = draft_body

        # Replace past-tense meeting references with future-tense or neutral
        replacements = [
            (
                r'(already|just)\s+(had|finished|completed|wrapped up)\s+(the|our|a)\s+(meeting|call)',
                r'have \3 \4 scheduled'
            ),
            (
                r'(great|good|nice)\s+(meeting|call|chat)\s+(earlier|today|this morning|this afternoon)',
                r'great \2'
            ),
            (
                r'(enjoyed|appreciated)\s+(our|the)\s+(meeting|call|conversation)\s+(earlier|today)',
                r'\1 \2 \3'
            ),
        ]

        for pattern, replacement in replacements:
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

        return cleaned

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
    ) -> ReplyDraftContent:
        """Generate reply draft via LLM with full context.

        Args:
            user_id: User ID (for PersonaBuilder and logging).
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

        # Calendar hallucination guardrail: inject if scheduling intent detected but no calendar data
        if self._detect_scheduling_intent(email) and not self._has_calendar_context(context):
            logger.info(
                "CALENDAR_GUARDRAIL: Scheduling intent detected for thread %s but no calendar data — injecting guardrail instruction",
                email.thread_id,
            )
            system_prompt += self._CALENDAR_GUARDRAIL_INSTRUCTION

        response = await self._llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=system_prompt,
            temperature=0.3,  # Lower temperature for consistent JSON output
        )

        # Parse LLM response with robust multi-step parser
        parsed = self._parse_draft_response(response, logger)

        # Validation gate: reject unparseable responses
        if not parsed.get("parsed") or parsed.get("error"):
            logger.error(
                "DRAFT_REJECTED: Unparseable LLM response for thread %s, email %s",
                email.thread_id,
                email.email_id,
            )
            raise ValueError(f"Unparseable LLM response: {parsed.get('error', 'unknown')}")

        body = parsed["body"]
        subject = parsed.get("subject") or f"Re: {email.subject}"

        # Validation gate: reject responses that still contain JSON artifacts
        if "```" in body or body.strip().startswith("{"):
            logger.error(
                "DRAFT_REJECTED: Body still contains JSON artifacts for thread %s, email %s",
                email.thread_id,
                email.email_id,
            )
            raise ValueError("Draft body contains JSON artifacts")

        return ReplyDraftContent(
            subject=subject,
            body=body,
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

        # Calendar context — full free/busy for scheduling emails
        if context.calendar_context and context.calendar_context.connected:
            cal = context.calendar_context
            all_meetings = cal.upcoming_meetings + cal.recent_meetings

            if all_meetings:
                # Build busy blocks
                busy_lines = []
                for m in sorted(all_meetings, key=lambda x: x.get("start", "")):
                    start_str = m.get("start", "TBD")
                    end_str = m.get("end", "")
                    title = m.get("title") or m.get("summary") or "Meeting"
                    if end_str:
                        busy_lines.append(f"- {start_str} to {end_str}: {title}")
                    else:
                        busy_lines.append(f"- {start_str}: {title}")

                busy_block = "\n".join(busy_lines) if busy_lines else "No meetings found."

                sections.append(f"""=== YOUR CALENDAR (NEXT 7 DAYS) ===
BUSY:
{busy_block}

When suggesting meeting times, ONLY suggest times that do NOT conflict with the BUSY blocks above. Prefer suggesting 2-3 specific available windows.""")
            else:
                sections.append("""=== CALENDAR ===
Your calendar is connected but no upcoming meetings were found in the next 7 days.
You can suggest meeting times freely.""")

        # CRM context
        if context.crm_context and context.crm_context.connected:
            crm_info = []
            if context.crm_context.lead_stage:
                crm_info.append(f"Lead stage: {context.crm_context.lead_stage}")
            if context.crm_context.deal_value:
                crm_info.append(f"Deal value: ${context.crm_context.deal_value:,.0f}")
            if crm_info:
                sections.append("=== CRM STATUS ===\n" + "\n".join(crm_info))

        # Current time context (critical for temporal awareness)
        current_utc = datetime.now(UTC)
        sections.append(f"""=== CURRENT TIME ===
Current date and time (UTC): {current_utc.isoformat()}Z

IMPORTANT: Use this to correctly determine if events are in the past or future.
- A meeting at 2pm today is in the FUTURE if the current time is 10am.
- Do NOT say you "already had" a meeting that hasn't happened yet.
- When referencing today/tonight/tomorrow, this is your reference point.""")

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
                .limit(1)
                .execute()
            )

            record = result.data[0] if result and result.data else None
            if record:
                return record.get("full_name", "there")
        except Exception as e:
            logger.warning("DRAFT_ENGINE: Failed to get user name: %s", e)

        return "there"

    async def _is_run_active(self, user_id: str) -> bool:
        """Check if a processing run is already active for this user.

        Prevents concurrent runs from the scheduler and API endpoint
        generating duplicate drafts. A run started within the last 10
        minutes with status 'running' blocks new runs.
        """
        try:
            result = (
                self._db.table("email_processing_runs")
                .select("id, started_at")
                .eq("user_id", user_id)
                .eq("status", "running")
                .limit(1)
                .execute()
            )
            if result.data:
                logger.info(
                    "DRAFT_ENGINE: Active run found for user %s: run_id=%s started_at=%s",
                    user_id,
                    result.data[0]["id"],
                    result.data[0]["started_at"],
                )
                return True
            return False
        except Exception as e:
            logger.warning(
                "DRAFT_ENGINE: Failed to check active runs for user %s: %s",
                user_id,
                e,
            )
            # On error, allow the run to proceed rather than silently blocking
            return False

    async def _cleanup_stale_runs(self, user_id: str) -> None:
        """Mark runs stuck in 'running' for >10min as failed."""
        try:
            from datetime import timedelta

            cutoff = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
            self._db.table("email_processing_runs").update(
                {
                    "status": "failed",
                    "completed_at": datetime.now(UTC).isoformat(),
                    "error_message": "Orphaned: server restart or timeout",
                }
            ).eq("user_id", user_id).eq("status", "running").lt(
                "started_at", cutoff
            ).execute()
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

            # Only save watermark for successful runs (completed or partial_failure)
            # Failed runs should NOT update the watermark - next run will reprocess
            if result.status in ("completed", "partial_failure"):
                if result.watermark_timestamp:
                    update_data["watermark_timestamp"] = result.watermark_timestamp
                if result.watermark_email_id:
                    update_data["watermark_email_id"] = result.watermark_email_id

            self._db.table("email_processing_runs").update(
                update_data
            ).eq("id", result.run_id).execute()

            logger.info(
                "[EMAIL_PIPELINE] Stage: run_finalized | run_id=%s | status=%s | "
                "emails_scanned=%d | drafts_generated=%d | drafts_failed=%d | time_ms=%s | watermark=%s",
                result.run_id,
                result.status,
                result.emails_scanned,
                result.drafts_generated,
                result.drafts_failed,
                processing_time_ms,
                result.watermark_timestamp or "none",
            )
        except Exception as e:
            logger.error(
                "[EMAIL_PIPELINE] Stage: run_finalize_failed | run_id=%s | error=%s",
                result.run_id,
                e,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Watermark Methods
    # ------------------------------------------------------------------

    async def _get_watermark(self, user_id: str) -> dict | None:
        """Get the watermark from the last completed processing run.

        The watermark represents the newest email that was successfully processed.
        Future scans should only fetch emails received AFTER this timestamp.

        Args:
            user_id: The user's ID.

        Returns:
            Dict with watermark_timestamp and watermark_email_id, or None if no watermark.
        """
        try:
            result = (
                self._db.table("email_processing_runs")
                .select("watermark_timestamp, watermark_email_id")
                .eq("user_id", user_id)
                .eq("status", "completed")
                .not_.is_("watermark_timestamp", "null")
                .order("watermark_timestamp", desc=True)
                .limit(1)
                .execute()
            )
            if result.data:
                return result.data[0]
            return None
        except Exception as e:
            logger.warning(
                "DRAFT_ENGINE: Failed to get watermark for user %s: %s",
                user_id,
                e,
            )
            return None

    # ------------------------------------------------------------------
    # Deduplication Methods
    # ------------------------------------------------------------------

    async def _check_existing_draft(
        self,
        user_id: str,
        thread_id: str,
        email_ids: list[str] | None = None,
    ) -> str | None:
        """Check if a non-rejected draft already exists for this thread or emails.

        Checks across ALL processing runs (not just the current one) by matching
        on thread_id OR original_email_id. Uses limit(1) so that pre-existing
        duplicates don't throw and snowball into more duplicates.

        A draft is considered "existing" if:
        - status is 'draft' or 'saved_to_client' (not edited, sent, or rejected)
        - user_action is NOT 'edited', 'sent', or 'rejected'

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

            # Check for drafts that haven't been rejected/edited/sent
            # user_action can be: null, 'pending', 'edited', 'sent', 'rejected'
            # We only want to skip if user hasn't taken action (null or pending)
            result = (
                self._db.table("email_drafts")
                .select("id")
                .eq("user_id", user_id)
                .in_("status", ["draft", "saved_to_client"])
                .or_(or_filter)
                .limit(1)
                .execute()
            )
            if result.data:
                existing_id = result.data[0]["id"]
                logger.info(
                    "DEDUP_HIT: Found existing draft %s for thread %s",
                    existing_id,
                    thread_id,
                )
                return existing_id
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

    def _check_user_already_replied(
        self,
        email: Any,
        context: DraftContext,
    ) -> tuple[bool, str | None]:
        """Check if user has already replied to this thread after the incoming email.

        This prevents ARIA from drafting replies to emails the user already responded
        to manually (e.g., user replied on mobile before ARIA's scan ran).

        Args:
            email: The incoming email that triggered NEEDS_REPLY (EmailCategory).
            context: The context from EmailContextGatherer with thread messages.

        Returns:
            Tuple of (has_replied, reply_timestamp). If has_replied is True,
            reply_timestamp contains the timestamp of the user's reply.
        """
        # No thread context available - can't verify, proceed with draft
        if not context.thread_context or not context.thread_context.messages:
            logger.debug(
                "REPLY_CHECK: No thread messages available for email_id=%s, proceeding with draft",
                email.email_id,
            )
            return (False, None)

        messages = context.thread_context.messages

        # Find the triggering email's timestamp
        # The triggering email is from the sender (not the user) and is the one we're replying to
        # We look for the latest non-user message as the trigger point
        triggering_timestamp: str | None = None
        for msg in messages:
            if not msg.is_from_user:
                # This is a message from someone else (the sender)
                # Use the latest one as the trigger point
                triggering_timestamp = msg.timestamp

        if not triggering_timestamp:
            logger.debug(
                "REPLY_CHECK: Could not find triggering message timestamp for email_id=%s",
                email.email_id,
            )
            return (False, None)

        # Check if any user message came AFTER the triggering email
        for msg in messages:
            if msg.is_from_user and msg.timestamp:
                # Compare timestamps - user reply must be AFTER the triggering email
                if msg.timestamp > triggering_timestamp:
                    logger.info(
                        "REPLY_CHECK: User reply detected at %s (after trigger at %s) for thread %s",
                        msg.timestamp,
                        triggering_timestamp,
                        email.thread_id,
                    )
                    return (True, msg.timestamp)

        logger.debug(
            "REPLY_CHECK: No user reply found after triggering email for thread %s",
            email.thread_id,
        )
        return (False, None)

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
