"""Custom Watch Topics Service.

Users define topics to watch (company names, keywords, therapeutic areas).
ARIA monitors signals and writes matches to memory, briefings, and all
intelligence surfaces.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class WatchTopicsService:
    """Manages user-defined watch topics and matches them against signals."""

    def __init__(self, supabase_client: Any) -> None:
        self._db = supabase_client

    async def add_topic(
        self,
        user_id: str,
        topic_type: str,
        topic_value: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Add a new watch topic for the user.

        Args:
            user_id: User UUID.
            topic_type: Type of topic (keyword, company, therapeutic_area).
            topic_value: The topic string to watch.
            description: Optional description of why this is being watched.

        Returns:
            Dict with created topic and retroactive match count.
        """
        keywords = self._derive_keywords(topic_value)

        result = (
            self._db.table("watch_topics")
            .insert(
                {
                    "user_id": user_id,
                    "topic_type": topic_type,
                    "topic_value": topic_value,
                    "description": description,
                    "keywords": keywords,
                    "is_active": True,
                }
            )
            .execute()
        )

        topic = result.data[0] if result.data else None

        # Write to semantic memory so ARIA knows about this watch topic
        if topic:
            try:
                self._db.table("memory_semantic").insert(
                    {
                        "user_id": user_id,
                        "fact": (
                            f"[Watch Topic] User is monitoring: {topic_value} "
                            f"({topic_type}). {description or ''}"
                        ),
                        "confidence": 1.0,
                        "source": "watch_topic",
                        "metadata": {
                            "topic_id": topic["id"],
                            "topic_type": topic_type,
                            "keywords": keywords,
                        },
                    }
                ).execute()
            except Exception as e:
                logger.warning("[WatchTopics] Failed to write memory: %s", e)

        # Retroactively match against existing signals
        matches = 0
        if topic:
            matches = await self.match_existing_signals(
                user_id, topic["id"], keywords
            )

        return {"topic": topic, "retroactive_matches": matches}

    async def get_topics(self, user_id: str, active_only: bool = True) -> list[dict[str, Any]]:
        """List user's watch topics.

        Args:
            user_id: User UUID.
            active_only: If True, only return active topics.

        Returns:
            List of watch topic dicts.
        """
        query = (
            self._db.table("watch_topics")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
        )
        if active_only:
            query = query.eq("is_active", True)

        result = query.execute()
        return result.data or []

    async def remove_topic(self, user_id: str, topic_id: str) -> bool:
        """Deactivate a watch topic.

        Args:
            user_id: User UUID.
            topic_id: UUID of the topic to remove.

        Returns:
            True if deactivated successfully.
        """
        try:
            self._db.table("watch_topics").update(
                {"is_active": False}
            ).eq("id", topic_id).eq("user_id", user_id).execute()
            return True
        except Exception as e:
            logger.warning("[WatchTopics] Failed to remove topic %s: %s", topic_id, e)
            return False

    async def match_signal(
        self, user_id: str, signal: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Check if a signal matches any of the user's watch topics.

        Args:
            user_id: User UUID.
            signal: Signal dict with headline, company_name, etc.

        Returns:
            List of matched topic dicts.
        """
        topics = (
            self._db.table("watch_topics")
            .select("id, topic_value, keywords, topic_type, signal_count")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .execute()
        )

        if not topics.data:
            return []

        headline = (signal.get("headline") or "").lower()
        company = (signal.get("company_name") or "").lower()

        matches: list[dict[str, Any]] = []
        for topic in topics.data:
            keywords = topic.get("keywords") or []
            topic_value = (topic.get("topic_value") or "").lower()

            # Check if any keyword matches in headline or company
            matched = False
            for kw in keywords:
                kw_lower = kw.lower()
                if kw_lower in headline or kw_lower in company:
                    matched = True
                    break

            if not matched and topic_value in headline:
                matched = True

            if matched:
                matches.append(topic)

                # Update match count and timestamp
                try:
                    self._db.table("watch_topics").update(
                        {
                            "signal_count": (topic.get("signal_count") or 0) + 1,
                            "last_matched_at": datetime.now(timezone.utc).isoformat(),
                        }
                    ).eq("id", topic["id"]).execute()
                except Exception as e:
                    logger.debug("[WatchTopics] Failed to update match count: %s", e)

                # Write match to semantic memory
                try:
                    self._db.table("memory_semantic").insert(
                        {
                            "user_id": user_id,
                            "fact": (
                                f"[Watch Match] Signal matching watched topic "
                                f"'{topic['topic_value']}': "
                                f"{signal.get('headline', '')[:200]}"
                            ),
                            "confidence": 0.85,
                            "source": "watch_topic_match",
                            "metadata": {
                                "topic_id": topic["id"],
                                "signal_id": signal.get("id"),
                                "company": signal.get("company_name"),
                            },
                        }
                    ).execute()
                except Exception as e:
                    logger.debug("[WatchTopics] Failed to write match memory: %s", e)

        return matches

    async def match_existing_signals(
        self, user_id: str, topic_id: str, keywords: list[str]
    ) -> int:
        """Retroactively match a new topic against existing signals.

        Args:
            user_id: User UUID.
            topic_id: UUID of the new topic.
            keywords: Derived keywords to search for.

        Returns:
            Number of matching signals found.
        """
        if not keywords:
            return 0

        total_matches = 0
        seen_ids: set[str] = set()

        for kw in keywords[:5]:
            try:
                signals = (
                    self._db.table("market_signals")
                    .select("id, headline, company_name")
                    .eq("user_id", user_id)
                    .ilike("headline", f"%{kw}%")
                    .limit(10)
                    .execute()
                )
                for s in signals.data or []:
                    if s["id"] not in seen_ids:
                        seen_ids.add(s["id"])
                        total_matches += 1
            except Exception as e:
                logger.debug("[WatchTopics] Retroactive match query failed: %s", e)

        if total_matches > 0 and topic_id:
            try:
                self._db.table("watch_topics").update(
                    {"signal_count": total_matches}
                ).eq("id", topic_id).execute()
            except Exception as e:
                logger.debug("[WatchTopics] Failed to update signal count: %s", e)

        return total_matches

    def _derive_keywords(self, topic_value: str) -> list[str]:
        """Derive search keywords from a topic value.

        Args:
            topic_value: The user's topic string.

        Returns:
            List of keyword strings for matching.
        """
        words = topic_value.replace(",", " ").replace(";", " ").split()

        # The full phrase is always a keyword
        keywords = [topic_value.strip()]

        # Multi-word subphrases (2+ words)
        if len(words) >= 2:
            for i in range(len(words) - 1):
                keywords.append(f"{words[i]} {words[i + 1]}")

        # Individual significant words (>3 chars, not common)
        stop_words = {
            "the", "and", "for", "with", "from", "that",
            "this", "into", "about", "any", "all",
        }
        for w in words:
            if len(w) > 3 and w.lower() not in stop_words:
                keywords.append(w)

        return list(set(keywords))
