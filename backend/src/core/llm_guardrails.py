"""Centralized LLM guardrails for email data handling.

Prevents hallucination by explicitly marking email content availability
when passing email data to LLM prompts. Every LLM surface that references
email data MUST use these guardrails.

Usage:
    from src.core.llm_guardrails import get_email_guardrail, format_emails_for_llm

    # In system prompt:
    system_prompt += get_email_guardrail()

    # When passing email data:
    email_text = format_emails_for_llm(email_list)
"""

from __future__ import annotations

import re
from typing import Any


EMAIL_CONTEXT_RULES = """
CRITICAL EMAIL DATA RULES - FOLLOW THESE EXACTLY:
- You may have email METADATA (sender name, email address, subject line, count, classification).
- You may or may NOT have email body content. Check each email entry below.
- If an email entry says "Email Body: NOT AVAILABLE" or has no body content, you MUST NOT:
  - Infer what the conversation is about
  - Describe the nature, intent, or direction of the thread
  - Use phrases like "moving toward", "discussing", "negotiating", "exploring", "indicating"
  - Fabricate relationship narratives or deal progress
- If you DO have email body content provided, you CAN summarize and reference it.
- For metadata-only emails, state ONLY factual information: sender name, company, email count, subject lines.
- NEVER make up what an email says. If you don't have the body, say so or stay silent about the content.
"""


FORMATTING_RULES = """
FORMATTING RULES:
- Never use em dashes (the long — character) or en dashes. Use regular dashes (-), commas, or periods instead.
- Keep sentences concise and direct.
"""


def get_formatting_rules() -> str:
    """Return formatting rules string for injection into LLM prompts."""
    return FORMATTING_RULES


def get_email_guardrail() -> str:
    """Return the email context rules string for injection into LLM prompts."""
    return EMAIL_CONTEXT_RULES


def _strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    return re.sub(r"<[^>]+>", "", text).strip()


def format_emails_for_llm(emails: list[dict[str, Any]]) -> str:
    """Format email data for LLM with explicit content availability markers.

    Each email is clearly marked with whether body content is available,
    preventing the LLM from inventing content for metadata-only emails.

    Args:
        emails: List of email dicts with keys like sender_name, sender_email,
                subject, snippet/body/bodyPreview.

    Returns:
        Formatted string with content availability markers per email.
    """
    lines: list[str] = []
    for email in emails:
        snippet = (
            email.get("snippet")
            or email.get("body")
            or email.get("bodyPreview")
            or ""
        )
        if isinstance(snippet, dict):
            snippet = snippet.get("content", "")
        if not isinstance(snippet, str):
            snippet = ""
        snippet = snippet.strip()

        # Strip HTML if present
        if snippet and "<" in snippet:
            snippet = _strip_html(snippet)

        sender = email.get("sender_name") or email.get("sender_email", "Unknown")
        subject = email.get("subject", "No subject")

        if snippet and len(snippet) > 0:
            lines.append(
                f"- From: {sender}\n"
                f"  Subject: {subject}\n"
                f"  Email Body: {snippet[:500]}"
            )
        else:
            lines.append(
                f"- From: {sender}\n"
                f"  Subject: {subject}\n"
                f"  Email Body: NOT AVAILABLE (metadata only)"
            )

    return "\n".join(lines)
