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


def test_count_tokens_returns_integer() -> None:
    """Test that count_tokens returns a token count."""
    from src.memory.working import count_tokens

    text = "Hello, this is a test message."
    tokens = count_tokens(text)

    assert isinstance(tokens, int)
    assert tokens > 0
    assert tokens < 100  # Sanity check for a short message
