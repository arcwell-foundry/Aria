"""Service for managing conversation metadata and history.

Provides:
- List user's conversations
- Get conversation messages
- Update conversation title
- Delete conversation
- Search conversations
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from supabase import Client

from src.core.exceptions import NotFoundError

logger = logging.getLogger(__name__)


@dataclass
class Conversation:
    """A conversation metadata record."""

    id: str
    user_id: str
    title: str | None
    message_count: int
    last_message_at: datetime | None
    last_message_preview: str | None
    created_at: datetime
    updated_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "message_count": self.message_count,
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
            "last_message_preview": self.last_message_preview,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Conversation:
        """Create Conversation from database record."""
        last_message_at = data.get("last_message_at")
        created_at = data["created_at"]
        updated_at = data["updated_at"]

        if isinstance(last_message_at, str):
            last_message_at = datetime.fromisoformat(last_message_at)
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)

        return cls(
            id=data["id"],
            user_id=data["user_id"],
            title=data.get("title"),
            message_count=data.get("message_count", 0),
            last_message_at=last_message_at,
            last_message_preview=data.get("last_message_preview"),
            created_at=created_at,
            updated_at=updated_at,
        )


@dataclass
class ConversationMessage:
    """A message in a conversation."""

    id: str
    conversation_id: str
    role: str
    content: str
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConversationMessage:
        """Create ConversationMessage from database record."""
        created_at = data["created_at"]
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        return cls(
            id=data["id"],
            conversation_id=data["conversation_id"],
            role=data["role"],
            content=data["content"],
            created_at=created_at,
        )


class ConversationService:
    """Service for conversation management operations."""

    def __init__(self, db_client: Client) -> None:
        """Initialize the conversation service.

        Args:
            db_client: Supabase client for database operations.
        """
        self.db = db_client

    async def list_conversations(
        self,
        user_id: str,
        search_query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Conversation]:
        """List all conversations for a user.

        Args:
            user_id: The user's ID.
            search_query: Optional search query to filter by title.
            limit: Maximum number of conversations to return.
            offset: Number of conversations to skip.

        Returns:
            List of Conversation objects, ordered by most recently updated.
        """
        query = self.db.table("conversations").select("*").eq("user_id", user_id)

        if search_query:
            # Search in title
            query = query.ilike("title", f"%{search_query}%")

        result = query.order("updated_at", desc=True).limit(limit).offset(offset).execute()

        if not result.data:
            return []

        return [Conversation.from_dict(conv) for conv in result.data]

    async def save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Insert a message row into the messages table.

        Args:
            conversation_id: The conversation this message belongs to.
            role: Message role ('user', 'assistant', or 'system').
            content: The message text content.
            metadata: Optional JSONB metadata to attach.

        Returns:
            The UUID string of the newly created message.
        """
        message_id = str(uuid.uuid4())
        row = {
            "id": message_id,
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "metadata": metadata or {},
        }

        self.db.table("messages").insert(row).execute()

        logger.debug(
            "Message saved",
            extra={
                "message_id": message_id,
                "conversation_id": conversation_id,
                "role": role,
            },
        )
        return message_id

    async def get_conversation_messages(
        self,
        user_id: str,
        conversation_id: str,
    ) -> list[ConversationMessage]:
        """Get all messages for a conversation.

        Args:
            user_id: The user's ID.
            conversation_id: The conversation ID.

        Returns:
            List of ConversationMessage objects in chronological order.

        Raises:
            NotFoundError: If conversation doesn't belong to user.
        """
        # Verify ownership
        conv = (
            self.db.table("conversations")
            .select("id")
            .eq("user_id", user_id)
            .eq("id", conversation_id)
            .single()
            .execute()
        )

        if not conv.data:
            raise NotFoundError(resource="Conversation", resource_id=conversation_id)

        # Read persisted messages from the messages table
        result = (
            self.db.table("messages")
            .select("*")
            .eq("conversation_id", conversation_id)
            .order("created_at", desc=False)
            .execute()
        )

        if not result.data:
            return []

        return [ConversationMessage.from_dict(row) for row in result.data]

    async def update_conversation_title(
        self,
        user_id: str,
        conversation_id: str,
        title: str,
    ) -> Conversation:
        """Update a conversation's title.

        Args:
            user_id: The user's ID.
            conversation_id: The conversation ID.
            title: New title for the conversation.

        Returns:
            The updated Conversation.

        Raises:
            ValueError: If conversation doesn't belong to user.
        """
        # First update
        (
            self.db.table("conversations")
            .update({"title": title, "updated_at": datetime.now(UTC).isoformat()})
            .eq("user_id", user_id)
            .eq("id", conversation_id)
            .execute()
        )

        # Then fetch the updated record
        result = (
            self.db.table("conversations")
            .select("*")
            .eq("user_id", user_id)
            .eq("id", conversation_id)
            .single()
            .execute()
        )

        if not result.data:
            raise NotFoundError(resource="Conversation", resource_id=conversation_id)

        return Conversation.from_dict(result.data)

    async def delete_conversation(
        self,
        user_id: str,
        conversation_id: str,
    ) -> None:
        """Delete a conversation.

        Args:
            user_id: The user's ID.
            conversation_id: The conversation ID.

        Raises:
            ValueError: If conversation doesn't belong to user.

        Note:
            This also deletes associated working memory. Conversation episodes
            are preserved for historical context.
        """
        # Verify ownership
        conv = (
            self.db.table("conversations")
            .select("id")
            .eq("user_id", user_id)
            .eq("id", conversation_id)
            .single()
            .execute()
        )

        if not conv.data:
            raise NotFoundError(resource="Conversation", resource_id=conversation_id)

        # Delete conversation record
        (
            self.db.table("conversations")
            .delete()
            .eq("user_id", user_id)
            .eq("id", conversation_id)
            .execute()
        )

        # Clear working memory
        from src.memory.working import WorkingMemoryManager

        memory_manager = WorkingMemoryManager()
        memory_manager.delete(conversation_id=conversation_id)

        logger.info(
            "Conversation deleted",
            extra={
                "user_id": user_id,
                "conversation_id": conversation_id,
            },
        )
