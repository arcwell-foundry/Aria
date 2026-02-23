"""Draft Feedback Tracker for email learning mode.

Polls email clients (Gmail/Outlook) to detect user actions on
ARIA-generated drafts. Since Composio lacks draft webhooks, we use
polling-based detection:

- APPROVED: Draft found in sent folder with same content (edit_distance >= 0.9)
- EDITED: Draft found in sent folder with different content (edit_distance < 0.9)
- REJECTED: Draft not in sent folder AND not in drafts folder
- IGNORED: Draft > 7 days old with no action
"""

import logging
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from typing import Any

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)

# Thresholds
EDIT_DISTANCE_APPROVED_THRESHOLD = 0.9  # >= 0.9 = approved (minor or no edits)
DRAFT_IGNORED_AGE_DAYS = 7


def levenshtein_ratio(s1: str, s2: str) -> float:
    """Calculate similarity ratio between two strings.

    Uses SequenceMatcher which is based on Gestalt Pattern Matching.
    Returns a float between 0 (completely different) and 1 (identical).

    Args:
        s1: First string.
        s2: Second string.

    Returns:
        Similarity ratio (0.0 to 1.0).
    """
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    # Normalize whitespace for comparison
    s1_normalized = " ".join(s1.split())
    s2_normalized = " ".join(s2.split())

    return SequenceMatcher(None, s1_normalized, s2_normalized).ratio()


class DraftFeedbackTracker:
    """Tracks user actions on ARIA-generated email drafts.

    Uses polling-based detection since Composio doesn't provide
    draft action webhooks. Checks sent folder and drafts folder
    to determine user action.
    """

    def __init__(self) -> None:
        """Initialize with database client."""
        self._db = SupabaseClient.get_client()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def poll_pending_drafts(self, user_id: str) -> dict[str, Any]:
        """Poll for feedback on pending drafts for a user.

        For each pending draft:
        1. Check if it's > 7 days old (mark as IGNORED)
        2. Check if it was sent (in sent folder)
        3. If sent, compare content to detect APPROVED vs EDITED
        4. If not sent and not in drafts, mark as REJECTED

        Args:
            user_id: The user whose drafts to poll.

        Returns:
            Dict with counts of actions detected.
        """
        results = {
            "checked": 0,
            "approved": 0,
            "edited": 0,
            "rejected": 0,
            "ignored": 0,
            "errors": 0,
        }

        try:
            # Get pending drafts for this user
            pending_drafts = await self._get_pending_drafts(user_id)
            results["checked"] = len(pending_drafts)

            if not pending_drafts:
                return results

            logger.info(
                "DRAFT_FEEDBACK: Checking %d pending drafts for user %s",
                len(pending_drafts),
                user_id,
            )

            # Check each draft
            for draft in pending_drafts:
                try:
                    action = await self._detect_draft_action(user_id, draft)

                    if action["action"] != "pending":
                        await self._update_draft_action(
                            draft_id=draft["id"],
                            action=action["action"],
                            edited_body=action.get("edited_body"),
                            edit_distance=action.get("edit_distance"),
                        )

                        results[action["action"]] = results.get(action["action"], 0) + 1

                        logger.info(
                            "DRAFT_FEEDBACK: Detected %s for draft %s (edit_distance: %.2f)",
                            action["action"],
                            draft["id"],
                            action.get("edit_distance", 0),
                        )

                except Exception as e:
                    logger.warning(
                        "DRAFT_FEEDBACK: Error checking draft %s: %s",
                        draft["id"],
                        e,
                    )
                    results["errors"] += 1

            logger.info(
                "DRAFT_FEEDBACK: Poll complete for user %s - approved: %d, edited: %d, rejected: %d, ignored: %d",
                user_id,
                results["approved"],
                results["edited"],
                results["rejected"],
                results["ignored"],
            )

        except Exception as e:
            logger.error(
                "DRAFT_FEEDBACK: Poll failed for user %s: %s",
                user_id,
                e,
                exc_info=True,
            )
            results["errors"] += 1

        return results

    async def poll_all_users(self) -> dict[str, Any]:
        """Poll pending drafts for all users with email integration.

        Returns:
            Aggregated results across all users.
        """
        results = {
            "users_checked": 0,
            "total_checked": 0,
            "total_approved": 0,
            "total_edited": 0,
            "total_rejected": 0,
            "total_ignored": 0,
            "total_errors": 0,
        }

        try:
            # Find users with pending drafts
            result = (
                self._db.table("email_drafts")
                .select("user_id")
                .eq("user_action", "pending")
                .execute()
            )

            user_ids = list({row["user_id"] for row in (result.data or [])})

            for user_id in user_ids:
                try:
                    user_result = await self.poll_pending_drafts(user_id)
                    results["users_checked"] += 1
                    results["total_checked"] += user_result["checked"]
                    results["total_approved"] += user_result["approved"]
                    results["total_edited"] += user_result["edited"]
                    results["total_rejected"] += user_result["rejected"]
                    results["total_ignored"] += user_result["ignored"]
                    results["total_errors"] += user_result["errors"]
                except Exception as e:
                    logger.warning(
                        "DRAFT_FEEDBACK: Failed to poll for user %s: %s",
                        user_id,
                        e,
                    )

        except Exception as e:
            logger.error(
                "DRAFT_FEEDBACK: Poll all users failed: %s",
                e,
                exc_info=True,
            )

        return results

    # ------------------------------------------------------------------
    # Action Detection
    # ------------------------------------------------------------------

    async def _detect_draft_action(
        self,
        user_id: str,
        draft: dict[str, Any],
    ) -> dict[str, Any]:
        """Detect what action the user took on a draft.

        Args:
            user_id: The user ID.
            draft: The draft record from database.

        Returns:
            Dict with action, edited_body, edit_distance.
        """
        draft_id = draft["id"]
        draft_body = draft.get("body", "")
        created_at_str = draft.get("created_at")

        # Check for IGNORED (too old)
        if created_at_str:
            created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            age_days = (datetime.now(UTC) - created_at).days

            if age_days >= DRAFT_IGNORED_AGE_DAYS:
                return {
                    "action": "ignored",
                    "edit_distance": None,
                    "edited_body": None,
                }

        # Check if draft was sent (in sent folder)
        sent_match = await self._find_in_sent_folder(user_id, draft)

        if sent_match:
            # Draft was sent - check if edited
            sent_body = sent_match.get("body", "")
            edit_distance = levenshtein_ratio(draft_body, sent_body)

            if edit_distance >= EDIT_DISTANCE_APPROVED_THRESHOLD:
                return {
                    "action": "approved",
                    "edit_distance": edit_distance,
                    "edited_body": None,
                }
            else:
                return {
                    "action": "edited",
                    "edit_distance": edit_distance,
                    "edited_body": sent_body,
                }

        # Check if draft still exists in drafts folder
        draft_exists = await self._check_draft_exists(user_id, draft)

        if not draft_exists:
            # Not sent and not in drafts = rejected
            return {
                "action": "rejected",
                "edit_distance": None,
                "edited_body": None,
            }

        # Still pending
        return {
            "action": "pending",
            "edit_distance": None,
            "edited_body": None,
        }

    async def _find_in_sent_folder(
        self,
        user_id: str,
        draft: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Check if a draft was sent (exists in sent folder).

        Uses Composio to check the sent folder for emails matching
        the draft's recipient and subject.

        Args:
            user_id: The user ID.
            draft: The draft record.

        Returns:
            Sent email dict if found, None otherwise.
        """
        try:
            # Get user's email provider and connection_id
            provider, connection_id = await self._get_email_integration(user_id)
            if not provider or not connection_id:
                return None

            from src.integrations.oauth import get_oauth_client

            oauth_client = get_oauth_client()

            recipient_email = draft.get("recipient_email", "").lower()
            subject = draft.get("subject", "")
            created_at = draft.get("created_at", "")

            # Search sent folder for matching emails since draft creation
            since_date = created_at[:10] if created_at else None

            if provider == "outlook":
                response = oauth_client.execute_action_sync(
                    connection_id=connection_id,
                    action="OUTLOOK_LIST_MAIL_FOLDER_MESSAGES",
                    params={
                        "mail_folder_id": "sentitems",
                        "$top": 50,
                        "$filter": f"sentDateTime ge {since_date}" if since_date else None,
                    },
                    user_id=user_id,
                )
                if response.get("successful") and response.get("data"):
                    emails = response["data"].get("value", [])
                else:
                    emails = []
            else:
                response = oauth_client.execute_action_sync(
                    connection_id=connection_id,
                    action="GMAIL_FETCH_EMAILS",
                    params={
                        "label": "SENT",
                        "max_results": 50,
                    },
                    user_id=user_id,
                )
                if response.get("successful") and response.get("data"):
                    emails = response["data"].get("emails", [])
                else:
                    emails = []

            # Look for matching email
            for email in emails:
                to_list = email.get("to", [])
                if isinstance(to_list, list) and to_list:
                    to_email = (
                        to_list[0].lower()
                        if isinstance(to_list[0], str)
                        else to_list[0].get("email", "").lower()
                    )

                    # Match by recipient and subject similarity
                    if to_email == recipient_email:
                        email_subject = email.get("subject", "")
                        subject_similarity = levenshtein_ratio(subject, email_subject)

                        if subject_similarity >= 0.8:
                            return email

            return None

        except Exception as e:
            logger.warning(
                "DRAFT_FEEDBACK: Error checking sent folder for draft %s: %s",
                draft.get("id"),
                e,
            )
            return None

    async def _check_draft_exists(
        self,
        user_id: str,
        draft: dict[str, Any],
    ) -> bool:
        """Check if a draft still exists in the email client's drafts folder.

        Args:
            user_id: The user ID.
            draft: The draft record.

        Returns:
            True if draft still exists, False otherwise.
        """
        try:
            client_draft_id = draft.get("client_draft_id")
            if not client_draft_id:
                # No client draft ID - assume exists (can't verify)
                return True

            provider, connection_id = await self._get_email_integration(user_id)
            if not provider or not connection_id:
                return True

            from src.integrations.oauth import get_oauth_client

            oauth_client = get_oauth_client()

            if provider == "outlook":
                response = oauth_client.execute_action_sync(
                    connection_id=connection_id,
                    action="OUTLOOK_OUTLOOK_GET_MESSAGE",
                    params={"message_id": client_draft_id},
                    user_id=user_id,
                )
            else:
                response = oauth_client.execute_action_sync(
                    connection_id=connection_id,
                    action="GMAIL_GET_DRAFT",
                    params={"draft_id": client_draft_id},
                    user_id=user_id,
                )

            # If we get a response without error, draft exists
            return bool(response.get("successful") and response.get("data"))

        except Exception as e:
            logger.debug(
                "DRAFT_FEEDBACK: Error checking draft existence for %s: %s",
                draft.get("id"),
                e,
            )
            # On error, assume exists (safer - don't mark as rejected)
            return True

    # ------------------------------------------------------------------
    # Private Helpers
    # ------------------------------------------------------------------

    async def _get_pending_drafts(self, user_id: str) -> list[dict[str, Any]]:
        """Get all pending drafts for a user.

        Args:
            user_id: The user whose drafts to retrieve.

        Returns:
            List of draft records with pending status.
        """
        try:
            result = (
                self._db.table("email_drafts")
                .select("*")
                .eq("user_id", user_id)
                .eq("user_action", "pending")
                .order("created_at", desc=False)
                .limit(50)
                .execute()
            )

            return result.data or []

        except Exception as e:
            logger.error(
                "DRAFT_FEEDBACK: Error getting pending drafts for user %s: %s",
                user_id,
                e,
            )
            return []

    async def _update_draft_action(
        self,
        draft_id: str,
        action: str,
        edited_body: str | None,
        edit_distance: float | None,
    ) -> None:
        """Update a draft with the detected user action.

        Args:
            draft_id: The draft ID.
            action: The detected action (approved/edited/rejected/ignored).
            edited_body: The edited body if action is 'edited'.
            edit_distance: The edit distance ratio if applicable.
        """
        try:
            update_data: dict[str, Any] = {
                "user_action": action,
                "action_detected_at": datetime.now(UTC).isoformat(),
            }

            if edited_body:
                update_data["user_edited_body"] = edited_body

            if edit_distance is not None:
                update_data["edit_distance"] = edit_distance

            (
                self._db.table("email_drafts")
                .update(update_data)
                .eq("id", draft_id)
                .execute()
            )

        except Exception as e:
            logger.error(
                "DRAFT_FEEDBACK: Error updating draft %s: %s",
                draft_id,
                e,
            )

    async def _get_email_integration(
        self, user_id: str
    ) -> tuple[str | None, str | None]:
        """Get the email provider and connection_id for a user.

        Args:
            user_id: The user ID.

        Returns:
            Tuple of (provider, connection_id) or (None, None).
        """
        try:
            # Prefer Outlook as it's more commonly working in enterprise
            # First try Outlook, then fall back to Gmail
            result = (
                self._db.table("user_integrations")
                .select("integration_type, composio_connection_id")
                .eq("user_id", user_id)
                .eq("integration_type", "outlook")
                .limit(1)
                .execute()
            )

            if not result.data:
                # Fall back to Gmail
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


# ---------------------------------------------------------------------------
# Singleton Access
# ---------------------------------------------------------------------------

_tracker: DraftFeedbackTracker | None = None


def get_draft_feedback_tracker() -> DraftFeedbackTracker:
    """Get the singleton DraftFeedbackTracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = DraftFeedbackTracker()
    return _tracker
