"""Service for email draft generation and management."""

import asyncio
import contextlib
import json
import logging
from datetime import UTC, datetime
from typing import Any, cast

from src.core.exceptions import EmailDraftError, EmailSendError, NotFoundError
from src.core.llm import LLMClient
from src.core.task_types import TaskType
from src.db.supabase import SupabaseClient
from src.integrations.oauth import get_oauth_client
from src.memory.digital_twin import DigitalTwin
from src.models.email_draft import EmailDraftPurpose, EmailDraftTone
from src.onboarding.personality_calibrator import PersonalityCalibrator
from src.services import notification_integration
from src.services.activity_service import ActivityService

logger = logging.getLogger(__name__)

EMAIL_GENERATION_PROMPT = """You are ARIA, an AI assistant helping a sales professional draft emails.
Generate a professional email based on the following parameters.

IMPORTANT: Your response MUST be valid JSON with exactly two fields:
{
  "subject": "The email subject line",
  "body": "The full email body"
}

Do not include any text outside the JSON object.
"""

EMAIL_REGENERATION_PROMPT = """You are ARIA, an AI assistant helping a sales professional draft emails.
Rewrite the email draft based on the parameters below.

IMPORTANT: Write ONLY the email body text. Do NOT wrap your response in JSON, code blocks,
or include a subject line. Output the email body directly as plain text, ready to send.
"""

PURPOSE_DESCRIPTIONS: dict[EmailDraftPurpose, str] = {
    EmailDraftPurpose.INTRO: "an introduction email to establish initial contact",
    EmailDraftPurpose.FOLLOW_UP: "a follow-up email to continue a previous conversation",
    EmailDraftPurpose.PROPOSAL: "a proposal email presenting an offer or solution",
    EmailDraftPurpose.THANK_YOU: "a thank you email expressing gratitude",
    EmailDraftPurpose.CHECK_IN: "a check-in email to maintain the relationship",
    EmailDraftPurpose.REPLY: "a professional reply to the sender's email",
    EmailDraftPurpose.OTHER: "a general business email",
}

TONE_INSTRUCTIONS: dict[EmailDraftTone, str] = {
    EmailDraftTone.FORMAL: "Use formal, professional language. Avoid contractions and casual expressions.",
    EmailDraftTone.FRIENDLY: "Use warm, approachable language while remaining professional.",
    EmailDraftTone.URGENT: "Convey urgency and importance. Be direct and action-oriented.",
}


class DraftService:
    """Service for managing email drafts.

    Handles email draft generation via LLM with Digital Twin style matching,
    as well as CRUD operations for draft management.
    """

    def __init__(self) -> None:
        """Initialize the DraftService with required dependencies."""
        self._llm = LLMClient()
        self._digital_twin = DigitalTwin()
        self._personality_calibrator = PersonalityCalibrator()
        self._activity = ActivityService()

    async def create_draft(
        self,
        user_id: str,
        recipient_email: str,
        purpose: EmailDraftPurpose,
        tone: EmailDraftTone = EmailDraftTone.FRIENDLY,
        recipient_name: str | None = None,
        subject_hint: str | None = None,
        context: str | None = None,
        lead_memory_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new email draft using LLM generation.

        Args:
            user_id: The ID of the user creating the draft.
            recipient_email: The recipient's email address.
            purpose: The purpose of the email.
            tone: The desired tone of the email.
            recipient_name: Optional name of the recipient for personalization.
            subject_hint: Optional hint for subject line generation.
            context: Optional additional context for draft generation.
            lead_memory_id: Optional lead memory ID for context enrichment.

        Returns:
            The created draft data as a dictionary.

        Raises:
            EmailDraftError: If draft creation fails.
        """
        try:
            # Get lead context if provided
            lead_context = await self._get_lead_context(user_id, lead_memory_id)

            # Get user's style guidelines from Digital Twin
            style_guidelines = await self._digital_twin.get_style_guidelines(user_id)

            # Get personality calibration (full object for traits)
            calibration = await self._personality_calibrator.get_calibration(user_id)

            # Build the generation prompt
            generation_prompt = self._build_generation_prompt(
                recipient_email=recipient_email,
                recipient_name=recipient_name,
                purpose=purpose,
                tone=tone,
                subject_hint=subject_hint,
                context=context,
                lead_context=lead_context,
                style_guidelines=style_guidelines,
                calibration=calibration,
            )

            # Generate email content via LLM
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": generation_prompt}],
                system_prompt=EMAIL_GENERATION_PROMPT,
                temperature=0.7,
                task=TaskType.SCRIBE_DRAFT_EMAIL,
                agent_id="draft_service",
            )

            # Parse JSON response from LLM
            try:
                email_content = json.loads(response)
                subject = email_content.get("subject", "")
                body = email_content.get("body", "")
            except json.JSONDecodeError:
                # Fallback: use raw response as body if JSON parsing fails
                subject = subject_hint or "Email from ARIA"
                body = response

            # Score how well the generated text matches user's writing style
            style_score = await self._digital_twin.score_style_match(user_id, body)

            # Store draft in database
            client = SupabaseClient.get_client()
            draft_data = {
                "user_id": user_id,
                "recipient_email": recipient_email,
                "recipient_name": recipient_name,
                "subject": subject,
                "body": body,
                "purpose": purpose.value,
                "tone": tone.value,
                "context": {"user_context": context, "lead_context": lead_context},
                "lead_memory_id": lead_memory_id,
                "style_match_score": style_score,
                "status": "pending_review",
            }

            result = client.table("email_drafts").insert(draft_data).execute()

            if not result.data or len(result.data) == 0:
                raise EmailDraftError("Failed to store draft")

            created_draft = cast(dict[str, Any], result.data[0])

            logger.info(
                "Email draft created",
                extra={"user_id": user_id, "draft_id": created_draft["id"]},
            )

            # Record activity
            try:
                await self._activity.record(
                    user_id=user_id,
                    agent="scribe",
                    activity_type="email_drafted",
                    title=f"Drafted email to {recipient_name or recipient_email}",
                    description=(
                        f"Created {purpose.value} email draft for "
                        f"{recipient_name or recipient_email}."
                    ),
                    confidence=style_score if isinstance(style_score, float) else 0.8,
                    related_entity_type="draft",
                    related_entity_id=created_draft["id"],
                    metadata={
                        "purpose": purpose.value,
                        "tone": tone.value,
                        "style_match_score": style_score,
                    },
                )
            except Exception:
                logger.debug("Failed to record email_drafted activity", exc_info=True)

            # Notify user that email draft is ready
            await notification_integration.notify_draft_ready(
                user_id=user_id,
                draft_type=purpose.value,
                recipient=recipient_name or recipient_email,
                draft_id=created_draft["id"],
            )

            return created_draft

        except EmailDraftError:
            raise
        except Exception as e:
            logger.exception("Failed to create draft")
            raise EmailDraftError(str(e)) from e

    async def get_draft(self, user_id: str, draft_id: str) -> dict[str, Any] | None:
        """Get a specific draft by ID.

        Args:
            user_id: The ID of the user who owns the draft.
            draft_id: The ID of the draft to retrieve.

        Returns:
            The draft data as a dictionary, or None if not found.
        """
        try:
            client = SupabaseClient.get_client()
            result = (
                client.table("email_drafts")
                .select("*")
                .eq("id", draft_id)
                .eq("user_id", user_id)
                .single()
                .execute()
            )
            return cast(dict[str, Any], result.data) if result.data else None
        except Exception:
            logger.exception("Failed to get draft")
            return None

    async def list_drafts(
        self,
        user_id: str,
        limit: int = 50,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """List user's drafts.

        Args:
            user_id: The ID of the user whose drafts to list.
            limit: Maximum number of drafts to return.
            status: Optional status filter.

        Returns:
            List of draft data dictionaries.
        """
        try:
            client = SupabaseClient.get_client()
            query = client.table("email_drafts").select("*").eq("user_id", user_id)

            if status:
                query = query.eq("status", status)

            result = query.order("created_at", desc=True).limit(limit).execute()

            return cast(list[dict[str, Any]], result.data) if result.data else []
        except Exception:
            logger.exception("Failed to list drafts")
            return []

    async def update_draft(
        self,
        user_id: str,
        draft_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any]:
        """Update a draft.

        Args:
            user_id: The ID of the user who owns the draft.
            draft_id: The ID of the draft to update.
            updates: Dictionary of fields to update.

        Returns:
            The updated draft data.

        Raises:
            NotFoundError: If the draft is not found.
            EmailDraftError: If the update fails.
        """
        try:
            client = SupabaseClient.get_client()

            # Filter out None values from updates
            filtered = {k: v for k, v in updates.items() if v is not None}

            if not filtered:
                # No actual updates, return existing draft
                draft = await self.get_draft(user_id, draft_id)
                if draft is None:
                    raise NotFoundError("Draft", draft_id)
                return draft

            result = (
                client.table("email_drafts")
                .update(filtered)
                .eq("id", draft_id)
                .eq("user_id", user_id)
                .execute()
            )

            if not result.data or len(result.data) == 0:
                raise NotFoundError("Draft", draft_id)

            logger.info(
                "Draft updated",
                extra={"user_id": user_id, "draft_id": draft_id},
            )

            # Fire-and-forget style recalibration when user edits draft content
            if "body" in filtered or "subject" in filtered:
                asyncio.create_task(
                    self._trigger_style_recalibration(user_id),
                    name=f"style-recal-{user_id[:8]}",
                )

            return cast(dict[str, Any], result.data[0])
        except NotFoundError:
            raise
        except Exception as e:
            logger.exception("Failed to update draft")
            raise EmailDraftError(str(e)) from e

    @staticmethod
    async def _trigger_style_recalibration(user_id: str) -> None:
        """Fire-and-forget style recalibration after user edits a draft."""
        try:
            calibrator = PersonalityCalibrator()
            await calibrator.calibrate(user_id)
        except Exception:
            logger.debug("Style recalibration failed for %s", user_id, exc_info=True)

    async def delete_draft(self, user_id: str, draft_id: str) -> bool:
        """Delete a draft.

        Args:
            user_id: The ID of the user who owns the draft.
            draft_id: The ID of the draft to delete.

        Returns:
            True if deletion succeeded, False otherwise.
        """
        try:
            client = SupabaseClient.get_client()
            (
                client.table("email_drafts")
                .delete()
                .eq("id", draft_id)
                .eq("user_id", user_id)
                .execute()
            )

            logger.info(
                "Draft deleted",
                extra={"user_id": user_id, "draft_id": draft_id},
            )

            return True
        except Exception:
            logger.exception("Failed to delete draft")
            return False

    async def regenerate_draft(
        self,
        user_id: str,
        draft_id: str,
        tone: EmailDraftTone | None = None,
        additional_context: str | None = None,
    ) -> dict[str, Any]:
        """Regenerate a draft with new parameters.

        Args:
            user_id: The ID of the user who owns the draft.
            draft_id: The ID of the draft to regenerate.
            tone: Optional new tone for the regenerated draft.
            additional_context: Optional additional context to include.

        Returns:
            The regenerated draft data.

        Raises:
            NotFoundError: If the draft is not found.
            EmailDraftError: If regeneration fails.
        """
        try:
            # Get existing draft
            draft = await self.get_draft(user_id, draft_id)
            if draft is None:
                raise NotFoundError("Draft", draft_id)

            # Use provided tone or existing tone
            use_tone = tone if tone else EmailDraftTone(draft["tone"])
            tone_was_explicit = tone is not None

            # Get lead context if originally provided
            lead_context = await self._get_lead_context(user_id, draft.get("lead_memory_id"))

            # Get style guidelines
            style_guidelines = await self._digital_twin.get_style_guidelines(user_id)

            # Only use personality calibration when user did NOT explicitly pick a tone.
            # An explicit tone selection (Professional/Casual/Urgent) overrides global
            # personality calibration to keep tone per-draft only.
            calibration = None
            if not tone_was_explicit:
                calibration = await self._personality_calibrator.get_calibration(user_id)

            # Build context - for REPLY drafts, load full email context from draft_context table.
            # NEVER use the existing draft body as context — always go back to the
            # original email and thread to prevent hallucination compounding.
            purpose = EmailDraftPurpose(draft["purpose"])
            combined_context = ""

            if purpose == EmailDraftPurpose.REPLY:
                # Load full draft context which contains the original email thread
                full_context = await self._load_draft_context(draft.get("draft_context_id"))
                if full_context:
                    combined_context = self._build_reply_context_from_draft_context(full_context)
                    logger.info(
                        "Regenerating REPLY draft with full email context (draft_context_id=%s)",
                        draft.get("draft_context_id"),
                    )
                else:
                    # Fallback: try to fetch original email content via original_email_id
                    original_email_context = await self._fetch_original_email_context(
                        draft.get("original_email_id"), draft.get("thread_id")
                    )
                    if original_email_context:
                        combined_context = original_email_context
                        logger.info(
                            "Regenerating REPLY draft with original email fallback (email_id=%s)",
                            draft.get("original_email_id"),
                        )
                    else:
                        # Last resort: use stored context (but NOT the draft body itself)
                        original_context = draft.get("context", {}).get("user_context", "")
                        combined_context = original_context
                        logger.warning(
                            "No draft_context or original email found for REPLY draft %s, using stored context",
                            draft_id,
                        )
            else:
                # For non-REPLY purposes, use the stored user context
                original_context = draft.get("context", {}).get("user_context", "")
                combined_context = original_context

            # Append any additional context provided by user
            if additional_context:
                combined_context = f"{combined_context}\n\n{additional_context}" if combined_context else additional_context

            # Build new generation prompt
            generation_prompt = self._build_generation_prompt(
                recipient_email=draft["recipient_email"],
                recipient_name=draft.get("recipient_name"),
                purpose=purpose,
                tone=use_tone,
                subject_hint=draft["subject"],  # Keep subject as hint for regeneration
                context=combined_context,
                lead_context=lead_context,
                style_guidelines=style_guidelines,
                calibration=calibration,
            )

            # Use regeneration prompt that asks for plain text, not JSON
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": generation_prompt}],
                system_prompt=EMAIL_REGENERATION_PROMPT,
                temperature=0.8,
                task=TaskType.SCRIBE_DRAFT_EMAIL,
                agent_id="draft_service",
            )

            # Post-process: strip any JSON/code-fence wrapping the LLM may produce
            body = self._clean_llm_body(response, draft["subject"])
            subject = draft["subject"]  # Keep original subject on tone change

            # Score style match
            style_score = await self._digital_twin.score_style_match(user_id, body)

            # Update the draft
            updates = {
                "subject": subject,
                "body": body,
                "tone": use_tone.value,
                "style_match_score": style_score,
            }

            updated_draft = await self.update_draft(user_id, draft_id, updates)

            # Record activity
            try:
                await self._activity.record(
                    user_id=user_id,
                    agent="scribe",
                    activity_type="draft_regenerated",
                    title=f"Regenerated draft for {draft.get('recipient_name') or draft['recipient_email']}",
                    description=(
                        f"Regenerated email draft with tone={use_tone.value}."
                    ),
                    confidence=style_score if isinstance(style_score, float) else 0.8,
                    related_entity_type="draft",
                    related_entity_id=draft_id,
                    metadata={"tone": use_tone.value, "style_match_score": style_score},
                )
            except Exception:
                logger.debug("Failed to record draft_regenerated activity", exc_info=True)

            return updated_draft

        except NotFoundError:
            raise
        except Exception as e:
            logger.exception("Failed to regenerate draft")
            raise EmailDraftError(str(e)) from e

    async def send_draft(self, user_id: str, draft_id: str) -> dict[str, Any]:
        """Send a draft email via user's email integration.

        Args:
            user_id: The ID of the user who owns the draft.
            draft_id: The ID of the draft to send.

        Returns:
            The updated draft data with sent status.

        Raises:
            NotFoundError: If the draft is not found.
            EmailSendError: If sending fails.
        """
        try:
            draft = await self.get_draft(user_id, draft_id)
            if draft is None:
                raise NotFoundError("Draft", draft_id)

            if draft["status"] == "sent":
                raise EmailSendError("Draft already sent", draft_id=draft_id)

            # Get email integration
            integration = await self._get_email_integration(user_id)
            if integration is None:
                raise EmailSendError(
                    "No email integration connected. Please connect Gmail or Outlook.",
                    draft_id=draft_id,
                )

            # Determine action based on integration type
            integration_type = integration["integration_type"]
            if integration_type == "gmail":
                action = "gmail_send_email"
            elif integration_type == "outlook":
                action = "outlook_send_email"
            else:
                raise EmailSendError(
                    f"Unsupported email integration: {integration_type}",
                    draft_id=draft_id,
                )

            # Execute send via Composio
            oauth_client = get_oauth_client()
            await oauth_client.execute_action(
                connection_id=integration["composio_connection_id"],
                action=action,
                params={
                    "to": draft["recipient_email"],
                    "subject": draft["subject"],
                    "body": draft["body"],
                },
            )

            # Update status to sent
            now = datetime.now(UTC)
            updates = {"status": "sent", "sent_at": now.isoformat()}
            result = await self.update_draft(user_id, draft_id, updates)

            logger.info(
                "Email draft sent",
                extra={
                    "user_id": user_id,
                    "draft_id": draft_id,
                    "integration": integration_type,
                },
            )

            # Record activity
            try:
                await self._activity.record(
                    user_id=user_id,
                    agent="scribe",
                    activity_type="email_sent",
                    title=f"Sent email to {draft.get('recipient_name') or draft['recipient_email']}",
                    description=(
                        f"Sent email '{draft.get('subject', '')}' "
                        f"via {integration_type}."
                    ),
                    confidence=1.0,
                    related_entity_type="draft",
                    related_entity_id=draft_id,
                    metadata={"integration_type": integration_type},
                )
            except Exception:
                logger.debug("Failed to record email_sent activity", exc_info=True)

            return result

        except (NotFoundError, EmailSendError):
            raise
        except Exception as e:
            # Try to update draft status to failed
            with contextlib.suppress(Exception):
                await self.update_draft(
                    user_id, draft_id, {"status": "failed", "error_message": str(e)}
                )
            logger.exception("Failed to send email draft")
            raise EmailSendError(str(e), draft_id=draft_id) from e

    async def _get_email_integration(self, user_id: str) -> dict[str, Any] | None:
        """Get user's email integration (Gmail or Outlook).

        Args:
            user_id: The ID of the user.

        Returns:
            Integration data as a dictionary, or None if not found.
        """
        try:
            client = SupabaseClient.get_client()
            # Try Gmail first
            result = (
                client.table("user_integrations")
                .select("*")
                .eq("user_id", user_id)
                .eq("integration_type", "gmail")
                .eq("status", "active")
                .limit(1)
                .execute()
            )
            record = result.data[0] if result and result.data else None
            if record:
                return cast(dict[str, Any], record)

            # Try Outlook
            result = (
                client.table("user_integrations")
                .select("*")
                .eq("user_id", user_id)
                .eq("integration_type", "outlook")
                .eq("status", "active")
                .limit(1)
                .execute()
            )
            record = result.data[0] if result and result.data else None
            if record:
                return cast(dict[str, Any], record)

            logger.warning("No active email integration for user %s", user_id)
            return None
        except Exception:
            logger.warning(f"Failed to get email integration for user {user_id}")
            return None

    async def _get_lead_context(
        self, user_id: str, lead_memory_id: str | None
    ) -> dict[str, Any] | None:
        """Get context from lead memory.

        Args:
            user_id: The ID of the user.
            lead_memory_id: The ID of the lead memory to retrieve.

        Returns:
            Lead memory data as a dictionary, or None if not found.
        """
        if not lead_memory_id:
            return None

        try:
            client = SupabaseClient.get_client()
            result = (
                client.table("lead_memories")
                .select("*")
                .eq("id", lead_memory_id)
                .eq("user_id", user_id)
                .single()
                .execute()
            )
            return cast(dict[str, Any], result.data) if result.data else None
        except Exception:
            logger.warning(f"Failed to get lead context for {lead_memory_id}")
            return None

    async def _load_draft_context(self, draft_context_id: str | None) -> dict[str, Any] | None:
        """Load full draft context from the draft_context table.

        This contains the original email thread and all gathered context
        for reply drafts created by the autonomous draft engine.

        Args:
            draft_context_id: The ID of the draft_context record.

        Returns:
            The draft context data, or None if not found.
        """
        if not draft_context_id:
            return None

        try:
            client = SupabaseClient.get_client()
            result = (
                client.table("draft_context")
                .select("*")
                .eq("id", draft_context_id)
                .single()
                .execute()
            )
            return cast(dict[str, Any], result.data) if result.data else None
        except Exception:
            logger.warning(f"Failed to load draft_context for {draft_context_id}")
            return None

    def _build_reply_context_from_draft_context(self, draft_context: dict[str, Any]) -> str:
        """Build context string for REPLY drafts from the full draft_context.

        This extracts the original email content and thread context to include
        in the generation prompt, similar to how autonomous_draft_engine does it.

        Args:
            draft_context: The full draft context from the database.

        Returns:
            A formatted context string for the generation prompt.
        """
        parts = []

        # Add original email info including the body from thread messages
        sender_email = draft_context.get("sender_email", "")
        subject = draft_context.get("subject", "")
        parts.append("=== ORIGINAL EMAIL YOU ARE REPLYING TO ===")
        parts.append(f"From: {sender_email}")
        parts.append(f"Subject: {subject}")

        # Extract the original email body from the thread messages.
        # The most recent non-user message is the email we're replying to.
        thread_context = draft_context.get("thread_context")
        original_body = ""
        if thread_context and isinstance(thread_context, dict):
            messages = thread_context.get("messages", [])
            # Find the last message that isn't from the user (the inbound email)
            for msg in reversed(messages):
                if not msg.get("is_from_user", False):
                    original_body = msg.get("body", "")
                    break
            # If all messages are from the user, just use the last message
            if not original_body and messages:
                original_body = messages[-1].get("body", "")

        # Also check thread_summary for a text summary
        thread_summary = ""
        if thread_context and isinstance(thread_context, dict):
            thread_summary = thread_context.get("summary", "")

        if original_body:
            # Truncate very long emails but keep enough for context
            if len(original_body) > 2000:
                original_body = original_body[:2000] + "..."
            parts.append(f"Body:\n{original_body}")
        elif thread_summary:
            parts.append(f"Summary: {thread_summary}")

        # Add thread context if available (earlier messages for thread awareness)
        if thread_context and isinstance(thread_context, dict):
            messages = thread_context.get("messages", [])
            # Show earlier thread messages for context (skip the last one already shown)
            earlier_messages = messages[:-1] if len(messages) > 1 else []
            if earlier_messages:
                parts.append("\n=== EARLIER THREAD MESSAGES ===")
                for msg in earlier_messages[-3:]:  # Last 3 earlier messages
                    sender = msg.get("sender_name") or msg.get("sender_email", "Unknown")
                    body = msg.get("body", "")
                    # Truncate long messages
                    if len(body) > 500:
                        body = body[:500] + "..."
                    is_from_user = msg.get("is_from_user", False)
                    prefix = "You" if is_from_user else sender
                    parts.append(f"\n{prefix}: {body}")

        # Add relationship history if available
        relationship_history = draft_context.get("relationship_history")
        if relationship_history and isinstance(relationship_history, dict):
            memory_facts = relationship_history.get("memory_facts", [])
            if memory_facts:
                fact_lines = "\n".join(
                    f"- {f.get('fact', str(f))}" for f in memory_facts[:3]
                )
                total = relationship_history.get("total_emails", 0)
                parts.append(f"\n=== RELATIONSHIP HISTORY ===")
                if total:
                    parts.append(f"Total interactions: {total}")
                parts.append(f"Key facts:\n{fact_lines}")

        # Add recipient research if available
        recipient_research = draft_context.get("recipient_research")
        if recipient_research and isinstance(recipient_research, dict):
            info_parts = []
            if recipient_research.get("sender_title"):
                info_parts.append(f"Title: {recipient_research['sender_title']}")
            if recipient_research.get("sender_company"):
                info_parts.append(f"Company: {recipient_research['sender_company']}")
            if recipient_research.get("bio"):
                bio = recipient_research["bio"]
                if len(bio) > 300:
                    bio = bio[:300] + "..."
                info_parts.append(f"Bio: {bio}")
            if info_parts:
                parts.append("\n=== ABOUT THE RECIPIENT ===")
                parts.extend(info_parts)

        return "\n".join(parts)

    def _parse_llm_response(self, response: str, fallback_subject: str) -> tuple[str, str]:
        """Parse LLM response to extract subject and body.

        Handles multiple response formats:
        1. Clean JSON: {"subject": "...", "body": "..."}
        2. JSON inside markdown code blocks
        3. Plain text (fallback)

        Args:
            response: The raw LLM response string.
            fallback_subject: Subject to use if parsing fails.

        Returns:
            Tuple of (subject, body).
        """
        import re

        # Try direct JSON parse first
        try:
            data = json.loads(response.strip())
            if isinstance(data, dict):
                return (
                    data.get("subject", fallback_subject),
                    data.get("body", response),
                )
        except json.JSONDecodeError:
            pass

        # Try extracting JSON from markdown code blocks
        # Pattern matches ```json ... ``` or ``` ... ```
        code_block_pattern = r"```(?:json)?\s*\n?(.*?)```"
        matches = re.findall(code_block_pattern, response, re.DOTALL | re.IGNORECASE)

        for match in matches:
            try:
                data = json.loads(match.strip())
                if isinstance(data, dict):
                    return (
                        data.get("subject", fallback_subject),
                        data.get("body", match),
                    )
            except json.JSONDecodeError:
                continue

        # Fallback: use raw response as body
        logger.warning(
            "Failed to parse LLM response as JSON, using raw response as body"
        )
        return (fallback_subject, response)

    def _clean_llm_body(self, response: str, fallback_subject: str) -> str:
        """Clean LLM response for regeneration — extract plain email body.

        When regenerating with EMAIL_REGENERATION_PROMPT, the LLM should return
        plain text. But if it returns JSON or code-fenced output anyway, extract
        just the body text.

        Args:
            response: The raw LLM response.
            fallback_subject: Subject line (unused, kept for signature parity).

        Returns:
            Clean email body text.
        """
        import re

        text = response.strip()

        # Strip markdown code fences (```json ... ``` or ``` ... ```)
        code_block_pattern = r"^```(?:json)?\s*\n?(.*?)```\s*$"
        match = re.match(code_block_pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            text = match.group(1).strip()

        # If it looks like JSON with subject/body keys, extract the body
        if text.startswith("{") or '"body"' in text or '"subject"' in text:
            try:
                data = json.loads(text)
                if isinstance(data, dict) and "body" in data:
                    return data["body"].strip()
            except json.JSONDecodeError:
                pass

        return text

    async def _fetch_original_email_context(
        self,
        original_email_id: str | None,
        thread_id: str | None,
    ) -> str | None:
        """Fetch original email content as fallback when draft_context is missing.

        Tries to load the original inbound email from draft_context table by
        email_id or thread_id. Returns a formatted context string or None.

        Args:
            original_email_id: The ID of the original email being replied to.
            thread_id: The thread ID to search by.

        Returns:
            Formatted context string, or None if not found.
        """
        if not original_email_id and not thread_id:
            return None

        try:
            client = SupabaseClient.get_client()

            # Try by email_id first (most specific)
            if original_email_id:
                result = (
                    client.table("draft_context")
                    .select("*")
                    .eq("email_id", original_email_id)
                    .order("created_at", desc=True)
                    .limit(1)
                    .execute()
                )
                record = result.data[0] if result and result.data else None
                if record:
                    return self._build_reply_context_from_draft_context(
                        cast(dict[str, Any], record)
                    )

            # Fall back to thread_id
            if thread_id:
                result = (
                    client.table("draft_context")
                    .select("*")
                    .eq("thread_id", thread_id)
                    .order("created_at", desc=True)
                    .limit(1)
                    .execute()
                )
                record = result.data[0] if result and result.data else None
                if record:
                    return self._build_reply_context_from_draft_context(
                        cast(dict[str, Any], record)
                    )

        except Exception:
            logger.warning(
                "Failed to fetch original email context (email_id=%s, thread_id=%s)",
                original_email_id,
                thread_id,
            )

        return None

    def _build_generation_prompt(
        self,
        recipient_email: str,
        recipient_name: str | None,
        purpose: EmailDraftPurpose,
        tone: EmailDraftTone,
        subject_hint: str | None,
        context: str | None,
        lead_context: dict[str, Any] | None,
        style_guidelines: str,
        calibration: Any | None = None,
    ) -> str:
        """Build the generation prompt for the LLM.

        Args:
            recipient_email: The recipient's email address.
            recipient_name: The recipient's name.
            purpose: The purpose of the email.
            tone: The desired tone.
            subject_hint: Optional hint for the subject line.
            context: Additional context provided by the user.
            lead_context: Context from lead memory.
            style_guidelines: User's writing style guidelines.
            calibration: PersonalityCalibration object with tone_guidance and traits.

        Returns:
            The formatted generation prompt.
        """
        parts = [
            f"Generate {PURPOSE_DESCRIPTIONS[purpose]}.",
            "",
            f"Recipient: {recipient_name or recipient_email}",
            f"Tone: {TONE_INSTRUCTIONS[tone]}",
        ]

        if subject_hint:
            parts.append(f"Subject hint: {subject_hint}")

        if context:
            parts.append(f"\nAdditional context: {context}")

        if lead_context:
            company = lead_context.get("company_name", "")
            stage = lead_context.get("lifecycle_stage", "")
            if company:
                parts.append(f"\nCompany: {company}")
            if stage:
                parts.append(f"Relationship stage: {stage}")

        parts.append(f"\n--- WRITING STYLE GUIDELINES ---\n{style_guidelines}")

        # Add personality calibration with tone guidance and traits
        if calibration and calibration.tone_guidance:
            trait_parts = []
            trait_parts.append(f"directness={calibration.directness:.1f}")
            trait_parts.append(f"warmth={calibration.warmth:.1f}")
            trait_parts.append(f"formality={calibration.formality:.1f}")
            parts.append(f"\n--- TONE GUIDANCE ---\n{calibration.tone_guidance}")
            parts.append(f"Personality traits: {', '.join(trait_parts)}")

        return "\n".join(parts)


# Singleton instance
_draft_service: DraftService | None = None


def get_draft_service() -> DraftService:
    """Get or create draft service singleton.

    Returns:
        The DraftService singleton instance.
    """
    global _draft_service
    if _draft_service is None:
        _draft_service = DraftService()
    return _draft_service
