"""Style recalibration job for email learning mode.

This job runs weekly (Sunday 2 AM) to re-analyze user's writing style
based on:
1. Last 50 sent emails from the past week
2. Edited drafts where user made significant changes

The recalibration updates:
- Global writing style fingerprint
- Per-recipient writing profiles
- Logs results to style_recalibration_log table

This enables ARIA to continuously improve style matching based on
real user behavior.
"""

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from src.db.supabase import SupabaseClient
from src.onboarding.writing_analysis import WritingAnalysisService

logger = logging.getLogger(__name__)

# Configuration
RECALIBRATION_WINDOW_DAYS = 7
MIN_SENT_EMAILS = 10
MIN_EDITED_DRAFTS = 3
MAX_EMAILS_TO_ANALYZE = 50


async def run_style_recalibration_job() -> dict[str, Any]:
    """Run weekly style recalibration for all users with email integrations.

    For each user:
    1. Fetch sent emails from past 7 days
    2. Fetch edited drafts from past 7 days
    3. Re-analyze writing style if enough data
    4. Update fingerprint and recipient profiles
    5. Log results to style_recalibration_log

    Returns:
        Dict with statistics about the recalibration run.
    """
    stats = {
        "users_processed": 0,
        "users_skipped_insufficient_data": 0,
        "fingerprints_updated": 0,
        "profiles_updated": 0,
        "errors": 0,
    }

    logger.info("STYLE_RECALIBRATION: Starting weekly style recalibration job")

    try:
        db = SupabaseClient.get_client()

        # Get users with email integrations
        result = (
            db.table("user_integrations")
            .select("user_id")
            .in_("integration_type", ["gmail", "outlook"])
            .eq("status", "active")
            .execute()
        )

        users = result.data or []
        logger.info(
            "STYLE_RECALIBRATION: Processing %d users with email integrations",
            len(users),
        )

        for user_record in users:
            user_id = user_record["user_id"]

            try:
                user_result = await _recalibrate_user_style(user_id)

                stats["users_processed"] += 1

                if user_result.get("skipped"):
                    stats["users_skipped_insufficient_data"] += 1
                else:
                    if user_result.get("fingerprint_updated"):
                        stats["fingerprints_updated"] += 1
                    if user_result.get("profiles_updated", 0) > 0:
                        stats["profiles_updated"] += user_result["profiles_updated"]

            except Exception as e:
                logger.warning(
                    "STYLE_RECALIBRATION: Failed for user %s: %s",
                    user_id,
                    e,
                    exc_info=True,
                )
                stats["errors"] += 1

        logger.info(
            "STYLE_RECALIBRATION: Complete. Processed %d users, %d fingerprints updated, "
            "%d profiles updated, %d skipped, %d errors",
            stats["users_processed"],
            stats["fingerprints_updated"],
            stats["profiles_updated"],
            stats["users_skipped_insufficient_data"],
            stats["errors"],
        )

    except Exception as e:
        logger.error(
            "STYLE_RECALIBRATION: Job failed: %s",
            e,
            exc_info=True,
        )
        stats["errors"] += 1

    return stats


async def _recalibrate_user_style(user_id: str) -> dict[str, Any]:
    """Recalibrate writing style for a single user.

    Args:
        user_id: The user to recalibrate.

    Returns:
        Dict with recalibration results.
    """
    db = SupabaseClient.get_client()
    result = {
        "user_id": user_id,
        "skipped": False,
        "fingerprint_updated": False,
        "profiles_updated": 0,
    }

    # Create log entry
    log_id = str(uuid.uuid4())
    started_at = datetime.now(UTC)
    date_range_start = started_at - timedelta(days=RECALIBRATION_WINDOW_DAYS)

    try:
        # Create initial log entry
        db.table("style_recalibration_log").insert(
            {
                "id": log_id,
                "user_id": user_id,
                "run_type": "weekly",
                "started_at": started_at.isoformat(),
                "date_range_start": date_range_start.isoformat(),
                "date_range_end": started_at.isoformat(),
                "status": "running",
            }
        ).execute()

        # Fetch sent emails from past week
        sent_emails = await _fetch_recent_sent_emails(user_id, days=RECALIBRATION_WINDOW_DAYS)

        # Fetch edited drafts from past week
        edited_drafts = await _fetch_edited_drafts(user_id, days=RECALIBRATION_WINDOW_DAYS)

        # Check if we have enough data
        if len(sent_emails) < MIN_SENT_EMAILS and len(edited_drafts) < MIN_EDITED_DRAFTS:
            logger.info(
                "STYLE_RECALIBRATION: Skipping user %s - insufficient data "
                "(%d sent emails, %d edited drafts)",
                user_id,
                len(sent_emails),
                len(edited_drafts),
            )

            # Update log as skipped
            db.table("style_recalibration_log").update(
                {
                    "status": "completed",
                    "completed_at": datetime.now(UTC).isoformat(),
                    "emails_analyzed": len(sent_emails),
                    "edited_drafts_included": len(edited_drafts),
                    "changes_summary": {"skipped_reason": "insufficient_data"},
                }
            ).eq("id", log_id).execute()

            result["skipped"] = True
            return result

        # Get previous fingerprint for comparison
        previous_fingerprint = await _get_current_fingerprint(user_id)

        # Prepare writing samples
        samples = []

        # Add sent email bodies
        for email in sent_emails[:MAX_EMAILS_TO_ANALYZE]:
            body = email.get("body", "")
            if body and len(body) >= 100:
                samples.append(body)

        # Add edited draft bodies (these represent user's preferred style)
        for draft in edited_drafts:
            edited_body = draft.get("user_edited_body", "")
            if edited_body and len(edited_body) >= 100:
                samples.append(edited_body)

        if not samples:
            result["skipped"] = True
            return result

        # Run analysis
        service = WritingAnalysisService()
        new_fingerprint = await service.analyze_samples(user_id, samples)

        # Check if fingerprint changed significantly
        fingerprint_changed = _fingerprint_changed(previous_fingerprint, new_fingerprint)

        # Update recipient profiles
        profiles_updated = 0
        if sent_emails:
            profiles = await service.analyze_recipient_samples(user_id, sent_emails)
            profiles_updated = len(profiles)

        # Build changes summary
        changes_summary = _build_changes_summary(
            previous_fingerprint,
            new_fingerprint,
            len(sent_emails),
            len(edited_drafts),
        )

        # Update log with results
        completed_at = datetime.now(UTC)
        db.table("style_recalibration_log").update(
            {
                "status": "completed",
                "completed_at": completed_at.isoformat(),
                "emails_analyzed": len(sent_emails),
                "edited_drafts_included": len(edited_drafts),
                "previous_fingerprint": previous_fingerprint,
                "new_fingerprint": new_fingerprint.model_dump() if new_fingerprint else None,
                "fingerprint_changed": fingerprint_changed,
                "profiles_updated": profiles_updated,
                "changes_summary": changes_summary,
                "previous_confidence": previous_fingerprint.get("confidence") if previous_fingerprint else None,
                "new_confidence": new_fingerprint.confidence if new_fingerprint else None,
            }
        ).eq("id", log_id).execute()

        result["fingerprint_updated"] = fingerprint_changed
        result["profiles_updated"] = profiles_updated

        logger.info(
            "STYLE_RECALIBRATION: Updated user %s - fingerprint_changed: %s, profiles_updated: %d",
            user_id,
            fingerprint_changed,
            profiles_updated,
        )

        return result

    except Exception as e:
        logger.error(
            "STYLE_RECALIBRATION: Error for user %s: %s",
            user_id,
            e,
            exc_info=True,
        )

        # Update log with error
        try:
            db.table("style_recalibration_log").update(
                {
                    "status": "failed",
                    "completed_at": datetime.now(UTC).isoformat(),
                    "error_message": str(e),
                }
            ).eq("id", log_id).execute()
        except Exception:
            pass

        raise


async def _fetch_recent_sent_emails(user_id: str, days: int) -> list[dict[str, Any]]:
    """Fetch recent sent emails via Composio.

    Args:
        user_id: The user whose emails to fetch.
        days: Number of days to look back.

    Returns:
        List of email dicts.
    """
    try:
        db = SupabaseClient.get_client()

        # Get email provider and connection_id
        # Prefer Outlook as it's more commonly working in enterprise
        result = (
            db.table("user_integrations")
            .select("integration_type, composio_connection_id")
            .eq("user_id", user_id)
            .eq("integration_type", "outlook")
            .limit(1)
            .execute()
        )

        if not result.data:
            # Fall back to Gmail
            result = (
                db.table("user_integrations")
                .select("integration_type, composio_connection_id")
                .eq("user_id", user_id)
                .eq("integration_type", "gmail")
                .limit(1)
                .execute()
            )

        if not result or not result.data:
            return []

        integration = result.data[0]
        provider = integration.get("integration_type", "").lower()
        connection_id = integration.get("composio_connection_id")

        if not connection_id:
            logger.warning(
                "STYLE_RECALIBRATION: No connection_id for user %s",
                user_id,
            )
            return []

        from src.integrations.oauth import get_oauth_client

        oauth_client = get_oauth_client()

        since_date = (datetime.now(UTC) - timedelta(days=days)).isoformat()

        if provider == "outlook":
            response = oauth_client.execute_action_sync(
                connection_id=connection_id,
                action="OUTLOOK_LIST_MAIL_FOLDER_MESSAGES",
                params={
                    "mail_folder_id": "sentitems",
                    "$top": MAX_EMAILS_TO_ANALYZE,
                    "$filter": f"sentDateTime ge {since_date}",
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
                    "max_results": MAX_EMAILS_TO_ANALYZE,
                },
                user_id=user_id,
            )
            if response.get("successful") and response.get("data"):
                emails = response["data"].get("emails", [])
            else:
                emails = []

        return emails

    except Exception as e:
        logger.warning(
            "STYLE_RECALIBRATION: Failed to fetch sent emails for user %s: %s",
            user_id,
            e,
        )
        return []


async def _fetch_edited_drafts(user_id: str, days: int) -> list[dict[str, Any]]:
    """Fetch edited drafts from the database.

    Args:
        user_id: The user whose drafts to fetch.
        days: Number of days to look back.

    Returns:
        List of draft records with user_edited_body.
    """
    try:
        db = SupabaseClient.get_client()

        since_date = (datetime.now(UTC) - timedelta(days=days)).isoformat()

        result = (
            db.table("email_drafts")
            .select("id, user_edited_body, edit_distance, recipient_email")
            .eq("user_id", user_id)
            .eq("user_action", "edited")
            .gte("action_detected_at", since_date)
            .not_.is_("user_edited_body", "null")
            .execute()
        )

        return result.data or []

    except Exception as e:
        logger.warning(
            "STYLE_RECALIBRATION: Failed to fetch edited drafts for user %s: %s",
            user_id,
            e,
        )
        return []


async def _get_current_fingerprint(user_id: str) -> dict[str, Any] | None:
    """Get the user's current writing style fingerprint.

    Args:
        user_id: The user whose fingerprint to get.

    Returns:
        Current fingerprint dict or None.
    """
    try:
        db = SupabaseClient.get_client()

        result = (
            db.table("user_settings")
            .select("preferences")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )

        if result and result.data:
            prefs = result.data.get("preferences", {}) or {}
            digital_twin = prefs.get("digital_twin", {})
            return digital_twin.get("writing_style")

        return None

    except Exception:
        return None


def _fingerprint_changed(
    previous: dict[str, Any] | None,
    new: Any,
) -> bool:
    """Check if fingerprint changed significantly.

    Args:
        previous: Previous fingerprint dict.
        new: New fingerprint model.

    Returns:
        True if changed significantly, False otherwise.
    """
    if not previous or not new:
        return new is not None

    # Compare key metrics
    new_dict = new.model_dump() if hasattr(new, "model_dump") else new

    key_fields = [
        "formality_index",
        "directness",
        "warmth",
        "assertiveness",
        "emoji_usage",
        "opening_style",
        "closing_style",
    ]

    for field in key_fields:
        old_val = previous.get(field)
        new_val = new_dict.get(field)

        # For numeric fields, check for 0.1+ change
        if isinstance(old_val, (int, float)) and isinstance(new_val, (int, float)):
            if abs(old_val - new_val) >= 0.1:
                return True
        # For string fields, check for any change
        elif old_val != new_val:
            return True

    return False


def _build_changes_summary(
    previous: dict[str, Any] | None,
    new: Any,
    emails_count: int,
    drafts_count: int,
) -> dict[str, Any]:
    """Build a summary of what changed in the recalibration.

    Args:
        previous: Previous fingerprint.
        new: New fingerprint.
        emails_count: Number of emails analyzed.
        drafts_count: Number of edited drafts included.

    Returns:
        Summary dict.
    """
    summary: dict[str, Any] = {
        "emails_analyzed": emails_count,
        "edited_drafts_included": drafts_count,
        "changes": [],
    }

    if not previous or not new:
        summary["initial_fingerprint"] = new is not None
        return summary

    new_dict = new.model_dump() if hasattr(new, "model_dump") else new

    # Track numeric changes
    numeric_fields = [
        ("formality_index", "formality"),
        ("directness", "directness"),
        ("warmth", "warmth"),
        ("assertiveness", "assertiveness"),
    ]

    for field, label in numeric_fields:
        old_val = previous.get(field)
        new_val = new_dict.get(field)

        if isinstance(old_val, (int, float)) and isinstance(new_val, (int, float)):
            if abs(old_val - new_val) >= 0.05:
                summary["changes"].append(
                    f"{label} shifted {old_val:.2f}→{new_val:.2f}"
                )

    # Track categorical changes
    if previous.get("emoji_usage") != new_dict.get("emoji_usage"):
        summary["changes"].append(
            f"emoji_usage: {previous.get('emoji_usage')}→{new_dict.get('emoji_usage')}"
        )

    if previous.get("opening_style") != new_dict.get("opening_style"):
        summary["changes"].append("opening_style changed")

    if previous.get("closing_style") != new_dict.get("closing_style"):
        summary["changes"].append("closing_style changed")

    return summary
