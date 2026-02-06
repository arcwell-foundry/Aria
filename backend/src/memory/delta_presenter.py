"""Memory Delta Presenter for confidence-calibrated memory display (US-920).

Generates human-readable, confidence-calibrated memory deltas.
Reusable across the entire app — onboarding, post-email processing,
post-meeting debriefs, profile updates, and any significant memory event.

Confidence → Language mapping:
- 95%+  → Stated as fact: "Your company specializes in..."
- 80-94% → With conviction: "Based on your communications, you prefer..."
- 60-79% → Hedged: "It appears that your team focuses on..."
- 40-59% → Explicit uncertainty: "I'm not certain, but it seems like..."
- <40%  → Asks for confirmation: "Can you confirm whether...?"
"""

import logging
from typing import Any, cast

from pydantic import BaseModel, Field

from src.db.supabase import SupabaseClient
from src.memory.audit import MemoryOperation, MemoryType, log_memory_operation

logger = logging.getLogger(__name__)


class MemoryFact(BaseModel):
    """A single fact with confidence-calibrated language."""

    id: str = ""
    fact: str
    confidence: float = Field(ge=0.0, le=1.0)
    source: str
    category: str = "general"
    language: str = ""


class MemoryDelta(BaseModel):
    """A group of memory facts within a domain."""

    domain: str
    facts: list[MemoryFact] = []
    summary: str = ""
    timestamp: str | None = None


class CorrectionRequest(BaseModel):
    """User correction to a memory fact."""

    fact_id: str
    corrected_value: str
    correction_type: str = "factual"


class MemoryDeltaPresenter:
    """Generates human-readable, confidence-calibrated memory deltas.

    Reads from memory_semantic, groups facts by domain, and transforms
    raw facts into confidence-appropriate language. Handles user
    corrections by creating new user_stated facts and demoting originals.
    """

    CONFIDENCE_THRESHOLDS: list[tuple[float, str]] = [
        (0.95, "stated"),
        (0.80, "conviction"),
        (0.60, "hedged"),
        (0.40, "uncertain"),
        (0.00, "question"),
    ]

    DOMAIN_MAP: dict[str, str] = {
        "product": "corporate_memory",
        "pipeline": "corporate_memory",
        "leadership": "corporate_memory",
        "financial": "corporate_memory",
        "manufacturing": "corporate_memory",
        "partnership": "corporate_memory",
        "regulatory": "corporate_memory",
        "competitive": "competitive",
        "contact": "relationship",
        "active_deal": "relationship",
        "stakeholder": "relationship",
        "communication_style": "digital_twin",
        "writing_style": "digital_twin",
        "tone": "digital_twin",
    }

    DOMAIN_LABELS: dict[str, str] = {
        "corporate_memory": "company intelligence",
        "competitive": "competitive landscape",
        "relationship": "relationships and contacts",
        "digital_twin": "communication style",
    }

    def __init__(self) -> None:
        """Initialize presenter with database client."""
        self._db = SupabaseClient.get_client()

    async def generate_delta(
        self,
        user_id: str,
        since: str | None = None,
        domain: str | None = None,
    ) -> list[MemoryDelta]:
        """Generate memory deltas for a user since a given timestamp.

        Args:
            user_id: The user to generate deltas for.
            since: ISO timestamp to filter facts created after.
            domain: Optional domain filter (corporate_memory, competitive, etc.).

        Returns:
            List of MemoryDelta objects grouped by domain.
        """
        facts_data = await self._fetch_facts(user_id, since, domain)

        grouped = self._group_by_domain(facts_data)

        deltas: list[MemoryDelta] = []
        for domain_key, domain_facts in grouped.items():
            delta = MemoryDelta(
                domain=domain_key,
                facts=domain_facts[:10],
                summary=self._build_summary(domain_key, domain_facts),
                timestamp=since,
            )
            deltas.append(delta)

        return deltas

    async def apply_correction(
        self,
        user_id: str,
        correction: CorrectionRequest,
    ) -> dict[str, Any]:
        """Apply a user correction to a memory fact.

        Corrections become source: user_stated with confidence 0.95.
        Original fact confidence is reduced and marked as superseded.

        Args:
            user_id: The user applying the correction.
            correction: The correction details.

        Returns:
            Status dict with correction result.
        """
        response = (
            self._db.table("memory_semantic")
            .select("*")
            .eq("id", correction.fact_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )

        if response is None or not response.data:
            return {"status": "not_found"}

        data = cast(dict[str, Any], response.data)
        original_fact = str(data.get("fact", ""))
        original_metadata = cast(dict[str, Any], data.get("metadata") or {})

        # Reduce original confidence and mark as superseded
        original_confidence = float(data.get("confidence", 0.5))
        self._db.table("memory_semantic").update(
            {
                "confidence": min(original_confidence * 0.3, 0.3),
                "metadata": {
                    **original_metadata,
                    "superseded_by_correction": True,
                },
            }
        ).eq("id", correction.fact_id).execute()

        # Insert corrected fact with user_stated confidence
        self._db.table("memory_semantic").insert(
            {
                "user_id": user_id,
                "fact": correction.corrected_value,
                "confidence": 0.95,
                "source": "user_stated",
                "metadata": {
                    **original_metadata,
                    "corrects": correction.fact_id,
                    "correction_type": correction.correction_type,
                },
            }
        ).execute()

        # Audit trail
        await log_memory_operation(
            user_id=user_id,
            operation=MemoryOperation.UPDATE,
            memory_type=MemoryType.SEMANTIC,
            memory_id=correction.fact_id,
            metadata={
                "action": "memory_correction",
                "original_fact": original_fact,
                "corrected_to": correction.corrected_value,
                "correction_type": correction.correction_type,
            },
            suppress_errors=True,
        )

        logger.info(
            "Memory correction applied",
            extra={
                "user_id": user_id,
                "fact_id": correction.fact_id,
                "correction_type": correction.correction_type,
            },
        )

        return {"status": "corrected", "new_confidence": 0.95}

    async def _fetch_facts(
        self,
        user_id: str,
        since: str | None,
        domain: str | None,
    ) -> list[dict[str, Any]]:
        """Fetch semantic facts from the database.

        Args:
            user_id: The user to fetch facts for.
            since: Optional ISO timestamp filter.
            domain: Optional domain filter.

        Returns:
            List of fact records.
        """
        query = self._db.table("memory_semantic").select("*").eq("user_id", user_id)

        if since:
            query = query.gte("created_at", since)

        if domain:
            # Filter by categories that map to this domain
            categories = [cat for cat, dom in self.DOMAIN_MAP.items() if dom == domain]
            if categories:
                query = query.in_("metadata->>category", categories)

        query = query.order("confidence", desc=True).limit(50)

        try:
            result = query.execute()
            return cast(list[dict[str, Any]], result.data or [])
        except Exception as e:
            logger.error("Failed to fetch memory facts: %s", e)
            return []

    def _group_by_domain(self, facts_data: list[dict[str, Any]]) -> dict[str, list[MemoryFact]]:
        """Group raw facts by domain with calibrated language.

        Args:
            facts_data: Raw fact records from the database.

        Returns:
            Facts grouped by domain key.
        """
        grouped: dict[str, list[MemoryFact]] = {}

        for row in facts_data:
            metadata: dict[str, Any] = row.get("metadata") or {}
            category = metadata.get("category", "general")
            domain_key = self.DOMAIN_MAP.get(category, "corporate_memory")
            fact_text = row.get("fact", "")
            confidence = row.get("confidence", 0.5)

            memory_fact = MemoryFact(
                id=str(row.get("id", "")),
                fact=fact_text,
                confidence=confidence,
                source=row.get("source", "unknown"),
                category=category,
                language=self.calibrate_language(fact_text, confidence),
            )

            if domain_key not in grouped:
                grouped[domain_key] = []
            grouped[domain_key].append(memory_fact)

        return grouped

    def calibrate_language(self, fact: str, confidence: float) -> str:
        """Transform a raw fact into confidence-appropriate language.

        Args:
            fact: The raw fact text.
            confidence: Confidence score (0.0-1.0).

        Returns:
            Fact text with appropriate hedging/conviction language.
        """
        if not fact:
            return fact

        for threshold, style in self.CONFIDENCE_THRESHOLDS:
            if confidence >= threshold:
                return self._apply_style(fact, style)

        return self._apply_style(fact, "question")

    def _apply_style(self, fact: str, style: str) -> str:
        """Apply linguistic style to a fact.

        Args:
            fact: The raw fact text.
            style: The linguistic style to apply.

        Returns:
            Styled fact text.
        """
        if not fact:
            return fact

        lowercase_start = f"{fact[0].lower()}{fact[1:]}"

        styles = {
            "stated": fact,
            "conviction": f"Based on available data, {lowercase_start}",
            "hedged": f"It appears that {lowercase_start}",
            "uncertain": f"I'm not fully certain, but {lowercase_start}",
            "question": f"Can you confirm: {fact}?",
        }

        return styles.get(style, fact)

    def _build_summary(self, domain: str, facts: list[MemoryFact]) -> str:
        """Generate a brief summary for a domain's delta.

        Args:
            domain: The domain key.
            facts: Facts in this domain.

        Returns:
            Human-readable summary string.
        """
        label = self.DOMAIN_LABELS.get(domain, domain)
        count = len(facts)
        if count == 1:
            return f"Learned 1 new fact about {label}"
        return f"Learned {count} new facts about {label}"
