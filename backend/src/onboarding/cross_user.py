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
                self._db.table("corporate_memory_facts")
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
                self._db.table("corporate_memory_facts")
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
                self._db.table("corporate_memory_facts")
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
        domains_covered = list(set(
            f.get("domain") for f in all_facts if f.get("domain")
        ))

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
