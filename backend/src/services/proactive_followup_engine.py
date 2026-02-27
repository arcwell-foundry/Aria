"""Proactive follow-up engine for overdue email commitments.

When a commitment extracted from email threads passes its due date
without resolution, this engine drafts a follow-up email automatically.

Commitments are stored in prospective_memories with metadata.source =
"email_commitment" by EmailContextGatherer._store_commitments().
This engine queries for overdue ones and uses AutonomousDraftEngine
to generate contextual follow-up drafts.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from src.core.llm import LLMClient
from src.core.task_types import TaskType
from src.db.supabase import SupabaseClient
from src.memory.digital_twin import DigitalTwin
from src.onboarding.personality_calibrator import PersonalityCalibrator
from src.services.email_client_writer import EmailClientWriter
from src.services.email_context_gatherer import DraftContext, EmailContextGatherer

logger = logging.getLogger(__name__)


class ProactiveFollowupEngine:
    """Draft follow-up emails for overdue email commitments.

    Scans prospective_memories for overdue commitments sourced from
    email threads, generates contextual follow-up drafts, saves them
    to email_drafts, and pushes to the user's email client.
    """

    def __init__(self) -> None:
        self._db = SupabaseClient.get_client()
        self._llm = LLMClient()
        self._context_gatherer = EmailContextGatherer()
        self._digital_twin = DigitalTwin()
        self._personality_calibrator = PersonalityCalibrator()
        self._client_writer = EmailClientWriter()

    async def check_and_draft_followups(self, user_id: str) -> list[dict[str, Any]]:
        """Check for overdue email commitments and draft follow-ups.

        Args:
            user_id: The user to check commitments for.

        Returns:
            List of saved draft dicts (id, recipient_email, subject).
        """
        now = datetime.now(UTC).isoformat()

        # 1. Find overdue email commitments via metadata source tag
        try:
            overdue_result = (
                self._db.table("prospective_memories")
                .select("*")
                .eq("user_id", user_id)
                .eq("status", "pending")
                .execute()
            )
        except Exception as e:
            logger.error(
                "PROACTIVE_FOLLOWUP: Failed to query prospective_memories: %s", e
            )
            return []

        if not overdue_result.data:
            return []

        # Filter to email commitments that are overdue
        overdue_commitments = []
        for task in overdue_result.data:
            metadata = task.get("metadata") or {}
            if metadata.get("source") != "email_commitment":
                continue
            # Check due date
            trigger_config = task.get("trigger_config") or {}
            due_at = trigger_config.get("due_at")
            if not due_at or due_at > now:
                continue
            overdue_commitments.append(task)

        if not overdue_commitments:
            return []

        logger.info(
            "PROACTIVE_FOLLOWUP: Found %d overdue email commitments for user=%s",
            len(overdue_commitments),
            user_id,
        )

        followups: list[dict[str, Any]] = []

        for commitment in overdue_commitments:
            try:
                draft = await self._draft_followup_for_commitment(
                    user_id, commitment
                )
                if draft:
                    followups.append(draft)
            except Exception as e:
                logger.warning(
                    "PROACTIVE_FOLLOWUP: Failed to draft followup for commitment %s: %s",
                    commitment.get("id", "?"),
                    e,
                )
                continue

        if followups:
            logger.info(
                "PROACTIVE_FOLLOWUP: Generated %d follow-up drafts for user=%s",
                len(followups),
                user_id,
            )

        return followups

    async def _draft_followup_for_commitment(
        self,
        user_id: str,
        commitment: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Generate and save a follow-up draft for a single overdue commitment.

        Returns:
            Saved draft dict, or None if skipped/failed.
        """
        metadata = commitment.get("metadata") or {}
        sender_email = metadata.get("sender_email")
        sender_name = metadata.get("sender_name", "")
        who = metadata.get("who", "sender")
        thread_id = metadata.get("thread_id", "")
        email_id = metadata.get("email_id", "")
        commitment_id = commitment["id"]
        commitment_task = commitment.get("task", "")
        trigger_config = commitment.get("trigger_config") or {}
        due_at = trigger_config.get("due_at", "unknown")

        if not sender_email:
            logger.debug(
                "PROACTIVE_FOLLOWUP: Skipping commitment %s — no sender_email",
                commitment_id,
            )
            return None

        # Check if we already drafted a follow-up for this commitment
        try:
            existing = (
                self._db.table("email_drafts")
                .select("id")
                .eq("user_id", user_id)
                .eq("source_commitment_id", commitment_id)
                .eq("draft_type", "proactive_followup")
                .execute()
            )
            if existing.data:
                return None  # Already drafted
        except Exception:
            pass  # Column may not exist yet; proceed anyway

        # Gather context from the original thread
        context = await self._gather_context_safe(
            user_id, email_id, thread_id, sender_email, sender_name,
            commitment_task,
        )

        # Build follow-up instruction based on who committed
        if who == "sender":
            followup_instruction = (
                f"Draft a friendly follow-up to {sender_name or sender_email}. "
                f"They committed to: '{commitment_task}' "
                f"which was due {due_at}. "
                f"Be warm, not demanding. Ask for an update."
            )
        else:
            followup_instruction = (
                f"Draft a message to {sender_name or sender_email} following up on "
                f"your commitment: '{commitment_task}' "
                f"which was due {due_at}. "
                f"Either deliver on the commitment or explain the delay."
            )

        # Generate the follow-up draft via LLM
        user_name = await self._get_user_name(user_id)
        style_guidelines = await self._digital_twin.get_style_guidelines(user_id)
        calibration = await self._personality_calibrator.get_calibration(user_id)
        tone_guidance = calibration.tone_guidance if calibration else ""

        draft_body = await self._generate_followup_body(
            user_id, user_name, sender_email, sender_name,
            commitment_task, due_at, who, context,
            style_guidelines, tone_guidance, followup_instruction,
        )

        if not draft_body:
            return None

        # Calculate confidence — proactive drafts are inherently lower confidence
        confidence_level = 0.55
        confidence_tier = "MEDIUM"

        subject = f"Re: {commitment_task[:80]}" if commitment_task else "Following up"
        aria_notes = (
            f"Proactive follow-up: '{commitment_task}' was due {due_at}. "
            f"{'Sender' if who == 'sender' else 'You'} committed to this action."
        )

        # Save draft
        draft_id = str(uuid4())
        insert_data: dict[str, Any] = {
            "id": draft_id,
            "user_id": user_id,
            "recipient_email": sender_email,
            "recipient_name": sender_name or None,
            "subject": subject,
            "body": draft_body,
            "purpose": "follow_up",
            "tone": "friendly",
            "original_email_id": email_id or None,
            "thread_id": thread_id or None,
            "style_match_score": 0.0,
            "confidence_level": confidence_level,
            "aria_notes": aria_notes,
            "status": "draft",
            "draft_type": "proactive_followup",
            "source_commitment_id": commitment_id,
            "confidence_tier": confidence_tier,
        }

        try:
            result = self._db.table("email_drafts").insert(insert_data).execute()
            if not result.data:
                logger.error(
                    "PROACTIVE_FOLLOWUP: Draft insert returned empty for commitment %s",
                    commitment_id,
                )
                return None
        except Exception as e:
            logger.error(
                "PROACTIVE_FOLLOWUP: Failed to save draft for commitment %s: %s",
                commitment_id,
                e,
            )
            return None

        # Save to email client (non-fatal)
        try:
            await self._client_writer.save_draft_to_client(user_id, draft_id)
        except Exception as e:
            logger.warning(
                "PROACTIVE_FOLLOWUP: Client save failed (non-fatal) for draft %s: %s",
                draft_id,
                e,
            )

        logger.info(
            "PROACTIVE_FOLLOWUP: Drafted follow-up to %s for overdue commitment: %s",
            sender_name or sender_email,
            commitment_task[:80],
        )

        return {
            "id": draft_id,
            "recipient_email": sender_email,
            "subject": subject,
            "commitment_id": commitment_id,
            "commitment_task": commitment_task,
        }

    async def _gather_context_safe(
        self,
        user_id: str,
        email_id: str,
        thread_id: str,
        sender_email: str,
        sender_name: str,
        subject: str,
    ) -> DraftContext:
        """Gather email context with fallback on error."""
        try:
            return await self._context_gatherer.gather_context(
                user_id=user_id,
                email_id=email_id or f"followup-{uuid4()}",
                thread_id=thread_id or f"followup-thread-{uuid4()}",
                sender_email=sender_email,
                sender_name=sender_name or None,
                subject=subject or "Follow-up",
            )
        except Exception as e:
            logger.warning(
                "PROACTIVE_FOLLOWUP: Context gathering failed, using minimal: %s", e,
            )
            return DraftContext(
                user_id=user_id,
                email_id=email_id or "",
                thread_id=thread_id or "",
                sender_email=sender_email,
                subject=subject or "Follow-up",
                sources_used=["fallback_minimal"],
            )

    async def _generate_followup_body(
        self,
        user_id: str,
        user_name: str,
        sender_email: str,
        sender_name: str,
        commitment_task: str,
        due_at: str,
        who: str,
        context: DraftContext,
        style_guidelines: str,
        tone_guidance: str,
        followup_instruction: str,
    ) -> str | None:
        """Generate follow-up email body via LLM."""
        # Build context summary
        context_parts: list[str] = []
        if context.thread_context and context.thread_context.summary:
            context_parts.append(
                f"Thread summary: {context.thread_context.summary[:500]}"
            )
        if context.relationship_history:
            history = context.relationship_history
            if history.recent_topics:
                context_parts.append(
                    f"Recent topics: {', '.join(history.recent_topics[:5])}"
                )
        context_text = "\n".join(context_parts) if context_parts else "No additional context available."

        prompt = f"""You are drafting a follow-up email on behalf of {user_name}.

INSTRUCTION: {followup_instruction}

CONTEXT:
{context_text}

STYLE GUIDELINES:
{style_guidelines or 'Professional, warm tone.'}

{f'TONE: {tone_guidance}' if tone_guidance else ''}

Return ONLY the email body as HTML. Do not include subject line, headers, or JSON wrapping.
Keep it concise (3-6 sentences). Be natural and human-sounding."""

        try:
            system_prompt = (
                "You are ARIA, an AI assistant drafting emails on behalf of a user. "
                "Match their writing style. Output HTML email body only."
            )
            try:
                from src.core.persona import PersonaRequest, get_persona_builder

                builder = get_persona_builder()
                persona_ctx = await builder.build(PersonaRequest(
                    user_id=user_id,
                    agent_name="proactive_followup",
                    agent_role_description="Drafting a proactive follow-up email for an overdue commitment",
                    task_description=f"Follow up with {sender_name or sender_email} re: {commitment_task}",
                    output_format="html",
                ))
                system_prompt = persona_ctx.to_system_prompt()
            except Exception as e:
                logger.warning("PROACTIVE_FOLLOWUP: PersonaBuilder unavailable: %s", e)

            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=system_prompt,
                temperature=0.4,
                max_tokens=800,
                user_id=user_id,
                task=TaskType.SCRIBE_DRAFT_EMAIL,
                agent_id="proactive_followup",
            )
            return response.strip() if response else None
        except Exception as e:
            logger.error(
                "PROACTIVE_FOLLOWUP: LLM generation failed: %s", e, exc_info=True,
            )
            return None

    async def _get_user_name(self, user_id: str) -> str:
        """Get user's full name from profile."""
        try:
            result = (
                self._db.table("user_profiles")
                .select("full_name")
                .eq("id", user_id)
                .single()
                .execute()
            )
            if result.data:
                return result.data.get("full_name") or "there"
        except Exception:
            pass
        return "there"
