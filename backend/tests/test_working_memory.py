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


def test_add_message_truncates_when_exceeding_max_tokens() -> None:
    """Test that old messages are removed when context exceeds max tokens."""
    memory = WorkingMemory(
        conversation_id="conv-123",
        user_id="user-456",
        max_tokens=15,  # Very small for testing (each message is ~6-8 tokens)
    )

    # Add messages that will exceed the limit
    memory.add_message(role="user", content="First message with some content.")
    memory.add_message(role="assistant", content="Second message with more content.")
    memory.add_message(role="user", content="Third message that should trigger truncation.")

    # Should have truncated old messages
    assert memory.context_tokens <= memory.max_tokens
    # First message should be removed
    assert not any(m["content"].startswith("First") for m in memory.messages)


def test_get_context_for_llm_returns_formatted_messages() -> None:
    """Test that get_context_for_llm returns properly formatted messages."""
    memory = WorkingMemory(
        conversation_id="conv-123",
        user_id="user-456",
    )

    memory.add_message(role="system", content="You are ARIA.")
    memory.add_message(role="user", content="Hello!")
    memory.add_message(role="assistant", content="Hi there!")

    context = memory.get_context_for_llm()

    assert len(context) == 3
    assert context[0] == {"role": "system", "content": "You are ARIA."}
    assert context[1] == {"role": "user", "content": "Hello!"}
    assert context[2] == {"role": "assistant", "content": "Hi there!"}


def test_get_context_for_llm_excludes_metadata() -> None:
    """Test that get_context_for_llm excludes internal metadata."""
    memory = WorkingMemory(
        conversation_id="conv-123",
        user_id="user-456",
    )

    memory.add_message(
        role="user",
        content="Hello!",
        metadata={"internal_id": "12345"},
    )

    context = memory.get_context_for_llm()

    assert "metadata" not in context[0]
    assert "internal_id" not in context[0]
