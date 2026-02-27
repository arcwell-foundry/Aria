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
from src.core.task_types import TaskType
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
from src.services.email_lead_intelligence import EmailLeadIntelligence
from src.services.learning_mode_service import get_learning_mode_service

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Strategic Guardrails for Draft Generation
# ---------------------------------------------------------------------------

STRATEGIC_GUARDRAILS = """
## Critical Guardrails — Do NOT include in the draft:
1. PRICING: Never quote specific prices, discounts, or ranges unless the
   thread shows pricing was already discussed and numbers were shared.
   Instead: "I'd be happy to discuss pricing — let me put together some options."

2. TIMELINES: Never commit to specific delivery dates or deadlines unless
   confirmed in the context. Instead: "Let me check on the timeline and
   get back to you."

3. MEETINGS: Never accept or propose specific meeting times. Instead:
   "I'd love to connect — I'll send some availability."

4. PRODUCT CLAIMS: Only reference product capabilities that appear in the
   corporate memory or prior thread. Don't invent features.

5. CONFIDENTIAL: Never share internal pricing strategies, competitive
   intelligence, or internal discussions in an external email.

6. AUTHORITY: Don't make decisions above the user's role. If unsure,
   suggest the user will "look into it" or "discuss with the team."

If you're uncertain about ANY commitment, err on the warm-but-vague side:
acknowledge the request, express interest, and defer specifics to a
follow-up conversation.
"""


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
  "body": "The full email body as clean HTML (see formatting instructions)"
}

The "body" value MUST be clean HTML suitable for email clients:
- Wrap each paragraph in <p> tags
- Use <ul>/<li> for bullet points if appropriate
- Use <br> for line breaks within a signoff block
- Do NOT include <html>, <head>, <body>, or <style> tags
- Do NOT include a signature block (the email client adds it)

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
        self._lead_intelligence = EmailLeadIntelligence()

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

            # 2. Check learning mode status (informational only — no gating)
            is_learning_mode = await self._learning_mode.is_learning_mode_active(user_id)

            if is_learning_mode:
                logger.info(
                    "DRAFT_ENGINE: Learning mode ACTIVE for user %s (informational only — drafting all contacts).",
                    user_id,
                )

            # 3. Group emails by thread and deduplicate
            grouped_emails = await self._group_emails_by_thread(scan_result.needs_reply)

            multi_msg_threads = sum(1 for emails in grouped_emails.values() if len(emails) > 1)
            if multi_msg_threads > 0:
                consolidated_count = len(scan_result.needs_reply) - len(grouped_emails)
                logger.info(
                    "[EMAIL_PIPELINE] Stage: thread_consolidation | "
                    "needs_reply=%d | threads=%d | multi_msg_threads=%d | "
                    "consolidated=%d | run_id=%s",
                    len(scan_result.needs_reply),
                    len(grouped_emails),
                    multi_msg_threads,
                    consolidated_count,
                    run_id,
                )

            # 3b. Pre-fetch sent thread IDs (one API call for dedup)
            sent_thread_ids = await self._fetch_sent_thread_ids(user_id, since_hours)

            emails_processed = 0
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

                # Build consolidation info for multi-message threads
                consolidated_from: list[dict[str, Any]] | None = None
                if len(thread_emails) > 1:
                    earlier = [e for e in thread_emails if e.email_id != email.email_id]
                    if earlier:
                        earlier_sorted = sorted(
                            earlier,
                            key=lambda e: getattr(e, "scanned_at", "") or "",
                        )
                        consolidated_from = [
                            {
                                "sender": e.sender_name or e.sender_email,
                                "subject": e.subject,
                                "date": str(getattr(e, "scanned_at", "")),
                                "snippet": (e.snippet or "")[:200],
                            }
                            for e in earlier_sorted
                        ]
                        logger.info(
                            "THREAD_CONSOLIDATED: %d messages in thread %s → single reply to %s",
                            len(thread_emails),
                            thread_id[:8] if len(thread_id) > 8 else thread_id,
                            email.sender_name or email.sender_email,
                        )

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

                # Assign confidence tier (no gating — all emails get drafted)
                confidence_tier = await self._assign_draft_confidence_tier(
                    user_id, email.sender_email,
                )

                # Increment interaction count for learning mode tracking
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
                        user_id, user_name, email, is_learning_mode, run_id,
                        confidence_tier=confidence_tier,
                        consolidated_from=consolidated_from,
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
                "deferred_active=%d | status=%s",
                run_id,
                result.drafts_generated,
                result.drafts_failed,
                emails_skipped_existing_draft,
                emails_skipped_already_replied,
                emails_deferred_active_conversation,
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

            # a2. Extract lead intelligence (non-blocking)
            lead_updates: list[dict] = []
            try:
                thread_summary = ""
                if context.thread_context and context.thread_context.summary:
                    thread_summary = context.thread_context.summary
                lead_updates = await self._lead_intelligence.process_email_for_leads(
                    user_id=user_id,
                    email={
                        "sender_email": email.sender_email,
                        "subject": getattr(email, "subject", email_data.get("subject", "")),
                        "body": getattr(email, "body", email_data.get("body", "")),
                    },
                    thread_summary=thread_summary,
                )
                if lead_updates:
                    logger.info(
                        "ON_DEMAND_DRAFT: Lead intel: %d signals from %s",
                        len(lead_updates),
                        email.sender_email,
                    )
            except Exception as e:
                logger.warning("ON_DEMAND_DRAFT: Lead intel failed (non-fatal): %s", e)

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

            # d2. Check guardrails for unauthorized commitments
            guardrail_warnings = await self._check_guardrails(draft_content.body, context)
            if guardrail_warnings:
                for warning in guardrail_warnings:
                    logger.warning(
                        "GUARDRAIL_WARNING: %s in on-demand draft for %s",
                        warning,
                        email.sender_email,
                    )

            # e. Score style match
            style_score = await self._digital_twin.score_style_match(
                user_id, draft_content.body,
            )

            # f. Calculate confidence (reduced by guardrail warnings)
            confidence = self._calculate_confidence(context)
            confidence = max(0.1, confidence - (len(guardrail_warnings) * 0.1))

            # g. Generate ARIA notes (with guardrail warnings)
            aria_notes = await self._generate_aria_notes(
                email, context, style_score, confidence,
                lead_updates=lead_updates,
                guardrail_warnings=guardrail_warnings,
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
    # Confidence Tier Assignment
    # ------------------------------------------------------------------

    async def _assign_draft_confidence_tier(
        self,
        user_id: str,
        sender_email: str,
    ) -> dict[str, Any]:
        """Assign confidence tier based on data richness, not a gate.

        Tiers:
        - HIGH: Top contact with 5+ emails — strong style match likely.
        - MEDIUM: Has recipient profile with 2+ emails.
        - LOW: Has digital twin but new contact.
        - MINIMAL: Very little data to work with.

        Args:
            user_id: The user's ID.
            sender_email: The email sender to evaluate.

        Returns:
            Dict with tier, note, is_top_contact, and email_count.
        """
        has_recipient_profile = False
        email_count = 0

        try:
            profile = (
                self._db.table("recipient_writing_profiles")
                .select("*")
                .eq("user_id", user_id)
                .eq("recipient_email", sender_email)
                .maybe_single()
                .execute()
            )
            has_recipient_profile = bool(profile.data)
            email_count = profile.data.get("email_count", 0) if profile.data else 0
        except Exception as e:
            logger.debug("Confidence tier: recipient profile lookup failed: %s", e)

        has_twin = False
        try:
            twin = (
                self._db.table("digital_twin_profiles")
                .select("id")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
            has_twin = bool(twin.data)
        except Exception as e:
            logger.debug("Confidence tier: digital twin lookup failed: %s", e)

        top_contacts = await self._get_top_contacts(user_id)
        is_top_contact = sender_email.lower() in {c.lower() for c in top_contacts}

        if is_top_contact and email_count >= 5:
            tier = "HIGH"
            sender_label = sender_email.split("@")[0]
            note = (
                f"I have {email_count} of your past emails to "
                f"{sender_label} to match your style."
            )
        elif has_recipient_profile and email_count >= 2:
            tier = "MEDIUM"
            note = (
                f"I have {email_count} emails as style reference. "
                f"My confidence will improve as we interact more."
            )
        elif has_twin:
            tier = "LOW"
            note = (
                "This is a new contact — I used your general writing style. "
                "Review this draft more carefully."
            )
        else:
            tier = "MINIMAL"
            note = (
                "Limited style data available. I wrote a professional reply "
                "but it may not match your voice perfectly."
            )

        return {
            "tier": tier,
            "note": note,
            "is_top_contact": is_top_contact,
            "email_count": email_count,
        }

    async def _get_top_contacts(self, user_id: str) -> list[str]:
        """Get the top contacts for a user via LearningModeService.

        Args:
            user_id: The user whose top contacts to retrieve.

        Returns:
            List of top contact email addresses.
        """
        return await self._learning_mode.get_top_contacts(user_id)

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
        confidence_tier: dict[str, Any] | None = None,
        consolidated_from: list[dict[str, Any]] | None = None,
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

            # a1b. Thread-based already-replied check (Tier 3)
            # Catches manual replies the sent-folder query missed
            if (
                context.thread_context
                and context.thread_context.messages
                and self._user_replied_in_thread(context.thread_context.messages)
            ):
                logger.info(
                    "SKIP_ALREADY_REPLIED_VIA_THREAD: email_id=%s thread_id=%s subject=%s",
                    email.email_id,
                    email.thread_id,
                    email.subject,
                )
                return DraftResult(
                    draft_id="",
                    recipient_email=email.sender_email,
                    recipient_name=email.sender_name,
                    subject=email.subject or "",
                    body="",
                    style_match_score=0.0,
                    confidence_level=0.0,
                    aria_notes="Skipped: user already replied in thread",
                    original_email_id=email.email_id,
                    thread_id=email.thread_id,
                    context_id=context.id,
                    success=False,
                    error="User already replied in thread",
                )

            # a2. Extract lead intelligence (non-blocking)
            lead_updates: list[dict] = []
            try:
                thread_summary = ""
                if context.thread_context and context.thread_context.summary:
                    thread_summary = context.thread_context.summary
                lead_updates = await self._lead_intelligence.process_email_for_leads(
                    user_id=user_id,
                    email={
                        "sender_email": email.sender_email,
                        "subject": email.subject,
                        "body": getattr(email, "body", getattr(email, "snippet", "")),
                    },
                    thread_summary=thread_summary,
                )
                if lead_updates:
                    logger.info(
                        "[EMAIL_PIPELINE] Stage: lead_intel | email_id=%s | signals=%d",
                        email.email_id,
                        len(lead_updates),
                    )
            except Exception as e:
                logger.warning(
                    "[EMAIL_PIPELINE] Lead intelligence extraction failed (non-fatal): %s", e,
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
                user_id, user_name, email, context, style_guidelines, tone_guidance,
                consolidated_from=consolidated_from,
            )

            # d2. Check guardrails for unauthorized commitments
            guardrail_warnings = await self._check_guardrails(draft_content.body, context)
            if guardrail_warnings:
                for warning in guardrail_warnings:
                    logger.warning(
                        "GUARDRAIL_WARNING: %s in draft for email_id=%s",
                        warning,
                        email.email_id,
                    )

            # e. Score style match
            style_score = await self._digital_twin.score_style_match(user_id, draft_content.body)

            # f. Calculate confidence (reduced by guardrail warnings)
            confidence = self._calculate_confidence(context)
            confidence = max(0.1, confidence - (len(guardrail_warnings) * 0.1))

            logger.info(
                "[EMAIL_PIPELINE] Stage: draft_scored | email_id=%s | style_score=%.2f | confidence=%.2f | guardrail_warnings=%d",
                email.email_id,
                style_score,
                confidence,
                len(guardrail_warnings),
            )

            # g. Generate ARIA notes (with confidence tier, learning mode, and guardrail warnings)
            aria_notes = await self._generate_aria_notes(
                email, context, style_score, confidence, is_learning_mode,
                lead_updates=lead_updates,
                guardrail_warnings=guardrail_warnings,
                confidence_tier=confidence_tier,
                consolidated_from=consolidated_from,
            )

            # h. Save draft with all metadata (including confidence tier)
            tier_label = confidence_tier.get("tier", "LOW") if confidence_tier else "LOW"
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
                confidence_tier=tier_label,
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
            if confidence_tier:
                tier = confidence_tier.get("tier", "UNKNOWN")
                error_notes = f"[Confidence: {tier}] | {error_notes}"
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
    # Formatting Patterns
    # ------------------------------------------------------------------

    async def _get_formatting_patterns(self, user_id: str) -> dict[str, Any] | None:
        """Fetch stored formatting patterns from digital_twin_profiles.

        Args:
            user_id: The user's ID.

        Returns:
            Formatting patterns dict, or None if not available.
        """
        try:
            result = (
                self._db.table("digital_twin_profiles")
                .select("formatting_patterns")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
            if result and result.data:
                raw = result.data.get("formatting_patterns")
                if isinstance(raw, str):
                    return json.loads(raw)
                if isinstance(raw, dict):
                    return raw
        except Exception as e:
            logger.debug("DRAFT_ENGINE: Could not fetch formatting patterns: %s", e)
        return None

    async def _get_raw_writing_style(self, user_id: str) -> str | None:
        """Fetch the raw writing_style description from digital_twin_profiles.

        This is the descriptive prose about the user's writing style,
        complementary to the structured style guidelines.

        Args:
            user_id: The user's ID.

        Returns:
            Raw writing style string, or None if not available.
        """
        try:
            result = (
                self._db.table("digital_twin_profiles")
                .select("writing_style")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
            if result and result.data:
                return result.data.get("writing_style")
        except Exception as e:
            logger.debug("DRAFT_ENGINE: Could not fetch writing_style: %s", e)
        return None

    def _detect_attachment_context(
        self,
        email: Any,
        thread_summary: str | None = None,
    ) -> str:
        """Detect attachment references in email and thread.

        Analyzes the incoming email for attachments and checks if the user
        may have promised to send a document based on thread history.

        Args:
            email: The email object with body and attachment data.
            thread_summary: Optional thread summary for context.

        Returns:
            A context string for the LLM prompt about attachments.
        """
        body = getattr(email, "body", "") or ""
        if isinstance(body, dict):
            body = body.get("content", "")

        has_attachments = bool(
            getattr(email, "hasAttachments", False)
            or getattr(email, "attachments", None)
        )

        attachment_words = [
            "attached", "attachment", "attaching", "enclosed",
            "see attached", "find attached", "PFA", "please find",
        ]
        sender_mentioned = any(w in body.lower() for w in attachment_words)

        parts: list[str] = []

        if has_attachments:
            attachments = getattr(email, "attachments", None) or []
            names = [a.get("name", "file") if isinstance(a, dict) else str(a) for a in attachments]
            parts.append(
                f"Sender attached: {', '.join(names)}. "
                f"Acknowledge the attachment in your reply."
            )
        elif sender_mentioned:
            parts.append(
                "Sender referenced an attachment but none was found. "
                "Consider asking them to resend."
            )

        # Check if user promised to send something
        thread = (thread_summary or "").lower()
        promise_phrases = [
            "i'll send", "i will send", "i'll attach",
            "will share the", "send you the", "i'll get you",
            "i'll forward", "let me send you",
        ]
        if any(p in thread for p in promise_phrases):
            parts.append(
                "⚠️ NOTE: Based on the thread, you may have promised to send "
                "a document. Remember to attach it before sending this reply."
            )

        return "\n".join(parts) if parts else "No attachment context."

    def _build_formatting_instructions(
        self, formatting: dict[str, Any] | None,
    ) -> str:
        """Build HTML formatting instructions for the draft generation prompt.

        Args:
            formatting: Formatting patterns from digital_twin_profiles, or None.

        Returns:
            Prompt section with formatting rules.
        """
        if formatting and formatting.get("typical_structure"):
            user_style = (
                f"\nThe user's typical email format:\n"
                f"- Structure: {formatting.get('typical_structure', 'greeting, 2-3 paragraphs, signoff')}\n"
                f"- Average paragraphs per email: {formatting.get('avg_paragraph_count', 3)}\n"
                f"- Uses bullet points: {'yes, occasionally' if formatting.get('uses_bullet_points') else 'rarely/never'}\n"
                f"- Average paragraph length: {formatting.get('avg_paragraph_length_sentences', 2)} sentences\n"
                f"- Match this formatting structure exactly."
            )
        else:
            user_style = (
                "Use standard professional email formatting: "
                "greeting, 2-3 concise paragraphs, signoff."
            )

        return f"""## Email Formatting
Output the reply as clean HTML for rendering in an email client.

Structure rules:
- Greeting on its own line: <p>{{greeting}}</p>
- Each paragraph in <p> tags: <p>paragraph text</p>
- If using bullet points: <ul><li>item</li></ul>
- Signoff on its own line: <p>{{signoff}}<br>{{name}}</p>
- Do NOT include <html>, <head>, <body>, or <style> tags
- Do NOT include a signature block (the email client adds it)
- Keep paragraphs short (2-3 sentences max unless the user writes longer)

{user_style}

Example of well-formatted output:
<p>Hi Rob,</p>
<p>Thanks for sending over the partnership overview. I've had a chance to review it and have a few thoughts.</p>
<p>The proposed timeline works well on our end. A couple of things I'd like to discuss:</p>
<ul>
<li>The data migration scope in Section 3</li>
<li>Integration testing windows for Q2</li>
</ul>
<p>Would Thursday afternoon work for a quick call to walk through these?</p>
<p>Best,<br>Dhruv</p>"""

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
        consolidated_from: list[dict[str, Any]] | None = None,
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
        # Fetch formatting patterns for HTML output
        formatting_patterns = await self._get_formatting_patterns(user_id)

        # Fetch raw writing_style description from digital twin
        raw_writing_style = await self._get_raw_writing_style(user_id)

        prompt = self._build_reply_prompt(
            user_name, email, context, style_guidelines, tone_guidance,
            special_instructions=special_instructions,
            formatting_patterns=formatting_patterns,
            consolidated_from=consolidated_from,
            raw_writing_style=raw_writing_style,
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
            task=TaskType.SCRIBE_DRAFT_EMAIL,
        )

        # Parse JSON response (strip markdown code fences if present)
        cleaned = response.strip()
        if cleaned.startswith("```"):
            # Remove opening fence (```json or ```)
            first_newline = cleaned.index("\n") if "\n" in cleaned else len(cleaned)
            cleaned = cleaned[first_newline + 1:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
            return ReplyDraftContent(
                subject=data.get("subject", f"Re: {email.subject}"),
                body=data.get("body", cleaned),
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
        formatting_patterns: dict[str, Any] | None = None,
        consolidated_from: list[dict[str, Any]] | None = None,
        raw_writing_style: str | None = None,
    ) -> str:
        """Build comprehensive reply generation prompt.

        Assembles all context sections into a structured prompt
        with full voice matching, strategic guardrails, HTML formatting
        instructions, and all available context sources.
        """
        sections: list[str] = []

        # Identity and voice matching (top of prompt for emphasis)
        sections.append(f"""You are drafting an email reply AS {user_name}.
You must match their exact writing style — they should not be able to tell
this wasn't written by them. Do NOT sound like an AI assistant.""")

        # Anti-hallucination instruction (critical — placed early for emphasis)
        sections.append("""## CRITICAL: Anti-Hallucination Rule
ONLY reference information present in the email and thread below.
Do NOT invent topics, projects, details, or context the sender didn't mention.
If the sender mentioned something specific, address it directly.
If you don't have information about something, do NOT make it up — either
skip it or suggest following up.""")

        # Filler phrase prohibition
        sections.append("""## Banned Phrases — Do NOT use any of these:
- "I hope this email finds you well"
- "I hope this finds you well"
- "Thank you for reaching out"
- "Thanks for reaching out"
- "Please don't hesitate to"
- "Don't hesitate to reach out"
- "Looking forward to your response"
- "I appreciate your time"
- "Per our conversation"
- "As per my last email"
- "Just circling back"
- "Just following up"
- "I wanted to touch base"
- "Let's circle back on this"
- "At your earliest convenience"
- "Synergy", "leverage" (as verb), "alignment", "bandwidth"
- "Moving forward"
- Any variation of these corporate filler phrases.
Write like a real person, not a template.""")

        # User's writing style guide
        voice_section = f"## Writing Style Guide\n{style_guidelines}"
        if raw_writing_style:
            voice_section += f"\n\nVoice profile: {raw_writing_style}"
        sections.append(voice_section)

        # Recipient-specific writing style
        if context.recipient_style and context.recipient_style.exists:
            rs = context.recipient_style
            recipient_label = email.sender_name or email.sender_email

            # Helper to avoid literal "None" strings in prompt (BL-7)
            def _clean_field(value: str | None, fallback: str) -> str:
                if value is None or value == "None" or value == "":
                    return fallback
                return value

            style_lines = [
                f"## How {user_name} writes to {recipient_label}",
                f"- Greeting style: {_clean_field(rs.greeting_style, 'Use global style above')}",
                f"- Signoff style: {_clean_field(rs.signoff_style, 'Use global style above')}",
                f"- Formality: {rs.formality_level:.1f}/1.0",
                f"- Tone: {_clean_field(rs.tone, 'balanced')}",
                f"- Uses emoji: {'Yes' if rs.uses_emoji else 'No'}",
                f"- Emails exchanged: {rs.email_count}",
            ]
            sections.append("\n".join(style_lines))

        # Tone guidance from personality calibrator
        if tone_guidance:
            sections.append(f"""## Tone Guidance
{tone_guidance}""")

        # HTML formatting instructions
        sections.append(self._build_formatting_instructions(formatting_patterns))

        # The original email being replied to
        email_body = getattr(email, "body", None)
        if not email_body:
            logger.warning(
                "BL-1: No body for email %s, falling back to snippet",
                email.subject,
            )
            email_body = email.snippet
        sections.append(f"""## The email you're replying to
From: {email.sender_name or 'Unknown'} <{email.sender_email}>
Subject: {email.subject}
Urgency: {email.urgency}

{email_body}""")

        # Earlier messages in thread that also need addressing (consolidation)
        if consolidated_from:
            earlier_lines = "\n".join(
                f"- {m['sender']} ({m['date']}): {m['snippet']}"
                for m in consolidated_from
            )
            sections.append(
                f"## Earlier messages in this thread that also need addressing\n"
                f"{earlier_lines}\n\n"
                f"Address ALL of these messages in your single reply, in addition to the "
                f"latest message above. Reference earlier points naturally — don't "
                f"reply to each one separately like a checklist."
            )

        # Extract thread summary for attachment context
        thread_summary = None
        if context.thread_context and context.thread_context.summary:
            thread_summary = context.thread_context.summary

        # Attachment context
        attachment_context = self._detect_attachment_context(email, thread_summary)
        sections.append(f"""## Attachments
{attachment_context}""")

        # Full conversation thread
        if context.thread_context and context.thread_context.messages:
            thread_summary_text = (
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
Summary: {thread_summary_text}
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

        # Strategic guardrails (expanded version)
        sections.append(STRATEGIC_GUARDRAILS)

        # Final instructions
        consolidation_instruction = ""
        if consolidated_from:
            consolidation_instruction = (
                f"\n6. Addresses ALL {len(consolidated_from) + 1} messages in this "
                f"thread in a single cohesive reply — don't reply to each separately"
            )

        sections.append(f"""## Step 1: Extract Key Points (do this mentally before writing)
Before writing the reply, identify every specific point, question, date,
request, or commitment from the sender's email above. Your reply MUST
address each one. Do not skip any.

## Step 2: Write the Reply
Write a reply that:
1. Addresses EVERY specific point the sender raised — dates, requests, questions, proposals
2. Sounds EXACTLY like {user_name} — same greeting, tone, length, signoff
3. References specific details from the sender's email (names, dates, topics they mentioned)
4. Is direct and action-oriented — include next steps, dates, or asks where appropriate
5. Is ready to send with minimal editing
6. Uses clean HTML formatting as described in the Email Formatting section{consolidation_instruction}

Sign off as {user_name}.
Output ONLY the HTML email body. No JSON wrapper. No markdown.
Use <p> tags for paragraphs. Start with a greeting. End with a signoff.

Respond with JSON: {{"subject": "Re: ...", "body": "<p>Hi ...</p><p>...</p><p>Best,<br>{user_name}</p>"}}""")

        return "\n\n".join(sections)

    async def _check_guardrails(
        self,
        draft_body: str,
        context: "DraftContext",
    ) -> list[str]:
        """Check draft for potential unauthorized commitments.

        Scans the generated draft body for indicators of pricing, timeline,
        meeting, or other commitments that may not have been authorized.

        Args:
            draft_body: The generated email body text.
            context: The draft context containing thread summary and other info.

        Returns:
            List of warning strings for any detected issues.
        """
        warnings: list[str] = []
        body_lower = draft_body.lower()

        # Check for pricing language
        price_indicators = [
            "$", "€", "£", "price", "pricing", "discount",
            "% off", "per unit", "per seat", "cost", "annual fee",
            "subscription", "license fee",
        ]
        if any(p in body_lower for p in price_indicators):
            # Check if pricing was in the thread context
            thread_summary = ""
            if context.thread_context and context.thread_context.summary:
                thread_summary = context.thread_context.summary.lower()

            # Also check thread messages for pricing context
            has_pricing_context = "price" in thread_summary or "cost" in thread_summary
            if not has_pricing_context and context.thread_context and context.thread_context.messages:
                for msg in context.thread_context.messages:
                    if msg.body and ("price" in msg.body.lower() or "cost" in msg.body.lower()):
                        has_pricing_context = True
                        break

            if not has_pricing_context:
                warnings.append(
                    "PRICING_COMMITMENT: Draft mentions pricing but no pricing context in thread"
                )

        # Check for timeline commitments
        timeline_indicators = [
            "by friday", "by monday", "next week", "by end of",
            "within 24 hours", "by tomorrow", "i'll have it",
            "will have it by", "delivered by", "complete by",
            "finish by", "ready by",
        ]
        if any(t in body_lower for t in timeline_indicators):
            warnings.append(
                "TIMELINE_COMMITMENT: Draft includes specific timeline promise"
            )

        # Check for meeting acceptance
        meeting_indicators = [
            "see you at", "confirmed for", "i'll be there",
            "meeting is set", "booked for", "accepted the meeting",
            "looking forward to meeting on", "see you on",
        ]
        if any(m in body_lower for m in meeting_indicators):
            warnings.append(
                "MEETING_COMMITMENT: Draft appears to confirm a meeting"
            )

        # Check for product claims that aren't backed by context
        capability_indicators = [
            "our platform can", "we support", "our system provides",
            "arria can", "the software includes",
        ]
        if any(c in body_lower for c in capability_indicators):
            # Check if corporate memory has product info
            has_product_context = False
            if context.corporate_memory and context.corporate_memory.facts:
                for fact in context.corporate_memory.facts:
                    fact_str = str(fact.get("fact", "")).lower()
                    if any(kw in fact_str for kw in ["product", "feature", "capability", "platform"]):
                        has_product_context = True
                        break
            if not has_product_context:
                warnings.append(
                    "PRODUCT_CLAIM: Draft makes product capability claims without context verification"
                )

        return warnings

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
        lead_updates: list[dict] | None = None,
        guardrail_warnings: list[str] | None = None,
        confidence_tier: dict[str, Any] | None = None,
        consolidated_from: list[dict[str, Any]] | None = None,
    ) -> str:
        """Generate internal notes explaining ARIA's reasoning.

        These notes help the user understand why ARIA drafted what it did,
        which context sources were used, and what was missing.
        """
        notes: list[str] = []

        # Add confidence tier note first (replaces the old learning mode note)
        if confidence_tier:
            tier = confidence_tier.get("tier", "UNKNOWN")
            tier_note = confidence_tier.get("note", "")
            notes.append(f"[Confidence: {tier}] {tier_note}")
        elif is_learning_mode:
            notes.append(self._learning_mode.get_learning_mode_note())

        # Add thread consolidation note
        if consolidated_from:
            total_msgs = len(consolidated_from) + 1
            senders = {m["sender"] for m in consolidated_from}
            sender_label = ", ".join(senders)
            notes.append(
                f"This reply addresses {total_msgs} messages from {sender_label} "
                f"in the same thread"
            )

        # Add guardrail warnings prominently at the top if present
        if guardrail_warnings:
            warning_prefix = "⚠️ GUARDRAIL ALERT"
            for warning in guardrail_warnings:
                # Extract the warning type for cleaner display
                warning_type = warning.split(":")[0] if ":" in warning else warning
                notes.append(f"{warning_prefix}: {warning_type}")

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

        # Attachment notes
        body = getattr(email, "body", "") or ""
        if isinstance(body, dict):
            body = body.get("content", "")
        has_attachments = bool(
            getattr(email, "hasAttachments", False)
            or getattr(email, "attachments", None)
        )
        if has_attachments:
            attachments = getattr(email, "attachments", None) or []
            names = [a.get("name", "file") if isinstance(a, dict) else str(a) for a in attachments]
            sender_name = email.sender_name or email.sender_email
            notes.append(
                f"{sender_name} attached '{names[0]}' — I acknowledged it in the reply"
            )

        # Check if user should attach something
        thread = ""
        if context.thread_context and context.thread_context.summary:
            thread = context.thread_context.summary.lower()
        promise_phrases = [
            "i'll send", "i will send", "i'll attach",
            "will share the", "send you the", "i'll get you",
            "i'll forward", "let me send you",
        ]
        if any(p in thread for p in promise_phrases):
            notes.append(
                "⚠️ You may need to attach a document before sending — "
                "the thread suggests you promised to send something"
            )

        # Confidence level
        confidence_label = (
            "HIGH" if confidence >= 0.75 else "MEDIUM" if confidence >= 0.5 else "LOW"
        )
        notes.append(f"Confidence: {confidence_label} ({confidence:.2f})")

        # Lead intelligence signals
        if lead_updates:
            companies = set()
            signal_summaries: list[str] = []
            for update in lead_updates:
                company = update.get("company", "unknown")
                companies.add(company)
                signal = update.get("signal", {})
                category = signal.get("category", "")
                detail = signal.get("detail", "")
                if category and detail:
                    signal_summaries.append(f"{company}: {detail}")

            if signal_summaries:
                notes.append(
                    f"Lead intel ({len(signal_summaries)} signals): "
                    + "; ".join(signal_summaries[:3])
                )

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
        confidence_tier: str | None = None,
    ) -> str:
        """Save draft with all metadata to email_drafts table."""
        draft_id = str(uuid4())

        # Safety: only reference draft_context_id if the context was actually saved
        safe_context_id = context_id if context_id else None

        insert_data: dict[str, Any] = {
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
            "confidence_tier": confidence_tier or "LOW",
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
                .eq("status", "active")
                .limit(1)
                .execute()
            )

            if not result.data:
                result = (
                    self._db.table("user_integrations")
                    .select("integration_type, composio_connection_id")
                    .eq("user_id", user_id)
                    .eq("integration_type", "gmail")
                    .eq("status", "active")
                    .limit(1)
                    .execute()
                )

            if result and result.data:
                integration = result.data[0]
                return (
                    integration.get("integration_type"),
                    integration.get("composio_connection_id"),
                )

            logger.warning("DRAFT_ENGINE: No active email integration for user %s", user_id)
            return None, None
        except Exception:
            return None, None

    async def _fetch_sent_thread_ids(
        self,
        user_id: str,
        since_hours: int = 24,
    ) -> set[str]:
        """Fetch thread IDs from the user's sent messages.

        Makes a single Composio API call to list messages sent by the user
        in the time window, then extracts thread/conversation IDs into a set
        for O(1) lookup during the main processing loop.

        For Outlook, uses OUTLOOK_LIST_MESSAGES with a from-address filter
        (OUTLOOK_LIST_MAIL_FOLDER_MESSAGES does not exist in Composio).

        Args:
            user_id: The user whose sent messages to check.
            since_hours: How far back to look.

        Returns:
            Set of thread IDs found in sent messages.
        """
        try:
            provider, connection_id = await self._get_email_integration(user_id)
            if not provider or not connection_id:
                return set()

            from src.integrations.oauth import get_oauth_client

            oauth_client = get_oauth_client()
            since_date = (datetime.now(UTC) - timedelta(hours=since_hours)).isoformat()

            if provider == "outlook":
                # Get user's email address for the from-address filter
                user_email = await self._get_user_email_address(user_id, provider)
                if not user_email:
                    logger.warning(
                        "DRAFT_ENGINE: No user email found for sent-folder query, "
                        "Tier 1 already-replied check will be skipped for user %s",
                        user_id,
                    )
                    return set()

                # Use OUTLOOK_LIST_MESSAGES with from-address filter
                # (replaces non-existent OUTLOOK_LIST_MAIL_FOLDER_MESSAGES)
                safe_email = user_email.replace("'", "''")
                response = oauth_client.execute_action_sync(
                    connection_id=connection_id,
                    action="OUTLOOK_OUTLOOK_LIST_MESSAGES",
                    params={
                        "$filter": (
                            f"from/emailAddress/address eq '{safe_email}' "
                            f"and sentDateTime ge {since_date}"
                        ),
                        "$top": 200,
                        "$orderby": "sentDateTime desc",
                        "$select": "conversationId",
                    },
                    user_id=user_id,
                )
                if response.get("successful") and response.get("data"):
                    messages = response["data"].get("value", [])
                    ids = {
                        msg.get("conversationId")
                        for msg in messages
                        if msg.get("conversationId")
                    }
                    logger.info(
                        "DRAFT_ENGINE: Fetched %d sent thread IDs for user %s (Outlook)",
                        len(ids),
                        user_id,
                    )
                    return ids
                else:
                    logger.warning(
                        "DRAFT_ENGINE: Outlook sent-message query failed: successful=%s error=%s",
                        response.get("successful"),
                        response.get("error"),
                    )
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
                    ids = {
                        msg.get("thread_id")
                        for msg in messages
                        if msg.get("thread_id")
                    }
                    logger.info(
                        "DRAFT_ENGINE: Fetched %d sent thread IDs for user %s (Gmail)",
                        len(ids),
                        user_id,
                    )
                    return ids

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
            logger.info(
                "ALREADY_REPLIED_TIER1_SENT_FOLDER: thread_id=%s",
                thread_id,
            )
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
                logger.info(
                    "ALREADY_REPLIED_TIER2_DB_DRAFT: thread_id=%s draft_id=%s",
                    thread_id,
                    result.data[0].get("id"),
                )
                return True
        except Exception as e:
            logger.warning(
                "DRAFT_ENGINE: DB check for already-replied failed for thread %s: %s",
                thread_id,
                e,
            )

        return False

    async def _get_user_email_address(
        self, user_id: str, provider: str,
    ) -> str:
        """Get the user's email address from their integration record.

        Args:
            user_id: The user ID.
            provider: The email provider (outlook or gmail).

        Returns:
            The user's email address, or empty string if not found.
        """
        try:
            result = (
                self._db.table("user_integrations")
                .select("account_email")
                .eq("user_id", user_id)
                .eq("integration_type", provider)
                .eq("status", "active")
                .limit(1)
                .execute()
            )
            if result.data:
                return result.data[0].get("account_email", "") or ""
        except Exception as e:
            logger.warning(
                "DRAFT_ENGINE: Failed to get user email for %s: %s",
                user_id,
                e,
            )
        return ""

    def _user_replied_in_thread(
        self,
        thread_messages: list,
    ) -> bool:
        """Check if the user already replied by examining thread messages.

        Uses a simple heuristic: if the most recent message in the
        chronologically-ordered thread is from the user, they have
        already replied and no draft is needed.

        Also checks if ANY user message appears among the last 3 messages
        to catch cases where a quick automated notification arrived after
        the user's reply.

        Args:
            thread_messages: List of ThreadMessage objects (chronological order).

        Returns:
            True if thread evidence shows the user already replied.
        """
        if not thread_messages:
            return False

        # Primary: last message is from user → they replied
        if thread_messages[-1].is_from_user:
            logger.info(
                "ALREADY_REPLIED_TIER3_THREAD: Last message in thread is from user "
                "(sender=%s, timestamp=%s)",
                thread_messages[-1].sender_email,
                thread_messages[-1].timestamp,
            )
            return True

        # Secondary: check if user sent any of the last 3 messages
        # (handles case where an auto-reply or notification landed after user's reply)
        recent = thread_messages[-3:]
        for msg in recent:
            if msg.is_from_user:
                logger.info(
                    "ALREADY_REPLIED_TIER3_THREAD: User message found in recent "
                    "thread messages (sender=%s, timestamp=%s)",
                    msg.sender_email,
                    msg.timestamp,
                )
                return True

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

    # ------------------------------------------------------------------
    # Draft Staleness Detection
    # ------------------------------------------------------------------

    async def check_draft_staleness(self, user_id: str) -> dict[str, int]:
        """Check existing drafts for staleness — thread may have evolved.

        A draft is considered stale if:
        1. It's older than 6 hours
        2. It's still in 'pending' user_action state
        3. The thread has new messages since the draft was created

        When stale, marks the draft with is_stale=True and adds a warning
        to aria_notes so the user knows to review before sending.

        Args:
            user_id: The user whose drafts to check.

        Returns:
            Dict with stats: {'checked': N, 'stale': M}
        """
        stats = {"checked": 0, "stale": 0}

        try:
            # Get all pending drafts older than 6 hours
            cutoff = (datetime.now(UTC) - timedelta(hours=6)).isoformat()

            result = (
                self._db.table("email_drafts")
                .select("id, thread_id, created_at, aria_notes")
                .eq("user_id", user_id)
                .eq("status", "draft")
                .eq("user_action", "pending")
                .lt("created_at", cutoff)
                .execute()
            )

            drafts = result.data or []
            stats["checked"] = len(drafts)

            if not drafts:
                logger.debug(
                    "STALE_CHECK: No pending drafts older than 6 hours for user %s",
                    user_id,
                )
                return stats

            logger.info(
                "STALE_CHECK: Checking %d drafts for staleness (user %s)",
                len(drafts),
                user_id,
            )

            for draft in drafts:
                draft_id = draft["id"]
                thread_id = draft.get("thread_id")
                created_at = draft.get("created_at", "")
                existing_notes = draft.get("aria_notes", "") or ""

                if not thread_id:
                    # Can't check staleness without thread_id
                    continue

                # Check if new emails arrived in this thread since draft was created
                try:
                    new_in_thread = (
                        self._db.table("email_scan_log")
                        .select("id, sender_email, subject, scanned_at")
                        .eq("user_id", user_id)
                        .eq("thread_id", thread_id)
                        .gt("scanned_at", created_at)
                        .order("scanned_at", desc=True)
                        .limit(10)
                        .execute()
                    )

                    if new_in_thread.data:
                        new_count = len(new_in_thread.data)
                        latest_sender = new_in_thread.data[0].get("sender_email", "unknown")
                        latest_subject = new_in_thread.data[0].get("subject", "")[:50]

                        # Build stale reason with details
                        stale_reason = (
                            f"{new_count} new message(s) in thread since draft was created. "
                            f"Latest from {latest_sender}: '{latest_subject}...'"
                        )

                        # Append staleness warning to aria_notes
                        staleness_warning = (
                            f"\n\n⚠️ STALE DRAFT: {new_count} new message(s) arrived after "
                            f"I drafted this. Review the latest thread messages before sending."
                        )
                        updated_notes = existing_notes + staleness_warning

                        # Mark as stale
                        self._db.table("email_drafts").update(
                            {
                                "is_stale": True,
                                "stale_reason": stale_reason,
                                "aria_notes": updated_notes,
                            }
                        ).eq("id", draft_id).execute()

                        stats["stale"] += 1
                        logger.info(
                            "STALE_DRAFT: Marked draft %s as stale — %d new messages in thread %s",
                            draft_id,
                            new_count,
                            thread_id[:16] if thread_id else "?",
                        )

                except Exception as e:
                    logger.warning(
                        "STALE_CHECK: Failed to check thread %s for draft %s: %s",
                        thread_id,
                        draft_id,
                        e,
                    )
                    continue

            if stats["stale"] > 0:
                logger.info(
                    "STALE_CHECK: Complete for user %s — checked %d, marked %d as stale",
                    user_id,
                    stats["checked"],
                    stats["stale"],
                )

        except Exception as e:
            logger.error(
                "STALE_CHECK: Failed to check draft staleness for user %s: %s",
                user_id,
                e,
                exc_info=True,
            )

        return stats


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
