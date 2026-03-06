"""Tests for email snippet capture during scan."""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.services.email_analyzer import EmailAnalyzer, EmailCategory


# Standard LLM classification response for mocking
_LLM_FYI_RESPONSE = json.dumps({
    "category": "FYI",
    "urgency": "LOW",
    "topic_summary": "General discussion",
    "needs_draft": False,
    "reason": "Informational email, no action required",
})


@pytest.fixture
def analyzer():
    """Create an EmailAnalyzer with mocked dependencies."""
    a = EmailAnalyzer.__new__(EmailAnalyzer)
    a._db = MagicMock()
    a._llm = AsyncMock()
    # Mock generate_response to return a valid JSON classification string
    a._llm.generate_response = AsyncMock(return_value=_LLM_FYI_RESPONSE)
    # Mock async helper methods called inside categorize_email
    a._load_exclusions = AsyncMock(return_value=[])
    a._get_user_email = AsyncMock(return_value=None)
    a._is_self_sent = AsyncMock(return_value=False)
    a._lookup_sender_relationship = AsyncMock(return_value=None)
    a.detect_urgency = AsyncMock(return_value="LOW")
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

        result = await analyzer.categorize_email(
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

        result = await analyzer.categorize_email(outlook_email, user_id="test-user")
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

        result = await analyzer.categorize_email(email, user_id="test-user")
        assert result.snippet == ""
