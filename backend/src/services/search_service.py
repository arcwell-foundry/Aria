"""Search service for ARIA.

This service handles:
- Global search across all memory types (leads, goals, conversations, documents, etc.)
- Recent items tracking and retrieval
- Recording item access for quick re-access
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A single search result."""

    type: str  # lead, goal, conversation, document, briefing, signal, etc.
    id: str
    title: str
    snippet: str
    score: float
    url: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "type": self.type,
            "id": self.id,
            "title": self.title,
            "snippet": self.snippet,
            "score": self.score,
            "url": self.url,
        }


@dataclass
class RecentItem:
    """A recently accessed item."""

    type: str
    id: str
    title: str
    url: str
    accessed_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "type": self.type,
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "accessed_at": self.accessed_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RecentItem":
        """Create from dictionary."""
        return cls(
            type=data["type"],
            id=data["id"],
            title=data["title"],
            url=data["url"],
            accessed_at=datetime.fromisoformat(data["accessed_at"]),
        )


class SearchService:
    """Service for global search and recent items tracking."""

    def __init__(self) -> None:
        """Initialize search service with Supabase client."""
        self._db = SupabaseClient.get_client()

    async def global_search(
        self,
        user_id: str,
        query: str,
        types: list[str] | None = None,
        limit: int = 10,
    ) -> list[SearchResult]:
        """Perform global search across all memory types.

        Args:
            user_id: The user's ID.
            query: Search query string.
            types: Optional list of types to filter by (e.g., ["leads", "goals"]).
            limit: Maximum results per type.

        Returns:
            List of SearchResult objects, ranked by relevance.
        """
        if not query or not query.strip():
            return []

        logger.info(
            "Global search",
            extra={"user_id": user_id, "query": query, "types": types},
        )

        results: list[SearchResult] = []
        search_types = types or [
            "memory_semantic",
            "leads",
            "goals",
            "conversations",
            "documents",
            "briefings",
        ]

        # Search semantic memory (facts)
        if "memory_semantic" in search_types:
            semantic_results = await self._search_semantic_memory(user_id, query, limit)
            results.extend(semantic_results)

        # Search lead memories
        if "leads" in search_types:
            lead_results = await self._search_leads(user_id, query, limit)
            results.extend(lead_results)

        # Search goals
        if "goals" in search_types:
            goal_results = await self._search_goals(user_id, query, limit)
            results.extend(goal_results)

        # Search conversations
        if "conversations" in search_types:
            conversation_results = await self._search_conversations(user_id, query, limit)
            results.extend(conversation_results)

        # Search company documents
        if "documents" in search_types:
            document_results = await self._search_documents(user_id, query, limit)
            results.extend(document_results)

        # Search daily briefings
        if "briefings" in search_types:
            briefing_results = await self._search_briefings(user_id, query, limit)
            results.extend(briefing_results)

        # Sort by score descending and deduplicate
        seen_ids: set[tuple[str, str]] = set()
        unique_results: list[SearchResult] = []

        for result in sorted(results, key=lambda r: r.score, reverse=True):
            key = (result.type, result.id)
            if key not in seen_ids:
                seen_ids.add(key)
                unique_results.append(result)

        logger.info(
            "Search results",
            extra={"user_id": user_id, "result_count": len(unique_results)},
        )

        return unique_results[:limit]

    async def _search_semantic_memory(
        self, _user_id: str, query: str, limit: int
    ) -> list[SearchResult]:
        """Search semantic memory (facts)."""
        try:
            result = (
                self._db.table("memory_semantic")
                .select("id, fact, confidence")
                .ilike("fact", f"%{query}%")
                .limit(limit)
                .execute()
            )

            results = []
            for row in result.data:
                snippet = row.get("fact", "")[:200]
                if len(row.get("fact", "")) > 200:
                    snippet += "..."

                results.append(
                    SearchResult(
                        type="memory",
                        id=row["id"],
                        title="Memory",
                        snippet=snippet,
                        score=row.get("confidence", 0.5),
                        url=f"/memory/{row['id']}",
                    )
                )
            return results
        except Exception as e:
            logger.warning("Failed to search semantic memory", extra={"error": str(e)})
            return []

    async def _search_leads(self, user_id: str, query: str, limit: int) -> list[SearchResult]:
        """Search lead memories."""
        try:
            result = (
                self._db.table("lead_memories")
                .select("id, company_name, stage, health_score")
                .eq("user_id", user_id)
                .ilike("company_name", f"%{query}%")
                .limit(limit)
                .execute()
            )

            results = []
            for row in result.data:
                stage = row.get("stage", "unknown")
                health = row.get("health_score", 0)
                snippet = f"Stage: {stage} | Health: {health}/100"

                results.append(
                    SearchResult(
                        type="lead",
                        id=row["id"],
                        title=row.get("company_name", "Unknown"),
                        snippet=snippet,
                        score=0.8 + (health / 500),  # Higher health = higher score
                        url=f"/leads/{row['id']}",
                    )
                )
            return results
        except Exception as e:
            logger.warning("Failed to search leads", extra={"error": str(e)})
            return []

    async def _search_goals(self, user_id: str, query: str, limit: int) -> list[SearchResult]:
        """Search goals."""
        try:
            result = (
                self._db.table("goals")
                .select("id, title, description, status, progress")
                .eq("user_id", user_id)
                .ilike("title", f"%{query}%")
                .limit(limit)
                .execute()
            )

            results = []
            for row in result.data:
                description = row.get("description", "")[:150]
                if len(row.get("description", "")) > 150:
                    description += "..."

                results.append(
                    SearchResult(
                        type="goal",
                        id=row["id"],
                        title=row["title"],
                        snippet=description or "No description",
                        score=0.75 + (row.get("progress", 0) / 400),
                        url=f"/goals/{row['id']}",
                    )
                )
            return results
        except Exception as e:
            logger.warning("Failed to search goals", extra={"error": str(e)})
            return []

    async def _search_conversations(
        self, user_id: str, query: str, limit: int
    ) -> list[SearchResult]:
        """Search conversations."""
        try:
            result = (
                self._db.table("conversations")
                .select("id, title, last_message_preview, updated_at")
                .eq("user_id", user_id)
                .ilike("title", f"%{query}%")
                .order("updated_at", desc=True)
                .limit(limit)
                .execute()
            )

            results = []
            for row in result.data:
                preview = row.get("last_message_preview", "")[:150]
                if len(row.get("last_message_preview", "")) > 150:
                    preview += "..."

                results.append(
                    SearchResult(
                        type="conversation",
                        id=row["id"],
                        title=row.get("title", "Untitled Conversation"),
                        snippet=preview or "No messages yet",
                        score=0.7,  # Base score for conversations
                        url=f"/chat/{row['id']}",
                    )
                )
            return results
        except Exception as e:
            logger.warning("Failed to search conversations", extra={"error": str(e)})
            return []

    async def _search_documents(self, user_id: str, query: str, limit: int) -> list[SearchResult]:
        """Search company documents."""
        try:
            # Get user's company
            user_result = (
                self._db.table("user_profiles")
                .select("company_id")
                .eq("id", user_id)
                .single()
                .execute()
            )

            if not user_result.data:
                return []

            company_id = user_result.data.get("company_id")

            result = (
                self._db.table("company_documents")
                .select("id, filename, file_type, quality_score")
                .eq("company_id", company_id)
                .ilike("filename", f"%{query}%")
                .limit(limit)
                .execute()
            )

            results = []
            for row in result.data:
                file_type = row.get("file_type", "unknown").upper()
                quality = row.get("quality_score", 0)

                results.append(
                    SearchResult(
                        type="document",
                        id=row["id"],
                        title=row["filename"],
                        snippet=f"{file_type} document | Quality: {quality:.0%}",
                        score=0.65 + quality,
                        url=f"/documents/{row['id']}",
                    )
                )
            return results
        except Exception as e:
            logger.warning("Failed to search documents", extra={"error": str(e)})
            return []

    async def _search_briefings(self, user_id: str, query: str, limit: int) -> list[SearchResult]:
        """Search daily briefings."""
        try:
            result = (
                self._db.table("daily_briefings")
                .select("id, briefing_date, summary, key_insights")
                .eq("user_id", user_id)
                .ilike("summary", f"%{query}%")
                .order("briefing_date", desc=True)
                .limit(limit)
                .execute()
            )

            results = []
            for row in result.data:
                row_dict: dict[str, Any] = row  # type: ignore
                date_str = row_dict.get("briefing_date", "")
                summary = row_dict.get("summary", "")[:150]
                if len(row_dict.get("summary", "")) > 150:
                    summary += "..."

                results.append(
                    SearchResult(
                        type="briefing",
                        id=row_dict["id"],
                        title=f"Daily Briefing - {date_str}",
                        snippet=summary or "No summary available",
                        score=0.6,
                        url=f"/briefings/{row_dict['id']}",
                    )
                )
            return results
        except Exception as e:
            logger.warning("Failed to search briefings", extra={"error": str(e)})
            return []

    async def recent_items(self, user_id: str, limit: int = 10) -> list[RecentItem]:
        """Get user's recently accessed items.

        Args:
            user_id: The user's ID.
            limit: Maximum number of items to return.

        Returns:
            List of RecentItem objects, sorted by accessed_at descending.
        """
        try:
            result = (
                self._db.table("user_preferences")
                .select("preferences")
                .eq("user_id", user_id)
                .single()
                .execute()
            )

            if not result.data:
                return []

            # .single() returns a dict directly, not a list
            user_pref = result.data if isinstance(result.data, dict) else None
            if not user_pref:
                return []

            preferences: dict[str, Any] = user_pref.get("preferences", {})
            recent_data: list[dict[str, Any]] = preferences.get("recent_items", [])

            # Convert to RecentItem objects and sort by accessed_at
            items = [RecentItem.from_dict(item) for item in recent_data]
            items.sort(key=lambda x: x.accessed_at, reverse=True)

            logger.info(
                "Recent items retrieved",
                extra={"user_id": user_id, "count": len(items)},
            )

            return items[:limit]

        except Exception as e:
            logger.warning("Failed to get recent items", extra={"error": str(e)})
            return []

    async def record_access(
        self,
        user_id: str,
        type: str,
        id: str,
        title: str,
        url: str,
    ) -> None:
        """Record access to an item for recent items tracking.

        Args:
            user_id: The user's ID.
            type: The item type (lead, goal, conversation, etc.).
            id: The item's ID.
            title: The item's title.
            url: The item's URL.
        """
        try:
            # Get existing preferences
            result = (
                self._db.table("user_preferences")
                .select("preferences")
                .eq("user_id", user_id)
                .single()
                .execute()
            )

            existing_data = result.data if result.data else {}
            preferences = existing_data.get("preferences", {})
            recent_items_raw = preferences.get("recent_items", [])

            # Create new item
            new_item = RecentItem(
                type=type,
                id=id,
                title=title,
                url=url,
                accessed_at=datetime.now(UTC),
            )

            # Parse existing items
            existing_items = [RecentItem.from_dict(item) for item in recent_items_raw]

            # Remove existing item with same type/id (if any)
            existing_items = [
                item for item in existing_items if not (item.type == type and item.id == id)
            ]

            # Add new item at front
            existing_items.insert(0, new_item)

            # Cap at 20 items
            existing_items = existing_items[:20]

            # Update preferences
            preferences["recent_items"] = [item.to_dict() for item in existing_items]

            # Update or insert
            if result.data:
                self._db.table("user_preferences").update({"preferences": preferences}).eq(
                    "user_id", user_id
                ).execute()
            else:
                self._db.table("user_preferences").insert(
                    {"user_id": user_id, "preferences": preferences}
                ).execute()

            logger.info(
                "Item access recorded",
                extra={"user_id": user_id, "type": type, "id": id},
            )

        except Exception as e:
            logger.warning("Failed to record item access", extra={"error": str(e)})
