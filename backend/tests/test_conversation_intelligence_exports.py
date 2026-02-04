"""Tests for conversation intelligence module exports."""


class TestConversationIntelligenceExports:
    """Tests for module exports."""

    def test_insight_exported(self):
        """Test that Insight is exported from memory module."""
        from src.memory import Insight

        assert Insight is not None

    def test_conversation_intelligence_exported(self):
        """Test that ConversationIntelligence is exported from memory module."""
        from src.memory import ConversationIntelligence

        assert ConversationIntelligence is not None
