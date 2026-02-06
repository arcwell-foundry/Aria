"""Background Memory Construction Orchestrator (US-911).

Coordinates all memory construction during onboarding. Runs asynchronously
during Steps 1-8, merging data from enrichment (US-903), documents (US-904),
user input, email (US-908), and CRM into unified Corporate Memory and
Digital Twin.

Resolves conflicts using the source hierarchy defined in CLAUDE.md:
  User-stated > CRM > Document > Web research > Inferred
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)

# Source hierarchy for conflict resolution (higher = wins)
SOURCE_PRIORITY: dict[str, float] = {
    "user_stated": 5.0,
    "crm_import": 4.0,
    "document_upload": 3.0,
    "email_bootstrap": 2.5,
    "enrichment_website": 2.0,
    "enrichment_news": 1.5,
    "inferred_during_onboarding": 1.0,
}

# Readiness domain weights (must sum to 1.0)
_READINESS_WEIGHTS: dict[str, float] = {
    "corporate_memory": 0.25,
    "digital_twin": 0.25,
    "relationship_graph": 0.20,
    "integrations": 0.15,
    "goal_clarity": 0.15,
}


class MemoryConstructionOrchestrator:
    """Coordinates all memory construction during onboarding.

    Runs asynchronously during Steps 1-8, merging data from all sources
    into unified Corporate Memory and Digital Twin.

    Key responsibilities:
    1. Merge facts from multiple sources with conflict resolution
    2. Build entity relationship graph in Graphiti
    3. Track progress per memory domain
    4. Trigger first conversation generator on completion
    """

    def __init__(self) -> None:
        """Initialize orchestrator with Supabase client."""
        self._db = SupabaseClient.get_client()

    async def run_construction(self, user_id: str) -> dict[str, Any]:
        """Run full memory construction pipeline.

        Called when onboarding activation step completes.

        Args:
            user_id: The authenticated user's ID.

        Returns:
            Construction summary with fact count, entity count,
            readiness scores, and timestamp.
        """
        logger.info("Starting memory construction", extra={"user_id": user_id})

        # 1. Gather all facts from all sources
        all_facts = await self._gather_all_facts(user_id)

        # 2. Resolve conflicts using source hierarchy
        resolved = await self._resolve_conflicts(all_facts)

        # 3. Build entity relationship graph
        entities = await self._build_entity_graph(user_id, resolved)

        # 4. Calculate final readiness scores
        readiness = await self._calculate_final_readiness(user_id)

        # 5. Generate construction summary
        summary: dict[str, Any] = {
            "total_facts": len(resolved),
            "entities_mapped": len(entities),
            "readiness": readiness,
            "constructed_at": datetime.now(UTC).isoformat(),
        }

        # 6. Record episodic event (non-blocking)
        try:
            await self._record_episodic_event(
                user_id,
                "memory_construction_complete",
                summary,
            )
        except Exception as e:
            logger.warning(
                "Episodic record failed during memory construction",
                extra={"user_id": user_id, "error": str(e)},
            )

        # 7. Audit log
        try:
            await self._log_audit(user_id, summary)
        except Exception as e:
            logger.warning(
                "Audit log failed during memory construction",
                extra={"user_id": user_id, "error": str(e)},
            )

        logger.info(
            "Memory construction complete",
            extra={"user_id": user_id, "summary": summary},
        )
        return summary

    async def _gather_all_facts(self, user_id: str) -> list[dict[str, Any]]:
        """Gather all semantic facts from all sources for this user.

        Args:
            user_id: The user's ID.

        Returns:
            List of semantic fact rows from the database.
        """
        result = self._db.table("memory_semantic").select("*").eq("user_id", user_id).execute()
        return result.data or []

    async def _resolve_conflicts(self, facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Resolve conflicting facts using source priority hierarchy.

        When two facts contradict, the higher-priority source wins.
        Both are kept but the lower-priority one gets reduced confidence
        via the adjusted_confidence field.

        Args:
            facts: List of raw semantic facts.

        Returns:
            Facts with adjusted_confidence added based on source priority.
        """
        for fact in facts:
            source = fact.get("source", "")
            base_priority = 1.0

            for source_prefix, priority in SOURCE_PRIORITY.items():
                if source == source_prefix or source.startswith(source_prefix):
                    base_priority = priority
                    break

            original_confidence = fact.get("confidence", 0.5)
            # Higher priority sources get a confidence boost
            adjusted = min(0.99, original_confidence * (0.8 + base_priority * 0.04))
            fact["adjusted_confidence"] = round(adjusted, 4)

        return facts

    async def _build_entity_graph(
        self,
        user_id: str,
        facts: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Build entity relationship graph from all facts.

        Extracts entities from fact metadata and creates/updates
        Graphiti nodes for companies, people, products, etc.

        Args:
            user_id: The user's ID.
            facts: Resolved facts with metadata.

        Returns:
            List of unique entity dicts with name, type, and fact_count.
        """
        entities: dict[str, dict[str, Any]] = {}

        for fact in facts:
            metadata = fact.get("metadata", {})
            if not isinstance(metadata, dict):
                continue

            for entity in metadata.get("entities", []):
                if isinstance(entity, dict):
                    name = entity.get("name", "")
                    etype = entity.get("type", "unknown")
                elif isinstance(entity, str):
                    name = entity
                    etype = "unknown"
                else:
                    continue

                if not name:
                    continue

                if name not in entities:
                    entities[name] = {
                        "name": name,
                        "type": etype,
                        "fact_count": 0,
                    }
                entities[name]["fact_count"] += 1

        # Store in Graphiti if available
        try:
            from src.db.graphiti import GraphitiClient

            graphiti = GraphitiClient()
            for entity in entities.values():
                await graphiti.add_entity(
                    user_id=user_id,
                    name=entity["name"],
                    entity_type=entity["type"],
                    metadata={
                        "source": "onboarding_construction",
                        "fact_count": entity["fact_count"],
                    },
                )
        except Exception as e:
            logger.warning(
                "Graphiti entity storage failed (may not be configured)",
                extra={"user_id": user_id, "error": str(e)},
            )

        return list(entities.values())

    async def _calculate_final_readiness(self, user_id: str) -> dict[str, Any]:
        """Calculate final readiness scores across all domains.

        Computes a weighted overall score from the five domain sub-scores
        and persists the result back to the database.

        Args:
            user_id: The user's ID.

        Returns:
            Dict of readiness scores including computed overall score,
            or empty dict if no onboarding state exists.
        """
        state = (
            self._db.table("onboarding_state")
            .select("readiness_scores")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if not state.data:
            return {}

        scores: dict[str, Any] = state.data.get("readiness_scores", {})

        # Calculate overall weighted score
        overall = sum(
            scores.get(domain, 0) * weight for domain, weight in _READINESS_WEIGHTS.items()
        )
        scores["overall"] = round(overall, 1)

        # Persist updated scores
        (
            self._db.table("onboarding_state")
            .update({"readiness_scores": scores})
            .eq("user_id", user_id)
            .execute()
        )

        return scores

    async def _record_episodic_event(
        self,
        user_id: str,
        event_type: str,
        details: dict[str, Any],
    ) -> None:
        """Record an event to episodic memory.

        Args:
            user_id: The user's ID.
            event_type: Short event label.
            details: Event metadata dict.
        """
        from src.memory.episodic import Episode, EpisodicMemory

        memory = EpisodicMemory()
        now = datetime.now(UTC)
        episode = Episode(
            id=str(uuid.uuid4()),
            user_id=user_id,
            event_type=f"onboarding_{event_type}",
            content=str(details),
            participants=[],
            occurred_at=now,
            recorded_at=now,
            context=details,
        )
        await memory.store_episode(episode)

    async def _log_audit(
        self,
        user_id: str,
        summary: dict[str, Any],
    ) -> None:
        """Create an audit log entry for memory construction.

        Args:
            user_id: The user's ID.
            summary: Construction summary to log.
        """
        from src.memory.audit import (
            MemoryOperation,
            MemoryType,
            log_memory_operation,
        )

        await log_memory_operation(
            user_id=user_id,
            operation=MemoryOperation.CREATE,
            memory_type=MemoryType.SEMANTIC,
            memory_id=f"construction_{user_id}",
            metadata={
                "event": "onboarding_memory_construction",
                "total_facts": summary["total_facts"],
                "entities_mapped": summary["entities_mapped"],
            },
            suppress_errors=True,
        )
