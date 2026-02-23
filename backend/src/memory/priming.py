"""Conversation priming service for context continuity.

Gathers context at conversation start:
- Recent conversation episodes
- Open threads requiring follow-up
- High-salience facts
- Relevant entities from knowledge graph

Provides formatted context for LLM consumption.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.memory.conversation import ConversationService
    from src.memory.salience import SalienceService
    from supabase import Client

logger = logging.getLogger(__name__)


@dataclass
class ConversationContext:
    """Context gathered for priming a new conversation.

    Contains all relevant information from past interactions
    to help ARIA continue naturally with the user.
    """

    recent_episodes: list[dict[str, Any]]
    open_threads: list[dict[str, Any]]
    salient_facts: list[dict[str, Any]]
    relevant_entities: list[dict[str, Any]]
    formatted_context: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary."""
        return {
            "recent_episodes": self.recent_episodes,
            "open_threads": self.open_threads,
            "salient_facts": self.salient_facts,
            "relevant_entities": self.relevant_entities,
            "formatted_context": self.formatted_context,
        }


class ConversationPrimingService:
    """Service for priming new conversations with relevant context.

    Gathers:
    - Recent conversation episodes (max 3)
    - Open threads requiring follow-up (max 5)
    - High-salience facts (min 0.3, max 10)
    - Relevant entities from knowledge graph

    Target performance: < 500ms for full priming.
    """

    MAX_EPISODES = 3
    MAX_THREADS = 5
    MAX_FACTS = 10
    SALIENCE_THRESHOLD = 0.3

    def __init__(
        self,
        conversation_service: ConversationService,
        salience_service: SalienceService,
        db_client: Client,
        graphiti_client: Any | None = None,
    ) -> None:
        """Initialize the priming service.

        Args:
            conversation_service: Service for episode/thread retrieval.
            salience_service: Service for salience-based memory lookup.
            db_client: Supabase client for direct queries.
            graphiti_client: Optional Graphiti client for entity context.
        """
        self.conversations = conversation_service
        self.salience = salience_service
        self.db = db_client
        self.graphiti = graphiti_client

    async def prime_conversation(
        self,
        user_id: str,
        initial_message: str | None = None,  # noqa: ARG002
    ) -> ConversationContext:
        """Gather context for starting a new conversation.

        Uses parallel fetching for performance (< 500ms target).

        Args:
            user_id: The user's ID.
            initial_message: Optional first message to find relevant entities.

        Returns:
            ConversationContext with all gathered information.
        """
        # Parallel fetch: episodes, threads, and salient fact IDs
        episodes_task = self.conversations.get_recent_episodes(
            user_id=user_id,
            limit=self.MAX_EPISODES,
            min_salience=self.SALIENCE_THRESHOLD,
        )
        threads_task = self.conversations.get_open_threads(
            user_id=user_id,
            limit=self.MAX_THREADS,
        )
        salience_task = self.salience.get_by_salience(
            user_id=user_id,
            memory_type="semantic",
            min_salience=self.SALIENCE_THRESHOLD,
            limit=self.MAX_FACTS,
        )

        episodes, threads, salient_records = await asyncio.gather(
            episodes_task,
            threads_task,
            salience_task,
        )

        # Fetch fact details for salient records
        facts = await self._fetch_fact_details(user_id, salient_records)

        # Convert episodes to dicts
        episode_dicts = [self._episode_to_dict(ep) for ep in episodes]

        # Get relevant entities (placeholder for now)
        entities: list[dict[str, Any]] = []

        # Format context for LLM
        formatted = self._format_context(episode_dicts, threads, facts, entities)

        return ConversationContext(
            recent_episodes=episode_dicts,
            open_threads=threads,
            salient_facts=facts,
            relevant_entities=entities,
            formatted_context=formatted,
        )

    async def _fetch_fact_details(
        self,
        user_id: str,
        salient_records: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Fetch full fact details for salient memory records.

        Args:
            user_id: The user's ID.
            salient_records: Records from salience service with graphiti_episode_id.

        Returns:
            List of fact dictionaries with full details.
        """
        facts: list[dict[str, Any]] = []

        # Query memory_semantic table (onboarding facts)
        try:
            result = (
                self.db.table("memory_semantic")
                .select("id, fact, confidence")
                .eq("user_id", user_id)
                .order("confidence", desc=True)
                .limit(self.MAX_FACTS // 2)  # Split between sources
                .execute()
            )
            if result.data:
                for item in result.data:
                    facts.append({
                        "id": item["id"],
                        "subject": item["fact"],
                        "predicate": "",
                        "object": "",
                        "confidence": item.get("confidence", 1.0),
                        "source": "onboarding",
                    })
        except Exception as e:
            logger.error(
                "Failed to fetch memory_semantic for user %s: %s",
                user_id,
                str(e),
            )

        # Also query semantic_facts table (conversation-extracted facts)
        try:
            result = (
                self.db.table("semantic_facts")
                .select("id, subject, predicate, object, confidence")
                .eq("user_id", user_id)
                .order("confidence", desc=True)
                .limit(self.MAX_FACTS // 2)
                .execute()
            )
            if result.data:
                for item in result.data:
                    facts.append({
                        "id": item["id"],
                        "subject": item["subject"],
                        "predicate": item["predicate"],
                        "object": item["object"],
                        "confidence": item.get("confidence", 0.75),
                        "source": "conversation",
                    })
        except Exception as e:
            logger.error(
                "Failed to fetch semantic_facts for user %s: %s",
                user_id,
                str(e),
            )

        # Sort by confidence and limit
        facts.sort(key=lambda x: x.get("confidence", 0), reverse=True)
        return facts[: self.MAX_FACTS]

    def _episode_to_dict(self, episode: Any) -> dict[str, Any]:
        """Convert episode to serializable dict.

        Args:
            episode: ConversationEpisode object.

        Returns:
            Dictionary representation.
        """
        ended_at = episode.ended_at
        ended_at = ended_at.isoformat() if hasattr(ended_at, "isoformat") else str(ended_at)

        return {
            "summary": episode.summary,
            "topics": episode.key_topics,
            "ended_at": ended_at,
            "open_threads": episode.open_threads,
            "outcomes": getattr(episode, "outcomes", []),
        }

    def _format_context(
        self,
        episodes: list[dict[str, Any]],
        threads: list[dict[str, Any]],
        facts: list[dict[str, Any]],
        entities: list[dict[str, Any]],
    ) -> str:
        """Format context as natural language for LLM.

        Args:
            episodes: Recent conversation episode dicts.
            threads: Open thread dicts.
            facts: High-salience fact dicts.
            entities: Relevant entity dicts.

        Returns:
            Formatted markdown string for LLM context.
        """
        parts: list[str] = []

        if episodes:
            parts.append("## Recent Conversations")
            for ep in episodes:
                parts.append(f"- {ep['summary']}")
                if ep.get("outcomes"):
                    outcomes_text = ", ".join(o.get("content", "") for o in ep["outcomes"][:2])
                    if outcomes_text:
                        parts.append(f"  Outcomes: {outcomes_text}")

        if threads:
            parts.append("\n## Open Threads")
            for thread in threads:
                parts.append(
                    f"- {thread.get('topic', 'Unknown')}: {thread.get('status', 'unknown')}"
                )

        if facts:
            parts.append("\n## Key Facts I Remember")
            for fact in facts[:5]:
                confidence = fact.get("confidence", 0)
                subject = fact.get("subject", "")
                predicate = fact.get("predicate", "")
                obj = fact.get("object", "")

                # If predicate/object are empty, subject contains the full fact
                if predicate and obj:
                    fact_text = f"{subject} {predicate} {obj}"
                else:
                    fact_text = subject

                parts.append(f"- {fact_text} ({confidence:.0%})")

        if entities:
            parts.append("\n## Relevant Context")
            for entity in entities[:3]:
                parts.append(
                    f"- {entity.get('name', 'Unknown')}: {entity.get('summary', 'No summary')}"
                )

        return "\n".join(parts) if parts else "No prior context available."
