"""Tests for working memory module."""

import json

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


def test_set_entity_stores_entity() -> None:
    """Test that set_entity stores an entity."""
    memory = WorkingMemory(
        conversation_id="conv-123",
        user_id="user-456",
    )

    memory.set_entity("current_contact", {"name": "John Doe", "email": "john@example.com"})

    assert "current_contact" in memory.active_entities
    assert memory.active_entities["current_contact"]["name"] == "John Doe"


def test_get_entity_returns_entity() -> None:
    """Test that get_entity returns a stored entity."""
    memory = WorkingMemory(
        conversation_id="conv-123",
        user_id="user-456",
    )

    memory.set_entity("deal", {"value": 50000, "stage": "negotiation"})

    entity = memory.get_entity("deal")
    assert entity is not None
    assert entity["value"] == 50000


def test_get_entity_returns_none_for_missing() -> None:
    """Test that get_entity returns None for missing entities."""
    memory = WorkingMemory(
        conversation_id="conv-123",
        user_id="user-456",
    )

    entity = memory.get_entity("nonexistent")
    assert entity is None


def test_remove_entity_removes_entity() -> None:
    """Test that remove_entity removes a stored entity."""
    memory = WorkingMemory(
        conversation_id="conv-123",
        user_id="user-456",
    )

    memory.set_entity("temp", {"data": "value"})
    assert "temp" in memory.active_entities

    memory.remove_entity("temp")
    assert "temp" not in memory.active_entities


def test_set_goal_stores_goal() -> None:
    """Test that set_goal stores the current goal."""
    memory = WorkingMemory(
        conversation_id="conv-123",
        user_id="user-456",
    )

    memory.set_goal(
        objective="Schedule a meeting with John",
        context={"contact_id": "john-123"},
    )

    assert memory.current_goal is not None
    assert memory.current_goal["objective"] == "Schedule a meeting with John"
    assert memory.current_goal["context"]["contact_id"] == "john-123"


def test_clear_goal_removes_goal() -> None:
    """Test that clear_goal removes the current goal."""
    memory = WorkingMemory(
        conversation_id="conv-123",
        user_id="user-456",
    )

    memory.set_goal(objective="Some task")
    assert memory.current_goal is not None

    memory.clear_goal()
    assert memory.current_goal is None


def test_to_dict_serializes_memory() -> None:
    """Test that to_dict returns a serializable dictionary."""
    memory = WorkingMemory(
        conversation_id="conv-123",
        user_id="user-456",
    )

    memory.add_message(role="user", content="Hello!")
    memory.set_entity("contact", {"name": "John"})
    memory.set_goal(objective="Find information")

    data = memory.to_dict()

    assert data["conversation_id"] == "conv-123"
    assert data["user_id"] == "user-456"
    assert len(data["messages"]) == 1
    assert "contact" in data["active_entities"]
    assert data["current_goal"]["objective"] == "Find information"

    # Verify it's JSON serializable
    json_str = json.dumps(data)
    assert isinstance(json_str, str)


def test_from_dict_deserializes_memory() -> None:
    """Test that from_dict creates a WorkingMemory from a dictionary."""
    data = {
        "conversation_id": "conv-123",
        "user_id": "user-456",
        "messages": [{"role": "user", "content": "Hello!"}],
        "active_entities": {"contact": {"name": "John"}},
        "current_goal": {"objective": "Find info", "context": {}},
        "context_tokens": 5,
        "max_tokens": 100000,
    }

    memory = WorkingMemory.from_dict(data)

    assert memory.conversation_id == "conv-123"
    assert memory.user_id == "user-456"
    assert len(memory.messages) == 1
    assert memory.active_entities["contact"]["name"] == "John"
    assert memory.current_goal["objective"] == "Find info"
