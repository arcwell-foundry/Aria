"""Working memory module for conversation context management.

Working memory stores current conversation context in-memory, including:
- Current goal being pursued
- Recent messages in the conversation
- Active entities mentioned in the conversation
- Token count for context window management
"""

import logging
from dataclasses import dataclass, field
from typing import Any

import tiktoken

logger = logging.getLogger(__name__)

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

    def get_context_for_llm(self) -> list[dict[str, str]]:
        """Get messages formatted for LLM consumption.

        Returns:
            List of messages with only role and content fields.
        """
        return [{"role": msg["role"], "content": msg["content"]} for msg in self.messages]

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

    def clear(self) -> None:
        """Clear all working memory state.

        Resets messages, entities, goal, and token count.
        Preserves conversation_id and user_id.
        """
        self.messages = []
        self.active_entities = {}
        self.current_goal = None
        self.context_tokens = 0

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


class WorkingMemoryManager:
    """Manages multiple working memory sessions.

    Singleton that tracks all active conversation sessions.
    Sessions are keyed by conversation_id. Supports Supabase persistence
    so sessions survive server restarts.
    """

    _sessions: dict[str, WorkingMemory] = {}

    async def get_or_create(
        self,
        conversation_id: str,
        user_id: str,
        max_tokens: int = 100000,
    ) -> WorkingMemory:
        """Get existing session or create a new one.

        Checks in-memory cache first, then attempts to restore from Supabase.
        Creates a fresh session if neither source has data.

        Args:
            conversation_id: Unique conversation identifier.
            user_id: The user who owns this conversation.
            max_tokens: Maximum tokens for context window.

        Returns:
            WorkingMemory instance for the conversation.
        """
        if conversation_id not in self._sessions:
            # Try to restore from Supabase
            restored = await self._load_from_db(conversation_id)
            if restored:
                self._sessions[conversation_id] = restored
            else:
                self._sessions[conversation_id] = WorkingMemory(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    max_tokens=max_tokens,
                )
        return self._sessions[conversation_id]

    async def persist_session(self, conversation_id: str) -> None:
        """Persist a working memory session to Supabase.

        Serializes the session via ``to_dict()`` and stores it in the
        ``conversations`` table's ``working_memory`` JSONB column.

        Args:
            conversation_id: The conversation to persist.
        """
        memory = self._sessions.get(conversation_id)
        if not memory:
            return
        try:
            from src.db.supabase import get_supabase_client

            db = get_supabase_client()
            db.table("conversations").update({
                "working_memory": memory.to_dict(),
            }).eq("id", conversation_id).execute()
        except Exception as e:
            logger.warning("Working memory persist failed: %s", e)

    async def _load_from_db(self, conversation_id: str) -> WorkingMemory | None:
        """Attempt to restore a session from Supabase.

        Args:
            conversation_id: The conversation to restore.

        Returns:
            WorkingMemory if found in DB, None otherwise.
        """
        try:
            from src.db.supabase import get_supabase_client

            db = get_supabase_client()
            result = (
                db.table("conversations")
                .select("working_memory")
                .eq("id", conversation_id)
                .maybe_single()
                .execute()
            )
            if result and result.data and result.data.get("working_memory"):
                return WorkingMemory.from_dict(result.data["working_memory"])
        except Exception:
            pass
        return None

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
