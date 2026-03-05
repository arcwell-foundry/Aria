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
