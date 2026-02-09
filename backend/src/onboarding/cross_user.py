"""US-917: Cross-User Onboarding Acceleration.

Accelerates onboarding for user #2+ at a company by detecting existing
Corporate Memory and skipping steps that don't need to be repeated.

Privacy enforcement: Only corporate facts are shared. User #2 never sees
User #1's Digital Twin, personal data, or individual contributions.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from src.db.supabase import SupabaseClient
from src.onboarding.orchestrator import OnboardingOrchestrator
from src.onboarding.readiness import OnboardingReadinessService

logger = logging.getLogger(__name__)


class CompanyCheckResult:
    """Result of checking if a company exists in Corporate Memory."""

    def __init__(
        self,
        exists: bool,
        company_id: str | None,
        company_name: str | None,
        richness_score: int,
        recommendation: str,
    ):
        """Initialize check result.

        Args:
            exists: Whether company exists in Corporate Memory.
            company_id: ID of existing company (if exists).
            company_name: Name of existing company (if exists).
            richness_score: Corporate memory richness (0-100).
            recommendation: "skip" (>70%), "partial" (30-70%), "full" (<30%).
        """
        self.exists = exists
        self.company_id = company_id
        self.company_name = company_name
        self.richness_score = richness_score
        self.recommendation = recommendation


class MemoryDeltaFact:
    """A single fact from Corporate Memory for display/confirmation."""

    def __init__(
        self,
        subject: str,
        predicate: str,
        object: str,
        confidence: float,
        source: str,
    ):
        """Initialize memory delta fact.

        Args:
            subject: Fact subject (e.g., "Company", "Product X").
            predicate: Fact predicate (e.g., "is", "manufactures", "focuses on").
            object: Fact object (e.g., "Biotech CDMO", "cell therapies").
            confidence: Confidence score (0-1).
            source: Fact source (extracted, aggregated, admin_stated).
        """
        self.subject = subject
        self.predicate = predicate
        self.object = object
        self.confidence = confidence
        self.source = source

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "confidence": self.confidence,
            "source": self.source,
        }


class CrossUserAccelerationService:
    """Service for cross-user onboarding acceleration.

    Detects when user #2+ joins an existing company and accelerates
    their onboarding by reusing Corporate Memory while maintaining
    privacy (no personal data shared).
    """

    def __init__(self) -> None:
        """Initialize service with database client."""
        self._db = SupabaseClient.get_client()

    def check_company_exists(self, domain: str) -> CompanyCheckResult:
        """Check if company domain exists in Corporate Memory.

        Args:
            domain: Company domain to check (e.g., "acme-corp.com").

        Returns:
            CompanyCheckResult with existence status and richness score.
        """
        # Normalize domain (remove protocol, path, etc.)
        normalized_domain = self._normalize_domain(domain)

        # Query companies table by domain
        result = (
            self._db.table("companies")
            .select("id, name, domain")
            .eq("domain", normalized_domain)
            .maybe_single()
            .execute()
        )

        if not result or not result.data:
            # Company doesn't exist
            return CompanyCheckResult(
                exists=False,
                company_id=None,
                company_name=None,
                richness_score=0,
                recommendation="full",
            )

        company = result.data
        company_id = company["id"]
        company_name = company["name"]

        # Calculate richness score based on corporate_facts
        richness = self._calculate_corporate_richness(company_id)

        # Determine recommendation based on richness
        if richness > 70:
            recommendation = "skip"
        elif richness >= 30:
            recommendation = "partial"
        else:
            recommendation = "full"

        logger.info(
            "Company existence check",
            extra={
                "domain": domain,
                "company_id": company_id,
                "richness_score": richness,
                "recommendation": recommendation,
            },
        )

        return CompanyCheckResult(
            exists=True,
            company_id=company_id,
            company_name=company_name,
            richness_score=richness,
            recommendation=recommendation,
        )

    def get_company_memory_delta(self, company_id: str, user_id: str) -> dict[str, Any]:
        """Get corporate memory delta for user confirmation.

        Returns ONLY corporate facts (no personal data). Privacy:
        User #2 never sees User #1's Digital Twin or personal contributions.

        Queries both corporate_facts and memory_semantic tables to capture
        all enrichment data (enrichment engine writes to memory_semantic).

        Args:
            company_id: ID of existing company.
            user_id: ID of requesting user (for logging, not filtering).

        Returns:
            Dict with facts list and metadata.
        """
        facts = []

        # Query active corporate facts for this company
        result = (
            self._db.table("corporate_facts")
            .select("subject, predicate, object, confidence, source")
            .eq("company_id", company_id)
            .eq("is_active", True)
            .execute()
        )

        if result.data:
            for row in result.data:
                fact = MemoryDeltaFact(
                    subject=row["subject"],
                    predicate=row["predicate"],
                    object=row["object"],
                    confidence=row["confidence"],
                    source=row["source"],
                )
                facts.append(fact.to_dict())

        # Also query memory_semantic for enrichment facts with this company_id.
        # The enrichment engine writes to memory_semantic with company_id in metadata.
        seen_facts = {f["object"] for f in facts}
        try:
            semantic_result = (
                self._db.table("memory_semantic")
                .select("fact, confidence, source, metadata")
                .contains("metadata", {"company_id": company_id})
                .execute()
            )

            if semantic_result.data:
                for row in semantic_result.data:
                    # Skip personal/digital-twin facts — only corporate data
                    source = row.get("source", "")
                    if "digital_twin" in source or "user_stated" in source:
                        continue
                    # Deduplicate against corporate_facts
                    fact_text = row["fact"]
                    if fact_text in seen_facts:
                        continue
                    seen_facts.add(fact_text)

                    metadata = row.get("metadata") or {}
                    fact = MemoryDeltaFact(
                        subject=metadata.get("category", "Company"),
                        predicate="has fact",
                        object=fact_text,
                        confidence=row["confidence"],
                        source=source,
                    )
                    facts.append(fact.to_dict())
        except Exception as e:
            logger.warning(
                "Failed to query memory_semantic for company facts",
                extra={"company_id": company_id, "error": str(e)},
            )

        logger.info(
            "Company memory delta retrieved",
            extra={"company_id": company_id, "user_id": user_id, "fact_count": len(facts)},
        )

        return {
            "facts": facts,
            "count": len(facts),
            "company_id": company_id,
        }

    async def confirm_company_data(
        self,
        company_id: str,
        user_id: str,
        corrections: dict[str, str],
    ) -> dict[str, Any]:
        """Confirm existing company data and link user to company.

        When user confirms existing data:
        1. Links user to company via user_profiles.company_id
        2. Applies any corrections provided to corporate_facts
        3. Marks company_discovery and document_upload as skipped
        4. Inherits corporate_memory readiness score from company richness

        Args:
            company_id: ID of existing company to link to.
            user_id: ID of user confirming data.
            corrections: Dict mapping fact IDs to corrected values.

        Returns:
            Dict with link status, skipped steps, inherited readiness, corrections count.
        """
        orchestrator = OnboardingOrchestrator()
        readiness_service = OnboardingReadinessService()

        # 1. Link user to company
        profile_result = (
            self._db.table("user_profiles")
            .update({"company_id": company_id})
            .eq("id", user_id)
            .execute()
        )
        user_linked = len(profile_result.data) > 0

        # 2. Apply corrections to corporate_facts if provided
        corrections_applied = 0
        if corrections:
            for fact_id, correction in corrections.items():
                # Parse correction to determine what to update
                # Format: "subject|predicate|object" -> new value
                # Simple approach: correction is the corrected object value
                update_result = (
                    self._db.table("corporate_facts")
                    .update({"object": correction, "updated_at": datetime.now(UTC).isoformat()})
                    .eq("id", fact_id)
                    .eq("company_id", company_id)
                    .execute()
                )
                if update_result.data:
                    corrections_applied += 1

        # 3. Calculate richness and inherit readiness score
        richness = self._calculate_corporate_richness(company_id)
        inherited_readiness = int(richness * 0.8)  # Corporate memory is 25% of readiness

        # Update user's readiness score
        await readiness_service.recalculate(user_id)

        # 4. Skip company_discovery and document_upload steps
        skipped_steps = []
        if richness > 30:
            # Skip company discovery
            try:
                await orchestrator.skip_step(
                    user_id,
                    "company_discovery",  # type: ignore[arg-type]
                    reason="Company data inherited from Corporate Memory",
                )
                skipped_steps.append("company_discovery")
            except Exception as e:
                logger.warning(f"Failed to skip company_discovery: {e}")

        if richness > 70:
            # Skip document upload for high richness
            try:
                await orchestrator.skip_step(
                    user_id,
                    "document_upload",  # type: ignore[arg-type]
                    reason="Corporate Memory sufficiently rich",
                )
                skipped_steps.append("document_upload")
            except Exception as e:
                logger.warning(f"Failed to skip document_upload: {e}")

        # 5. Record episodic memory event
        await self._record_episodic_event(
            user_id,
            company_id,
            len(skipped_steps),
            inherited_readiness,
        )

        logger.info(
            "Cross-user acceleration applied",
            extra={
                "user_id": user_id,
                "company_id": company_id,
                "skipped_steps": len(skipped_steps),
                "inherited_readiness": inherited_readiness,
            },
        )

        return {
            "user_linked": user_linked,
            "steps_skipped": skipped_steps,
            "readiness_inherited": inherited_readiness,
            "corrections_applied": corrections_applied,
        }

    def _calculate_corporate_richness(self, company_id: str) -> int:
        """Calculate Corporate Memory richness score for a company.

        Queries both corporate_facts and memory_semantic to capture all
        enrichment data (enrichment engine writes to memory_semantic).

        Richness is based on:
        - Number of facts across both tables (target: 20+)
        - Diversity of predicates/categories (target: 8+ unique)
        - Confidence aggregation (average confidence)

        Args:
            company_id: ID of company to analyze.

        Returns:
            Richness score from 0-100.
        """
        all_predicates: set[str] = set()
        all_confidences: list[float] = []

        # Get all active facts from corporate_facts
        result = (
            self._db.table("corporate_facts")
            .select("predicate, confidence")
            .eq("company_id", company_id)
            .eq("is_active", True)
            .execute()
        )

        if result.data:
            for f in result.data:
                all_predicates.add(f["predicate"])
                all_confidences.append(f["confidence"])

        # Also query memory_semantic for enrichment facts with this company_id
        try:
            semantic_result = (
                self._db.table("memory_semantic")
                .select("confidence, source, metadata")
                .contains("metadata", {"company_id": company_id})
                .execute()
            )

            if semantic_result.data:
                for row in semantic_result.data:
                    # Skip personal facts — only corporate data
                    source = row.get("source", "")
                    if "digital_twin" in source or "user_stated" in source:
                        continue
                    all_confidences.append(row["confidence"])
                    metadata = row.get("metadata") or {}
                    category = metadata.get("category", source)
                    all_predicates.add(category)
        except Exception as e:
            logger.warning(
                "Failed to query memory_semantic for richness",
                extra={"company_id": company_id, "error": str(e)},
            )

        fact_count = len(all_confidences)
        if fact_count == 0:
            return 0

        predicate_diversity = len(all_predicates)
        avg_confidence = sum(all_confidences) / fact_count

        # Richness formula:
        # - Fact count: 40% weight (target 20+)
        # - Predicate diversity: 30% weight (target 8+ unique)
        # - Confidence: 30% weight

        fact_score = min(100, (fact_count / 20) * 100)
        diversity_score = min(100, (predicate_diversity / 8) * 100)
        confidence_score = avg_confidence * 100

        richness = (fact_score * 0.4) + (diversity_score * 0.3) + (confidence_score * 0.3)

        return int(richness)

    def _normalize_domain(self, domain: str) -> str:
        """Normalize domain for lookup.

        Removes protocol, www, path, and port. Returns lowercase domain.

        Args:
            domain: Raw domain input.

        Returns:
            Normalized domain (e.g., "acme-corp.com").
        """
        # Remove protocol
        for protocol in ["https://", "http://", "www."]:
            if domain.startswith(protocol):
                domain = domain[len(protocol) :]

        # Remove path and port
        domain = domain.split("/")[0].split(":")[0].lower()

        return domain

    async def _record_episodic_event(
        self,
        user_id: str,
        company_id: str,
        skipped_count: int,
        inherited_readiness: int,
    ) -> None:
        """Record cross-user acceleration event to episodic memory.

        Args:
            user_id: ID of user who was accelerated.
            company_id: ID of company user joined.
            skipped_count: Number of onboarding steps skipped.
            inherited_readiness: Readiness score inherited from company.
        """
        try:
            from src.memory.episodic import Episode, EpisodicMemory

            memory = EpisodicMemory()
            now = datetime.now(UTC)

            episode = Episode(
                id=str(uuid.uuid4()),
                user_id=user_id,
                event_type="cross_user_acceleration",
                content=f"Cross-user acceleration applied — skipped {skipped_count} steps based on existing data",
                participants=[],
                occurred_at=now,
                recorded_at=now,
                context={
                    "company_id": company_id,
                    "steps_skipped": skipped_count,
                    "readiness_inherited": inherited_readiness,
                },
            )
            await memory.store_episode(episode)

        except Exception as e:
            logger.warning(
                "Failed to record episodic event",
                extra={"user_id": user_id, "error": str(e)},
            )
