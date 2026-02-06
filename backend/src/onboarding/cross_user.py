"""Cross-user onboarding acceleration service (US-917).

Detects existing Corporate Memory when user #2+ at a company starts onboarding
and recommends step skipping based on data richness.

Key privacy principle: User #2+ should NOT see any personal data from User #1.
Only shared, company-level facts (Corporate Memory) influence acceleration.
"""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from supabase import Client

logger = logging.getLogger(__name__)


@dataclass
class CompanyCheckResult:
    """Result of checking if a company exists in Corporate Memory.

    Attributes:
        exists: Whether the company was found.
        company_id: The company UUID if found.
        company_name: The company name if found.
        richness_score: 0-100 score of Corporate Memory completeness.
        recommendation: skip (rich > 80), partial (30-80), full (< 30 or not found).
    """

    exists: bool
    company_id: str | None
    company_name: str | None
    richness_score: int
    recommendation: Literal["skip", "partial", "full"]


class CrossUserAccelerationService:
    """Detects existing Corporate Memory for cross-user onboarding acceleration.

    When a user starts onboarding, checks if their company domain already has
    Corporate Memory from previous users. If so, recommends skipping or shortening
    company discovery steps based on data richness.

    CRITICAL: Privacy by design - only corporate facts flow across users.
    Class variables define explicit allow/block lists for data sources.
    """

    # Corporate sources: Shared across all users in a company
    _CORPORATE_SOURCES = frozenset([
        "extracted",      # Extracted from documents (anonymized)
        "aggregated",     # Aggregated from cross-user patterns
        "admin_stated",   # Manually entered by company admin
    ])

    # Personal sources: NEVER shared across users (block list)
    _PERSONAL_SOURCES = frozenset([
        "user_stated",    # Directly stated by user in conversation
        "crm_import",     # Imported from user's personal CRM
        "email_analyzed", # Derived from user's personal email
    ])

    # Richness score thresholds
    _RICHNESS_THRESHOLD_SKIP = 80
    _RICHNESS_THRESHOLD_PARTIAL = 30

    # Richness score calculation weights and caps
    _FACT_WEIGHT = 2
    _FACT_MAX_SCORE = 50
    _DOMAIN_WEIGHT = 10
    _DOMAIN_MAX_SCORE = 30
    _DOC_WEIGHT = 5
    _DOC_MAX_SCORE = 20

    def __init__(self, db: "Client", llm_client: None = None) -> None:
        """Initialize cross-user acceleration service.

        Args:
            db: Supabase client for database queries.
            llm_client: Reserved for future LLM-based enrichment (not used in MVP).
        """
        self._db = db
        self._llm_client = llm_client
        logger.info("CrossUserAccelerationService initialized")

    def check_company_exists(self, domain: str) -> CompanyCheckResult:
        """Check if a company domain exists in Corporate Memory.

        Queries the companies table by domain. If found, calculates richness
        score and returns recommendation. If not found, returns full recommendation.

        Args:
            domain: The company domain to check (e.g., "acme-corp.com").

        Returns:
            CompanyCheckResult with existence status and recommendation.
        """
        company = self._get_company_by_domain(domain)

        if not company:
            logger.info(f"Company not found for domain: {domain}")
            return CompanyCheckResult(
                exists=False,
                company_id=None,
                company_name=None,
                richness_score=0,
                recommendation="full",
            )

        company_id = company["id"]
        company_name = company.get("name")
        richness_score = self._calculate_richness_score(company_id)

        # Determine recommendation based on richness
        recommendation: Literal["skip", "partial", "full"]
        if richness_score > self._RICHNESS_THRESHOLD_SKIP:
            recommendation = "skip"
        elif richness_score >= self._RICHNESS_THRESHOLD_PARTIAL:
            recommendation = "partial"
        else:
            recommendation = "full"

        logger.info(
            f"Company found: {company_name} ({company_id}), "
            f"richness={richness_score}, recommendation={recommendation}"
        )

        return CompanyCheckResult(
            exists=True,
            company_id=company_id,
            company_name=company_name,
            richness_score=richness_score,
            recommendation=recommendation,
        )

    def _get_company_by_domain(self, domain: str) -> dict[str, Any] | None:
        """Query companies table by domain.

        Args:
            domain: The company domain to look up.

        Returns:
            Company dict if found, None otherwise.
        """
        try:
            response = (
                self._db.table("companies")
                .select("*")
                .eq("domain", domain)
                .maybe_single()
                .execute()
            )

            if response and response.data:
                return response.data  # type: ignore[return-value]
            return None

        except Exception as e:
            logger.exception(f"Error querying company by domain {domain}: {e}")
            return None

    def _calculate_richness_score(self, company_id: str) -> int:
        """Calculate Corporate Memory richness score for a company.

        Weighted formula (max 100):
        - Fact count (max 50): facts * 2, capped at 50
        - Domain coverage (max 30): distinct domains * 10, capped at 30
        - Document count (max 20): docs * 5, capped at 20

        Args:
            company_id: The company UUID to score.

        Returns:
            Richness score from 0-100.
        """
        fact_count = self._count_company_facts(company_id)
        domain_coverage = self._calculate_domain_coverage(company_id)
        document_count = self._count_company_documents(company_id)

        # Apply weights with caps
        fact_score = min(fact_count * self._FACT_WEIGHT, self._FACT_MAX_SCORE)
        domain_score = min(domain_coverage * self._DOMAIN_WEIGHT, self._DOMAIN_MAX_SCORE)
        doc_score = min(document_count * self._DOC_WEIGHT, self._DOC_MAX_SCORE)

        total_score = fact_score + domain_score + doc_score

        logger.debug(
            f"Richness calculation for {company_id}: "
            f"facts={fact_count}, domains={domain_coverage}, docs={document_count}, "
            f"score={total_score}"
        )

        return total_score

    def _count_company_facts(self, company_id: str) -> int:
        """Count corporate facts for a company.

        Only counts facts with corporate sources (excludes personal sources).

        Args:
            company_id: The company UUID.

        Returns:
            Number of active corporate facts.
        """
        try:
            response = (
                self._db.table("corporate_facts")
                .select("id", count="exact")  # type: ignore[arg-type]
                .eq("company_id", company_id)
                .eq("is_active", True)
                .in_("source", list(self._CORPORATE_SOURCES))
                .execute()
            )

            if response and hasattr(response, "count") and response.count:
                return response.count
            return 0

        except Exception as e:
            logger.exception(f"Error counting facts for company {company_id}: {e}")
            return 0

    def _calculate_domain_coverage(self, company_id: str) -> int:
        """Count distinct knowledge domains covered by corporate facts.

        Domains are derived from fact predicates (e.g., "has_headquarters"
        falls under geography, "specializes_in" under industry).

        Args:
            company_id: The company UUID.

        Returns:
            Number of distinct domains covered.
        """
        # For MVP: Count distinct predicates as proxy for domains
        # Future enhancement: Group predicates into semantic domains
        try:
            response = (
                self._db.table("corporate_facts")
                .select("predicate")
                .eq("company_id", company_id)
                .eq("is_active", True)
                .in_("source", list(self._CORPORATE_SOURCES))
                .execute()
            )

            if response and response.data:
                predicates: set[str] = set()
                for fact in response.data:
                    if isinstance(fact, dict) and "predicate" in fact:
                        predicates.add(fact["predicate"])
                return len(predicates)

            return 0

        except Exception as e:
            logger.exception(f"Error calculating domain coverage for company {company_id}: {e}")
            return 0

    def _count_company_documents(self, company_id: str) -> int:
        """Count documents ingested for a company.

        Args:
            company_id: The company UUID.

        Returns:
            Number of documents associated with the company.
        """
        try:
            response = (
                self._db.table("company_documents")
                .select("id", count="exact")  # type: ignore[arg-type]
                .eq("company_id", company_id)
                .execute()
            )

            if response and hasattr(response, "count") and response.count:
                return response.count
            return 0

        except Exception as e:
            logger.exception(f"Error counting documents for company {company_id}: {e}")
            return 0

    def get_company_memory_delta(self, company_id: str, user_id: str) -> dict[str, Any]:
        """Get existing company facts for user confirmation.

        Returns tiered Memory Delta with:
        - High-confidence facts shown first
        - ONLY corporate data (personal data filtered out)

        Privacy: Enforced at query level with source filtering.

        Args:
            company_id: The company UUID to get facts for.
            user_id: The user UUID (for logging/audit purposes).

        Returns:
            Dict with:
                - facts: all corporate facts as list of dicts
                - high_confidence_facts: subset with confidence >= 0.8
                - domains_covered: list of distinct domains
                - total_fact_count: total number of facts
        """
        # Query only corporate memory facts with allowed sources
        try:
            response = (
                self._db.table("corporate_facts")
                .select("*")
                .eq("company_id", company_id)
                .eq("is_active", True)
                .in_("source", list(self._CORPORATE_SOURCES))
                .execute()
            )

            facts = response.data if response and response.data else []

        except Exception as e:
            logger.exception(f"Error querying facts for company {company_id}: {e}")
            facts = []

        # Build fact representations from database records
        # Note: corporate_facts table has subject/predicate/object structure
        # We derive a human-readable "fact" string and extract domain from predicate
        all_facts = []
        for f in facts:
            if not isinstance(f, dict):
                continue

            # Derive domain from predicate (e.g., "specializes_in" -> "product")
            # For MVP: use predicate as domain proxy
            predicate = f.get("predicate", "")
            domain = self._derive_domain_from_predicate(predicate)

            # Build human-readable fact string
            subject = f.get("subject", "Unknown")
            obj = f.get("object", "")
            fact_str = f"{subject} {predicate} {obj}" if obj else f"{subject} {predicate}"

            all_facts.append({
                "id": f.get("id"),
                "fact": fact_str,
                "domain": domain,
                "confidence": f.get("confidence", 0.5),
                "source": f.get("source"),
            })

        # Separate high-confidence facts (>=0.8) for tiered display
        high_confidence_facts = [f for f in all_facts if f.get("confidence", 0) >= 0.8]

        # Extract distinct domains covered
        domains_covered = list({
            f.get("domain") for f in all_facts if f.get("domain")
        })

        logger.info(
            f"Retrieved {len(all_facts)} corporate facts for company {company_id}, "
            f"user {user_id} ({len(high_confidence_facts)} high-confidence)"
        )

        return {
            "facts": all_facts,
            "high_confidence_facts": high_confidence_facts,
            "domains_covered": domains_covered,
            "total_fact_count": len(all_facts),
        }

    def _derive_domain_from_predicate(self, predicate: str) -> str:
        """Derive knowledge domain from a predicate.

        Maps predicates to semantic domains for categorization.
        For MVP, uses simple keyword matching.

        Args:
            predicate: The predicate string (e.g., "specializes_in", "has_headquarters").

        Returns:
            Domain string (e.g., "product", "geography", "leadership").
        """
        predicate_lower = predicate.lower()

        # Domain mapping
        domain_mapping = {
            # Product domain
            "specializes_in": "product",
            "manufactures": "product",
            "develops": "product",
            "offers": "product",

            # Geography domain
            "has_headquarters": "geography",
            "located_in": "geography",
            "has_office": "geography",
            "operates_in": "geography",

            # Leadership domain
            "founded_by": "leadership",
            "led_by": "leadership",
            "ceo_is": "leadership",
            "executive": "leadership",

            # Financial domain
            "founded_in": "financial",
            "funding_round": "financial",
            "revenue": "financial",
            "valuation": "financial",

            # Partnership domain
            "partners_with": "partnership",
            "collaborates": "partnership",
            "strategic_alliance": "partnership",
        }

        # Check for exact matches first
        if predicate_lower in domain_mapping:
            return domain_mapping[predicate_lower]

        # Check for partial matches
        for key, domain in domain_mapping.items():
            if key in predicate_lower:
                return domain

        # Default to corporate domain
        return "corporate"

    def confirm_company_data(
        self,
        company_id: str,
        user_id: str,
        corrections: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Confirm existing company data and link user to company.

        When user #2+ confirms their company data, this method:
        1. Links user to company via user_profiles
        2. Applies any corrections provided by user
        3. Marks company_discovery and document_upload as skipped
        4. Inherits corporate_memory readiness score from company richness

        Args:
            company_id: The company UUID to link to.
            user_id: The user UUID to link.
            corrections: Optional dict of field names to corrected values.

        Returns:
            Dict with:
                - user_linked: bool, whether user was successfully linked
                - steps_skipped: list of step names that were skipped
                - readiness_inherited: int, corporate_memory readiness score inherited
                - corrections_applied: int, number of corrections applied
        """
        logger.info(
            f"Confirming company data for user {user_id} "
            f"at company {company_id}"
        )

        # Calculate richness score for inheritance
        richness_score = self._calculate_richness_score(company_id)

        # Link user to company
        user_linked = self._link_user_to_company(company_id, user_id)

        # Apply corrections if provided
        corrections_applied = 0
        if corrections:
            corrections_applied = self._apply_corrections(
                company_id,
                user_id,
                corrections,
            )

        # Skip onboarding steps
        steps_skipped = self._skip_onboarding_steps(user_id)

        # Inherit readiness score
        self._inherit_readiness_score(user_id, richness_score)

        logger.info(
            f"Company data confirmed: user_linked={user_linked}, "
            f"steps_skipped={steps_skipped}, readiness_inherited={richness_score}, "
            f"corrections_applied={corrections_applied}"
        )

        return {
            "user_linked": user_linked,
            "steps_skipped": steps_skipped,
            "readiness_inherited": richness_score,
            "corrections_applied": corrections_applied,
        }

    def _link_user_to_company(self, company_id: str, user_id: str) -> bool:
        """Link user to company via user_profiles table.

        Args:
            company_id: The company UUID to link to.
            user_id: The user UUID to link.

        Returns:
            True if successful, False otherwise.
        """
        try:
            response = (
                self._db.table("user_profiles")
                .update({"company_id": company_id})
                .eq("id", user_id)
                .execute()
            )

            if response and response.data:
                logger.info(f"Linked user {user_id} to company {company_id}")
                return True
            return False

        except Exception as e:
            logger.exception(
                f"Error linking user {user_id} to company {company_id}: {e}"
            )
            return False

    def _apply_corrections(
        self,
        company_id: str,
        user_id: str,
        corrections: dict[str, str],
    ) -> int:
        """Apply user corrections to corporate memory.

        For each correction, inserts a new fact into corporate_facts with
        source="admin_stated" and confidence=0.95 (highest priority per
        Source Hierarchy for Conflict Resolution).

        User corrections are elevated to admin-level shared facts to ensure
        they flow into corporate memory for all users at the company.

        Args:
            company_id: The company UUID.
            user_id: The user UUID making the corrections.
            corrections: Dict of field names to corrected values.

        Returns:
            Number of corrections applied.
        """
        applied_count = 0

        for field, value in corrections.items():
            if not value:
                continue

            try:
                # Map common field names to predicates
                predicate = self._map_field_to_predicate(field)
                if not predicate:
                    logger.warning(f"Unknown correction field: {field}")
                    continue

                # Insert correction as high-confidence fact
                # Use admin_stated (not user_stated) to ensure it's shared across users
                (
                    self._db.table("corporate_facts")
                    .insert({
                        "company_id": company_id,
                        "subject": company_id,  # Company is the subject
                        "predicate": predicate,
                        "object": str(value),
                        "confidence": 0.95,  # User-stated = highest priority
                        "source": "admin_stated",
                        "created_by": user_id,
                        "is_active": True,
                    })
                    .execute()
                )

                applied_count += 1
                logger.info(
                    f"Applied correction for {field}={value} "
                    f"at company {company_id}"
                )

            except Exception as e:
                logger.exception(
                    f"Error applying correction {field}={value}: {e}"
                )

        return applied_count

    def _map_field_to_predicate(self, field: str) -> str | None:
        """Map a field name to a corporate_facts predicate.

        Args:
            field: The field name (e.g., "headquarters", "founded_year").

        Returns:
            Predicate string or None if unknown.
        """
        field_mapping = {
            "headquarters": "has_headquarters",
            "founded_year": "founded_in",
            "company_name": "named",
            "industry": "specializes_in",
            "ceo": "ceo_is",
            "revenue": "revenue",
            "employee_count": "has_employee_count",
            "description": "described_as",
        }

        return field_mapping.get(field)

    def _skip_onboarding_steps(self, user_id: str) -> list[str]:
        """Mark company_discovery and document_upload as skipped.

        Args:
            user_id: The user UUID.

        Returns:
            List of skipped step names.
        """
        skipped_steps = ["company_discovery", "document_upload"]

        try:
            (
                self._db.table("onboarding_state")
                .update({"skipped_steps": skipped_steps})
                .eq("user_id", user_id)
                .execute()
            )

            logger.info(f"Marked steps as skipped for user {user_id}: {skipped_steps}")

        except Exception as e:
            logger.exception(f"Error skipping steps for user {user_id}: {e}")

        return skipped_steps

    def _inherit_readiness_score(self, user_id: str, richness_score: int) -> None:
        """Update corporate_memory readiness score from company richness.

        Args:
            user_id: The user UUID.
            richness_score: The richness score to inherit (0-100).
        """
        try:
            # Get current onboarding_state
            response = (
                self._db.table("onboarding_state")
                .select("readiness_scores")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )

            if not response or not response.data:
                logger.warning(f"No onboarding_state found for user {user_id}")
                return

            # Type narrowing for response.data which is JSON type
            data_dict = response.data if isinstance(response.data, dict) else {}
            current_scores = data_dict.get("readiness_scores", {})
            if not isinstance(current_scores, dict):
                current_scores = {}

            # Update corporate_memory sub-score
            updated_scores = {
                **current_scores,
                "corporate_memory": richness_score,
            }

            # Write back
            (
                self._db.table("onboarding_state")
                .update({"readiness_scores": updated_scores})
                .eq("user_id", user_id)
                .execute()
            )

            logger.info(
                f"Updated readiness_scores for user {user_id}: "
                f"corporate_memory={richness_score}"
            )

        except Exception as e:
            logger.exception(
                f"Error inheriting readiness score for user {user_id}: {e}"
            )
