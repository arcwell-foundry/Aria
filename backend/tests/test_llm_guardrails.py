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
