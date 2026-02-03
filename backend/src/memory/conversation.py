"""Conversation episode service for extracting durable memories.

Extracts structured information from conversations:
- Summary of key points
- Topics discussed
- Entities mentioned
- User emotional/cognitive state
- Outcomes and decisions
- Open threads requiring follow-up
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.core.llm import LLMClient
    from supabase import Client

logger = logging.getLogger(__name__)


@dataclass
class ConversationEpisode:
    """A durable memory extracted from a conversation.

    Represents the essential content of a conversation that should
    persist beyond the session for future context priming.
    """

    id: str
    user_id: str
    conversation_id: str
    summary: str
    key_topics: list[str]
    entities_discussed: list[str]
    user_state: dict[str, Any]
    outcomes: list[dict[str, Any]]
    open_threads: list[dict[str, Any]]
    message_count: int
    duration_minutes: int
    started_at: datetime
    ended_at: datetime
    current_salience: float = 1.0
    last_accessed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    access_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "conversation_id": self.conversation_id,
            "summary": self.summary,
            "key_topics": self.key_topics,
            "entities_discussed": self.entities_discussed,
            "user_state": self.user_state,
            "outcomes": self.outcomes,
            "open_threads": self.open_threads,
            "message_count": self.message_count,
            "duration_minutes": self.duration_minutes,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat(),
            "current_salience": self.current_salience,
            "last_accessed_at": self.last_accessed_at.isoformat(),
            "access_count": self.access_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConversationEpisode:
        """Create a ConversationEpisode from a dictionary."""
        started_at = data["started_at"]
        ended_at = data["ended_at"]
        last_accessed = data.get("last_accessed_at")

        if isinstance(started_at, str):
            started_at = datetime.fromisoformat(started_at)
        if isinstance(ended_at, str):
            ended_at = datetime.fromisoformat(ended_at)
        if isinstance(last_accessed, str):
            last_accessed = datetime.fromisoformat(last_accessed)

        return cls(
            id=data["id"],
            user_id=data["user_id"],
            conversation_id=data["conversation_id"],
            summary=data["summary"],
            key_topics=data.get("key_topics", []),
            entities_discussed=data.get("entities_discussed", []),
            user_state=data.get("user_state", {}),
            outcomes=data.get("outcomes", []),
            open_threads=data.get("open_threads", []),
            message_count=data.get("message_count", 0),
            duration_minutes=data.get("duration_minutes", 0),
            started_at=started_at,
            ended_at=ended_at,
            current_salience=data.get("current_salience", 1.0),
            last_accessed_at=last_accessed or datetime.now(UTC),
            access_count=data.get("access_count", 0),
        )


# LLM prompts for episode extraction
SUMMARY_PROMPT = """Summarize this conversation concisely in 2-3 sentences:

{conversation}

Focus on:
- Key decisions made
- Important information shared
- Action items agreed
- Questions left unanswered

Summary:"""

EXTRACTION_PROMPT = """Analyze this conversation and extract structured information:

{conversation}

Return a JSON object with:
- "key_topics": list of 3-5 main topics discussed (short phrases)
- "user_state": object with "mood" (stressed/neutral/positive), "confidence" (uncertain/moderate/high), "focus" (main area of attention)
- "outcomes": list of objects with "type" (decision/action_item/information) and "content" (what was decided/agreed)
- "open_threads": list of objects with "topic", "status" (pending/awaiting_response/blocked), and "context" (brief explanation)

Return ONLY valid JSON, no explanation:"""


class ConversationService:
    """Service for extracting and storing conversation episodes.

    Extracts durable memories from conversations including:
    - Summary of key points
    - Topics discussed
    - User emotional/cognitive state
    - Outcomes and decisions made
    - Open threads requiring follow-up
    """

    IDLE_THRESHOLD_MINUTES = 30

    def __init__(
        self,
        db_client: Client,
        llm_client: LLMClient,
    ) -> None:
        """Initialize the conversation service.

        Args:
            db_client: Supabase client for database operations.
            llm_client: LLM client for Claude API calls.
        """
        self.db = db_client
        self.llm = llm_client

    def _format_messages(self, messages: list[dict[str, str]]) -> str:
        """Format messages as readable conversation text.

        Args:
            messages: List of message dicts with 'role' and 'content'.

        Returns:
            Formatted conversation string.
        """
        if not messages:
            return ""

        lines = []
        for msg in messages:
            role = msg.get("role", "unknown").capitalize()
            content = msg.get("content", "")
            lines.append(f"{role}: {content}")

        return "\n\n".join(lines)

    def _get_message_timestamp(self, message: dict[str, Any]) -> datetime:
        """Extract timestamp from a message.

        Args:
            message: Message dict that may contain 'created_at' field.

        Returns:
            Datetime of the message, or current time if not available.
        """
        created_at = message.get("created_at")
        if created_at is None:
            return datetime.now(UTC)
        if isinstance(created_at, datetime):
            return created_at
        if isinstance(created_at, str):
            return datetime.fromisoformat(created_at)
        return datetime.now(UTC)

    def _parse_extraction_response(self, response: str) -> dict[str, Any]:
        """Parse LLM extraction response JSON.

        Handles malformed JSON gracefully by returning defaults.

        Args:
            response: LLM response string that should be JSON.

        Returns:
            Parsed dict with extracted fields, or defaults if parsing fails.
        """
        defaults: dict[str, Any] = {
            "key_topics": [],
            "user_state": {},
            "outcomes": [],
            "open_threads": [],
        }

        try:
            parsed = json.loads(response)
            # Validate and merge with defaults
            return {
                "key_topics": parsed.get("key_topics", []),
                "user_state": parsed.get("user_state", {}),
                "outcomes": parsed.get("outcomes", []),
                "open_threads": parsed.get("open_threads", []),
            }
        except json.JSONDecodeError:
            logger.warning(
                "Failed to parse LLM extraction response as JSON",
                extra={"response_preview": response[:100]},
            )
            return defaults

    async def _extract_entities(
        self,
        messages: list[dict[str, Any]],  # noqa: ARG002
    ) -> list[str]:
        """Extract entity names from conversation messages.

        This is a stub that returns an empty list.
        Full Graphiti integration will be added in Task 6.

        Args:
            messages: List of conversation messages.

        Returns:
            List of entity names (currently empty).
        """
        # TODO: Implement Graphiti entity extraction in Task 6
        return []

    async def extract_episode(
        self,
        user_id: str,
        conversation_id: str,
        messages: list[dict[str, Any]],
    ) -> ConversationEpisode:
        """Extract durable content from a conversation.

        Uses LLM to generate summary and extract structured information,
        then stores as a conversation episode.

        Args:
            user_id: The user's ID.
            conversation_id: Unique conversation identifier.
            messages: List of message dicts with 'role', 'content', and 'created_at'.

        Returns:
            The created ConversationEpisode.

        Raises:
            ValueError: If messages list is empty.
            RuntimeError: If database storage fails.
        """
        if not messages:
            raise ValueError("Cannot extract episode from empty conversation")

        # Format messages for LLM
        formatted_conversation = self._format_messages(messages)

        # Step 1: Generate summary using LLM
        summary_prompt = SUMMARY_PROMPT.format(conversation=formatted_conversation)
        summary = await self.llm.generate_response(
            messages=[{"role": "user", "content": summary_prompt}],
            max_tokens=500,
            temperature=0.3,
        )

        # Step 2: Extract structured information using LLM
        extraction_prompt = EXTRACTION_PROMPT.format(conversation=formatted_conversation)
        extraction_response = await self.llm.generate_response(
            messages=[{"role": "user", "content": extraction_prompt}],
            max_tokens=1000,
            temperature=0.2,
        )

        # Parse the extraction response (handles malformed JSON gracefully)
        extracted = self._parse_extraction_response(extraction_response)

        # Step 3: Extract entities (stub for now)
        entities = await self._extract_entities(messages)

        # Step 4: Calculate duration from timestamps
        if messages:
            started_at = self._get_message_timestamp(messages[0])
            ended_at = self._get_message_timestamp(messages[-1])
            duration_seconds = (ended_at - started_at).total_seconds()
            duration_minutes = max(1, int(duration_seconds / 60))
        else:
            now = datetime.now(UTC)
            started_at = now
            ended_at = now
            duration_minutes = 0

        # Step 5: Prepare episode data for database
        now = datetime.now(UTC)
        episode_data = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "summary": summary.strip(),
            "key_topics": extracted["key_topics"],
            "entities_discussed": entities,
            "user_state": extracted["user_state"],
            "outcomes": extracted["outcomes"],
            "open_threads": extracted["open_threads"],
            "message_count": len(messages),
            "duration_minutes": duration_minutes,
            "started_at": started_at.isoformat(),
            "ended_at": ended_at.isoformat(),
            "current_salience": 1.0,
            "last_accessed_at": now.isoformat(),
            "access_count": 0,
        }

        # Step 6: Store in database
        result = self.db.table("conversation_episodes").insert(episode_data).execute()

        if not result.data:
            raise RuntimeError("Failed to store conversation episode")

        # Step 7: Return ConversationEpisode from stored data
        stored_data: dict[str, Any] = result.data[0]  # type: ignore[assignment]
        return ConversationEpisode.from_dict(stored_data)

    async def get_recent_episodes(
        self,
        user_id: str,
        limit: int = 5,
        min_salience: float = 0.1,
    ) -> list[ConversationEpisode]:
        """Get recent conversation episodes for context priming.

        Args:
            user_id: The user's ID.
            limit: Maximum number of episodes to return.
            min_salience: Minimum salience threshold.

        Returns:
            List of recent ConversationEpisode objects.
        """
        result = (
            self.db.table("conversation_episodes")
            .select("*")
            .eq("user_id", user_id)
            .gte("current_salience", min_salience)
            .order("ended_at", desc=True)
            .limit(limit)
            .execute()
        )

        if not result.data:
            return []

        return [ConversationEpisode.from_dict(ep) for ep in result.data]

    async def get_open_threads(
        self,
        user_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get all unresolved threads across conversations.

        Args:
            user_id: The user's ID.
            limit: Maximum number of threads to return.

        Returns:
            List of open thread dicts with conversation context.
        """
        result = (
            self.db.table("conversation_episodes")
            .select("open_threads, ended_at, conversation_id")
            .eq("user_id", user_id)
            .neq("open_threads", [])
            .order("ended_at", desc=True)
            .limit(20)  # Fetch more episodes to gather enough threads
            .execute()
        )

        if not result.data:
            return []

        # Flatten threads from all episodes
        threads: list[dict[str, Any]] = []
        for ep in result.data:
            ep_threads = ep.get("open_threads", [])
            if not ep_threads:
                continue
            for thread in ep_threads:
                thread_with_context = {
                    **thread,
                    "from_conversation": ep["conversation_id"],
                    "conversation_ended": ep["ended_at"],
                }
                threads.append(thread_with_context)

        return threads[:limit]

    async def get_episode(
        self,
        user_id: str,
        episode_id: str,
    ) -> ConversationEpisode | None:
        """Get a specific episode by ID.

        Args:
            user_id: The user's ID.
            episode_id: The episode's UUID.

        Returns:
            ConversationEpisode or None if not found.
        """
        result = (
            self.db.table("conversation_episodes")
            .select("*")
            .eq("user_id", user_id)
            .eq("id", episode_id)
            .single()
            .execute()
        )

        if not result.data:
            return None

        return ConversationEpisode.from_dict(result.data)
