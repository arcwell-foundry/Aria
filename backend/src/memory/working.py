"""Working memory module for conversation context management.

Working memory stores current conversation context in-memory, including:
- Current goal being pursued
- Recent messages in the conversation
- Active entities mentioned in the conversation
- Token count for context window management
"""

from dataclasses import dataclass, field
from typing import Any

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
