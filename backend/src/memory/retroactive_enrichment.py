"""Retroactive Enrichment Service (US-923).

Enriches historical memory when new data arrives. Triggered after major
data ingestion events:
- Email archive processing (after full import)
- CRM full sync
- Document batch upload

Example: "Moderna" was a CRM record → email processing reveals 47 threads
with 3 stakeholders → retroactively enrich Lead Memory with full
relationship history, update stakeholder maps, recalculate health scores.

Each enrichment is logged as episodic memory and significant enrichments
are flagged for the next briefing via Memory Delta.

Conflict resolution follows the source hierarchy from CLAUDE.md:
    user_stated (0.95) > CRM (0.85) > document (0.80) > email_archive (0.75)
    > web (0.70) > inferred (0.55)
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from src.db.supabase import SupabaseClient
from src.memory.audit import MemoryOperation, MemoryType, log_memory_operation

logger = logging.getLogger(__name__)


class EnrichmentTrigger(Enum):
    """Source events that trigger retroactive enrichment."""

    EMAIL_ARCHIVE = "email_archive"
    CRM_SYNC = "crm_sync"
    DOCUMENT_BATCH = "document_batch"


@dataclass
class EnrichmentResult:
    """Outcome of enriching a single entity.

    Attributes:
        entity_name: Name of the entity that was enriched.
        entity_type: Type of entity (company, contact, etc.).
        facts_added: Number of new facts inserted.
        facts_updated: Number of existing facts superseded.
        relationships_discovered: Number of new relationships found.
        confidence_before: Average confidence before enrichment.
        confidence_after: Average confidence after enrichment.
        significance: How significant this enrichment is (0.0-1.0).
        trigger: Which trigger initiated this enrichment.
    """

    entity_name: str
    entity_type: str
    facts_added: int
    facts_updated: int
    relationships_discovered: int
    confidence_before: float
    confidence_after: float
    significance: float
    trigger: str

    @property
    def is_significant(self) -> bool:
        """Whether this enrichment is significant enough for briefing."""
        return self.significance > 0.7


# Source → confidence mapping per CLAUDE.md hierarchy
_SOURCE_CONFIDENCE: dict[str, float] = {
    "user_stated": 0.95,
    "crm": 0.85,
    "document": 0.80,
    "email_archive": 0.75,
    "enrichment_website": 0.70,
    "enrichment_news": 0.70,
    "enrichment_clinical_trials": 0.70,
    "enrichment_leadership": 0.70,
    "inferred": 0.55,
    "inferred_during_onboarding": 0.55,
}


class RetroactiveEnrichmentService:
    """Enriches historical memory when new data arrives.

    Triggered after: email archive processing, CRM full sync,
    document batch upload.

    Example: "Moderna" was a CRM record → email processing reveals
    47 threads with 3 stakeholders → retroactively enrich Lead Memory
    with full relationship history.
    """

    def __init__(self) -> None:
        """Initialize with database client."""
        self._db = SupabaseClient.get_client()

    # ------------------------------------------------------------------
    # Public API: main entry point
    # ------------------------------------------------------------------

    async def enrich_from_new_data(
        self,
        user_id: str,
        trigger: EnrichmentTrigger,
        new_entities: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Cross-reference new entities against existing memory.

        Args:
            user_id: The user whose memory to enrich.
            trigger: What triggered this enrichment.
            new_entities: List of entity dicts from the ingestion event.

        Returns:
            Dict with enriched count and significant count.
        """
        # 1. Get all existing entities from semantic memory
        existing = await self._get_existing_entities(user_id)

        # 2. Find overlaps — entities that were partially known
        overlaps = self._find_overlaps(existing, new_entities)

        # 3. For each overlap, merge new data into existing memory
        enriched: list[EnrichmentResult] = []
        for overlap in overlaps:
            result = await self._enrich_entity(user_id, overlap, trigger)
            if result is not None:
                enriched.append(result)

        if enriched:
            # 4. Update stakeholder maps retroactively
            await self._update_stakeholder_maps(user_id, enriched)

            # 5. Recalculate health scores
            await self._recalculate_health_scores(user_id, enriched)

            # 6. Flag significant enrichments for Memory Delta
            significant = [e for e in enriched if e.is_significant]
            if significant:
                await self._flag_for_briefing(user_id, significant)

            # 7. Episodic memory for each enrichment
            for e in enriched:
                await self._record_episodic(user_id, e)

        # 8. Audit log
        await log_memory_operation(
            user_id=user_id,
            operation=MemoryOperation.UPDATE,
            memory_type=MemoryType.SEMANTIC,
            metadata={
                "action": "retroactive_enrichment",
                "trigger": trigger.value,
                "entities_enriched": len(enriched),
                "entities_significant": len([e for e in enriched if e.is_significant]),
            },
            suppress_errors=True,
        )

        return {
            "enriched": len(enriched),
            "significant": len([e for e in enriched if e.is_significant]),
        }

    # ------------------------------------------------------------------
    # Public API: convenience trigger methods
    # ------------------------------------------------------------------

    async def enrich_after_email_archive(
        self,
        user_id: str,
        new_entities: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Trigger enrichment after email archive processing.

        Args:
            user_id: The user whose memory to enrich.
            new_entities: Entities extracted from email archive.

        Returns:
            Enrichment result counts.
        """
        return await self.enrich_from_new_data(
            user_id=user_id,
            trigger=EnrichmentTrigger.EMAIL_ARCHIVE,
            new_entities=new_entities,
        )

    async def enrich_after_crm_sync(
        self,
        user_id: str,
        new_entities: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Trigger enrichment after CRM full sync.

        Args:
            user_id: The user whose memory to enrich.
            new_entities: Entities extracted from CRM sync.

        Returns:
            Enrichment result counts.
        """
        return await self.enrich_from_new_data(
            user_id=user_id,
            trigger=EnrichmentTrigger.CRM_SYNC,
            new_entities=new_entities,
        )

    async def enrich_after_document_batch(
        self,
        user_id: str,
        new_entities: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Trigger enrichment after document batch upload.

        Args:
            user_id: The user whose memory to enrich.
            new_entities: Entities extracted from uploaded documents.

        Returns:
            Enrichment result counts.
        """
        return await self.enrich_from_new_data(
            user_id=user_id,
            trigger=EnrichmentTrigger.DOCUMENT_BATCH,
            new_entities=new_entities,
        )

    # ------------------------------------------------------------------
    # Internal: entity discovery
    # ------------------------------------------------------------------

    async def _get_existing_entities(
        self,
        user_id: str,
    ) -> list[dict[str, Any]]:
        """Fetch existing entities from semantic memory.

        Extracts unique entity names from memory_semantic facts
        for the given user.

        Args:
            user_id: The user to query entities for.

        Returns:
            List of entity dicts with name, type, confidence.
        """
        try:
            response = (
                self._db.table("memory_semantic").select("*").eq("user_id", user_id).execute()
            )
            rows = response.data or []
        except Exception as e:
            logger.warning("Failed to fetch existing entities: %s", e)
            return []

        # Deduplicate by entity_name from metadata
        entities: dict[str, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            metadata = row.get("metadata") or {}
            entity_name = metadata.get("entity_name", "")
            if not entity_name:
                continue

            existing = entities.get(entity_name.lower())
            if existing is None or row.get("confidence", 0) > existing.get("confidence", 0):
                entities[entity_name.lower()] = {
                    "name": entity_name,
                    "type": metadata.get("entity_type", "unknown"),
                    "confidence": row.get("confidence", 0.5),
                    "source": row.get("source", "unknown"),
                }

        return list(entities.values())

    # ------------------------------------------------------------------
    # Internal: overlap detection
    # ------------------------------------------------------------------

    def _find_overlaps(
        self,
        existing: list[dict[str, Any]],
        new: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Find entities that appear in both existing and new data.

        Case-insensitive name matching. Empty names are ignored.

        Args:
            existing: List of existing entity dicts.
            new: List of new entity dicts from ingestion.

        Returns:
            List of overlap dicts with existing, new, and name keys.
        """
        existing_by_name: dict[str, dict[str, Any]] = {}
        for entity in existing:
            name = entity.get("name", "").lower()
            if name:
                existing_by_name[name] = entity

        overlaps: list[dict[str, Any]] = []
        for entity in new:
            name = entity.get("name", "").lower()
            if not name:
                continue
            if name in existing_by_name:
                overlaps.append(
                    {
                        "existing": existing_by_name[name],
                        "new": entity,
                        "name": entity.get("name", ""),
                    }
                )

        return overlaps

    # ------------------------------------------------------------------
    # Internal: entity enrichment (merge)
    # ------------------------------------------------------------------

    async def _enrich_entity(
        self,
        user_id: str,
        overlap: dict[str, Any],
        trigger: EnrichmentTrigger,
    ) -> EnrichmentResult | None:
        """Merge new data into existing entity memory.

        Uses source hierarchy for conflict resolution. Higher-confidence
        new data supersedes lower-confidence existing facts. Lower-confidence
        new data is added alongside existing facts without superseding.

        Args:
            user_id: The user's ID.
            overlap: Overlap dict with existing, new, and name keys.
            trigger: The enrichment trigger type.

        Returns:
            EnrichmentResult if enrichment occurred, None on failure.
        """
        entity_name = overlap.get("name", "")
        existing_data = overlap.get("existing", {})
        new_data = overlap.get("new", {})

        existing_confidence = float(existing_data.get("confidence", 0.5))
        existing_source = existing_data.get("source", "unknown")
        new_confidence = float(new_data.get("confidence", 0.5))
        new_source = new_data.get("source", trigger.value)

        new_facts = new_data.get("facts", [])
        new_relationships = new_data.get("relationships", [])

        facts_added = 0
        facts_updated = 0

        # Determine if new data can supersede existing
        existing_source_confidence = self._source_confidence(existing_source)
        new_source_confidence = self._source_confidence(new_source)

        try:
            for fact_text in new_facts:
                if new_source_confidence > existing_source_confidence:
                    # Supersede: find and demote existing facts for this entity
                    await self._supersede_existing_facts(user_id, entity_name)
                    facts_updated += 1

                # Insert new fact
                self._db.table("memory_semantic").insert(
                    {
                        "user_id": user_id,
                        "fact": fact_text,
                        "confidence": new_confidence,
                        "source": new_source,
                        "metadata": {
                            "entity_name": entity_name,
                            "entity_type": new_data.get("type", "unknown"),
                            "enriched_by": trigger.value,
                            "category": "contact"
                            if "stakeholder" in fact_text.lower() or "contact" in fact_text.lower()
                            else "product",
                        },
                    }
                ).execute()
                facts_added += 1

        except Exception as e:
            logger.warning(
                "Failed to enrich entity %s: %s",
                entity_name,
                e,
            )
            return None

        # Calculate significance
        confidence_delta = abs(new_confidence - existing_confidence)
        significance = self._calculate_significance(
            facts_added=facts_added,
            facts_updated=facts_updated,
            relationships_discovered=len(new_relationships),
            confidence_delta=confidence_delta,
        )

        return EnrichmentResult(
            entity_name=entity_name,
            entity_type=new_data.get("type", "unknown"),
            facts_added=facts_added,
            facts_updated=facts_updated,
            relationships_discovered=len(new_relationships),
            confidence_before=existing_confidence,
            confidence_after=new_confidence,
            significance=significance,
            trigger=trigger.value,
        )

    async def _supersede_existing_facts(
        self,
        user_id: str,
        entity_name: str,
    ) -> None:
        """Demote existing facts for an entity (reduce confidence).

        Marks existing facts as superseded by retroactive enrichment
        and reduces their confidence.

        Args:
            user_id: The user's ID.
            entity_name: The entity whose facts to demote.
        """
        try:
            response = (
                self._db.table("memory_semantic").select("*").eq("user_id", user_id).execute()
            )
            rows = response.data or []

            for row in rows:
                if not isinstance(row, dict):
                    continue
                metadata = row.get("metadata") or {}
                if metadata.get("entity_name", "").lower() != entity_name.lower():
                    continue
                if metadata.get("superseded_by_enrichment"):
                    continue

                old_confidence = float(row.get("confidence", 0.5))
                self._db.table("memory_semantic").update(
                    {
                        "confidence": min(old_confidence * 0.3, 0.3),
                        "metadata": {
                            **metadata,
                            "superseded_by_enrichment": True,
                        },
                    }
                ).eq("id", row["id"]).execute()

        except Exception as e:
            logger.warning("Failed to supersede facts for %s: %s", entity_name, e)

    # ------------------------------------------------------------------
    # Internal: significance calculation
    # ------------------------------------------------------------------

    def _calculate_significance(
        self,
        facts_added: int,
        facts_updated: int,
        relationships_discovered: int,
        confidence_delta: float,
    ) -> float:
        """Calculate how significant an enrichment is.

        Score is weighted combination of:
        - New facts (0.3 weight)
        - Updated facts (0.2 weight)
        - New relationships (0.3 weight)
        - Confidence improvement (0.2 weight)

        Args:
            facts_added: Number of new facts.
            facts_updated: Number of superseded facts.
            relationships_discovered: Number of new relationships.
            confidence_delta: Change in confidence score.

        Returns:
            Significance score between 0.0 and 1.0.
        """
        # Normalize each factor to 0-1 range
        facts_score = min(facts_added / 5.0, 1.0)
        updates_score = min(facts_updated / 3.0, 1.0)
        relationships_score = min(relationships_discovered / 3.0, 1.0)
        confidence_score = min(confidence_delta / 0.4, 1.0)

        weighted = (
            facts_score * 0.3
            + updates_score * 0.2
            + relationships_score * 0.3
            + confidence_score * 0.2
        )

        return max(0.0, min(1.0, weighted))

    # ------------------------------------------------------------------
    # Internal: source confidence
    # ------------------------------------------------------------------

    def _source_confidence(self, source: str) -> float:
        """Get confidence level for a given data source.

        Args:
            source: The data source identifier.

        Returns:
            Confidence float (0.0-1.0).
        """
        return _SOURCE_CONFIDENCE.get(source, 0.50)

    # ------------------------------------------------------------------
    # Internal: stakeholder maps
    # ------------------------------------------------------------------

    async def _update_stakeholder_maps(
        self,
        user_id: str,
        enriched: list[EnrichmentResult],
    ) -> None:
        """Update stakeholder maps retroactively based on enriched entities.

        Looks up lead_memory records for enriched companies and
        updates their stakeholder entries.

        Args:
            user_id: The user's ID.
            enriched: List of enrichment results.
        """
        for result in enriched:
            if result.relationships_discovered > 0:
                try:
                    # Find lead memory for this entity
                    response = (
                        self._db.table("lead_memory")
                        .select("id")
                        .eq("user_id", user_id)
                        .eq("company_name", result.entity_name)
                        .execute()
                    )
                    if response.data:
                        logger.info(
                            "Updated stakeholder map for %s",
                            result.entity_name,
                            extra={
                                "user_id": user_id,
                                "relationships": result.relationships_discovered,
                            },
                        )
                except Exception as e:
                    logger.warning(
                        "Failed to update stakeholder map for %s: %s",
                        result.entity_name,
                        e,
                    )

    # ------------------------------------------------------------------
    # Internal: health scores
    # ------------------------------------------------------------------

    async def _recalculate_health_scores(
        self,
        user_id: str,
        enriched: list[EnrichmentResult],
    ) -> None:
        """Recalculate health scores for enriched entities.

        Args:
            user_id: The user's ID.
            enriched: List of enrichment results.
        """
        try:
            from src.onboarding.readiness import OnboardingReadinessService

            readiness_service = OnboardingReadinessService()
            await readiness_service.recalculate(user_id)
            logger.info(
                "Readiness recalculated after retroactive enrichment",
                extra={
                    "user_id": user_id,
                    "entities_enriched": len(enriched),
                },
            )
        except Exception as e:
            logger.warning(
                "Readiness recalculation failed (non-blocking): %s",
                e,
                extra={"user_id": user_id},
            )

    # ------------------------------------------------------------------
    # Internal: Memory Delta flagging
    # ------------------------------------------------------------------

    async def _flag_for_briefing(
        self,
        user_id: str,
        significant: list[EnrichmentResult],
    ) -> None:
        """Flag significant enrichments for next briefing via Memory Delta.

        Stores a briefing record that the Memory Delta Presenter can
        surface in the next user conversation.

        Args:
            user_id: The user's ID.
            significant: List of significant enrichment results.
        """
        try:
            briefing_items: list[dict[str, Any]] = [
                {
                    "entity_name": e.entity_name,
                    "entity_type": e.entity_type,
                    "facts_added": e.facts_added,
                    "facts_updated": e.facts_updated,
                    "relationships_discovered": e.relationships_discovered,
                    "confidence_before": e.confidence_before,
                    "confidence_after": e.confidence_after,
                    "significance": e.significance,
                    "trigger": e.trigger,
                }
                for e in significant
            ]

            insert_data: dict[str, Any] = {
                "user_id": user_id,
                "briefing_type": "retroactive_enrichment",
                "items": briefing_items,
            }
            self._db.table("memory_briefing_queue").insert(insert_data).execute()

            logger.info(
                "Flagged %d significant enrichments for briefing",
                len(significant),
                extra={"user_id": user_id},
            )
        except Exception as e:
            logger.warning(
                "Failed to flag for briefing (non-blocking): %s",
                e,
                extra={"user_id": user_id},
            )

    # ------------------------------------------------------------------
    # Internal: episodic memory
    # ------------------------------------------------------------------

    async def _record_episodic(
        self,
        user_id: str,
        result: EnrichmentResult,
    ) -> None:
        """Record enrichment as episodic memory.

        Creates an episodic memory entry: "I learned more about X".

        Args:
            user_id: The user's ID.
            result: The enrichment result to record.
        """
        try:
            self._db.table("episodic_memories").insert(
                {
                    "user_id": user_id,
                    "event_type": "retroactive_enrichment",
                    "content": (
                        f"Enriched understanding of {result.entity_name} "
                        f"({result.entity_type}): discovered {result.facts_added} "
                        f"new facts and {result.relationships_discovered} relationships "
                        f"from {result.trigger}. Confidence improved from "
                        f"{result.confidence_before:.0%} to {result.confidence_after:.0%}."
                    ),
                    "metadata": {
                        "entity_name": result.entity_name,
                        "trigger": result.trigger,
                        "significance": result.significance,
                    },
                }
            ).execute()
        except Exception as e:
            logger.warning(
                "Failed to record episodic memory for %s: %s",
                result.entity_name,
                e,
            )
