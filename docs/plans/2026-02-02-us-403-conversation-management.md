# US-403: Conversation Management Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a premium, Apple-inspired conversation management system with sidebar, search, titles, and delete functionality that seamlessly integrates with the existing ARIA Chat UI.

**Architecture:** Extend existing chat system with persistent conversation storage, sidebar component for navigation, search/filter capabilities, and conversation management actions. Backend adds conversations table and API routes; frontend adds sidebar UI and integrates with existing AriaChatPage.

**Tech Stack:** React 18, TypeScript, Tailwind CSS 4, React Query, Supabase PostgreSQL, Python/FastAPI

**Design Direction:** Apple-inspired luxury - premium SF Pro typography, sophisticated neutral palette with subtle cyan accents, buttery 60fps animations, tasteful glass morphism, generous whitespace, refined shadows and layering. Sidebar should feel like a refined navigation panel matching US-402's aesthetic.

---

## Dependencies

This plan builds on:
- US-401: Chat Backend (already implemented)
- US-402: ARIA Chat UI (already implemented)
- conversation_episodes table (already exists)

No new npm packages required.

---

## Task 1: Create Conversations Database Table

**Files:**
- Create: `backend/supabase/migrations/20260202000006_create_conversations.sql`

**Step 1: Write the migration file**

Create `backend/supabase/migrations/20260202000006_create_conversations.sql`:

```sql
-- Migration: US-403 Conversation Management
-- Stores conversation metadata for sidebar navigation

-- =============================================================================
-- Conversations Table
-- =============================================================================

CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,

    -- Optional title (auto-generated or user-editable)
    title TEXT,

    -- Metadata
    message_count INTEGER DEFAULT 0,
    last_message_at TIMESTAMPTZ,
    last_message_preview TEXT,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Ensure one conversation record per conversation_id
    UNIQUE(id, user_id)
);

-- =============================================================================
-- Indexes
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_conversations_user_updated ON conversations(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_user_last_message ON conversations(user_id, last_message_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_title_search ON conversations(user_id, title) WHERE title IS NOT NULL;

-- =============================================================================
-- Row Level Security
-- =============================================================================

ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own conversations" ON conversations
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own conversations" ON conversations
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own conversations" ON conversations
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own conversations" ON conversations
    FOR DELETE USING (auth.uid() = user_id);

CREATE POLICY "Service role full access to conversations" ON conversations
    FOR ALL USING (auth.role() = 'service_role');

-- =============================================================================
-- Triggers for updated_at
-- =============================================================================

CREATE TRIGGER update_conversations_updated_at
    BEFORE UPDATE ON conversations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

**Step 2: Verify SQL syntax**

Run: `psql -f backend/supabase/migrations/20260202000006_create_conversations.sql -c "EXPLAIN SELECT * FROM conversations"`
Expected: No syntax errors (table structure explained)

**Step 3: Commit**

```bash
git add backend/supabase/migrations/20260202000006_create_conversations.sql
git commit -m "schema: add conversations table for US-403"
```

---

## Task 2: Add Conversation Management to Chat Service

**Files:**
- Modify: `backend/src/services/chat.py`

**Step 1: Add conversation tracking methods**

Add to `ChatService` class in `backend/src/services/chat.py`. Insert after the `__init__` method (after line 50):

```python
    async def _ensure_conversation_record(
        self,
        user_id: str,
        conversation_id: str,
    ) -> None:
        """Ensure a conversation record exists for this conversation_id.

        Args:
            user_id: The user's ID.
            conversation_id: Unique conversation identifier.

        Note:
            This is a fire-and-forget operation. Errors are logged but not raised.
        """
        from src.db.supabase import get_supabase_client

        try:
            db = get_supabase_client()

            # Check if conversation exists
            result = (
                db.table("conversations")
                .select("id")
                .eq("user_id", user_id)
                .eq("id", conversation_id)
                .execute()
            )

            if result.data:
                # Conversation exists, update it
                (
                    db.table("conversations")
                    .update(
                        {
                            "updated_at": datetime.now(UTC).isoformat(),
                        }
                    )
                    .eq("user_id", user_id)
                    .eq("id", conversation_id)
                    .execute()
                )
            else:
                # Create new conversation record
                db.table("conversations").insert(
                    {
                        "id": conversation_id,
                        "user_id": user_id,
                        "message_count": 0,
                    }
                ).execute()

        except Exception as e:
            logger.warning(
                "Failed to ensure conversation record",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "error": str(e),
                },
            )

    async def _update_conversation_metadata(
        self,
        user_id: str,
        conversation_id: str,
        user_message: str,
        assistant_message: str,
    ) -> None:
        """Update conversation metadata after message exchange.

        Args:
            user_id: The user's ID.
            conversation_id: Unique conversation identifier.
            user_message: The user's message content.
            assistant_message: The assistant's response content.

        Note:
            This is a fire-and-forget operation. Errors are logged but not raised.
        """
        from src.db.supabase import get_supabase_client

        try:
            db = get_supabase_client()

            # Generate preview from user message (first 100 chars)
            preview = user_message[:100]
            if len(user_message) > 100:
                preview += "..."

            # Get current message count
            current = (
                db.table("conversations")
                .select("message_count")
                .eq("user_id", user_id)
                .eq("id", conversation_id)
                .single()
                .execute()
            )

            message_count = 0
            if current.data:
                message_count = current.data.get("message_count", 0)

            # Update metadata
            (
                db.table("conversations")
                .update(
                    {
                        "message_count": message_count + 2,  # user + assistant
                        "last_message_at": datetime.now(UTC).isoformat(),
                        "last_message_preview": preview,
                        "updated_at": datetime.now(UTC).isoformat(),
                    }
                )
                .eq("user_id", user_id)
                .eq("id", conversation_id)
                .execute()
            )

        except Exception as e:
            logger.warning(
                "Failed to update conversation metadata",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "error": str(e),
                },
            )
```

**Step 2: Update process_message to call tracking methods**

Modify the `process_message` method in `ChatService` class. Add these calls:

After line 78 (after getting working memory), add:
```python
        # Ensure conversation record exists
        await self._ensure_conversation_record(user_id, conversation_id)
```

Before the return statement (before line 137), add:
```python
        # Update conversation metadata
        await self._update_conversation_metadata(
            user_id=user_id,
            conversation_id=conversation_id,
            user_message=message,
            assistant_message=response_text,
        )
```

**Step 3: Verify Python syntax**

Run: `cd backend && python -m py_compile src/services/chat.py`
Expected: No syntax errors

**Step 4: Commit**

```bash
git add backend/src/services/chat.py
git commit -m "feat(chat): add conversation tracking to ChatService"
```

---

## Task 3: Create Conversation Service

**Files:**
- Create: `backend/src/services/conversations.py`

**Step 1: Create the conversation service module**

Create `backend/src/services/conversations.py`:

```python
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
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from supabase import Client

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

    def to_dict(self) -> dict:
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
    def from_dict(cls, data: dict) -> Conversation:
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

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dictionary."""
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> ConversationMessage:
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
        query = (
            self.db.table("conversations")
            .select("*")
            .eq("user_id", user_id)
        )

        if search_query:
            # Search in title
            query = query.ilike("title", f"%{search_query}%")

        result = (
            query
            .order("updated_at", desc=True)
            .limit(limit)
            .offset(offset)
            .execute()
        )

        if not result.data:
            return []

        return [Conversation.from_dict(conv) for conv in result.data]

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
            ValueError: If conversation doesn't belong to user.
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
            raise ValueError("Conversation not found")

        # Get messages from working memory (for now)
        # In production, these would be stored in a messages table
        from src.memory.working import WorkingMemoryManager

        memory_manager = WorkingMemoryManager()
        working_memory = memory_manager.get_or_create(
            conversation_id=conversation_id,
            user_id=user_id,
        )

        messages = working_memory.get_messages()

        return [
            ConversationMessage(
                id=f"{conversation_id}-{idx}",
                conversation_id=conversation_id,
                role=msg["role"],
                content=msg["content"],
                created_at=msg.get("created_at", datetime.now(UTC)),
            )
            for idx, msg in enumerate(messages)
        ]

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
        result = (
            self.db.table("conversations")
            .update({"title": title, "updated_at": datetime.now(UTC).isoformat()})
            .eq("user_id", user_id)
            .eq("id", conversation_id)
            .select("*")
            .single()
            .execute()
        )

        if not result.data:
            raise ValueError("Conversation not found")

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
            raise ValueError("Conversation not found")

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
```

**Step 2: Verify Python syntax**

Run: `cd backend && python -m py_compile src/services/conversations.py`
Expected: No syntax errors

**Step 3: Commit**

```bash
git add backend/src/services/conversations.py
git commit -m "feat(conversations): add ConversationService for CRUD operations"
```

---

## Task 4: Add Conversation API Routes

**Files:**
- Modify: `backend/src/api/routes/chat.py`

**Step 1: Import the conversation service**

Add at the top of `backend/src/api/routes/chat.py` (after existing imports):

```python
from src.services.conversations import ConversationService
from src.db.supabase import get_supabase_client
```

**Step 2: Add list conversations endpoint**

Add to `backend/src/api/routes/chat.py` after the existing chat endpoint (after line 100):

```python
class ConversationListResponse(BaseModel):
    """Response for listing conversations."""

    conversations: list[dict]
    total: int


class ConversationTitleRequest(BaseModel):
    """Request to update conversation title."""

    title: str = Field(..., min_length=1, max_length=200)


class ConversationTitleResponse(BaseModel):
    """Response for updating conversation title."""

    id: str
    title: str | None
    message_count: int
    last_message_at: str | None
    last_message_preview: str | None
    updated_at: str


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    current_user: CurrentUser,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> ConversationListResponse:
    """List all conversations for the current user.

    Args:
        current_user: The authenticated user.
        search: Optional search query to filter by title.
        limit: Maximum number of conversations to return.
        offset: Number of conversations to skip.

    Returns:
        List of conversations ordered by most recently updated.
    """
    db = get_supabase_client()
    service = ConversationService(db_client=db)

    conversations = await service.list_conversations(
        user_id=current_user.id,
        search_query=search,
        limit=limit,
        offset=offset,
    )

    # Get total count
    count_result = (
        db.table("conversations")
        .select("id", count="exact")
        .eq("user_id", current_user.id)
        .execute()
    )
    total = count_result.count if hasattr(count_result, "count") else len(conversations)

    return ConversationListResponse(
        conversations=[c.to_dict() for c in conversations],
        total=total,
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationListResponse)
async def get_conversation(
    current_user: CurrentUser,
    conversation_id: str,
) -> ConversationListResponse:
    """Get messages for a specific conversation.

    Args:
        current_user: The authenticated user.
        conversation_id: The conversation ID.

    Returns:
        List of messages in the conversation.

    Raises:
        HTTPException: If conversation not found.
    """
    db = get_supabase_client()
    service = ConversationService(db_client=db)

    try:
        messages = await service.get_conversation_messages(
            user_id=current_user.id,
            conversation_id=conversation_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    return ConversationListResponse(
        conversations=[m.to_dict() for m in messages],
        total=len(messages),
    )


@router.put("/conversations/{conversation_id}/title", response_model=ConversationTitleResponse)
async def update_conversation_title(
    current_user: CurrentUser,
    conversation_id: str,
    request: ConversationTitleRequest,
) -> ConversationTitleResponse:
    """Update the title of a conversation.

    Args:
        current_user: The authenticated user.
        conversation_id: The conversation ID.
        request: Request containing new title.

    Returns:
        Updated conversation metadata.

    Raises:
        HTTPException: If conversation not found.
    """
    db = get_supabase_client()
    service = ConversationService(db_client=db)

    try:
        conversation = await service.update_conversation_title(
            user_id=current_user.id,
            conversation_id=conversation_id,
            title=request.title,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    return ConversationTitleResponse(
        id=conversation.id,
        title=conversation.title,
        message_count=conversation.message_count,
        last_message_at=conversation.last_message_at.isoformat() if conversation.last_message_at else None,
        last_message_preview=conversation.last_message_preview,
        updated_at=conversation.updated_at.isoformat(),
    )


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    current_user: CurrentUser,
    conversation_id: str,
) -> dict[str, str]:
    """Delete a conversation.

    Args:
        current_user: The authenticated user.
        conversation_id: The conversation ID.

    Returns:
        Success message.

    Raises:
        HTTPException: If conversation not found.
    """
    db = get_supabase_client()
    service = ConversationService(db_client=db)

    try:
        await service.delete_conversation(
            user_id=current_user.id,
            conversation_id=conversation_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    logger.info(
        "Conversation deleted via API",
        extra={
            "user_id": current_user.id,
            "conversation_id": conversation_id,
        },
    )

    return {"status": "deleted", "id": conversation_id}
```

**Step 3: Verify Python syntax**

Run: `cd backend && python -m py_compile src/api/routes/chat.py`
Expected: No syntax errors

**Step 4: Commit**

```bash
git add backend/src/api/routes/chat.py
git commit -m "feat(api): add conversation management endpoints"
```

---

## Task 5: Add Conversation List API to Frontend

**Files:**
- Modify: `frontend/src/api/chat.ts`

**Step 1: Update the chat API with new endpoints**

Add new types and functions to `frontend/src/api/chat.ts`. After the `Conversation` interface (after line 18), add:

```typescript
export interface ConversationListResponse {
  conversations: Conversation[];
  total: number;
}

export interface UpdateConversationTitleRequest {
  title: string;
}

export interface DeleteConversationResponse {
  status: string;
  id: string;
}
```

After the `listConversations` function (after line 43), add:

```typescript
export async function updateConversationTitle(
  conversationId: string,
  data: UpdateConversationTitleRequest
): Promise<Conversation> {
  const response = await apiClient.put<Conversation>(
    `/chat/conversations/${conversationId}/title`,
    data
  );
  return response.data;
}

export async function deleteConversation(conversationId: string): Promise<void> {
  await apiClient.delete(`/chat/conversations/${conversationId}`);
}

export async function searchConversations(query: string): Promise<Conversation[]> {
  const response = await apiClient.get<Conversation[]>("/chat/conversations", {
    params: { search: query },
  });
  return response.data;
}
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/api/chat.ts
git commit -m "feat(api): add conversation management API functions"
```

---

## Task 6: Add Conversation Hooks

**Files:**
- Modify: `frontend/src/hooks/useChat.ts`

**Step 1: Add conversation management hooks**

Add to `frontend/src/hooks/useChat.ts`. After the `chatKeys` object (after line 228), add:

```typescript
// Update conversation title mutation
export function useUpdateConversationTitle() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ conversationId, title }: { conversationId: string; title: string }) =>
      updateConversationTitle(conversationId, { title }),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: chatKeys.conversations(),
      });
      queryClient.invalidateQueries({
        queryKey: chatKeys.conversation(variables.conversationId),
      });
    },
  });
}

// Delete conversation mutation
export function useDeleteConversation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: deleteConversation,
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: chatKeys.conversations(),
      });
    },
  });
}

// Search conversations hook
export function useSearchConversations(query: string) {
  return useQuery({
    queryKey: [...chatKeys.conversations(), "search", query],
    queryFn: () => searchConversations(query),
    enabled: query.length > 0,
  });
}
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/hooks/useChat.ts
git commit -m "feat(hooks): add conversation management hooks"
```

---

## Task 7: Create ConversationSidebar Component

**Files:**
- Create: `frontend/src/components/chat/ConversationSidebar.tsx`

**Step 1: Create the sidebar component**

Create `frontend/src/components/chat/ConversationSidebar.tsx`:

```typescript
import { useState, useCallback } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  useConversations,
  useUpdateConversationTitle,
  useDeleteConversation,
  type Conversation,
} from "@/hooks/useChat";

interface ConversationSidebarProps {
  currentConversationId: string | null;
  onNewConversation: () => void;
  onConversationSelect: (conversationId: string) => void;
  isOpen: boolean;
  onClose: () => void;
}

export function ConversationSidebar({
  currentConversationId,
  onNewConversation,
  onConversationSelect,
  isOpen,
  onClose,
}: ConversationSidebarProps) {
  const location = useLocation();
  const { data: conversations, isLoading } = useConversations();
  const updateTitle = useUpdateConversationTitle();
  const deleteConversation = useDeleteConversation();

  const [searchQuery, setSearchQuery] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");

  const filteredConversations = conversations?.filter((conv) => {
    if (!searchQuery) return true;
    const title = conv.title || conv.last_message_preview || "New Conversation";
    return title.toLowerCase().includes(searchQuery.toLowerCase());
  }) || [];

  const handleStartEdit = useCallback((conv: Conversation) => {
    setEditingId(conv.id);
    setEditTitle(conv.title || "");
  }, []);

  const handleSaveTitle = useCallback(
    (conversationId: string) => {
      if (editTitle.trim()) {
        updateTitle.mutate({ conversationId, title: editTitle.trim() });
      }
      setEditingId(null);
      setEditTitle("");
    },
    [editTitle, updateTitle]
  );

  const handleCancelEdit = useCallback(() => {
    setEditingId(null);
    setEditTitle("");
  }, []);

  const handleDelete = useCallback(
    (conversationId: string, e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();

      if (window.confirm("Delete this conversation?")) {
        deleteConversation.mutate(conversationId, {
          onSuccess: () => {
            if (currentConversationId === conversationId) {
              onNewConversation();
            }
          },
        });
      }
    },
    [deleteConversation, currentConversationId, onNewConversation]
  );

  const formatTime = (dateStr: string | null) => {
    if (!dateStr) return "";
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffHours = diffMs / (1000 * 60 * 60);

    if (diffHours < 1) {
      return "Just now";
    } else if (diffHours < 24) {
      return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } else if (diffHours < 24 * 7) {
      return date.toLocaleDateString([], { weekday: "short" });
    } else {
      return date.toLocaleDateString([], { month: "short", day: "numeric" });
    }
  };

  return (
    <>
      {/* Mobile backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={onClose}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed top-0 left-0 z-50 h-full w-80 bg-slate-800/95 backdrop-blur-xl border-r border-white/5 transform transition-transform duration-300 ease-out ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        } lg:translate-x-0 lg:static lg:z-0 flex flex-col`}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-4 border-b border-white/5">
          <h2 className="text-sm font-semibold text-white uppercase tracking-wider">
            Conversations
          </h2>
          <button
            onClick={onClose}
            className="lg:hidden text-slate-400 hover:text-white transition-colors p-1"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Search */}
        <div className="p-4 border-b border-white/5">
          <div className="relative">
            <svg
              className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
              />
            </svg>
            <input
              type="text"
              placeholder="Search conversations..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-slate-900/50 text-white placeholder-slate-400 rounded-lg pl-10 pr-4 py-2 text-sm border border-white/10 focus:border-primary-500/50 focus:outline-none focus:ring-1 focus:ring-primary-500/50 transition-all"
            />
          </div>
        </div>

        {/* New conversation button */}
        <div className="p-4">
          <button
            onClick={() => {
              onNewConversation();
              onClose();
            }}
            className="w-full px-4 py-3 bg-gradient-to-r from-primary-600 to-primary-700 hover:from-primary-500 hover:to-primary-600 text-white rounded-xl font-medium transition-all duration-200 flex items-center justify-center gap-2 shadow-lg shadow-primary-500/20 hover:shadow-primary-500/30 active:scale-[0.98]"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            New Conversation
          </button>
        </div>

        {/* Conversations list */}
        <div className="flex-1 overflow-y-auto px-2 pb-4">
          {isLoading ? (
            <div className="flex items-center justify-center h-32">
              <div className="w-6 h-6 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : filteredConversations.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-sm text-slate-400">
                {searchQuery ? "No conversations found" : "No conversations yet"}
              </p>
            </div>
          ) : (
            <div className="space-y-1">
              {filteredConversations.map((conv) => (
                <div
                  key={conv.id}
                  className={`group relative rounded-xl transition-all duration-200 ${
                    currentConversationId === conv.id
                      ? "bg-primary-600/20 border border-primary-500/30"
                      : "hover:bg-slate-700/50 border border-transparent"
                  }`}
                >
                  {editingId === conv.id ? (
                    // Edit mode
                    <div className="px-3 py-3">
                      <input
                        type="text"
                        value={editTitle}
                        onChange={(e) => setEditTitle(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") handleSaveTitle(conv.id);
                          if (e.key === "Escape") handleCancelEdit();
                        }}
                        autoFocus
                        className="w-full bg-slate-900 text-white text-sm rounded-lg px-3 py-2 border border-primary-500/50 focus:outline-none focus:ring-1 focus:ring-primary-500/50"
                        onBlur={() => handleSaveTitle(conv.id)}
                      />
                    </div>
                  ) : (
                    // Display mode
                    <button
                      onClick={() => {
                        onConversationSelect(conv.id);
                        onClose();
                      }}
                      className="w-full px-3 py-3 text-left"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-white truncate">
                            {conv.title || conv.last_message_preview || "New Conversation"}
                          </p>
                          {conv.message_count > 0 && (
                            <p className="text-xs text-slate-400 mt-0.5 truncate">
                              {conv.last_message_preview || "No messages"}
                            </p>
                          )}
                        </div>
                        <span className="text-xs text-slate-500 flex-shrink-0">
                          {formatTime(conv.updated_at)}
                        </span>
                      </div>
                    </button>
                  )}

                  {/* Action buttons */}
                  {editingId !== conv.id && (
                    <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleStartEdit(conv);
                        }}
                        className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-600/50 rounded-lg transition-colors"
                        title="Rename"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"
                          />
                        </svg>
                      </button>
                      <button
                        onClick={(e) => handleDelete(conv.id, e)}
                        className="p-1.5 text-slate-400 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
                        title="Delete"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                          />
                        </svg>
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/chat/ConversationSidebar.tsx
git commit -m "feat(chat): add ConversationSidebar component with search, rename, delete"
```

---

## Task 8: Update Chat Component Index

**Files:**
- Modify: `frontend/src/components/chat/index.ts`

**Step 1: Export the new component**

Modify `frontend/src/components/chat/index.ts`:

```typescript
export { ChatInput } from "./ChatInput";
export { ChatMessage, StreamingMessage } from "./ChatMessage";
export { MarkdownRenderer } from "./MarkdownRenderer";
export { ConversationSidebar } from "./ConversationSidebar";
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/chat/index.ts
git commit -m "feat(chat): export ConversationSidebar from index"
```

---

## Task 9: Integrate Sidebar with AriaChatPage

**Files:**
- Modify: `frontend/src/pages/AriaChat.tsx`

**Step 1: Update AriaChatPage to include sidebar**

Modify `frontend/src/pages/AriaChat.tsx`:

1. Update imports:
```typescript
import { useState, useRef, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { DashboardLayout } from "@/components/DashboardLayout";
import { ChatInput, ChatMessage, StreamingMessage, ConversationSidebar } from "@/components/chat";
import { useStreamingMessage, useConversationMessages } from "@/hooks/useChat";
import type { ChatMessage as ChatMessageType } from "@/api/chat";
```

2. Add navigate and sidebar state after existing state declarations (after line 12):
```typescript
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);
```

3. Add conversation messages hook (after existing hooks, after line 13):
```typescript
  const { data: conversationMessages } = useConversationMessages(conversationId);
```

4. Update useEffect to sync messages when conversation is selected (after the existing useEffect for scroll, after line 23):
```typescript
  // Load conversation messages when selected
  useEffect(() => {
    if (conversationId && conversationMessages) {
      setMessages(conversationMessages);
    }
  }, [conversationId, conversationMessages]);
```

5. Update handleSend to include conversation loading (replace existing handleSend, starting at line 24):
```typescript
  const handleSend = useCallback(
    (content: string) => {
      // Add user message immediately
      const userMessage: ChatMessageType = {
        id: crypto.randomUUID(),
        conversation_id: conversationId || "",
        role: "user",
        content,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMessage]);

      // Reset any previous stream state
      reset();

      // Start streaming
      cancelStreamRef.current = startStream(
        {
          content,
          conversation_id: conversationId || undefined,
        },
        (assistantMessage) => {
          // On complete, add the full message and navigate to conversation
          setMessages((prev) => {
            // Remove the temporary user message and add both messages properly
            const withoutTemp = prev.slice(0, -1);
            return [...withoutTemp, userMessage, assistantMessage];
          });

          // Update conversation ID and navigate
          const newConversationId = assistantMessage.conversation_id;
          setConversationId(newConversationId);
          navigate(`/dashboard/aria?c=${newConversationId}`, { replace: true });
          reset();
        }
      );
    },
    [conversationId, startStream, reset, navigate]
  );
```

6. Update handleNewConversation (replace existing, around line 65):
```typescript
  const handleNewConversation = useCallback(() => {
    setMessages([]);
    setConversationId(null);
    reset();
    navigate("/dashboard/aria", { replace: true });
  }, [reset, navigate]);

  const handleConversationSelect = useCallback((convId: string) => {
    setConversationId(convId);
    navigate(`/dashboard/aria?c=${convId}`, { replace: true });
  }, [navigate]);
```

7. Update the return statement to add sidebar toggle button (in header, find the New Chat button and add sidebar toggle before it, around line 107):
```typescript
          <div className="flex items-center gap-3">
            {/* Sidebar toggle button (shows on desktop) */}
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="hidden lg:flex px-3 py-2 text-sm font-medium text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-all duration-200 items-center gap-2"
            >
              <svg
                className="w-4 h-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                {sidebarOpen ? (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
                ) : (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 5l7 7-7 7M5 5l7 7-7 7" />
                )}
              </svg>
            </button>

            {/* Mobile menu button */}
            <button
              onClick={() => setSidebarOpen(true)}
              className="lg:hidden px-3 py-2 text-sm font-medium text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-all duration-200"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
          </div>
```

8. Wrap the entire main content with sidebar (update the outermost div, around line 72):
```typescript
  return (
    <DashboardLayout>
      <div className="relative h-[calc(100vh-4rem)] flex">
        {/* Conversation Sidebar */}
        <ConversationSidebar
          currentConversationId={conversationId}
          onNewConversation={handleNewConversation}
          onConversationSelect={handleConversationSelect}
          isOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
        />

        {/* Main chat area */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Existing content - atmospheric background through input area */}
          {/* Keep all the existing content, just wrap it in this div */}
```

9. Close the wrapper div at the end (before closing DashboardLayout tag):
```typescript
        </div>
      </div>
    </DashboardLayout>
  );
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/pages/AriaChat.tsx
git commit -m "feat(chat): integrate ConversationSidebar with AriaChatPage"
```

---

## Task 10: Handle URL Parameter for Conversation Selection

**Files:**
- Modify: `frontend/src/pages/AriaChat.tsx`

**Step 1: Load conversation from URL on mount**

Add URL parameter handling. After the existing imports, add `useSearchParams`:
```typescript
import { useState, useRef, useEffect, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
```

Add after the other hooks (around line 14):
```typescript
  const [searchParams] = useSearchParams();
```

Add a useEffect to handle URL parameter (after the existing useEffects, around line 70):
```typescript
  // Handle URL parameter for conversation selection
  useEffect(() => {
    const convId = searchParams.get("c");
    if (convId && convId !== conversationId) {
      setConversationId(convId);
    }
  }, [searchParams, conversationId]);
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/pages/AriaChat.tsx
git commit -m "feat(chat): add URL parameter handling for conversation selection"
```

---

## Task 11: Add Mobile Menu Button to DashboardLayout

**Files:**
- Modify: `frontend/src/components/DashboardLayout.tsx`

**Step 1: Add mobile menu button to header**

The header already has a mobile menu button (lines 192-209). Verify it's present and working.

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit (if changes made)**

```bash
git add frontend/src/components/DashboardLayout.tsx
git commit -m "refactor(layout): ensure mobile menu button exists in header"
```

---

## Task 12: Final Verification and Quality Gates

**Files:**
- All modified/created files

**Step 1: Run backend type check**

Run: `cd backend && mypy src/ --strict`
Expected: No errors (or only existing known errors)

**Step 2: Run backend tests**

Run: `cd backend && pytest tests/ -v`
Expected: Tests pass

**Step 3: Run frontend type check**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 4: Run frontend lint**

Run: `cd frontend && npm run lint`
Expected: No errors or warnings

**Step 5: Run frontend build**

Run: `cd frontend && npm run build`
Expected: Build completes successfully

**Step 6: Manual verification checklist**

Start both servers:
```bash
# Terminal 1
cd backend && uvicorn src.main:app --reload --port 8000

# Terminal 2
cd frontend && npm run dev
```

Navigate to: `http://localhost:3000/dashboard/aria`

Verify:
- [ ] Sidebar appears on desktop (left of chat area)
- [ ] Sidebar can be toggled open/closed on desktop
- [ ] Mobile menu button opens sidebar on mobile
- [ ] New Conversation button creates new conversation
- [ ] Conversations list shows existing conversations
- [ ] Clicking a conversation loads its messages
- [ ] Conversation title or preview is displayed
- [ ] Time stamps are formatted correctly
- [ ] Search filters conversations by title
- [ ] Edit button allows renaming conversations
- [ ] Delete button removes conversation with confirmation
- [ ] URL updates when conversation is selected
- [ ] Refreshing page maintains selected conversation
- [ ] Styling matches US-402 premium aesthetic

**Step 7: Final commit with summary**

```bash
git add -A
git commit -m "feat(US-403): implement Conversation Management

- Add conversations table with RLS policies
- Add ConversationService for CRUD operations
- Add conversation API endpoints (list, get, update title, delete)
- Integrate conversation tracking into ChatService
- Add ConversationSidebar component with search, rename, delete
- Integrate sidebar with AriaChatPage
- Add URL parameter handling for conversation selection
- Premium Apple-inspired styling matching US-402

Closes US-403"
```

---

## Summary of Files Created/Modified

### Created (2 files):
- `backend/supabase/migrations/20260202000006_create_conversations.sql` - Conversations table
- `backend/src/services/conversations.py` - ConversationService
- `frontend/src/components/chat/ConversationSidebar.tsx` - Sidebar component

### Modified (5 files):
- `backend/src/services/chat.py` - Add conversation tracking
- `backend/src/api/routes/chat.py` - Add conversation endpoints
- `frontend/src/api/chat.ts` - Add conversation API functions
- `frontend/src/hooks/useChat.ts` - Add conversation hooks
- `frontend/src/components/chat/index.ts` - Export sidebar
- `frontend/src/pages/AriaChat.tsx` - Integrate sidebar

---

## Notes for Implementation

1. **Message Persistence**: Currently, messages are stored in working memory (Redis). For production persistence, create a `messages` table and update `get_conversation_messages` to query it.

2. **Auto-Generated Titles**: Title generation is not implemented. Titles default to showing the last message preview. To add auto-generation, use the LLM to generate a title from the first few messages.

3. **Salience Tracking**: The conversation table doesn't include salience tracking like conversation_episodes. Consider adding this if you want conversations to be surfaced in intelligence pulse.

4. **Mobile Experience**: The sidebar is hidden by default on mobile and slides in when triggered. Ensure the close button works properly on small screens.

5. **Search Performance**: The search implementation uses PostgreSQL ILIKE on the title column. For better performance with many conversations, consider using full-text search with `to_tsvector`.

6. **Deleting Conversations**: This implementation deletes the conversation record and clears working memory, but preserves conversation episodes for historical context. Adjust this behavior if needed.

7. **URL Sharing**: The URL parameter approach allows deep-linking to specific conversations. The format is `/dashboard/aria?c={conversation_id}`.
