"""Service for email draft generation and management."""

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

PURPOSE_DESCRIPTIONS: dict[EmailDraftPurpose, str] = {
    EmailDraftPurpose.INTRO: "an introduction email to establish initial contact",
    EmailDraftPurpose.FOLLOW_UP: "a follow-up email to continue a previous conversation",
    EmailDraftPurpose.PROPOSAL: "a proposal email presenting an offer or solution",
    EmailDraftPurpose.THANK_YOU: "a thank you email expressing gratitude",
    EmailDraftPurpose.CHECK_IN: "a check-in email to maintain the relationship",
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
                "status": "draft",
            }

            result = client.table("email_drafts").insert(draft_data).execute()

            if not result.data or len(result.data) == 0:
                raise EmailDraftError("Failed to store draft")

            created_draft = cast(dict[str, Any], result.data[0])

            logger.info(
                "Email draft created",
                extra={"user_id": user_id, "draft_id": created_draft["id"]},
            )

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

            return cast(dict[str, Any], result.data[0])
        except NotFoundError:
            raise
        except Exception as e:
            logger.exception("Failed to update draft")
            raise EmailDraftError(str(e)) from e

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

            # Get lead context if originally provided
            lead_context = await self._get_lead_context(user_id, draft.get("lead_memory_id"))

            # Get style guidelines
            style_guidelines = await self._digital_twin.get_style_guidelines(user_id)

            # Get personality calibration (full object for traits)
            calibration = await self._personality_calibrator.get_calibration(user_id)

            # Combine original context with additional context
            original_context = draft.get("context", {}).get("user_context", "")
            combined_context = (
                f"{original_context}\n{additional_context}"
                if additional_context
                else original_context
            )

            # Build new generation prompt
            generation_prompt = self._build_generation_prompt(
                recipient_email=draft["recipient_email"],
                recipient_name=draft.get("recipient_name"),
                purpose=EmailDraftPurpose(draft["purpose"]),
                tone=use_tone,
                subject_hint=None,  # Let LLM generate new subject
                context=combined_context,
                lead_context=lead_context,
                style_guidelines=style_guidelines,
                calibration=calibration,
            )

            # Generate with slightly higher temperature for variation
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": generation_prompt}],
                system_prompt=EMAIL_GENERATION_PROMPT,
                temperature=0.8,
                task=TaskType.SCRIBE_DRAFT_EMAIL,
                agent_id="draft_service",
            )

            # Parse response
            try:
                email_content = json.loads(response)
                subject = email_content.get("subject", draft["subject"])
                body = email_content.get("body", "")
            except json.JSONDecodeError:
                subject = draft["subject"]
                body = response

            # Score style match
            style_score = await self._digital_twin.score_style_match(user_id, body)

            # Update the draft
            updates = {
                "subject": subject,
                "body": body,
                "tone": use_tone.value,
                "style_match_score": style_score,
            }

            return await self.update_draft(user_id, draft_id, updates)

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
                .maybe_single()
                .execute()
            )
            if result.data:
                return cast(dict[str, Any], result.data)

            # Try Outlook
            result = (
                client.table("user_integrations")
                .select("*")
                .eq("user_id", user_id)
                .eq("integration_type", "outlook")
                .eq("status", "active")
                .maybe_single()
                .execute()
            )
            if result.data:
                return cast(dict[str, Any], result.data)

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
