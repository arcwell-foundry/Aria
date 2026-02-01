"""Tests for working memory module."""

from src.memory.working import WorkingMemory


def test_working_memory_initialization() -> None:
    """Test WorkingMemory initializes with correct defaults."""
    memory = WorkingMemory(
        conversation_id="conv-123",
        user_id="user-456",
    )

    assert memory.conversation_id == "conv-123"
    assert memory.user_id == "user-456"
    assert memory.current_goal is None
    assert memory.messages == []
    assert memory.active_entities == {}
    assert memory.context_tokens == 0
    assert memory.max_tokens == 100000
