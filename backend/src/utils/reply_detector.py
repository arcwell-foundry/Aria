"""Reply detection utility for email classification.

Detects whether a user has already replied to an email thread,
preventing ARIA from incorrectly marking threads as NEEDS_REPLY
when the user has already responded via their email client or ARIA.

Sources checked (in order, short-circuiting on first hit):
1. ARIA's sent drafts (email_drafts with status='sent')
2. User's own emails in the scan log (email_scan_log from user's address)
3. Email provider thread check (Composio: Outlook/Gmail API)
"""

import logging
import re
from datetime import UTC, datetime
from typing import Any

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


async def get_user_emails(db: SupabaseClient, user_id: str) -> set[str]:
    """Get all known email addresses for a user.

    Collects from user_integrations, user_profiles, and auth.

    Args:
        db: Supabase client instance.
        user_id: The user's ID.

    Returns:
        Set of lowercased email addresses belonging to the user.
    """
    user_emails: set[str] = set()

    try:
        # From active integrations
        integrations = (
            db.table("user_integrations")
            .select("account_email")
            .eq("user_id", user_id)
            .eq("status", "active")
            .execute()
        )
        for row in integrations.data or []:
            if row.get("account_email"):
                user_emails.add(row["account_email"].lower())

        # From user_profiles
        profiles = (
            db.table("user_profiles")
            .select("email")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if profiles.data and profiles.data[0].get("email"):
            user_emails.add(profiles.data[0]["email"].lower())

        # From Supabase Auth
        try:
            result = db.auth.admin.get_user_by_id(user_id)
            if result.user and result.user.email:
                user_emails.add(result.user.email.lower())
        except Exception:
            pass

    except Exception as e:
        logger.warning(
            "REPLY_DETECTOR: Failed to get user emails for %s: %s",
            user_id,
            e,
        )

    return user_emails


def _get_email_integration(
    db: SupabaseClient, user_id: str
) -> tuple[str, str] | None:
    """Get the user's active email integration (provider + connection_id).

    Args:
        db: Supabase client instance.
        user_id: The user's ID.

    Returns:
        Tuple of (provider, connection_id) or None if no integration found.
    """
    # Try Outlook first (more common in enterprise), then Gmail
    for provider in ("outlook", "gmail"):
        try:
            result = (
                db.table("user_integrations")
                .select("integration_type, composio_connection_id")
                .eq("user_id", user_id)
                .eq("integration_type", provider)
                .eq("status", "active")
                .limit(1)
                .execute()
            )
            if result.data:
                connection_id = result.data[0].get("composio_connection_id")
                if connection_id:
                    return (provider, connection_id)
        except Exception:
            continue
    return None


def _extract_email_address(raw: str) -> str:
    """Extract email address from 'Name <email>' format."""
    if not raw:
        return ""
    match = re.search(r"<([^>]+)>", raw)
    if match:
        return match.group(1).lower()
    return raw.strip().lower()


async def _check_provider_for_reply(
    db: SupabaseClient,
    user_id: str,
    thread_id: str,
    email_timestamp: str | None,
    user_emails: set[str],
) -> bool:
    """Source 3: Check with email provider if user replied in this thread.

    Fetches thread messages from Outlook/Gmail via Composio and checks if
    any message in the thread is FROM the user's email and NEWER than the
    incoming email.

    Args:
        db: Supabase client instance.
        user_id: The user's ID.
        thread_id: The email thread/conversation ID.
        email_timestamp: ISO timestamp of the incoming email.
        user_emails: Set of user's known email addresses (lowercased).

    Returns:
        True if the provider confirms a reply exists.
    """
    integration = _get_email_integration(db, user_id)
    if not integration:
        logger.debug(
            "REPLY_DETECTOR: No email integration found for user %s, "
            "skipping provider check",
            user_id,
        )
        return False

    provider, connection_id = integration

    try:
        from src.integrations.oauth import get_oauth_client

        oauth_client = get_oauth_client()

        if provider == "outlook":
            return await _check_outlook_thread(
                oauth_client=oauth_client,
                connection_id=connection_id,
                user_id=user_id,
                thread_id=thread_id,
                email_timestamp=email_timestamp,
                user_emails=user_emails,
            )
        else:
            return await _check_gmail_thread(
                oauth_client=oauth_client,
                connection_id=connection_id,
                user_id=user_id,
                thread_id=thread_id,
                email_timestamp=email_timestamp,
                user_emails=user_emails,
            )

    except Exception as e:
        logger.warning(
            "REPLY_DETECTOR: Source 3 (provider) check failed for thread %s: %s",
            thread_id,
            e,
        )
        return False


async def _check_outlook_thread(
    oauth_client: Any,
    connection_id: str,
    user_id: str,
    thread_id: str,
    email_timestamp: str | None,
    user_emails: set[str],
) -> bool:
    """Check Outlook conversation for user replies via OUTLOOK_LIST_MESSAGES."""
    response = oauth_client.execute_action_sync(
        connection_id=connection_id,
        action="OUTLOOK_LIST_MESSAGES",
        params={
            "conversationId": thread_id,
            "orderby": ["receivedDateTime asc"],
            "top": 50,
        },
        user_id=user_id,
        dangerously_skip_version_check=True,
    )

    if not response.get("successful"):
        logger.warning(
            "REPLY_DETECTOR: Outlook thread fetch failed for %s: %s",
            thread_id[:60] if thread_id else "NONE",
            response.get("error"),
        )
        return False

    # Handle both Composio response formats
    data = response.get("data", {})
    if "response_data" in data:
        messages_data = data["response_data"].get("value", [])
    else:
        messages_data = data.get("value", [])

    logger.info(
        "REPLY_DETECTOR: Outlook thread %s has %d messages",
        thread_id[:40] if thread_id else "NONE",
        len(messages_data),
    )

    for msg in messages_data:
        sender = msg.get("from", {}).get("emailAddress", {})
        msg_sender = sender.get("address", "").lower()
        msg_date = msg.get("receivedDateTime", "")

        # Check if this message is FROM the user
        if msg_sender not in user_emails:
            continue

        # Check if it's newer than the incoming email
        if email_timestamp and msg_date and msg_date > email_timestamp:
            logger.info(
                "REPLY_DETECTOR: Found Outlook reply from %s at %s "
                "(after incoming at %s) in thread %s",
                msg_sender,
                msg_date,
                email_timestamp,
                thread_id[:40] if thread_id else "NONE",
            )
            return True

        # If no timestamp to compare, any message from user counts as a reply
        if not email_timestamp and msg_sender in user_emails:
            logger.info(
                "REPLY_DETECTOR: Found Outlook message from user %s in thread %s "
                "(no timestamp comparison)",
                msg_sender,
                thread_id[:40] if thread_id else "NONE",
            )
            return True

    return False


async def _check_gmail_thread(
    oauth_client: Any,
    connection_id: str,
    user_id: str,
    thread_id: str,
    email_timestamp: str | None,
    user_emails: set[str],
) -> bool:
    """Check Gmail thread for user replies via GMAIL_FETCH_MESSAGE_BY_THREAD_ID."""
    response = oauth_client.execute_action_sync(
        connection_id=connection_id,
        action="GMAIL_FETCH_MESSAGE_BY_THREAD_ID",
        params={"thread_id": thread_id},
        user_id=user_id,
    )

    if not response.get("successful"):
        logger.warning(
            "REPLY_DETECTOR: Gmail thread fetch failed for %s: %s",
            thread_id[:60] if thread_id else "NONE",
            response.get("error"),
        )
        return False

    thread_data = response.get("data", {})
    thread_messages = thread_data.get("messages", [])

    logger.info(
        "REPLY_DETECTOR: Gmail thread %s has %d messages",
        thread_id[:40] if thread_id else "NONE",
        len(thread_messages),
    )

    for msg in thread_messages:
        # Gmail stores headers in payload.headers
        headers = {
            h["name"].lower(): h["value"]
            for h in msg.get("payload", {}).get("headers", [])
        }
        msg_sender = _extract_email_address(headers.get("from", ""))
        msg_date = headers.get("date", "")

        # Check if this message is FROM the user
        if msg_sender not in user_emails:
            continue

        # For Gmail, use internalDate (epoch ms) for timestamp comparison
        internal_date = msg.get("internalDate")
        if email_timestamp and internal_date:
            try:
                msg_dt = datetime.fromtimestamp(int(internal_date) / 1000, tz=UTC)
                email_dt = datetime.fromisoformat(
                    email_timestamp.replace("Z", "+00:00")
                )
                if msg_dt > email_dt:
                    logger.info(
                        "REPLY_DETECTOR: Found Gmail reply from %s at %s "
                        "(after incoming at %s) in thread %s",
                        msg_sender,
                        msg_dt.isoformat(),
                        email_timestamp,
                        thread_id[:40] if thread_id else "NONE",
                    )
                    return True
            except (ValueError, TypeError):
                # Can't parse timestamps — fall through to simple presence check
                pass

        # If no timestamp comparison possible, any message from user = reply
        if not email_timestamp:
            logger.info(
                "REPLY_DETECTOR: Found Gmail message from user %s in thread %s "
                "(no timestamp comparison)",
                msg_sender,
                thread_id[:40] if thread_id else "NONE",
            )
            return True

    return False


async def has_user_replied(
    db: SupabaseClient,
    user_id: str,
    thread_id: str,
    email_timestamp: str | None,
    user_emails: set[str],
) -> bool:
    """Check if the user has already replied to a thread.

    Checks three sources in order (short-circuits on first hit):
    1. ARIA's sent drafts (local DB — fast)
    2. User's emails in scan log (local DB — fast)
    3. Email provider thread check (API call — only if 1 & 2 miss)

    Args:
        db: Supabase client instance.
        user_id: The user's ID.
        thread_id: The email thread ID.
        email_timestamp: ISO timestamp of the incoming email (for ordering).
        user_emails: Set of the user's known email addresses (lowercased).

    Returns:
        True if a reply from the user exists in this thread.
    """
    if not thread_id or not user_emails:
        return False

    # Check cached result first
    try:
        cached = (
            db.table("email_scan_log")
            .select("user_replied")
            .eq("user_id", user_id)
            .eq("thread_id", thread_id)
            .eq("category", "NEEDS_REPLY")
            .not_.is_("user_replied", "null")
            .limit(1)
            .execute()
        )
        if cached.data:
            result = cached.data[0].get("user_replied")
            if result is not None:
                return bool(result)
    except Exception:
        pass  # Cache miss is fine — proceed with checks

    # Source 1: Check if ARIA sent a draft for this thread
    try:
        sent_drafts = (
            db.table("email_drafts")
            .select("id")
            .eq("user_id", user_id)
            .eq("thread_id", thread_id)
            .eq("status", "sent")
            .limit(1)
            .execute()
        )
        if sent_drafts.data:
            logger.info(
                "REPLY_DETECTOR: Found sent ARIA draft for thread %s (user %s)",
                thread_id,
                user_id,
            )
            _cache_reply_result(db, user_id, thread_id, True)
            return True
    except Exception as e:
        logger.warning(
            "REPLY_DETECTOR: Source 1 (sent drafts) check failed for thread %s: %s",
            thread_id,
            e,
        )

    # Source 2: Check email_scan_log for emails FROM the user in this thread
    try:
        for user_email in user_emails:
            query = (
                db.table("email_scan_log")
                .select("id")
                .eq("user_id", user_id)
                .eq("thread_id", thread_id)
                .eq("sender_email", user_email)
            )
            if email_timestamp:
                query = query.gt("scanned_at", email_timestamp)

            scan_result = query.limit(1).execute()
            if scan_result.data:
                logger.info(
                    "REPLY_DETECTOR: Found user reply in scan log for thread %s "
                    "(user %s, sender %s)",
                    thread_id,
                    user_id,
                    user_email,
                )
                _cache_reply_result(db, user_id, thread_id, True)
                return True
    except Exception as e:
        logger.warning(
            "REPLY_DETECTOR: Source 2 (scan log) check failed for thread %s: %s",
            thread_id,
            e,
        )

    # Source 3: Check with email provider (API call — most reliable but expensive)
    try:
        provider_replied = await _check_provider_for_reply(
            db=db,
            user_id=user_id,
            thread_id=thread_id,
            email_timestamp=email_timestamp,
            user_emails=user_emails,
        )
        if provider_replied:
            _cache_reply_result(db, user_id, thread_id, True)
            return True
    except Exception as e:
        logger.warning(
            "REPLY_DETECTOR: Source 3 (provider) check failed for thread %s: %s",
            thread_id,
            e,
        )

    # No reply found across all sources — cache negative result
    _cache_reply_result(db, user_id, thread_id, False)
    return False


def _cache_reply_result(
    db: SupabaseClient,
    user_id: str,
    thread_id: str,
    replied: bool,
) -> None:
    """Cache the reply check result in email_scan_log.user_replied column.

    Stores the result so we don't re-check on every page load.
    NULL = not checked, True = user replied, False = user hasn't replied.
    """
    try:
        db.table("email_scan_log").update(
            {"user_replied": replied}
        ).eq("user_id", user_id).eq("thread_id", thread_id).execute()
    except Exception as e:
        # Non-critical — just means we'll re-check next time
        logger.debug(
            "REPLY_DETECTOR: Failed to cache reply result for thread %s: %s",
            thread_id,
            e,
        )


async def update_replied_emails(
    db: SupabaseClient,
    user_id: str,
) -> int:
    """Re-check all NEEDS_REPLY emails and downgrade to FYI if the user has replied.

    Catches cases where the user replied AFTER ARIA classified the email.
    Should run during each scan cycle.

    Only checks emails that haven't been checked yet (user_replied IS NULL)
    or were previously marked as not replied (user_replied = false).

    Args:
        db: Supabase client instance.
        user_id: The user's ID.

    Returns:
        Number of emails reclassified from NEEDS_REPLY to FYI.
    """
    reclassified = 0

    try:
        user_emails = await get_user_emails(db, user_id)
        if not user_emails:
            return 0

        # Get NEEDS_REPLY emails that haven't been confirmed as replied
        # Skip emails already cached as user_replied=true (already handled)
        needs_reply_emails = (
            db.table("email_scan_log")
            .select("id, thread_id, scanned_at")
            .eq("user_id", user_id)
            .eq("category", "NEEDS_REPLY")
            .execute()
        )

        if not needs_reply_emails.data:
            return 0

        for email_row in needs_reply_emails.data:
            thread_id = email_row.get("thread_id")
            if not thread_id:
                continue

            replied = await has_user_replied(
                db=db,
                user_id=user_id,
                thread_id=thread_id,
                email_timestamp=email_row.get("scanned_at"),
                user_emails=user_emails,
            )

            if replied:
                try:
                    db.table("email_scan_log").update(
                        {
                            "category": "FYI",
                            "urgency": "LOW",
                            "needs_draft": False,
                            "reason": "User has already replied to this thread",
                            "user_replied": True,
                        }
                    ).eq("id", email_row["id"]).execute()
                    reclassified += 1
                    logger.info(
                        "REPLY_DETECTOR: Reclassified email %s from NEEDS_REPLY to FYI "
                        "(thread %s, user %s)",
                        email_row["id"],
                        thread_id,
                        user_id,
                    )
                except Exception as e:
                    logger.warning(
                        "REPLY_DETECTOR: Failed to reclassify email %s: %s",
                        email_row["id"],
                        e,
                    )

    except Exception as e:
        logger.warning(
            "REPLY_DETECTOR: update_replied_emails failed for user %s: %s",
            user_id,
            e,
        )

    if reclassified > 0:
        logger.info(
            "REPLY_DETECTOR: Reclassified %d NEEDS_REPLY emails to FYI for user %s",
            reclassified,
            user_id,
        )

    return reclassified
