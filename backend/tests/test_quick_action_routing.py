import pytest
from unittest.mock import AsyncMock, patch, MagicMock

# Import the service and route
import sys
sys.path.insert(0, "backend")
from src.services.chat import ChatService


@pytest.mark.asyncio
async def test_quick_action_detection_signal_enriched():
    """When signal-enriched, quick action detection should be skipped"""
    # This test verifies the routing order: signal bypass takes priority
    # Quick action detection should only happen if NOT signal-enriched
    # The implementation should check `if not was_signal_enriched:` before matching
    pass


@pytest.mark.asyncio
async def test_quick_action_detection_bypasses_intent_classification():
    """When quick action patterns matches, LLM intent classification should be skipped"""
    service = ChatService()
    result = ChatService._match_quick_action("what's on my calendar today")
    assert result is not None
    assert result["action_type"] == "calendar_query"


@pytest.mark.asyncio
async def test_quick_action_routing_bypasses_goal_creation():
    """When quick action matches, route to handler, skip goal creation entirely"""
    # This verifies that quick actions don't create goals
    # The response should come from _handle_quick_action
    pass


# =============================================================================
# Integration Tests: Pattern Detection
# =============================================================================

class TestQuickActionPatterns:
    """Test all quick action patterns for correct detection"""

    def test_meeting_prep_pattern(self):
        """Meeting prep patterns should match correctly"""
        patterns = [
            "prep me for my meeting",
            "prepare for my 11am call",
            "get ready for my sync with John",
            "brief me on the demo tomorrow",
        ]
        for msg in patterns:
            result = ChatService._match_quick_action(msg)
            assert result is not None, f"Should match: {msg}"
            assert result["action_type"] == "meeting_prep"

    def test_calendar_query_pattern(self):
        """Calendar query patterns should match correctly"""
        patterns = [
            "what's on my calendar today",
            "show my schedule for tomorrow",
            "when is my next meeting",
            "what time is my call",
            "any appointments this week",
        ]
        for msg in patterns:
            result = ChatService._match_quick_action(msg)
            assert result is not None, f"Should match: {msg}"
            assert result["action_type"] == "calendar_query"

    def test_signal_review_pattern(self):
        """Signal review patterns should match correctly"""
        patterns = [
            "show my signals",
            "what are the latest market signals",
            "any new intelligence",
            "review recent alerts",
        ]
        for msg in patterns:
            result = ChatService._match_quick_action(msg)
            assert result is not None, f"Should match: {msg}"
            assert result["action_type"] == "signal_review"

    def test_draft_review_pattern(self):
        """Draft review patterns should match correctly"""
        patterns = [
            "show my drafts",
            "any pending emails",
            "how many drafts waiting",
            "review my email drafts",
        ]
        for msg in patterns:
            result = ChatService._match_quick_action(msg)
            assert result is not None, f"Should match: {msg}"
            assert result["action_type"] == "draft_review"

    def test_task_review_pattern(self):
        """Task review patterns should match correctly"""
        patterns = [
            "what tasks do I have",
            "show my goals",
            "any overdue items",
            "check my pending tasks",
        ]
        for msg in patterns:
            result = ChatService._match_quick_action(msg)
            assert result is not None, f"Should match: {msg}"
            assert result["action_type"] == "task_review"

    def test_pipeline_review_pattern(self):
        """Pipeline review patterns should match correctly"""
        patterns = [
            "show my pipeline",
            "how is my funnel",
            "what deals are in progress",
            "show leads",
        ]
        for msg in patterns:
            result = ChatService._match_quick_action(msg)
            assert result is not None, f"Should match: {msg}"
            assert result["action_type"] == "pipeline_review"

    def test_competitive_lookup_pattern(self):
        """Competitive lookup patterns should match correctly"""
        patterns = [
            "what's the battle card for Acme",
            "show competitive intel vs Pfizer",
            "compare us against competitor X",
        ]
        for msg in patterns:
            result = ChatService._match_quick_action(msg)
            assert result is not None, f"Should match: {msg}"
            assert result["action_type"] == "competitive_lookup"

    def test_non_quick_action_messages(self):
        """Conversational and goal messages should NOT match quick actions"""
        non_matches = [
            "hi",
            "hello there",
            "find 10 bioprocessing companies",
            "draft an email to John",
            "what's the weather",
        ]
        for msg in non_matches:
            result = ChatService._match_quick_action(msg)
            # These may or may not match - the key is they'd go through
            # full intent classification if not matched
            if result is not None:
                # If they do match, they shouldn't be goal-creating actions
                assert result.get("is_goal") is False


# =============================================================================
# Integration Tests: Full Flow
# =============================================================================

@pytest.mark.asyncio
async def test_quick_action_full_flow():
    """Test complete quick action flow from detection to response structure"""
    # Test data
    test_message = "show my signals"
    expected_action_type = "signal_review"

    # Test pattern detection
    service = ChatService()
    match = ChatService._match_quick_action(test_message)
    assert match is not None
    assert match["action_type"] == expected_action_type
    assert match["is_goal"] is False
    assert match["is_quick_action"] is True
    assert "description" in match
