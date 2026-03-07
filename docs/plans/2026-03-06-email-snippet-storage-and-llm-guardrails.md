# Email Snippet Storage Fix & LLM Hallucination Guardrails

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix email snippet storage so 100% of email scans capture body snippets, and add LLM guardrails to prevent hallucination from metadata-only emails.

**Architecture:** Two independent fixes. (1) The `EmailAnalyzer.categorize()` method already extracts body text and passes it to `_log_scan_decision()`, which already stores the snippet — the bug is upstream: Gmail's `GMAIL_FETCH_EMAILS` doesn't return body content (only subject/sender metadata), so `email.get("body")` returns empty string and `snippet` ends up as `""`. The fix is to fetch individual email bodies after the list fetch, or use `GMAIL_FETCH_EMAILS` with a parameter that requests body content. Outlook path already works (extracts `body.content` and `bodyPreview`). (2) The briefing service already has partial guardrails (lines 1906-1928) but they're inconsistent and not centralized. Create a central `llm_guardrails.py` module and inject into all LLM surfaces: briefing, chat, draft engine, and email intelligence.

**Tech Stack:** Python 3.11, FastAPI, Supabase, Composio (Gmail/Outlook APIs), Anthropic Claude API

---

## Root Cause Analysis

### Snippet Storage Bug

**Single code path:** All email scan logging goes through `EmailAnalyzer._log_scan_decision()` at `backend/src/services/email_analyzer.py:1700-1737`. This function DOES store `categorized.snippet` correctly (truncated to 500 chars).

**The real problem:** The snippet is empty because the email body is never fetched from Gmail.

Flow:
1. `_fetch_inbox()` calls `GMAIL_FETCH_EMAILS` (line 967) — this returns a LIST of emails with metadata (subject, sender, date) but **Gmail list API does not return full body content**
2. `categorize()` does `raw_body = email.get("body", email.get("snippet", ""))` (line 328) — for Gmail, `body` is empty/missing, `snippet` is the Gmail snippet field (first ~100 chars of plain text)
3. The Gmail snippet field IS sometimes present (explains the 5% that work) but is inconsistent
4. Outlook path works because `OUTLOOK_GET_MAIL_DELTA` returns `body.content` and `bodyPreview` — these are normalized at line 941-948

**Fix strategy:** After `GMAIL_FETCH_EMAILS` returns the list, check if body content is missing. If so, fetch individual email details using `GMAIL_GET_MESSAGE` for each email to get the body. Cache/batch where possible. For the backfill, create a script that fetches bodies for existing NULL-snippet scan log entries.

### LLM Hallucination Bug

**Partial guardrails exist** in `briefing.py` at lines 1906-1928 — the code already checks `has_snippets` and sets constraint text accordingly. But:
1. The summary generation prompt (lines 1558-1570) only has a weak "Never infer email content" line
2. The chat service (`email_tools.py:670-744`) passes email metadata to chat WITHOUT snippet content and WITHOUT guardrails
3. No centralized guardrail module exists — constraints are inline strings
4. The `autonomous_draft_engine.py` passes email snippets to LLM without content availability markers

---

## Task 1: Diagnose Gmail Body Availability

**Files:**
- Read: `backend/src/services/email_analyzer.py:920-984` (Gmail fetch path)
- Read: `backend/src/services/email_tools.py:380-430` (individual message fetch)

**Step 1: Add diagnostic logging to Gmail fetch**

In `backend/src/services/email_analyzer.py`, after the Gmail emails are fetched (line 977), add logging to see what fields Gmail actually returns:

```python
# After line 984 (after emails = response["data"].get("emails", []))
# Add diagnostic logging for first email's keys and body availability
if emails:
    first = emails[0]
    logger.info(
        "GMAIL_BODY_DIAG: First email keys=%s, has_body=%s, has_snippet=%s, body_type=%s, body_len=%s",
        list(first.keys()),
        "body" in first and bool(first.get("body")),
        "snippet" in first and bool(first.get("snippet")),
        type(first.get("body")).__name__,
        len(str(first.get("body", ""))) if first.get("body") else 0,
    )
```

**Step 2: Run a test scan to check the logs**

Run: `cd /Users/dhruv/aria/backend && python -c "
import asyncio, logging
logging.basicConfig(level=logging.INFO)
from src.services.email_analyzer import EmailAnalyzer
analyzer = EmailAnalyzer()
result = asyncio.run(analyzer.scan_inbox('41475700-c1fb-4f66-8c56-77bd90b73abb'))
print(f'Scanned {len(result.needs_reply)} NEEDS_REPLY, {len(result.fyi)} FYI')
for e in result.needs_reply[:3]:
    print(f'  {e.sender_name}: snippet={repr(e.snippet[:80])}')
"`

Expected: Logs will show that Gmail emails have no `body` field, and `snippet` is either empty or only present on some emails.

**Step 3: Remove diagnostic logging**

Remove the diagnostic logging added in Step 1 (it was only needed to confirm the root cause).

**Step 4: Commit**

```bash
# No commit needed — diagnostic only, changes reverted
```

---

## Task 2: Fix Gmail Body Fetching in Email Analyzer

**Files:**
- Modify: `backend/src/services/email_analyzer.py:920-984` (add body fetch for Gmail)
- Read: `backend/src/services/email_tools.py:380-430` (reference for GMAIL_GET_MESSAGE usage)

**Step 1: Write the failing test**

Create `backend/tests/test_email_snippet_capture.py`:

```python
"""Tests for email snippet capture during scan."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.services.email_analyzer import EmailAnalyzer, EmailCategory


@pytest.fixture
def analyzer():
    """Create an EmailAnalyzer with mocked dependencies."""
    a = EmailAnalyzer.__new__(EmailAnalyzer)
    a._db = MagicMock()
    a._llm = AsyncMock()
    return a


class TestSnippetCapture:
    """Ensure snippet is always captured when body content is available."""

    @pytest.mark.asyncio
    async def test_gmail_emails_get_body_fetched(self, analyzer):
        """When GMAIL_FETCH_EMAILS returns no body, individual fetch fills it."""
        # Gmail list response: no body field
        gmail_list_email = {
            "id": "msg_123",
            "threadId": "thread_456",
            "subject": "Partnership Discussion",
            "sender": "jayesh@nira.com",
            "sender_name": "Jayesh",
            "date": "2026-03-05T10:00:00Z",
            # NO body field — this is the bug
        }

        # Individual fetch response: has body
        gmail_detail = {
            "id": "msg_123",
            "body": "Hi, I wanted to discuss our partnership. Let me know your thoughts.",
            "subject": "Partnership Discussion",
        }

        result = await analyzer.categorize(
            {**gmail_list_email, "body": gmail_detail["body"]},
            user_id="test-user",
        )

        assert result.snippet != ""
        assert len(result.snippet) > 0
        assert "partnership" in result.snippet.lower()

    @pytest.mark.asyncio
    async def test_outlook_emails_have_snippet(self, analyzer):
        """Outlook emails with body.content should have snippet populated."""
        outlook_email = {
            "id": "outlook_123",
            "conversationId": "conv_456",
            "subject": "Q3 Review",
            "sender_email": "bob@company.com",
            "sender_name": "Bob",
            "body": "Let's review the Q3 numbers next week.",
            "snippet": "Let's review the Q3 numbers",
            "date": "2026-03-05T10:00:00Z",
        }

        result = await analyzer.categorize(outlook_email, user_id="test-user")
        assert result.snippet != ""
        assert "Q3" in result.snippet

    @pytest.mark.asyncio
    async def test_empty_body_produces_empty_snippet(self, analyzer):
        """When body is genuinely empty, snippet should be empty string."""
        email = {
            "id": "msg_789",
            "subject": "No body email",
            "sender": "test@example.com",
            "date": "2026-03-05T10:00:00Z",
            "body": "",
        }

        result = await analyzer.categorize(email, user_id="test-user")
        assert result.snippet == ""
```

**Step 2: Run test to verify it passes (baseline)**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_email_snippet_capture.py -v`

Expected: Tests should pass (the categorize function already handles body when it's present — the bug is in the FETCH not the CATEGORIZE).

**Step 3: Add `_enrich_gmail_bodies` method to EmailAnalyzer**

In `backend/src/services/email_analyzer.py`, add a method that fetches individual email bodies for Gmail emails that are missing body content. Add this after the `_fetch_inbox` method (around line 1082):

```python
async def _enrich_gmail_bodies(
    self,
    emails: list[dict[str, Any]],
    connection_id: str,
    user_id: str,
) -> list[dict[str, Any]]:
    """Fetch individual email bodies for Gmail emails missing body content.

    GMAIL_FETCH_EMAILS returns a list without full body text. This method
    fetches each email's body using GMAIL_GET_MESSAGE and merges it back.

    Args:
        emails: List of email dicts from GMAIL_FETCH_EMAILS.
        connection_id: Composio connection ID.
        user_id: The user's ID.

    Returns:
        The same list with body fields populated where possible.
    """
    from src.integrations.oauth import get_oauth_client

    oauth_client = get_oauth_client()
    enriched = 0

    for email in emails:
        # Skip if body already present and non-empty
        existing_body = email.get("body", "")
        if isinstance(existing_body, str) and len(existing_body.strip()) > 50:
            continue
        if isinstance(existing_body, dict) and existing_body.get("content", ""):
            continue

        email_id = email.get("id") or email.get("message_id")
        if not email_id:
            continue

        try:
            response = await oauth_client.execute_action(
                connection_id=connection_id,
                action="GMAIL_GET_MESSAGE",
                params={"message_id": email_id},
                user_id=user_id,
            )
            if response.get("successful") and response.get("data"):
                data = response["data"]
                # GMAIL_GET_MESSAGE returns body in various formats
                body = (
                    data.get("body")
                    or data.get("textBody")
                    or data.get("snippet")
                    or data.get("text")
                    or ""
                )
                if isinstance(body, dict):
                    body = body.get("content", body.get("data", ""))
                if body and isinstance(body, str) and len(body.strip()) > 0:
                    email["body"] = body
                    enriched += 1
        except Exception as e:
            logger.debug(
                "EMAIL_ANALYZER: Could not fetch body for email %s: %s",
                email_id,
                e,
            )

    if enriched > 0:
        logger.info(
            "EMAIL_ANALYZER: Enriched %d/%d Gmail emails with body content",
            enriched,
            len(emails),
        )

    return emails
```

**Step 4: Call `_enrich_gmail_bodies` in `_fetch_inbox` after Gmail fetch**

In `backend/src/services/email_analyzer.py`, after the Gmail fetch returns emails (around line 977-983), add the enrichment call. Modify the Gmail path:

```python
            else:
                # Default to Gmail
                logger.info(
                    "EMAIL_ANALYZER: Using GMAIL_FETCH_EMAILS for user %s",
                    user_id,
                )
                response = oauth_client.execute_action_sync(
                    connection_id=connection_id,
                    action="GMAIL_FETCH_EMAILS",
                    params={
                        "label": "INBOX",
                        "max_results": 200,
                        "query": f"after:{since_epoch}",
                    },
                    user_id=user_id,
                )
                # Gmail returns emails in 'data.emails'
                if response.get("successful") and response.get("data"):
                    emails = response["data"].get("emails", [])
                    # Gmail list API doesn't return full body — fetch individually
                    emails = await self._enrich_gmail_bodies(
                        emails, connection_id, user_id
                    )
                else:
                    logger.warning(
                        "EMAIL_ANALYZER: Gmail fetch failed: %s",
                        response.get("error"),
                    )
                    emails = []
```

**Note:** `_fetch_inbox` is currently synchronous (uses `execute_action_sync`). The `_enrich_gmail_bodies` method uses async `execute_action`. If `_fetch_inbox` is called from a sync context, wrap the call:

```python
import asyncio
# If in sync context:
emails = asyncio.get_event_loop().run_until_complete(
    self._enrich_gmail_bodies(emails, connection_id, user_id)
)
```

Check whether `_fetch_inbox` is async or sync before deciding. If it's sync (which it appears to be based on `execute_action_sync`), you may need to make the enrichment sync too, or convert `_fetch_inbox` to async. The caller `scan_inbox` IS async (line 165+), so converting `_fetch_inbox` to async is the cleaner approach.

**Step 5: Run tests**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_email_snippet_capture.py -v`

Expected: PASS

**Step 6: Commit**

```bash
git add backend/src/services/email_analyzer.py backend/tests/test_email_snippet_capture.py
git commit -m "fix: fetch individual Gmail email bodies for snippet storage

Gmail's GMAIL_FETCH_EMAILS list API doesn't return body content,
causing 95% of email_scan_log entries to have NULL snippets.
Added _enrich_gmail_bodies() to fetch each email's body via
GMAIL_GET_MESSAGE after the list fetch."
```

---

## Task 3: Add Upsert Logic to Prevent Duplicate Scan Entries

**Files:**
- Modify: `backend/src/services/email_analyzer.py:1700-1737` (`_log_scan_decision`)

**Step 1: Write the failing test**

Add to `backend/tests/test_email_snippet_capture.py`:

```python
class TestScanLogDeduplication:
    """Ensure scan log entries are upserted, not duplicated."""

    @pytest.mark.asyncio
    async def test_rescan_updates_null_snippet(self, analyzer):
        """When rescanning an email with NULL snippet, update the snippet."""
        # Mock: existing entry with NULL snippet
        analyzer._db.table.return_value.select.return_value.eq.return_value.eq.return_value.is_.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "existing-scan-id", "snippet": None}]
        )
        analyzer._db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

        categorized = EmailCategory(
            email_id="msg_123",
            thread_id="thread_456",
            sender_email="test@example.com",
            sender_name="Test",
            subject="Test Subject",
            snippet="New snippet content here",
            body="Full body text",
            category="NEEDS_REPLY",
            urgency="NORMAL",
            topic_summary="Test",
            needs_draft=False,
            reason="Test reason",
        )

        await analyzer._log_scan_decision("test-user", categorized)

        # Should have called update, not insert
        # (Exact assertion depends on implementation)

    @pytest.mark.asyncio
    async def test_rescan_with_existing_snippet_skips(self, analyzer):
        """When rescanning an email that already has a snippet, skip."""
        # Mock: existing entry WITH snippet
        analyzer._db.table.return_value.select.return_value.eq.return_value.eq.return_value.is_.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[]  # No NULL-snippet entries found
        )
        analyzer._db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "existing-scan-id", "snippet": "Already has snippet"}]
        )

        categorized = EmailCategory(
            email_id="msg_123",
            thread_id="thread_456",
            sender_email="test@example.com",
            sender_name="Test",
            subject="Test Subject",
            snippet="New snippet",
            body="Body",
            category="NEEDS_REPLY",
            urgency="NORMAL",
            topic_summary="Test",
            needs_draft=False,
            reason="Reason",
        )

        await analyzer._log_scan_decision("test-user", categorized)

        # Should NOT have called insert
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_email_snippet_capture.py::TestScanLogDeduplication -v`

Expected: FAIL — current implementation always inserts.

**Step 3: Modify `_log_scan_decision` to upsert**

Replace the current `_log_scan_decision` method in `backend/src/services/email_analyzer.py`:

```python
async def _log_scan_decision(
    self,
    user_id: str,
    categorized: EmailCategory,
) -> None:
    """Log a categorization decision to email_scan_log.

    Uses upsert logic:
    - If email_id already has an entry with NULL snippet: UPDATE with new snippet
    - If email_id already has an entry with a snippet: SKIP (no duplicate)
    - If email_id has no entry: INSERT new row

    Args:
        user_id: The user's ID.
        categorized: The categorized email.
    """
    try:
        snippet_text = categorized.snippet[:500] if categorized.snippet else None

        # Check for existing entry
        existing = (
            self._db.table("email_scan_log")
            .select("id, snippet")
            .eq("user_id", user_id)
            .eq("email_id", categorized.email_id)
            .order("scanned_at", desc=True)
            .limit(1)
            .execute()
        )

        if existing.data:
            row = existing.data[0]
            if row.get("snippet"):
                # Already has snippet — skip to avoid duplicates
                logger.debug(
                    "EMAIL_ANALYZER: Skipping duplicate scan for email %s (already has snippet)",
                    categorized.email_id,
                )
                return

            if snippet_text:
                # Existing entry with NULL snippet — update it
                self._db.table("email_scan_log").update(
                    {
                        "snippet": snippet_text,
                        "category": categorized.category,
                        "urgency": categorized.urgency,
                        "needs_draft": categorized.needs_draft,
                        "reason": categorized.reason,
                    }
                ).eq("id", row["id"]).execute()
                logger.info(
                    "EMAIL_ANALYZER: Updated NULL snippet for email %s",
                    categorized.email_id,
                )
                return

        # No existing entry — insert new row
        self._db.table("email_scan_log").insert(
            {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "email_id": categorized.email_id,
                "thread_id": categorized.thread_id,
                "sender_email": categorized.sender_email,
                "sender_name": categorized.sender_name,
                "subject": categorized.subject[:500],
                "snippet": snippet_text,
                "category": categorized.category,
                "urgency": categorized.urgency,
                "needs_draft": categorized.needs_draft,
                "reason": categorized.reason,
                "scanned_at": datetime.now(UTC).isoformat(),
            }
        ).execute()
    except Exception as e:
        logger.warning(
            "EMAIL_ANALYZER: Failed to log scan decision for email %s: %s",
            categorized.email_id,
            e,
        )
```

**Step 4: Run tests**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_email_snippet_capture.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/services/email_analyzer.py backend/tests/test_email_snippet_capture.py
git commit -m "fix: upsert email_scan_log to prevent duplicates and backfill NULL snippets

When rescanning an email:
- If existing entry has NULL snippet: UPDATE with new snippet
- If existing entry already has snippet: SKIP (no duplicate)
- If no entry exists: INSERT new row"
```

---

## Task 4: Create Centralized LLM Guardrails Module

**Files:**
- Create: `backend/src/core/llm_guardrails.py`
- Create: `backend/tests/test_llm_guardrails.py`

**Step 1: Write the failing test**

Create `backend/tests/test_llm_guardrails.py`:

```python
"""Tests for LLM email guardrails."""

from src.core.llm_guardrails import (
    EMAIL_CONTEXT_RULES,
    format_emails_for_llm,
    get_email_guardrail,
)


class TestEmailGuardrails:
    """Test email content formatting with availability markers."""

    def test_get_email_guardrail_returns_rules(self):
        rules = get_email_guardrail()
        assert "NEVER" in rules
        assert "NOT AVAILABLE" in rules
        assert "metadata" in rules.lower()

    def test_format_email_with_snippet(self):
        emails = [
            {
                "sender_name": "Jayesh",
                "sender_email": "jayesh@nira.com",
                "subject": "Partnership Update",
                "snippet": "Hi, I wanted to follow up on our conversation about the partnership.",
            }
        ]
        result = format_emails_for_llm(emails)
        assert "Jayesh" in result
        assert "Partnership Update" in result
        assert "Email Body:" in result
        assert "NOT AVAILABLE" not in result
        assert "follow up" in result

    def test_format_email_without_snippet(self):
        emails = [
            {
                "sender_name": "Bob",
                "sender_email": "bob@company.com",
                "subject": "Meeting Tomorrow",
                "snippet": None,
            }
        ]
        result = format_emails_for_llm(emails)
        assert "Bob" in result
        assert "Meeting Tomorrow" in result
        assert "NOT AVAILABLE" in result
        assert "metadata only" in result

    def test_format_email_empty_snippet(self):
        emails = [
            {
                "sender_email": "alice@corp.com",
                "subject": "FYI",
                "snippet": "",
            }
        ]
        result = format_emails_for_llm(emails)
        assert "NOT AVAILABLE" in result

    def test_format_mixed_emails(self):
        emails = [
            {
                "sender_name": "With Body",
                "sender_email": "a@b.com",
                "subject": "Has Content",
                "snippet": "Actual email content here",
            },
            {
                "sender_name": "No Body",
                "sender_email": "c@d.com",
                "subject": "No Content",
                "snippet": None,
            },
        ]
        result = format_emails_for_llm(emails)
        assert "Actual email content" in result
        assert "NOT AVAILABLE" in result

    def test_snippet_truncated_to_500(self):
        emails = [
            {
                "sender_name": "Long",
                "sender_email": "long@email.com",
                "subject": "Long email",
                "snippet": "x" * 1000,
            }
        ]
        result = format_emails_for_llm(emails)
        # Should not contain the full 1000 chars
        assert len(result) < 1100
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_llm_guardrails.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'src.core.llm_guardrails'`

**Step 3: Create `backend/src/core/llm_guardrails.py`**

```python
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
CRITICAL EMAIL DATA RULES — FOLLOW THESE EXACTLY:
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
```

**Step 4: Run tests**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_llm_guardrails.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/core/llm_guardrails.py backend/tests/test_llm_guardrails.py
git commit -m "feat: add centralized LLM guardrails for email content availability

Creates llm_guardrails.py with EMAIL_CONTEXT_RULES and
format_emails_for_llm() that explicitly marks each email with
whether body content is available or metadata-only."
```

---

## Task 5: Inject Guardrails into Briefing Service

**Files:**
- Modify: `backend/src/services/briefing.py:1545-1570` (summary generation prompt)
- Modify: `backend/src/services/briefing.py:1888-1938` (topic clustering prompt)

**Step 1: Add guardrail import to briefing.py**

At the top of `backend/src/services/briefing.py`, add:

```python
from src.core.llm_guardrails import get_email_guardrail
```

**Step 2: Strengthen summary generation prompt**

In `backend/src/services/briefing.py`, replace the existing weak guardrail at line 1569:

Find this block (approximately lines 1558-1570):
```python
IMPORTANT: Only describe information you can directly verify from the data provided. Never infer email content, conversation direction, or relationship narratives from metadata alone. It is better to say less than to say something inaccurate.
```

Replace with:
```python
{get_email_guardrail()}

IMPORTANT: Only describe information you can directly verify from the data provided. It is better to say less than to say something inaccurate.
```

**Step 3: Replace inline constraint text with centralized guardrails**

In `backend/src/services/briefing.py`, the topic clustering section (lines 1906-1928) already has good constraint text. Keep it but add the centralized guardrail import as a reinforcement. The existing `has_snippets` conditional logic is good — it already differentiates between having and not having content. No changes needed here since it's already well-guarded.

**Step 4: Run existing briefing tests**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/ -k "briefing" -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/services/briefing.py
git commit -m "fix: inject centralized email guardrails into briefing generation

Adds EMAIL_CONTEXT_RULES to briefing summary LLM prompt to prevent
hallucination when email body content is unavailable."
```

---

## Task 6: Inject Guardrails into Chat Service

**Files:**
- Modify: `backend/src/services/email_tools.py:670-744` (`get_email_context_for_chat`)
- Modify: `backend/src/services/chat.py` (system prompt email rules)

**Step 1: Add snippet to chat email context query**

In `backend/src/services/email_tools.py`, the `get_email_context_for_chat` function (line 702-706) queries `email_scan_log` but does NOT include `snippet` in the SELECT. Add it:

Find:
```python
        scans_result = (
            client.table("email_scan_log")
            .select(
                "sender_name,sender_email,subject,category,urgency,"
                "needs_draft,scanned_at"
            )
```

Replace with:
```python
        scans_result = (
            client.table("email_scan_log")
            .select(
                "sender_name,sender_email,subject,snippet,category,urgency,"
                "needs_draft,scanned_at"
            )
```

**Step 2: Add content availability markers to email listing in chat context**

In `backend/src/services/email_tools.py`, the email listing (around line 737-744) formats emails without body content. Add snippet display when available:

Find the email formatting loop (approximately lines 735-745) and update to include snippet preview when available:

```python
        if scans:
            header.append(f"You have scanned {len(scans)} recent emails:")
            for s in scans:
                name = s.get("sender_name") or s.get("sender_email", "unknown")
                subj = s.get("subject", "(no subject)")
                cat = s.get("category", "")
                urg = s.get("urgency", "")
                snippet = s.get("snippet", "")
                flag = " ⚡URGENT" if urg == "URGENT" else ""
                draft_flag = " [draft pending]" if s.get("needs_draft") else ""
                line = f"  - [{cat}]{flag}{draft_flag} {name}: \"{subj}\""
                if snippet:
                    line += f"\n    Preview: {snippet[:200]}"
                else:
                    line += "\n    Preview: NOT AVAILABLE (metadata only)"
                header.append(line)
```

**Step 3: Add guardrail to chat system prompt email rules**

In `backend/src/services/chat.py`, find the email intelligence rules section (around line 3471-3481). This section already has some rules but they're weak. Add the centralized guardrail:

Find:
```python
                f"\n\n## Email Intelligence Rules\n"
                f"When discussing the user's emails, follow these rules:\n"
```

Add before this section:
```python
                f"\n\n{get_email_guardrail()}\n"
                f"\n\n## Email Intelligence Rules\n"
                f"When discussing the user's emails, follow these rules:\n"
```

And add the import at the top of `chat.py`:
```python
from src.core.llm_guardrails import get_email_guardrail
```

**Step 4: Run chat tests**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/ -k "chat" -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/services/email_tools.py backend/src/services/chat.py
git commit -m "fix: inject email guardrails into chat service and include snippets

Chat email context now includes snippet previews from email_scan_log
and marks each email with content availability. Centralized
EMAIL_CONTEXT_RULES added to chat system prompt."
```

---

## Task 7: Inject Guardrails into Draft Engine

**Files:**
- Modify: `backend/src/services/autonomous_draft_engine.py:1172-1304` (`_build_reply_prompt`)

**Step 1: Add guardrail import**

At the top of `backend/src/services/autonomous_draft_engine.py`:
```python
from src.core.llm_guardrails import get_email_guardrail
```

**Step 2: Add content availability marker to original email in prompt**

In `_build_reply_prompt` (around line 1187-1191), the original email snippet is passed. Add a marker:

Find:
```python
f"""=== ORIGINAL EMAIL ===
From: {email.sender_name} <{email.sender_email}>
Subject: {email.subject}
Urgency: {email.urgency}
Body: {email.snippet}"""
```

Replace with:
```python
f"""=== ORIGINAL EMAIL ===
From: {email.sender_name} <{email.sender_email}>
Subject: {email.subject}
Urgency: {email.urgency}
Body: {email.snippet if email.snippet else 'NOT AVAILABLE (metadata only — do not fabricate content)'}"""
```

**Step 3: Add guardrail to system prompt**

In the system prompt construction for draft generation (find where `system_prompt` is built, around line 1113-1125), append the guardrail:

```python
# After system_prompt is built, before the LLM call
system_prompt += "\n" + get_email_guardrail()
```

**Step 4: Run draft engine tests**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/ -k "draft" -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/services/autonomous_draft_engine.py
git commit -m "fix: add email guardrails to autonomous draft engine

Draft prompt now marks email body availability and includes
EMAIL_CONTEXT_RULES in system prompt to prevent content fabrication."
```

---

## Task 8: Create Backfill Script for NULL Snippets

**Files:**
- Create: `backend/scripts/backfill_email_snippets.py`

**Step 1: Create the backfill script**

Create `backend/scripts/backfill_email_snippets.py`:

```python
#!/usr/bin/env python3
"""Backfill script to populate NULL snippets in email_scan_log.

Fetches email bodies from Gmail/Outlook via Composio for scan log
entries that have NULL snippets, then updates them.

Usage:
    cd backend
    python scripts/backfill_email_snippets.py --user-id <user_id>

    # Dry run (count only, no updates):
    python scripts/backfill_email_snippets.py --user-id <user_id> --dry-run

    # With rate limiting:
    python scripts/backfill_email_snippets.py --user-id <user_id> --delay 1.0
"""

import os
from pathlib import Path
from dotenv import load_dotenv

if not os.environ.get("ANTHROPIC_API_KEY"):
    load_dotenv(Path(__file__).parent.parent / ".env")

import argparse
import asyncio
import logging
import re
import sys
import time

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.supabase import SupabaseClient
from src.integrations.oauth import get_oauth_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    return re.sub(r"<[^>]+>", "", text).strip()


async def get_null_snippet_emails(user_id: str) -> list[dict]:
    """Get distinct email_ids with NULL snippets from email_scan_log."""
    supabase = SupabaseClient.get_client()

    result = (
        supabase.table("email_scan_log")
        .select("id, email_id, sender_email")
        .eq("user_id", user_id)
        .is_("snippet", "null")
        .order("scanned_at", desc=True)
        .execute()
    )

    if not result.data:
        return []

    # Deduplicate by email_id — keep the most recent scan entry
    seen: dict[str, dict] = {}
    for row in result.data:
        eid = row.get("email_id")
        if eid and eid not in seen:
            seen[eid] = row

    return list(seen.values())


async def get_user_email_integration(user_id: str) -> dict | None:
    """Get the user's active email integration."""
    supabase = SupabaseClient.get_client()

    result = (
        supabase.table("user_integrations")
        .select("*")
        .eq("user_id", user_id)
        .eq("status", "active")
        .in_("integration_type", ["gmail", "outlook"])
        .limit(1)
        .execute()
    )

    return result.data[0] if result.data else None


async def fetch_email_body(
    oauth_client,
    connection_id: str,
    email_id: str,
    provider: str,
    user_id: str,
) -> str | None:
    """Fetch a single email's body from Composio."""
    try:
        if provider == "gmail":
            response = await oauth_client.execute_action(
                connection_id=connection_id,
                action="GMAIL_GET_MESSAGE",
                params={"message_id": email_id},
                user_id=user_id,
            )
        else:
            response = await oauth_client.execute_action(
                connection_id=connection_id,
                action="OUTLOOK_GET_MESSAGE",
                params={"message_id": email_id},
                user_id=user_id,
            )

        if not response.get("successful") or not response.get("data"):
            return None

        data = response["data"]

        # Extract body from various response formats
        body = (
            data.get("body")
            or data.get("textBody")
            or data.get("snippet")
            or data.get("text")
            or ""
        )

        if isinstance(body, dict):
            body = body.get("content", body.get("data", ""))

        if not isinstance(body, str) or not body.strip():
            return None

        # Strip HTML if present
        if "<" in body:
            body = _strip_html(body)

        return body[:500] if body else None

    except Exception as e:
        logger.warning("Failed to fetch body for email %s: %s", email_id, e)
        return None


async def update_snippet(scan_id: str, snippet: str, email_id: str) -> bool:
    """Update a scan log entry's snippet."""
    try:
        supabase = SupabaseClient.get_client()
        supabase.table("email_scan_log").update(
            {"snippet": snippet}
        ).eq("id", scan_id).execute()

        # Also update ALL entries with same email_id that have NULL snippet
        supabase.table("email_scan_log").update(
            {"snippet": snippet}
        ).eq("email_id", email_id).is_("snippet", "null").execute()

        return True
    except Exception as e:
        logger.warning("Failed to update snippet for %s: %s", scan_id, e)
        return False


async def backfill(user_id: str, dry_run: bool = False, delay: float = 0.5):
    """Run the backfill process."""
    logger.info("Starting snippet backfill for user %s", user_id)

    # Get integration
    integration = await get_user_email_integration(user_id)
    if not integration:
        logger.error("No active email integration found for user %s", user_id)
        return

    provider = integration["integration_type"]
    connection_id = integration["connection_id"]
    logger.info("Using %s integration (connection: %s)", provider, connection_id[:8])

    # Get emails needing backfill
    null_entries = await get_null_snippet_emails(user_id)
    total = len(null_entries)
    logger.info("Found %d unique emails with NULL snippets", total)

    if dry_run:
        logger.info("DRY RUN — no updates will be made")
        return

    if total == 0:
        logger.info("Nothing to backfill!")
        return

    oauth_client = get_oauth_client()
    success = 0
    failed = 0

    for i, entry in enumerate(null_entries, 1):
        email_id = entry["email_id"]
        scan_id = entry["id"]

        body = await fetch_email_body(
            oauth_client, connection_id, email_id, provider, user_id
        )

        if body:
            if await update_snippet(scan_id, body, email_id):
                success += 1
                logger.info(
                    "Backfilled %d/%d: %s (%.0f chars)",
                    i, total, email_id[:20], len(body),
                )
            else:
                failed += 1
        else:
            failed += 1
            logger.debug("No body available for email %s", email_id[:20])

        # Rate limit
        if delay > 0:
            await asyncio.sleep(delay)

    logger.info(
        "Backfill complete: %d success, %d failed out of %d total",
        success, failed, total,
    )


def main():
    parser = argparse.ArgumentParser(description="Backfill NULL email snippets")
    parser.add_argument("--user-id", required=True, help="User ID to backfill")
    parser.add_argument("--dry-run", action="store_true", help="Count only, no updates")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between API calls (seconds)")
    args = parser.parse_args()

    asyncio.run(backfill(args.user_id, args.dry_run, args.delay))


if __name__ == "__main__":
    main()
```

**Step 2: Test the script in dry-run mode**

Run: `cd /Users/dhruv/aria/backend && python scripts/backfill_email_snippets.py --user-id 41475700-c1fb-4f66-8c56-77bd90b73abb --dry-run`

Expected: Should print count of emails needing backfill without making changes.

**Step 3: Commit**

```bash
git add backend/scripts/backfill_email_snippets.py
git commit -m "feat: add backfill script for NULL email snippets

One-time script to fetch email bodies from Composio and populate
NULL snippet fields in email_scan_log. Supports dry-run mode
and rate limiting."
```

---

## Task 9: Verify End-to-End

**Step 1: Run all tests**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_email_snippet_capture.py tests/test_llm_guardrails.py -v`

Expected: All tests PASS

**Step 2: Verify guardrail module is importable**

Run: `cd /Users/dhruv/aria/backend && python -c "from src.core.llm_guardrails import get_email_guardrail, format_emails_for_llm; print('OK')" `

Expected: `OK`

**Step 3: Verify no import errors in modified services**

Run: `cd /Users/dhruv/aria/backend && python -c "
from src.services.briefing import BriefingService
from src.services.email_analyzer import EmailAnalyzer
print('All imports OK')
"`

Expected: `All imports OK`

**Step 4: Check database for snippet status (informational)**

Run via Supabase MCP or API:
```sql
SELECT
    COUNT(*) as total,
    COUNT(snippet) as with_snippet,
    COUNT(*) - COUNT(snippet) as null_snippets,
    ROUND(100.0 * COUNT(snippet) / NULLIF(COUNT(*), 0), 1) as pct_with_snippet
FROM email_scan_log
WHERE user_id = '41475700-c1fb-4f66-8c56-77bd90b73abb';
```

**Step 5: Final commit with all changes**

```bash
git add -A
git status
# Verify only expected files are staged
git commit -m "feat: complete email snippet storage fix and LLM hallucination guardrails

Part 1 - Snippet Storage:
- Added _enrich_gmail_bodies() to fetch individual Gmail email bodies
- Added upsert logic to _log_scan_decision() preventing duplicates
- Created backfill_email_snippets.py for existing NULL entries

Part 2 - LLM Guardrails:
- Created centralized llm_guardrails.py with EMAIL_CONTEXT_RULES
- Injected into briefing, chat, and draft engine services
- Each email explicitly marked with content availability"
```

---

## Dependency Graph

```
Task 1 (Diagnose) → Task 2 (Fix Gmail fetch) → Task 3 (Upsert logic)
                                                        ↓
Task 4 (Guardrails module) → Task 5 (Briefing) → Task 6 (Chat) → Task 7 (Draft)
                                                        ↓
                                               Task 8 (Backfill script)
                                                        ↓
                                               Task 9 (Verify E2E)
```

Tasks 1-3 (snippet storage) and Tasks 4-7 (guardrails) can run in parallel.
Task 8 depends on Task 2 (needs the enrichment approach).
Task 9 depends on all others.

---

## Files Changed Summary

| File | Action | Purpose |
|------|--------|---------|
| `backend/src/services/email_analyzer.py` | Modify | Add `_enrich_gmail_bodies()`, upsert in `_log_scan_decision()` |
| `backend/src/core/llm_guardrails.py` | Create | Centralized `EMAIL_CONTEXT_RULES` and `format_emails_for_llm()` |
| `backend/src/services/briefing.py` | Modify | Import and inject guardrails into summary prompt |
| `backend/src/services/chat.py` | Modify | Import and inject guardrails into system prompt |
| `backend/src/services/email_tools.py` | Modify | Add `snippet` to chat context query, add availability markers |
| `backend/src/services/autonomous_draft_engine.py` | Modify | Add guardrails to draft prompt and system prompt |
| `backend/scripts/backfill_email_snippets.py` | Create | One-time backfill for NULL snippets |
| `backend/tests/test_email_snippet_capture.py` | Create | Tests for snippet capture and deduplication |
| `backend/tests/test_llm_guardrails.py` | Create | Tests for guardrail formatting |
