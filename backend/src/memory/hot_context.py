"""Hot context builder for always-loaded conversation context.

Provides fast (<200ms) access to essential user context that should
be included in every LLM call. Total budget: <3000 tokens.

Sections:
- User identity (150 tokens)
- Active goal (400 tokens)
- Recent conversation (1200 tokens)
- Top 3 priorities (300 tokens)
- Today's schedule (300 tokens)
- Salient facts (600 tokens)
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from src.core.cache import get_cache
from src.memory.working import count_tokens

if TYPE_CHECKING:
    from src.memory.working import WorkingMemory

logger = logging.getLogger(__name__)

# Token budgets per section
BUDGET_USER_IDENTITY = 150
BUDGET_ACTIVE_GOAL = 400
BUDGET_RECENT_CONVERSATION = 1200
BUDGET_PRIORITIES = 300
BUDGET_SCHEDULE = 300
BUDGET_SALIENT_FACTS = 600
BUDGET_TOTAL = 3000

# Cache TTL in seconds
CACHE_TTL = 60


@dataclass
class HotContextSection:
    """A single section of hot context."""

    label: str
    content: str
    tokens: int


@dataclass
class HotContext:
    """Assembled hot context for a user.

    Contains all sections that fit within the 3000-token budget,
    ready for injection into LLM system prompts.
    """

    user_id: str
    sections: list[HotContextSection] = field(default_factory=list)
    total_tokens: int = 0
    assembled_at_ms: int = 0

    @property
    def formatted(self) -> str:
        """Format all sections as markdown for LLM consumption."""
        parts: list[str] = []
        for section in self.sections:
            if section.content:
                parts.append(f"## {section.label}\n{section.content}")
        return "\n\n".join(parts) if parts else ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "user_id": self.user_id,
            "sections": [
                {"label": s.label, "content": s.content, "tokens": s.tokens}
                for s in self.sections
            ],
            "total_tokens": self.total_tokens,
            "assembled_at_ms": self.assembled_at_ms,
        }


class HotContextBuilder:
    """Builds hot context by fetching user data in parallel.

    Each section fetcher is independently fault-tolerant: if one
    section fails, the others still populate. Build never raises.
    """

    def __init__(self, db_client: Any) -> None:
        """Initialize the builder.

        Args:
            db_client: Supabase client for database queries.
        """
        self.db = db_client

    async def build(
        self,
        user_id: str,
        working_memory: WorkingMemory | None = None,
        active_goal: dict[str, Any] | None = None,
    ) -> HotContext:
        """Build hot context for a user.

        Checks cache first (60s TTL), then fetches all sections
        in parallel on cache miss.

        Args:
            user_id: The user to build context for.
            working_memory: Optional working memory with recent messages.
            active_goal: Optional pre-fetched active goal.

        Returns:
            HotContext with all available sections.
        """
        cache = get_cache()
        cache_store = cache.get_or_create_decorator_cache("hot_context", CACHE_TTL)
        cache_key = f"hot_context:{user_id}"

        try:
            cached = cache_store[cache_key]
            cache._hits += 1
            return cached
        except KeyError:
            cache._misses += 1

        start_ms = int(time.time() * 1000)

        # Fetch all sections in parallel
        results = await asyncio.gather(
            self._fetch_user_identity(user_id),
            self._fetch_active_goal(user_id, active_goal),
            self._fetch_recent_conversation(user_id, working_memory),
            self._fetch_priorities(user_id),
            self._fetch_schedule(user_id),
            self._fetch_salient_facts(user_id),
            return_exceptions=True,
        )

        sections: list[HotContextSection] = []
        for result in results:
            if isinstance(result, BaseException):
                logger.warning("Hot context section fetch failed: %s", result)
                continue
            if result is not None and result.content:
                sections.append(result)

        # Enforce total budget: trim from the end (salient facts first)
        total = sum(s.tokens for s in sections)
        while total > BUDGET_TOTAL and sections:
            removed = sections.pop()
            total -= removed.tokens

        assembled_at_ms = int(time.time() * 1000)
        ctx = HotContext(
            user_id=user_id,
            sections=sections,
            total_tokens=total,
            assembled_at_ms=assembled_at_ms,
        )

        cache_store[cache_key] = ctx

        elapsed = assembled_at_ms - start_ms
        logger.debug(
            "Built hot context for user %s: %d tokens in %dms",
            user_id,
            total,
            elapsed,
        )

        return ctx

    def invalidate(self, user_id: str) -> None:
        """Invalidate cached hot context for a user.

        Args:
            user_id: The user whose cache to invalidate.
        """
        import contextlib

        cache = get_cache()
        cache_store = cache.get_or_create_decorator_cache("hot_context", CACHE_TTL)
        cache_key = f"hot_context:{user_id}"
        with contextlib.suppress(KeyError):
            del cache_store[cache_key]

    def _truncate(self, text: str, budget: int) -> tuple[str, int]:
        """Truncate text to fit within a token budget.

        Args:
            text: The text to truncate.
            budget: Maximum tokens allowed.

        Returns:
            Tuple of (truncated_text, token_count).
        """
        tokens = count_tokens(text)
        if tokens <= budget:
            return text, tokens
        # Rough truncation: cut by character ratio
        ratio = budget / tokens
        cut_len = int(len(text) * ratio * 0.9)  # 10% margin
        truncated = text[:cut_len] + "..."
        final_tokens = count_tokens(truncated)
        return truncated, final_tokens

    async def _fetch_user_identity(self, user_id: str) -> HotContextSection | None:
        """Fetch user identity from user_profiles and companies."""
        try:
            result = (
                self.db.table("user_profiles")
                .select("full_name, role, company_id, companies(name)")
                .eq("id", user_id)
                .maybe_single()
                .execute()
            )
            data = result.data if result else None
            if not data:
                return None

            parts: list[str] = []
            if data.get("full_name"):
                parts.append(f"Name: {data['full_name']}")
            if data.get("role"):
                parts.append(f"Role: {data['role']}")
            company_name = (data.get("companies") or {}).get("name")
            if company_name:
                parts.append(f"Company: {company_name}")

            if not parts:
                return None

            content = "\n".join(parts)
            content, tokens = self._truncate(content, BUDGET_USER_IDENTITY)
            return HotContextSection(label="User", content=content, tokens=tokens)
        except Exception as e:
            logger.warning("Failed to fetch user identity: %s", e)
            return None

    async def _fetch_active_goal(
        self,
        user_id: str,
        preloaded: dict[str, Any] | None = None,
    ) -> HotContextSection | None:
        """Fetch the most recent active goal."""
        try:
            if preloaded:
                data = preloaded
            else:
                result = (
                    self.db.table("goals")
                    .select("id, objective, status, context")
                    .eq("user_id", user_id)
                    .eq("status", "active")
                    .order("created_at", desc=True)
                    .limit(1)
                    .execute()
                )
                rows = result.data if result else []
                if not rows:
                    return None
                data = rows[0]

            parts: list[str] = []
            if data.get("objective"):
                parts.append(f"Goal: {data['objective']}")
            if data.get("status"):
                parts.append(f"Status: {data['status']}")

            if not parts:
                return None

            content = "\n".join(parts)
            content, tokens = self._truncate(content, BUDGET_ACTIVE_GOAL)
            return HotContextSection(label="Active Goal", content=content, tokens=tokens)
        except Exception as e:
            logger.warning("Failed to fetch active goal: %s", e)
            return None

    async def _fetch_recent_conversation(
        self,
        user_id: str,  # noqa: ARG002
        working_memory: WorkingMemory | None = None,
    ) -> HotContextSection | None:
        """Extract last 5 turns from working memory."""
        try:
            if not working_memory or not working_memory.messages:
                return None

            recent = working_memory.messages[-5:]
            parts: list[str] = []
            for msg in recent:
                role = msg.get("role", "unknown")
                text = msg.get("content", "")
                # Trim individual messages
                if len(text) > 300:
                    text = text[:297] + "..."
                parts.append(f"**{role}**: {text}")

            if not parts:
                return None

            content = "\n".join(parts)
            content, tokens = self._truncate(content, BUDGET_RECENT_CONVERSATION)
            return HotContextSection(
                label="Recent Conversation", content=content, tokens=tokens
            )
        except Exception as e:
            logger.warning("Failed to fetch recent conversation: %s", e)
            return None

    async def _fetch_priorities(self, user_id: str) -> HotContextSection | None:
        """Fetch top 3 high/urgent pending prospective memories."""
        try:
            result = (
                self.db.table("prospective_memories")
                .select("description, priority")
                .eq("user_id", user_id)
                .eq("status", "pending")
                .in_("priority", ["high", "urgent"])
                .order("created_at", desc=True)
                .limit(3)
                .execute()
            )
            rows = result.data if result else []
            if not rows:
                return None

            parts: list[str] = []
            for row in rows:
                priority = row.get("priority", "")
                desc = row.get("description", "")
                parts.append(f"- [{priority}] {desc}")

            content = "\n".join(parts)
            content, tokens = self._truncate(content, BUDGET_PRIORITIES)
            return HotContextSection(
                label="Top Priorities", content=content, tokens=tokens
            )
        except Exception as e:
            logger.warning("Failed to fetch priorities: %s", e)
            return None

    async def _fetch_schedule(self, user_id: str) -> HotContextSection | None:
        """Fetch time-triggered prospective memories as today's schedule."""
        try:
            result = (
                self.db.table("prospective_memories")
                .select("description, due_date, trigger_config")
                .eq("user_id", user_id)
                .eq("status", "pending")
                .eq("trigger_type", "time")
                .order("due_date", desc=False)
                .limit(5)
                .execute()
            )
            rows = result.data if result else []
            if not rows:
                return None

            parts: list[str] = []
            for row in rows:
                time_val = row.get("due_date") or row.get("trigger_config") or ""
                desc = row.get("description", "")
                parts.append(f"- {time_val}: {desc}")

            content = "\n".join(parts)
            content, tokens = self._truncate(content, BUDGET_SCHEDULE)
            return HotContextSection(
                label="Today's Schedule", content=content, tokens=tokens
            )
        except Exception as e:
            logger.warning("Failed to fetch schedule: %s", e)
            return None

    async def _fetch_salient_facts(self, user_id: str) -> HotContextSection | None:
        """Fetch high-salience semantic facts."""
        try:
            # Get salient fact IDs from salience table
            salience_result = (
                self.db.table("semantic_fact_salience")
                .select("graphiti_episode_id, current_salience")
                .eq("user_id", user_id)
                .gte("current_salience", 0.3)
                .order("current_salience", desc=True)
                .limit(5)
                .execute()
            )
            salience_rows = salience_result.data if salience_result else []
            if not salience_rows:
                return None

            fact_ids = [r["graphiti_episode_id"] for r in salience_rows]

            # Fetch fact details
            facts_result = (
                self.db.table("memory_semantic")
                .select("id, fact, confidence")
                .eq("user_id", user_id)
                .in_("id", fact_ids)
                .execute()
            )
            fact_rows = facts_result.data if facts_result else []
            if not fact_rows:
                return None

            parts: list[str] = []
            for row in fact_rows:
                fact_text = row.get("fact", "")
                confidence = row.get("confidence", 0)
                parts.append(f"- {fact_text} ({confidence:.0%})")

            content = "\n".join(parts)
            content, tokens = self._truncate(content, BUDGET_SALIENT_FACTS)
            return HotContextSection(
                label="Key Facts", content=content, tokens=tokens
            )
        except Exception as e:
            logger.warning("Failed to fetch salient facts: %s", e)
            return None
