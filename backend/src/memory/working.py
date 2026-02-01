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
