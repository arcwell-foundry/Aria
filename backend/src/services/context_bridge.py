"""Context bridge service for cross-modality continuity.

Ensures seamless context transfer between chat and video surfaces:
- chat_to_video_context: loads recent chat into Tavus conversational context
- video_to_chat_context: persists video transcript/outcomes back into chat
- bridge_active_session: links a video session to a chat conversation
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from src.core.llm import LLMClient
from src.core.ws import ws_manager
from src.db.supabase import SupabaseClient
from src.memory.prospective import (
    ProspectiveMemory,
    ProspectiveTask,
    TaskPriority,
    TaskStatus,
    TriggerType,
)
from src.memory.working import WorkingMemoryManager

logger = logging.getLogger(__name__)

# Maximum chat messages to include in video context
_MAX_CHAT_MESSAGES = 10

# Maximum active goals to include in context
_MAX_GOALS = 3

_TRANSCRIPT_EXTRACTION_PROMPT = """\
You are analysing a video conversation transcript between ARIA (an AI colleague) and a user.

Extract the following as JSON:
{
  "summary": "2-3 sentence summary of what was discussed",
  "action_items": [
    {"task": "short description", "priority": "low|medium|high|urgent"}
  ],
  "commitments": ["things ARIA promised to do"]
}

Only include action_items that are clearly stated tasks or follow-ups.
Return valid JSON only, no markdown fencing."""


class ContextBridgeService:
    """Bidirectional context bridge between chat and video modalities.

    Follows the lazy initialisation pattern used by ChatService.
    """

    def __init__(self) -> None:
        self._llm_client: LLMClient | None = None
        self._working_memory: WorkingMemoryManager | None = None
        self._prospective: ProspectiveMemory | None = None

    # -- lazy properties --------------------------------------------------

    @property
    def llm(self) -> LLMClient:
        if self._llm_client is None:
            self._llm_client = LLMClient()
        return self._llm_client

    @property
    def working_memory(self) -> WorkingMemoryManager:
        if self._working_memory is None:
            self._working_memory = WorkingMemoryManager()
        return self._working_memory

    @property
    def prospective(self) -> ProspectiveMemory:
        if self._prospective is None:
            self._prospective = ProspectiveMemory()
        return self._prospective

    # -- public API -------------------------------------------------------

    async def chat_to_video_context(
        self,
        user_id: str,
        conversation_id: str | None = None,
    ) -> str:
        """Build a spoken-friendly context string from the active chat.

        Args:
            user_id: The user's UUID.
            conversation_id: Optional chat conversation to pull history from.

        Returns:
            Plain-text context string suitable for Tavus conversational_context.
        """
        db = SupabaseClient.get_client()
        parts: list[str] = []

        # 1. Recent chat messages
        if conversation_id:
            messages = await self._load_recent_messages(db, conversation_id)
            if messages:
                summary = self._summarise_messages(messages)
                parts.append(f"Recent chat context: {summary}")

        # 2. Working memory (entities + current goal)
        if conversation_id:
            try:
                wm = await self.working_memory.get_or_create(conversation_id, user_id)
                if wm.current_goal:
                    goal_obj = wm.current_goal.get("objective", "")
                    if goal_obj:
                        parts.append(f"Current focus: {goal_obj}")
                if wm.active_entities:
                    entity_names = list(wm.active_entities.keys())[:5]
                    if entity_names:
                        parts.append(f"Key entities in discussion: {', '.join(entity_names)}")
            except Exception:
                logger.debug("Could not load working memory for context bridge", exc_info=True)

        # 3. Active goals
        try:
            goals_result = (
                db.table("goals")
                .select("title")
                .eq("user_id", user_id)
                .eq("status", "active")
                .order("priority", desc=True)
                .limit(_MAX_GOALS)
                .execute()
            )
            if goals_result.data:
                titles = [g["title"] for g in goals_result.data]
                parts.append(f"Active goals: {', '.join(titles)}")
        except Exception:
            logger.debug("Could not load goals for context bridge", exc_info=True)

        return "\n".join(parts) if parts else ""

    async def video_to_chat_context(
        self,
        user_id: str,
        video_session_id: str,
    ) -> dict[str, Any]:
        """Persist video session outcomes back into the linked chat.

        Stores transcript as messages, extracts action items, updates
        working memory, and posts a summary message via WebSocket.

        Args:
            user_id: The user's UUID.
            video_session_id: The video session that just ended.

        Returns:
            Dict with summary, action_items, messages_stored, tasks_created.
        """
        db = SupabaseClient.get_client()

        # Look up session and its linked conversation
        session_result = (
            db.table("video_sessions")
            .select("id, conversation_id, session_type")
            .eq("id", video_session_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not session_result.data:
            logger.warning("video_to_chat_context: session not found %s", video_session_id)
            return {"summary": "", "action_items": [], "messages_stored": 0, "tasks_created": 0}

        session = session_result.data[0]
        conversation_id: str | None = session.get("conversation_id")

        # Fetch transcript
        transcript_result = (
            db.table("video_transcript_entries")
            .select("speaker, content, timestamp_ms")
            .eq("video_session_id", video_session_id)
            .order("timestamp_ms")
            .execute()
        )
        entries = transcript_result.data or []
        if not entries:
            logger.info("video_to_chat_context: no transcript entries for %s", video_session_id)
            return {"summary": "", "action_items": [], "messages_stored": 0, "tasks_created": 0}

        # Group consecutive same-speaker entries
        grouped = self._group_transcript_entries(entries)

        # Store as messages in the linked conversation
        messages_stored = 0
        if conversation_id:
            messages_stored = await self._store_transcript_messages(
                db, conversation_id, grouped, video_session_id
            )

        # Extract summary + action items via LLM
        full_transcript = "\n".join(
            f"{'User' if e['speaker'] == 'user' else 'ARIA'}: {e['content']}" for e in entries
        )
        extraction = await self._extract_outcomes(full_transcript)

        summary = extraction.get("summary", "")
        action_items = extraction.get("action_items", [])
        commitments = extraction.get("commitments", [])

        # Create prospective tasks for action items
        tasks_created = 0
        for item in action_items:
            try:
                priority_str = item.get("priority", "medium")
                try:
                    priority = TaskPriority(priority_str)
                except ValueError:
                    priority = TaskPriority.MEDIUM
                task = ProspectiveTask(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    task=item.get("task", "Follow up from video session"),
                    description=f"From video session {video_session_id}",
                    trigger_type=TriggerType.TIME,
                    trigger_config={},
                    status=TaskStatus.PENDING,
                    priority=priority,
                    related_goal_id=None,
                    related_lead_id=None,
                    completed_at=None,
                    created_at=datetime.now(UTC),
                )
                await self.prospective.create_task(task)
                tasks_created += 1
            except Exception:
                logger.warning("Failed to create prospective task from video", exc_info=True)

        # Update working memory with summary
        if conversation_id:
            try:
                wm = await self.working_memory.get_or_create(conversation_id, user_id)
                wm.set_entity(
                    "last_video_session",
                    {
                        "session_id": video_session_id,
                        "summary": summary,
                        "action_items": [i.get("task", "") for i in action_items],
                        "commitments": commitments,
                    },
                )
                await self.working_memory.persist_session(conversation_id)
            except Exception:
                logger.warning("Failed to update working memory from video", exc_info=True)

        # Build and post summary message into chat
        summary_message = self._build_summary_message(summary, action_items, commitments)
        if conversation_id:
            try:
                msg_id = str(uuid.uuid4())
                db.table("messages").insert(
                    {
                        "id": msg_id,
                        "conversation_id": conversation_id,
                        "role": "assistant",
                        "content": summary_message,
                        "metadata": {
                            "source": "video",
                            "video_session_id": video_session_id,
                            "type": "video_summary",
                        },
                    }
                ).execute()
            except Exception:
                logger.warning("Failed to persist video summary message", exc_info=True)

        # Send via WebSocket for real-time delivery
        await ws_manager.send_aria_message(
            user_id=user_id,
            message=summary_message,
            rich_content=[
                {
                    "type": "video_session_summary",
                    "video_session_id": video_session_id,
                    "summary": summary,
                    "action_items": action_items,
                }
            ],
            suggestions=["Show me the full transcript", "Adjust those action items"],
        )

        return {
            "summary": summary,
            "action_items": action_items,
            "messages_stored": messages_stored,
            "tasks_created": tasks_created,
        }

    async def bridge_active_session(
        self,
        user_id: str,
        video_session_id: str,
        conversation_id: str,
    ) -> None:
        """Link a video session to a chat conversation.

        Args:
            user_id: The user's UUID (for authorization scoping).
            video_session_id: The video session to link.
            conversation_id: The chat conversation to link to.
        """
        db = SupabaseClient.get_client()
        db.table("video_sessions").update({"conversation_id": conversation_id}).eq(
            "id", video_session_id
        ).eq("user_id", user_id).execute()

        logger.info(
            "Linked video session to conversation",
            extra={
                "video_session_id": video_session_id,
                "conversation_id": conversation_id,
                "user_id": user_id,
            },
        )

    # -- private helpers --------------------------------------------------

    async def _load_recent_messages(self, db: Any, conversation_id: str) -> list[dict[str, Any]]:
        """Load the most recent messages from a conversation."""
        try:
            result = (
                db.table("messages")
                .select("role, content, created_at")
                .eq("conversation_id", conversation_id)
                .order("created_at", desc=True)
                .limit(_MAX_CHAT_MESSAGES)
                .execute()
            )
            rows = result.data or []
            rows.reverse()  # chronological order
            return rows
        except Exception:
            logger.warning("Failed to load recent messages for context bridge", exc_info=True)
            return []

    @staticmethod
    def _summarise_messages(messages: list[dict[str, Any]]) -> str:
        """Produce a spoken-friendly summary of recent messages."""
        parts: list[str] = []
        for msg in messages[-_MAX_CHAT_MESSAGES:]:
            role = "User" if msg["role"] == "user" else "ARIA"
            content = msg["content"]
            # Truncate long messages for context window
            if len(content) > 300:
                content = content[:297] + "..."
            parts.append(f"{role}: {content}")
        return "\n".join(parts)

    @staticmethod
    def _group_transcript_entries(
        entries: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Group consecutive same-speaker transcript entries."""
        if not entries:
            return []

        grouped: list[dict[str, Any]] = []
        current_speaker = entries[0]["speaker"]
        current_parts: list[str] = [entries[0]["content"]]

        for entry in entries[1:]:
            if entry["speaker"] == current_speaker:
                current_parts.append(entry["content"])
            else:
                grouped.append(
                    {
                        "speaker": current_speaker,
                        "content": " ".join(current_parts),
                    }
                )
                current_speaker = entry["speaker"]
                current_parts = [entry["content"]]

        grouped.append(
            {
                "speaker": current_speaker,
                "content": " ".join(current_parts),
            }
        )
        return grouped

    @staticmethod
    async def _store_transcript_messages(
        db: Any,
        conversation_id: str,
        grouped: list[dict[str, Any]],
        video_session_id: str,
    ) -> int:
        """Store grouped transcript entries as chat messages."""
        stored = 0
        for entry in grouped:
            role = "user" if entry["speaker"] == "user" else "assistant"
            try:
                db.table("messages").insert(
                    {
                        "id": str(uuid.uuid4()),
                        "conversation_id": conversation_id,
                        "role": role,
                        "content": entry["content"],
                        "metadata": {
                            "source": "video",
                            "video_session_id": video_session_id,
                        },
                    }
                ).execute()
                stored += 1
            except Exception:
                logger.warning("Failed to store transcript message", exc_info=True)
        return stored

    async def _extract_outcomes(self, transcript: str) -> dict[str, Any]:
        """Use LLM to extract summary, action items, and commitments."""
        try:
            raw = await self.llm.generate_response(
                messages=[{"role": "user", "content": transcript}],
                system_prompt=_TRANSCRIPT_EXTRACTION_PROMPT,
                max_tokens=1024,
                temperature=0.3,
            )
            return json.loads(raw)
        except (json.JSONDecodeError, Exception):
            logger.warning("LLM extraction from transcript failed", exc_info=True)
            return {"summary": "", "action_items": [], "commitments": []}

    @staticmethod
    def _build_summary_message(
        summary: str,
        action_items: list[dict[str, Any]],
        commitments: list[str],
    ) -> str:
        """Format the post-video summary as a chat message."""
        parts = ["I just finished our video session."]

        if summary:
            parts.append(f"Here's what we covered: {summary}")

        if action_items:
            items_text = "\n".join(f"- {i.get('task', '')}" for i in action_items)
            parts.append(f"\nAction items I've queued:\n{items_text}")

        if commitments:
            commits_text = "\n".join(f"- {c}" for c in commitments)
            parts.append(f"\nI committed to:\n{commits_text}")

        parts.append("\nAnything you'd like to adjust?")
        return "\n".join(parts)


# Module-level singleton
_context_bridge: ContextBridgeService | None = None


def get_context_bridge() -> ContextBridgeService:
    """Get or create the ContextBridgeService singleton."""
    global _context_bridge
    if _context_bridge is None:
        _context_bridge = ContextBridgeService()
    return _context_bridge
