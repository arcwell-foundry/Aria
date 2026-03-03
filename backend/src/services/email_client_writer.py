"""Email Client Writer Service.

Saves ARIA-generated drafts to user's actual email client (Gmail/Outlook).
ARIA NEVER SENDS - only saves to Drafts folder for user to manually send.
"""

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from src.db.supabase import SupabaseClient
from src.integrations.domain import IntegrationType
from src.integrations.oauth import get_oauth_client
from src.integrations.service import IntegrationService
from src.services.activity_service import ActivityService

logger = logging.getLogger(__name__)


class DraftSaveError(Exception):
    """Raised when saving draft to email client fails."""

    def __init__(self, message: str, provider: str | None = None) -> None:
        super().__init__(message)
        self.provider = provider


class EmailClientWriter:
    """Saves drafts to user's email client via Composio.

    ARIA NEVER sends emails - this service only saves drafts to the user's
    email client so they can review and manually send.
    """

    def __init__(self) -> None:
        self._integration_service = IntegrationService()
        self._activity_service = ActivityService()
        self._oauth_client = get_oauth_client()
        self._db = SupabaseClient.get_client()

    async def save_draft_to_client(
        self,
        user_id: str,
        draft_id: UUID | str,
    ) -> dict[str, Any]:
        """Save an ARIA draft to the user's email client drafts folder.

        Args:
            user_id: User's ID
            draft_id: ID of the draft in email_drafts table

        Returns:
            dict with success status and client_draft_id

        Raises:
            DraftSaveError: If save fails
        """
        # 1. Get the draft from database
        draft = await self._get_draft(str(draft_id))
        if not draft:
            raise DraftSaveError(f"Draft {draft_id} not found")

        # Check if already saved
        if draft.get("saved_to_client") or draft.get("saved_to_client_at"):
            logger.info(
                "EMAIL_CLIENT: Draft %s already saved to %s",
                draft_id,
                draft.get("client_provider"),
            )
            return {
                "success": True,
                "client_draft_id": draft.get("client_draft_id"),
                "provider": draft.get("client_provider"),
                "already_saved": True,
            }

        # 2. Get user's email integrations (try both providers)
        integrations = await self._get_email_integrations_ranked(user_id)
        if not integrations:
            logger.warning(
                "EMAIL_CLIENT: No email integration found for user %s",
                user_id,
            )
            raise DraftSaveError(
                "No email integration found. Connect Gmail or Outlook in Settings."
            )

        # 3. Try each provider in order, fall back if auth fails
        last_error: Exception | None = None
        for integration in integrations:
            provider = integration.get("integration_type", "")
            connection_id = integration.get("composio_connection_id", "")

            logger.info(
                "EMAIL_CLIENT: SAVE_TO_CLIENT_ATTEMPT: draft_id=%s, user_id=%s, provider=%s, connection_id=%s",
                draft_id,
                user_id,
                provider,
                connection_id[:8] + "..." if connection_id else "NONE",
            )

            # Normalize provider name
            if provider == IntegrationType.GMAIL.value:
                provider = "gmail"
            elif provider == IntegrationType.OUTLOOK.value:
                provider = "outlook"

            try:
                if provider == "gmail":
                    result = await self._save_to_gmail(
                        connection_id=connection_id,
                        draft=draft,
                        user_id=user_id,
                    )
                elif provider == "outlook":
                    result = await self._save_to_outlook(
                        connection_id=connection_id,
                        draft=draft,
                        user_id=user_id,
                    )
                else:
                    continue

                # Composio returns {"successful": bool, "data": {...}, "error": ...}
                if not result.get("successful", False):
                    error_msg = result.get("error") or "Unknown Composio error"
                    raise DraftSaveError(
                        f"Composio {provider} create draft failed: {error_msg}",
                        provider=provider,
                    )

                # Extract client draft ID from nested data
                data = result.get("data") or result
                client_draft_id = (
                    data.get("id") or data.get("draft_id") or data.get("Id")
                )

                # 4. Update email_drafts record
                await self._update_draft_sync_status(
                    draft_id=str(draft_id),
                    client_draft_id=client_draft_id,
                    provider=provider,
                )

                # 5. Log activity
                await self._activity_service.record(
                    user_id=user_id,
                    agent="scribe",
                    activity_type="draft_saved_to_client",
                    title=f"Draft saved to {provider.title()}",
                    description=f"Reply to {draft.get('recipient_email')}: {draft.get('subject')}",
                    confidence=draft.get("style_match_score") or 0.8,
                    related_entity_type="email_draft",
                    related_entity_id=str(draft_id),
                )

                logger.info(
                    "EMAIL_CLIENT: Draft %s saved to %s as %s",
                    draft_id,
                    provider,
                    client_draft_id,
                )
                return {
                    "success": True,
                    "client_draft_id": client_draft_id,
                    "provider": provider,
                    "already_saved": False,
                }

            except Exception as e:
                logger.warning(
                    "EMAIL_CLIENT: Failed to save draft %s via %s, trying next provider: %s",
                    draft_id,
                    provider,
                    e,
                )
                last_error = e

        # All providers failed
        raise DraftSaveError(
            f"Failed to save draft to any provider: {last_error}",
            provider="none",
        )

    async def _save_to_gmail(
        self,
        connection_id: str,
        draft: dict[str, Any],
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Save draft to Gmail via Composio.

        Args:
            connection_id: Composio connection ID
            draft: Draft data from email_drafts table
            user_id: User ID for Composio entity resolution

        Returns:
            Result from Composio with draft ID
        """
        params: dict[str, Any] = {
            "recipient_email": draft.get("recipient_email", ""),
            "subject": draft.get("subject", ""),
            "body": draft.get("body", ""),
            "is_html": True,
        }

        # Add threading if replying to existing email
        thread_id = draft.get("thread_id")
        if thread_id:
            params["thread_id"] = thread_id

        logger.info(
            "EMAIL_CLIENT: Gmail create draft params: recipient=%s, subject=%s, thread_id=%s",
            params.get("recipient_email"),
            params.get("subject"),
            thread_id,
        )

        try:
            result = await self._oauth_client.execute_action(
                connection_id=connection_id,
                action="GMAIL_CREATE_EMAIL_DRAFT",
                params=params,
                user_id=user_id,
            )
            logger.info(
                "EMAIL_CLIENT: Gmail create draft result: successful=%s, data_keys=%s",
                result.get("successful"),
                list(result.get("data", {}).keys()) if isinstance(result.get("data"), dict) else str(result.get("data"))[:100],
            )
            return result
        except Exception as e:
            logger.error(
                "EMAIL_CLIENT: Gmail create draft failed: %s",
                e,
                exc_info=True,
            )
            raise

    async def _save_to_outlook(
        self,
        connection_id: str,
        draft: dict[str, Any],
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Save draft to Outlook via Composio.

        Uses OUTLOOK_CREATE_DRAFT action which expects:
        - subject (str, required)
        - body (str, required) - plain text or HTML content
        - is_html (bool) - True if body is HTML
        - to_recipients (list[str]) - email addresses

        Args:
            connection_id: Composio connection ID
            draft: Draft data from email_drafts table
            user_id: User ID for Composio entity resolution

        Returns:
            Result from Composio with draft ID
        """
        recipient_email = draft.get("recipient_email", "")
        params: dict[str, Any] = {
            "subject": draft.get("subject", ""),
            "body": draft.get("body", ""),
            "is_html": True,
            "to_recipients": [recipient_email] if recipient_email else [],
        }

        logger.info(
            "EMAIL_CLIENT: Outlook create draft params: to_recipients=%s, subject=%s",
            params.get("to_recipients"),
            params.get("subject"),
        )

        try:
            result = await self._oauth_client.execute_action(
                connection_id=connection_id,
                action="OUTLOOK_CREATE_DRAFT",
                params=params,
                user_id=user_id,
            )
            logger.info(
                "EMAIL_CLIENT: Outlook create draft result: successful=%s, data_keys=%s",
                result.get("successful"),
                list(result.get("data", {}).keys()) if isinstance(result.get("data"), dict) else str(result.get("data"))[:100],
            )
            return result
        except Exception as e:
            logger.error(
                "EMAIL_CLIENT: Outlook create draft failed: %s",
                e,
                exc_info=True,
            )
            raise

    async def _get_draft(self, draft_id: str) -> dict[str, Any] | None:
        """Get draft from database.

        Args:
            draft_id: Draft UUID

        Returns:
            Draft dict or None
        """
        try:
            result = (
                self._db.table("email_drafts")
                .select("*")
                .eq("id", draft_id)
                .maybe_single()
                .execute()
            )
            return result.data if result else None
        except Exception as e:
            logger.error("EMAIL_CLIENT: Failed to get draft %s: %s", draft_id, e)
            return None

    async def _get_email_integrations_ranked(self, user_id: str) -> list[dict[str, Any]]:
        """Get user's active email integrations, ranked by preference.

        Returns all active email integrations so the caller can fall back
        if the preferred provider has an expired OAuth token.

        Args:
            user_id: User's UUID

        Returns:
            List of active integration dicts (may be empty)
        """
        result: list[dict[str, Any]] = []

        # Try Gmail first
        gmail = await self._integration_service.get_integration(
            user_id=user_id,
            integration_type=IntegrationType.GMAIL,
        )
        if gmail and gmail.get("status") == "active":
            result.append(gmail)

        # Then Outlook
        outlook = await self._integration_service.get_integration(
            user_id=user_id,
            integration_type=IntegrationType.OUTLOOK,
        )
        if outlook and outlook.get("status") == "active":
            result.append(outlook)

        return result

    async def _update_draft_sync_status(
        self,
        draft_id: str,
        client_draft_id: str | None,
        provider: str,
    ) -> None:
        """Update draft with client sync info.

        Args:
            draft_id: Draft UUID
            client_draft_id: ID from email client
            provider: 'gmail' or 'outlook'
        """
        try:
            self._db.table("email_drafts").update(
                {
                    "saved_to_client": True,
                    "email_client": provider,
                    "saved_to_client_at": datetime.now(UTC).isoformat(),
                }
            ).eq("id", draft_id).execute()
        except Exception as e:
            logger.error(
                "EMAIL_CLIENT: Failed to update draft sync status for %s: %s",
                draft_id,
                e,
            )
            # Don't raise - the draft was saved to client successfully


# ---------------------------------------------------------------------------
# Singleton Access
# ---------------------------------------------------------------------------

_writer: EmailClientWriter | None = None


def get_email_client_writer() -> EmailClientWriter:
    """Get the singleton EmailClientWriter instance."""
    global _writer
    if _writer is None:
        _writer = EmailClientWriter()
    return _writer
