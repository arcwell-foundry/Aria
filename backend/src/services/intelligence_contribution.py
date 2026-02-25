"""Intelligence Contribution Service - extracts shareable insights from goal executions.

When a goal completes successfully, this service:
1. Extracts facts about accounts/companies from the goal results
2. Filters out personal/private information
3. Contributes shareable facts to the shared_intelligence pool
4. Only contributes if the user has opted in to team intelligence sharing

This enables the "team intelligence" feature where Rep A's learnings about
a shared account can benefit Rep B at the same company.
"""

import logging
import re
from typing import Any

from src.db.supabase import SupabaseClient
from src.memory.shared_intelligence import (
    IntelligenceSource,
    get_shared_intelligence_service,
)

logger = logging.getLogger(__name__)


# Patterns for extracting account-related facts from goal outputs
_ACCOUNT_FACT_PATTERNS = [
    # Company uses product/service
    r"(\w[\w\s]+?)\s+(?:uses|uses the|implemented|deployed|adopted)\s+(\w[\w\s]+)",
    # Company is/focuses on
    r"(\w[\w\s]+?)\s+(?:is a|specializes in|focuses on|is focused on)\s+(\w[\w\s]+)",
    # Decision maker/contact
    r"(\w[\w\s]+?)\s+(?:is the|is a|serves as)\s+(.+?)(?:at|for)\s+(\w[\w\s]+)",
    # Product/platform
    r"(\w[\w\s]+?)\s+(?:platform|product|solution)\s+(?:is|provides|offers)\s+(.+)",
    # Need/pain point
    r"(\w[\w\s]+?)\s+(?:needs|requires|is looking for|seeking)\s+(.+)",
]

# Patterns to EXCLUDE (private/personal information)
_EXCLUSION_PATTERNS = [
    r"\b(?:password|ssn|social security|credit card|bank account)\b",
    r"\b(?:salary|compensation|bonus)\b",
    r"\b(?:personal|private|confidential)\b",
    r"\b(?:my |our |i am|i have)\b",
    r"@[\w.-]+\.[\w]+",  # Email addresses
    r"\d{3}[-.\s]?\d{3}[-.\s]?\d{4}",  # Phone numbers
]


class IntelligenceContributionService:
    """Service for extracting and contributing shareable insights from goals.

    Hooks into goal completion to automatically extract account-level facts
    that can be shared with team members (if opted in).
    """

    def __init__(self) -> None:
        """Initialize service."""
        self._db = SupabaseClient.get_client()
        self._shared_intel = get_shared_intelligence_service()

    async def process_goal_completion(
        self,
        user_id: str,
        goal_id: str,
        goal_title: str,
        goal_results: dict[str, Any],
        retrospective: dict[str, Any] | None = None,
    ) -> int:
        """Extract shareable insights from a completed goal and contribute them.

        Args:
            user_id: The user who completed the goal.
            goal_id: The goal ID.
            goal_title: Title of the completed goal.
            goal_results: Results from agent executions.
            retrospective: Optional retrospective data.

        Returns:
            Number of facts contributed to shared intelligence.
        """
        try:
            # Get user's company_id
            company_id = await self._get_user_company_id(user_id)
            if not company_id:
                logger.debug(
                    "User has no company_id, skipping intelligence contribution",
                    extra={"user_id": user_id},
                )
                return 0

            # Check if user has opted in
            if not await self._shared_intel.is_user_opted_in(user_id):
                logger.debug(
                    "User not opted into team intelligence, skipping contribution",
                    extra={"user_id": user_id},
                )
                return 0

            # Extract the account name from the goal context
            account_name = await self._extract_account_name(goal_id, goal_title)

            # Extract facts from goal results
            facts = await self._extract_facts_from_results(
                goal_results=goal_results,
                retrospective=retrospective,
                account_name=account_name,
            )

            if not facts:
                return 0

            # Contribute each fact
            contributed = 0
            for fact in facts:
                result = await self._shared_intel.contribute_fact(
                    user_id=user_id,
                    company_id=company_id,
                    subject=fact["subject"],
                    predicate=fact["predicate"],
                    object=fact["object"],
                    confidence=fact.get("confidence", 0.7),
                    related_account_name=account_name,
                    source_type=IntelligenceSource.GOAL_EXECUTION,
                    is_anonymized=True,  # Default to anonymized for privacy
                )
                if result:
                    contributed += 1

            if contributed > 0:
                logger.info(
                    "Contributed shared intelligence from goal",
                    extra={
                        "user_id": user_id,
                        "goal_id": goal_id,
                        "facts_contributed": contributed,
                        "account_name": account_name,
                    },
                )

            return contributed

        except Exception as e:
            logger.warning(
                "Failed to process goal completion for intelligence contribution",
                extra={"user_id": user_id, "goal_id": goal_id, "error": str(e)},
            )
            return 0

    async def _get_user_company_id(self, user_id: str) -> str | None:
        """Get the company_id for a user.

        Args:
            user_id: The user ID.

        Returns:
            Company ID if found, None otherwise.
        """
        try:
            result = (
                self._db.table("user_profiles")
                .select("company_id")
                .eq("id", user_id)
                .maybe_single()
                .execute()
            )

            if result and result.data:
                return result.data.get("company_id")

            return None

        except Exception:
            return None

    async def _extract_account_name(
        self,
        goal_id: str,
        goal_title: str,
    ) -> str | None:
        """Extract the primary account name from goal context.

        Args:
            goal_id: The goal ID.
            goal_title: The goal title.

        Returns:
            Account name if found, None otherwise.
        """
        # First, try to get from goal metadata
        try:
            result = (
                self._db.table("goals")
                .select("metadata, context")
                .eq("id", goal_id)
                .maybe_single()
                .execute()
            )

            if result and result.data:
                metadata = result.data.get("metadata", {}) or {}
                context = result.data.get("context", {}) or {}

                # Check common locations for account name
                account_name = (
                    metadata.get("account_name")
                    or metadata.get("company_name")
                    or context.get("account_name")
                    or context.get("company_name")
                )

                if account_name:
                    return str(account_name)

        except Exception:
            pass

        # Fallback: try to extract from goal title
        # Common patterns: "Research Acme Pharma", "Analyze BioGenix account", etc.
        title_lower = goal_title.lower()
        for prefix in ["research ", "analyze ", "study ", "investigate ", "review "]:
            if title_lower.startswith(prefix):
                return goal_title[len(prefix):].strip()

        return None

    async def _extract_facts_from_results(
        self,
        goal_results: dict[str, Any],
        retrospective: dict[str, Any] | None,
        account_name: str | None,
    ) -> list[dict[str, Any]]:
        """Extract shareable facts from goal results.

        Args:
            goal_results: Results from agent executions.
            retrospective: Optional retrospective data.
            account_name: The account this goal is about.

        Returns:
            List of extracted fact dictionaries.
        """
        facts: list[dict[str, Any]] = []
        seen_facts: set[str] = set()  # For deduplication

        # Extract from agent execution results
        if goal_results:
            for agent_name, result in goal_results.items():
                if isinstance(result, dict):
                    # Check for analysis output
                    analysis = result.get("analysis") or result.get("output") or result.get("result")
                    if isinstance(analysis, str):
                        extracted = self._extract_facts_from_text(analysis, account_name)
                        for fact in extracted:
                            fact_key = f"{fact['subject']}|{fact['predicate']}|{fact['object']}"
                            if fact_key not in seen_facts:
                                seen_facts.add(fact_key)
                                facts.append(fact)

                    # Check for structured findings
                    findings = result.get("findings") or result.get("key_findings") or []
                    if isinstance(findings, list):
                        for finding in findings:
                            if isinstance(finding, str):
                                extracted = self._extract_facts_from_text(finding, account_name)
                                for fact in extracted:
                                    fact_key = f"{fact['subject']}|{fact['predicate']}|{fact['object']}"
                                    if fact_key not in seen_facts:
                                        seen_facts.add(fact_key)
                                        facts.append(fact)

        # Extract from retrospective
        if retrospective:
            summary = retrospective.get("summary", "")
            if isinstance(summary, str):
                extracted = self._extract_facts_from_text(summary, account_name)
                for fact in extracted:
                    fact_key = f"{fact['subject']}|{fact['predicate']}|{fact['object']}"
                    if fact_key not in seen_facts:
                        seen_facts.add(fact_key)
                        facts.append(fact)

            learnings = retrospective.get("key_learnings", [])
            if isinstance(learnings, list):
                for learning in learnings:
                    if isinstance(learning, str):
                        extracted = self._extract_facts_from_text(learning, account_name)
                        for fact in extracted:
                            fact_key = f"{fact['subject']}|{fact['predicate']}|{fact['object']}"
                            if fact_key not in seen_facts:
                                seen_facts.add(fact_key)
                                facts.append(fact)

        return facts

    def _extract_facts_from_text(
        self,
        text: str,
        account_name: str | None,
    ) -> list[dict[str, Any]]:
        """Extract structured facts from unstructured text.

        Args:
            text: Text to extract facts from.
            account_name: Optional account name for context.

        Returns:
            List of extracted fact dictionaries.
        """
        facts: list[dict[str, Any]] = []

        # Skip if text contains private information
        text_lower = text.lower()
        for pattern in _EXCLUSION_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return []

        # Try to match fact patterns
        for pattern in _ACCOUNT_FACT_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                groups = match.groups()
                if len(groups) >= 2:
                    subject = groups[0].strip() if groups[0] else account_name
                    predicate = self._infer_predicate(match.group(0))
                    obj = groups[-1].strip() if groups[-1] else ""

                    # Validate extracted fact
                    if (
                        subject
                        and obj
                        and len(subject) > 2
                        and len(obj) > 2
                        and subject.lower() != obj.lower()
                    ):
                        facts.append({
                            "subject": subject,
                            "predicate": predicate,
                            "object": obj,
                            "confidence": 0.7,  # Default confidence for extracted facts
                        })

        return facts

    def _infer_predicate(self, matched_text: str) -> str:
        """Infer the predicate type from matched text.

        Args:
            matched_text: The text that matched a pattern.

        Returns:
            A normalized predicate string.
        """
        text_lower = matched_text.lower()

        if any(w in text_lower for w in ["uses", "implemented", "deployed", "adopted"]):
            return "uses"
        if any(w in text_lower for w in ["is a", "specializes in", "focuses on"]):
            return "is"
        if any(w in text_lower for w in ["is the", "is a", "serves as"]):
            return "has_role"
        if any(w in text_lower for w in ["needs", "requires", "looking for", "seeking"]):
            return "needs"
        if any(w in text_lower for w in ["provides", "offers"]):
            return "provides"

        return "has_property"


# Singleton instance
_intelligence_contribution_service: IntelligenceContributionService | None = None


def get_intelligence_contribution_service() -> IntelligenceContributionService:
    """Get or create the IntelligenceContributionService singleton.

    Returns:
        The singleton IntelligenceContributionService instance.
    """
    global _intelligence_contribution_service  # noqa: PLW0603
    if _intelligence_contribution_service is None:
        _intelligence_contribution_service = IntelligenceContributionService()
    return _intelligence_contribution_service
