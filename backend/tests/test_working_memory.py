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


def test_add_message_stores_message() -> None:
    """Test that add_message stores a message and updates token count."""
    memory = WorkingMemory(
        conversation_id="conv-123",
        user_id="user-456",
    )

    memory.add_message(role="user", content="Hello, ARIA!")

    assert len(memory.messages) == 1
    assert memory.messages[0]["role"] == "user"
    assert memory.messages[0]["content"] == "Hello, ARIA!"
    assert memory.context_tokens > 0


def test_add_message_with_metadata() -> None:
    """Test that add_message can include metadata."""
    memory = WorkingMemory(
        conversation_id="conv-123",
        user_id="user-456",
    )

    memory.add_message(
        role="assistant",
        content="I can help you with that.",
        metadata={"tool_calls": ["search"]},
    )

    assert memory.messages[0]["metadata"] == {"tool_calls": ["search"]}
