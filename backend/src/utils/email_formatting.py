"""Email formatting utilities for converting plain text to HTML."""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Automated/generic local parts that should not be parsed into names
_SKIP_LOCAL_PARTS = {
    "noreply", "no-reply", "no_reply", "donotreply",
    "do-not-reply", "do_not_reply", "mailer-daemon",
    "postmaster", "admin", "support", "info", "help",
    "notifications", "notification", "alerts", "alert",
    "news", "newsletter", "updates", "billing", "sales",
    "team", "hello", "contact", "feedback", "service",
}


def parse_name_from_email(email_address: str) -> str | None:
    """Derive a human-readable name from an email address.

    Examples:
        john.smith@company.com -> John Smith
        jane_doe@example.org  -> Jane Doe
        noreply@service.com   -> None (skip automated addresses)
    """
    if not email_address or "@" not in email_address:
        return None

    local = email_address.split("@")[0].lower()

    if local in _SKIP_LOCAL_PARTS:
        return None

    # Split on dots, hyphens, underscores
    parts = re.split(r"[._\-]+", local)

    # Filter out pure numbers and single chars
    name_parts = [p for p in parts if len(p) > 1 and not p.isdigit()]

    if not name_parts:
        return None

    return " ".join(p.capitalize() for p in name_parts)


async def resolve_recipient_name(
    db: Any,
    sender_name: str | None,
    recipient_email: str,
) -> str | None:
    """Resolve a recipient's display name from multiple sources.

    Fallback order:
    1. sender_name from the incoming email (primary source)
    2. email_scan_log: lookup by sender_email
    3. memory_semantic: lookup contact name by email
    4. Parse the email address: "john.smith@co.com" -> "John Smith"
    5. None if all fail

    Args:
        db: Supabase client instance.
        sender_name: Name from the incoming email (may be empty/None).
        recipient_email: The recipient's email address.

    Returns:
        Resolved name or None.
    """
    # 1. Primary: sender_name from the email being replied to
    if sender_name and sender_name.strip():
        return sender_name.strip()

    # 2. email_scan_log: find a known name for this email address
    try:
        result = (
            db.table("email_scan_log")
            .select("sender_name")
            .eq("sender_email", recipient_email)
            .neq("sender_name", "")
            .not_.is_("sender_name", "null")
            .order("scanned_at", desc=True)
            .limit(1)
            .execute()
        )
        if result.data and result.data[0].get("sender_name"):
            name = result.data[0]["sender_name"].strip()
            if name:
                logger.debug(
                    "resolve_recipient_name: from email_scan_log: %s -> %s",
                    recipient_email,
                    name,
                )
                return name
    except Exception as e:
        logger.debug("resolve_recipient_name: email_scan_log lookup failed: %s", e)

    # 3. memory_semantic: check if email is associated with a known contact
    try:
        result = (
            db.table("memory_semantic")
            .select("entity_name")
            .ilike("fact", f"%{recipient_email}%")
            .not_.is_("entity_name", "null")
            .limit(1)
            .execute()
        )
        if result.data and result.data[0].get("entity_name"):
            name = result.data[0]["entity_name"].strip()
            if name:
                logger.debug(
                    "resolve_recipient_name: from memory_semantic: %s -> %s",
                    recipient_email,
                    name,
                )
                return name
    except Exception as e:
        logger.debug("resolve_recipient_name: memory_semantic lookup failed: %s", e)

    # 4. Parse email address as last resort
    name = parse_name_from_email(recipient_email)
    if name:
        return name

    # 5. All sources exhausted
    return None


def plain_text_to_email_html(text: str) -> str:
    """Convert plain text email body to properly formatted HTML for email clients.

    This ensures emails look the same in Outlook/Gmail as they do in ARIA's UI.
    Email clients ignore \\n characters in plain text, so we must convert to HTML.

    Handles:
    - Paragraph breaks (\\n\\n → <p> tags with margin)
    - Single line breaks (\\n → <br>)
    - HTML entity escaping

    Args:
        text: Plain text email body with \\n line breaks

    Returns:
        Complete HTML document with styled paragraphs
    """
    import html

    if not text:
        return ""

    # Escape HTML entities first to prevent XSS
    text = html.escape(text)

    # Split into paragraphs (double newline)
    paragraphs = text.split("\n\n")

    # Convert each paragraph
    html_parts = []
    for para in paragraphs:
        if not para.strip():
            continue
        # Convert single newlines within a paragraph to <br>
        para_html = para.strip().replace("\n", "<br>")
        html_parts.append(
            f'<p style="margin: 0 0 16px 0; line-height: 1.5; font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Arial, sans-serif;">{para_html}</p>'
        )

    body_html = "\n".join(html_parts)

    # Wrap in a basic email HTML template
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
    font-size: 14px;
    color: #333333;
    line-height: 1.5;
    margin: 0;
    padding: 16px;
  }}
  p {{ margin: 0 0 16px 0; }}
</style>
</head>
<body>
{body_html}
</body>
</html>"""
