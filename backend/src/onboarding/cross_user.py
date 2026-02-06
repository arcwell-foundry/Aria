"""Cross-user onboarding acceleration service (US-917).

Detects existing Corporate Memory when user #2+ at a company starts onboarding
and recommends step skipping based on data richness.

Key privacy principle: User #2+ should NOT see any personal data from User #1.
Only shared, company-level facts (Corporate Memory) influence acceleration.
"""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from src.db.supabase import SupabaseClient

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
        if richness_score > 80:
            recommendation = "skip"
        elif richness_score >= 30:
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
                return response.data
            return None

        except Exception as e:
            logger.exception(f"Error querying company by domain: {domain}")
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
        fact_score = min(fact_count * 2, 50)
        domain_score = min(domain_coverage * 10, 30)
        doc_score = min(document_count * 5, 20)

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
            logger.exception(f"Error counting facts for company: {company_id}")
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
            logger.exception(f"Error calculating domain coverage: {company_id}")
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
            logger.exception(f"Error counting documents for company: {company_id}")
            return 0
