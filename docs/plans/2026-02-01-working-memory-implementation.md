# US-202: Working Memory Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create an in-memory working memory system that maintains conversation context, active entities, and current goals for each session.

**Architecture:** WorkingMemory is a dataclass-based structure stored in-memory per conversation session. It manages messages with token counting, tracks active entities mentioned in conversation, stores the current goal, and provides serialization for context handoff. A WorkingMemoryManager singleton handles multiple concurrent sessions.

**Tech Stack:** Python dataclasses, tiktoken for token counting, JSON serialization for context handoff

---

## Prerequisites

Before starting, ensure:
- Backend environment is set up: `cd /Users/dhruv/aria/backend`
- Dependencies installed: `pip install -r requirements.txt`
- tiktoken is available (used by anthropic SDK, already a transitive dependency)

---

## Task 1: Add Memory Module Exception

**Files:**
- Modify: `backend/src/core/exceptions.py`
- Modify: `backend/tests/test_exceptions.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_exceptions.py`:

```python
def test_memory_error_attributes() -> None:
    """Test MemoryError has correct attributes."""
    from src.core.exceptions import MemoryError

    error = MemoryError("Context window exceeded")
    assert error.message == "Memory operation failed: Context window exceeded"
    assert error.code == "MEMORY_ERROR"
    assert error.status_code == 400
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_exceptions.py::test_memory_error_attributes -v`
Expected: FAIL with ImportError

**Step 3: Add MemoryError to exceptions.py**

Add after `GraphitiConnectionError` class (around line 178):

```python
class MemoryError(ARIAException):
    """Memory operation error (400)."""

    def __init__(self, message: str = "Unknown error") -> None:
        """Initialize memory error.

        Args:
            message: Error details.
        """
        super().__init__(
            message=f"Memory operation failed: {message}",
            code="MEMORY_ERROR",
            status_code=400,
        )
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_exceptions.py::test_memory_error_attributes -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/core/exceptions.py backend/tests/test_exceptions.py
git commit -m "$(cat <<'EOF'
feat(exceptions): add MemoryError for memory operation failures

US-202: Working Memory Implementation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Create WorkingMemory Dataclass

**Files:**
- Create: `backend/src/memory/working.py`
- Create: `backend/tests/test_working_memory.py`

**Step 1: Write the failing test for WorkingMemory structure**

Create `backend/tests/test_working_memory.py`:

```python
"""Tests for working memory module."""

import pytest
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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_working_memory.py::test_working_memory_initialization -v`
Expected: FAIL with ImportError

**Step 3: Create initial WorkingMemory dataclass**

Create `backend/src/memory/working.py`:

```python
"""Working memory module for conversation context management.

Working memory stores current conversation context in-memory, including:
- Current goal being pursued
- Recent messages in the conversation
- Active entities mentioned in the conversation
- Token count for context window management
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkingMemory:
    """In-memory storage for current conversation context.

    Maintains conversation state including messages, goals, and entities.
    Manages token count to stay within context window limits.
    """

    conversation_id: str
    user_id: str
    current_goal: dict[str, Any] | None = None
    messages: list[dict[str, Any]] = field(default_factory=list)
    active_entities: dict[str, Any] = field(default_factory=dict)
    context_tokens: int = 0
    max_tokens: int = 100000
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_working_memory.py::test_working_memory_initialization -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/working.py backend/tests/test_working_memory.py
git commit -m "$(cat <<'EOF'
feat(memory): create WorkingMemory dataclass structure

US-202: Working Memory Implementation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Add Token Counting Utility

**Files:**
- Modify: `backend/src/memory/working.py`
- Modify: `backend/tests/test_working_memory.py`

**Step 1: Write the failing test for token counting**

Add to `backend/tests/test_working_memory.py`:

```python
def test_count_tokens_returns_integer() -> None:
    """Test that count_tokens returns a token count."""
    from src.memory.working import count_tokens

    text = "Hello, this is a test message."
    tokens = count_tokens(text)

    assert isinstance(tokens, int)
    assert tokens > 0
    assert tokens < 100  # Sanity check for a short message
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_working_memory.py::test_count_tokens_returns_integer -v`
Expected: FAIL with ImportError

**Step 3: Add count_tokens function**

Add to `backend/src/memory/working.py` after imports:

```python
import tiktoken

# Use cl100k_base encoding (used by Claude and GPT-4)
_ENCODING = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Count tokens in a text string.

    Args:
        text: The text to count tokens for.

    Returns:
        Number of tokens in the text.
    """
    return len(_ENCODING.encode(text))
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_working_memory.py::test_count_tokens_returns_integer -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/working.py backend/tests/test_working_memory.py
git commit -m "$(cat <<'EOF'
feat(memory): add token counting utility using tiktoken

US-202: Working Memory Implementation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Implement add_message Method

**Files:**
- Modify: `backend/src/memory/working.py`
- Modify: `backend/tests/test_working_memory.py`

**Step 1: Write the failing test for add_message**

Add to `backend/tests/test_working_memory.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_working_memory.py::test_add_message_stores_message tests/test_working_memory.py::test_add_message_with_metadata -v`
Expected: FAIL with AttributeError

**Step 3: Add add_message method to WorkingMemory**

Add to `WorkingMemory` class in `backend/src/memory/working.py`:

```python
    def add_message(
        self,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add a message to the conversation history.

        Args:
            role: The role of the message sender ('user', 'assistant', 'system').
            content: The message content.
            metadata: Optional metadata to attach to the message.
        """
        message: dict[str, Any] = {
            "role": role,
            "content": content,
        }
        if metadata:
            message["metadata"] = metadata

        message_tokens = count_tokens(content)
        self.messages.append(message)
        self.context_tokens += message_tokens
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_working_memory.py::test_add_message_stores_message tests/test_working_memory.py::test_add_message_with_metadata -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/working.py backend/tests/test_working_memory.py
git commit -m "$(cat <<'EOF'
feat(memory): implement add_message with token tracking

US-202: Working Memory Implementation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Implement Context Window Truncation

**Files:**
- Modify: `backend/src/memory/working.py`
- Modify: `backend/tests/test_working_memory.py`

**Step 1: Write the failing test for truncation**

Add to `backend/tests/test_working_memory.py`:

```python
def test_add_message_truncates_when_exceeding_max_tokens() -> None:
    """Test that old messages are removed when context exceeds max tokens."""
    memory = WorkingMemory(
        conversation_id="conv-123",
        user_id="user-456",
        max_tokens=50,  # Very small for testing
    )

    # Add messages that will exceed the limit
    memory.add_message(role="user", content="First message with some content.")
    memory.add_message(role="assistant", content="Second message with more content.")
    memory.add_message(role="user", content="Third message that should trigger truncation.")

    # Should have truncated old messages
    assert memory.context_tokens <= memory.max_tokens
    # First message should be removed
    assert not any(m["content"].startswith("First") for m in memory.messages)
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_working_memory.py::test_add_message_truncates_when_exceeding_max_tokens -v`
Expected: FAIL (assertion fails)

**Step 3: Add truncation logic to add_message**

Update `add_message` method in `backend/src/memory/working.py`:

```python
    def add_message(
        self,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add a message to the conversation history.

        Automatically truncates old messages if context window is exceeded.
        System messages are preserved during truncation.

        Args:
            role: The role of the message sender ('user', 'assistant', 'system').
            content: The message content.
            metadata: Optional metadata to attach to the message.
        """
        message: dict[str, Any] = {
            "role": role,
            "content": content,
        }
        if metadata:
            message["metadata"] = metadata

        message_tokens = count_tokens(content)
        self.messages.append(message)
        self.context_tokens += message_tokens

        # Truncate old messages if exceeding max tokens
        self._truncate_if_needed()

    def _truncate_if_needed(self) -> None:
        """Remove oldest non-system messages until under token limit."""
        while self.context_tokens > self.max_tokens and len(self.messages) > 1:
            # Find first non-system message to remove
            for i, msg in enumerate(self.messages):
                if msg["role"] != "system":
                    removed_tokens = count_tokens(msg["content"])
                    self.messages.pop(i)
                    self.context_tokens -= removed_tokens
                    break
            else:
                # All messages are system messages, can't truncate further
                break
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_working_memory.py::test_add_message_truncates_when_exceeding_max_tokens -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/working.py backend/tests/test_working_memory.py
git commit -m "$(cat <<'EOF'
feat(memory): implement context window truncation strategy

Automatically removes oldest non-system messages when exceeding max tokens.

US-202: Working Memory Implementation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Implement get_context_for_llm Method

**Files:**
- Modify: `backend/src/memory/working.py`
- Modify: `backend/tests/test_working_memory.py`

**Step 1: Write the failing test for get_context_for_llm**

Add to `backend/tests/test_working_memory.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_working_memory.py::test_get_context_for_llm_returns_formatted_messages tests/test_working_memory.py::test_get_context_for_llm_excludes_metadata -v`
Expected: FAIL with AttributeError

**Step 3: Add get_context_for_llm method**

Add to `WorkingMemory` class in `backend/src/memory/working.py`:

```python
    def get_context_for_llm(self) -> list[dict[str, str]]:
        """Get messages formatted for LLM consumption.

        Returns:
            List of messages with only role and content fields.
        """
        return [
            {"role": msg["role"], "content": msg["content"]}
            for msg in self.messages
        ]
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_working_memory.py::test_get_context_for_llm_returns_formatted_messages tests/test_working_memory.py::test_get_context_for_llm_excludes_metadata -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/working.py backend/tests/test_working_memory.py
git commit -m "$(cat <<'EOF'
feat(memory): implement get_context_for_llm for Claude integration

US-202: Working Memory Implementation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Implement Entity Management Methods

**Files:**
- Modify: `backend/src/memory/working.py`
- Modify: `backend/tests/test_working_memory.py`

**Step 1: Write the failing tests for entity management**

Add to `backend/tests/test_working_memory.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_working_memory.py::test_set_entity_stores_entity tests/test_working_memory.py::test_get_entity_returns_entity tests/test_working_memory.py::test_get_entity_returns_none_for_missing tests/test_working_memory.py::test_remove_entity_removes_entity -v`
Expected: FAIL with AttributeError

**Step 3: Add entity management methods**

Add to `WorkingMemory` class in `backend/src/memory/working.py`:

```python
    def set_entity(self, key: str, value: Any) -> None:
        """Store an active entity in working memory.

        Args:
            key: Unique identifier for the entity.
            value: The entity data to store.
        """
        self.active_entities[key] = value

    def get_entity(self, key: str) -> Any | None:
        """Retrieve an active entity from working memory.

        Args:
            key: The entity identifier.

        Returns:
            The entity data if found, None otherwise.
        """
        return self.active_entities.get(key)

    def remove_entity(self, key: str) -> None:
        """Remove an entity from working memory.

        Args:
            key: The entity identifier to remove.
        """
        self.active_entities.pop(key, None)
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_working_memory.py::test_set_entity_stores_entity tests/test_working_memory.py::test_get_entity_returns_entity tests/test_working_memory.py::test_get_entity_returns_none_for_missing tests/test_working_memory.py::test_remove_entity_removes_entity -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/working.py backend/tests/test_working_memory.py
git commit -m "$(cat <<'EOF'
feat(memory): implement entity management (set, get, remove)

US-202: Working Memory Implementation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Implement Goal Management

**Files:**
- Modify: `backend/src/memory/working.py`
- Modify: `backend/tests/test_working_memory.py`

**Step 1: Write the failing tests for goal management**

Add to `backend/tests/test_working_memory.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_working_memory.py::test_set_goal_stores_goal tests/test_working_memory.py::test_clear_goal_removes_goal -v`
Expected: FAIL with AttributeError

**Step 3: Add goal management methods**

Add to `WorkingMemory` class in `backend/src/memory/working.py`:

```python
    def set_goal(
        self,
        objective: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Set the current conversation goal.

        Args:
            objective: Description of what the user wants to achieve.
            context: Additional context related to the goal.
        """
        self.current_goal = {
            "objective": objective,
            "context": context or {},
        }

    def clear_goal(self) -> None:
        """Clear the current goal."""
        self.current_goal = None
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_working_memory.py::test_set_goal_stores_goal tests/test_working_memory.py::test_clear_goal_removes_goal -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/working.py backend/tests/test_working_memory.py
git commit -m "$(cat <<'EOF'
feat(memory): implement goal management (set, clear)

US-202: Working Memory Implementation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Implement Serialization for Context Handoff

**Files:**
- Modify: `backend/src/memory/working.py`
- Modify: `backend/tests/test_working_memory.py`

**Step 1: Write the failing tests for serialization**

Add to `backend/tests/test_working_memory.py`:

```python
import json


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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_working_memory.py::test_to_dict_serializes_memory tests/test_working_memory.py::test_from_dict_deserializes_memory -v`
Expected: FAIL with AttributeError

**Step 3: Add serialization methods**

Add to `WorkingMemory` class in `backend/src/memory/working.py`:

```python
    def to_dict(self) -> dict[str, Any]:
        """Serialize working memory to a dictionary.

        Returns:
            Dictionary representation suitable for JSON serialization.
        """
        return {
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "messages": self.messages,
            "active_entities": self.active_entities,
            "current_goal": self.current_goal,
            "context_tokens": self.context_tokens,
            "max_tokens": self.max_tokens,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkingMemory":
        """Create a WorkingMemory instance from a dictionary.

        Args:
            data: Dictionary containing working memory state.

        Returns:
            WorkingMemory instance with restored state.
        """
        memory = cls(
            conversation_id=data["conversation_id"],
            user_id=data["user_id"],
            max_tokens=data.get("max_tokens", 100000),
        )
        memory.messages = data.get("messages", [])
        memory.active_entities = data.get("active_entities", {})
        memory.current_goal = data.get("current_goal")
        memory.context_tokens = data.get("context_tokens", 0)
        return memory
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_working_memory.py::test_to_dict_serializes_memory tests/test_working_memory.py::test_from_dict_deserializes_memory -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/working.py backend/tests/test_working_memory.py
git commit -m "$(cat <<'EOF'
feat(memory): implement serialization for context handoff

Adds to_dict and from_dict for session transfer.

US-202: Working Memory Implementation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Implement clear Method

**Files:**
- Modify: `backend/src/memory/working.py`
- Modify: `backend/tests/test_working_memory.py`

**Step 1: Write the failing test for clear**

Add to `backend/tests/test_working_memory.py`:

```python
def test_clear_resets_all_state() -> None:
    """Test that clear resets messages, entities, and goal."""
    memory = WorkingMemory(
        conversation_id="conv-123",
        user_id="user-456",
    )

    memory.add_message(role="user", content="Hello!")
    memory.set_entity("contact", {"name": "John"})
    memory.set_goal(objective="Find information")

    assert len(memory.messages) > 0
    assert len(memory.active_entities) > 0
    assert memory.current_goal is not None
    assert memory.context_tokens > 0

    memory.clear()

    assert memory.messages == []
    assert memory.active_entities == {}
    assert memory.current_goal is None
    assert memory.context_tokens == 0
    # conversation_id and user_id should remain
    assert memory.conversation_id == "conv-123"
    assert memory.user_id == "user-456"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_working_memory.py::test_clear_resets_all_state -v`
Expected: FAIL with AttributeError

**Step 3: Add clear method**

Add to `WorkingMemory` class in `backend/src/memory/working.py`:

```python
    def clear(self) -> None:
        """Clear all working memory state.

        Resets messages, entities, goal, and token count.
        Preserves conversation_id and user_id.
        """
        self.messages = []
        self.active_entities = {}
        self.current_goal = None
        self.context_tokens = 0
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_working_memory.py::test_clear_resets_all_state -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/working.py backend/tests/test_working_memory.py
git commit -m "$(cat <<'EOF'
feat(memory): implement clear method for conversation end

US-202: Working Memory Implementation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Create WorkingMemoryManager Singleton

**Files:**
- Modify: `backend/src/memory/working.py`
- Modify: `backend/tests/test_working_memory.py`

**Step 1: Write the failing tests for manager**

Add to `backend/tests/test_working_memory.py`:

```python
from src.memory.working import WorkingMemoryManager


@pytest.fixture(autouse=True)
def reset_manager() -> None:
    """Reset the manager singleton before each test."""
    WorkingMemoryManager._sessions = {}


def test_manager_get_or_create_creates_new_session() -> None:
    """Test that get_or_create creates a new session."""
    manager = WorkingMemoryManager()

    memory = manager.get_or_create(
        conversation_id="conv-123",
        user_id="user-456",
    )

    assert memory.conversation_id == "conv-123"
    assert memory.user_id == "user-456"


def test_manager_get_or_create_returns_existing_session() -> None:
    """Test that get_or_create returns existing session."""
    manager = WorkingMemoryManager()

    memory1 = manager.get_or_create("conv-123", "user-456")
    memory1.add_message(role="user", content="Hello!")

    memory2 = manager.get_or_create("conv-123", "user-456")

    assert memory1 is memory2
    assert len(memory2.messages) == 1


def test_manager_get_returns_none_for_missing() -> None:
    """Test that get returns None for non-existent session."""
    manager = WorkingMemoryManager()

    memory = manager.get("nonexistent")

    assert memory is None


def test_manager_delete_removes_session() -> None:
    """Test that delete removes a session."""
    manager = WorkingMemoryManager()

    manager.get_or_create("conv-123", "user-456")
    assert manager.get("conv-123") is not None

    manager.delete("conv-123")

    assert manager.get("conv-123") is None
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_working_memory.py::test_manager_get_or_create_creates_new_session -v`
Expected: FAIL with ImportError

**Step 3: Add WorkingMemoryManager class**

Add to `backend/src/memory/working.py` after `WorkingMemory` class:

```python
class WorkingMemoryManager:
    """Manages multiple working memory sessions.

    Singleton that tracks all active conversation sessions.
    Sessions are keyed by conversation_id.
    """

    _sessions: dict[str, WorkingMemory] = {}

    def get_or_create(
        self,
        conversation_id: str,
        user_id: str,
        max_tokens: int = 100000,
    ) -> WorkingMemory:
        """Get existing session or create a new one.

        Args:
            conversation_id: Unique conversation identifier.
            user_id: The user who owns this conversation.
            max_tokens: Maximum tokens for context window.

        Returns:
            WorkingMemory instance for the conversation.
        """
        if conversation_id not in self._sessions:
            self._sessions[conversation_id] = WorkingMemory(
                conversation_id=conversation_id,
                user_id=user_id,
                max_tokens=max_tokens,
            )
        return self._sessions[conversation_id]

    def get(self, conversation_id: str) -> WorkingMemory | None:
        """Get an existing session.

        Args:
            conversation_id: The conversation identifier.

        Returns:
            WorkingMemory if found, None otherwise.
        """
        return self._sessions.get(conversation_id)

    def delete(self, conversation_id: str) -> None:
        """Delete a session.

        Args:
            conversation_id: The conversation to delete.
        """
        self._sessions.pop(conversation_id, None)

    def clear_all(self) -> None:
        """Clear all sessions."""
        self._sessions.clear()

    def list_sessions(self) -> list[str]:
        """List all active session IDs.

        Returns:
            List of conversation IDs.
        """
        return list(self._sessions.keys())
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_working_memory.py -k "manager" -v`
Expected: All manager tests PASS

**Step 5: Commit**

```bash
git add backend/src/memory/working.py backend/tests/test_working_memory.py
git commit -m "$(cat <<'EOF'
feat(memory): create WorkingMemoryManager for session management

Singleton pattern for managing multiple concurrent conversations.

US-202: Working Memory Implementation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Update memory/__init__.py Exports

**Files:**
- Modify: `backend/src/memory/__init__.py`

**Step 1: Update exports**

Replace `backend/src/memory/__init__.py`:

```python
"""Six-type memory system for ARIA.

This module implements ARIA's cognitive memory architecture:
- Working: Current conversation context (in-memory, session only)
- Episodic: Past events and interactions (Graphiti)
- Semantic: Facts and knowledge (Graphiti + pgvector)
- Procedural: Learned workflows (Supabase)
- Prospective: Future tasks/reminders (Supabase)
- Lead: Sales pursuit tracking (Graphiti + Supabase)
"""

from src.memory.working import (
    WorkingMemory,
    WorkingMemoryManager,
    count_tokens,
)

__all__ = [
    "WorkingMemory",
    "WorkingMemoryManager",
    "count_tokens",
]
```

**Step 2: Verify import works**

Run: `cd /Users/dhruv/aria/backend && python -c "from src.memory import WorkingMemory, WorkingMemoryManager; print('Import successful')"`
Expected: "Import successful"

**Step 3: Commit**

```bash
git add backend/src/memory/__init__.py
git commit -m "$(cat <<'EOF'
feat(memory): export WorkingMemory from memory module

US-202: Working Memory Implementation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: Run All Tests

**Files:** None (validation only)

**Step 1: Run all working memory tests**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_working_memory.py -v`
Expected: All tests PASS

**Step 2: Run full test suite**

Run: `cd /Users/dhruv/aria/backend && pytest tests/ -v`
Expected: All tests PASS

**Step 3: If any failures, fix and commit**

If tests fail, fix the issues and:

```bash
git add -A
git commit -m "$(cat <<'EOF'
fix(memory): address test failures

US-202: Working Memory Implementation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: Run Quality Gates

**Files:** None (validation only)

**Step 1: Run mypy**

Run: `cd /Users/dhruv/aria/backend && mypy src/memory/ --strict`
Expected: No errors

**Step 2: Run ruff check**

Run: `cd /Users/dhruv/aria/backend && ruff check src/memory/`
Expected: No errors

**Step 3: Run ruff format**

Run: `cd /Users/dhruv/aria/backend && ruff format src/memory/ --check`
Expected: No formatting issues (or run `ruff format src/memory/` to fix)

**Step 4: Fix any issues and commit**

If any quality gate failures:

```bash
ruff format src/memory/
git add -A
git commit -m "$(cat <<'EOF'
chore: fix quality gate issues for working memory

US-202: Working Memory Implementation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Summary

This plan implements US-202: Working Memory Implementation with:

1. **MemoryError** exception for memory operation failures
2. **WorkingMemory** dataclass with:
   - Conversation and user identifiers
   - Message storage with token counting
   - Active entity tracking
   - Current goal management
   - Context window truncation strategy
   - Serialization for handoff
   - Clear method for session end
3. **Token counting** using tiktoken (cl100k_base encoding)
4. **WorkingMemoryManager** singleton for multi-session management
5. **Comprehensive unit tests** for all operations
6. **Quality gates** verified passing

All acceptance criteria met:
- [x] `src/memory/working.py` created
- [x] In-memory storage per conversation session
- [x] Stores: current goal, recent messages, active entities
- [x] Max context window management (truncation strategy)
- [x] Serialization for context handoff
- [x] Clear on conversation end
- [x] Unit tests for all operations
