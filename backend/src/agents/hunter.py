"""HunterAgent module for ARIA.

Discovers and qualifies new leads based on Ideal Customer Profile (ICP).
"""

import logging
from typing import TYPE_CHECKING, Any

from src.agents.base import AgentResult, BaseAgent

if TYPE_CHECKING:
    from src.core.llm import LLMClient

logger = logging.getLogger(__name__)


class HunterAgent(BaseAgent):
    """Discovers and qualifies new leads based on ICP.

    The Hunter agent searches for companies that match the user's
    Ideal Customer Profile, enriches company data, finds contacts,
    and scores fit quality.
    """

    name = "Hunter Pro"
    description = "Discovers and qualifies new leads based on ICP"

    def __init__(self, llm_client: "LLMClient", user_id: str) -> None:
        """Initialize the Hunter agent.

        Args:
            llm_client: LLM client for reasoning and generation.
            user_id: ID of the user this agent is working for.
        """
        self._company_cache: dict[str, Any] = {}
        super().__init__(llm_client=llm_client, user_id=user_id)

    def validate_input(self, task: dict[str, Any]) -> bool:
        """Validate Hunter agent task input.

        Args:
            task: Task specification to validate.

        Returns:
            True if valid, False otherwise.
        """
        # Check required fields exist
        if "icp" not in task:
            return False
        if "target_count" not in task:
            return False

        # Validate icp is a dict with required industry field
        icp = task["icp"]
        if not isinstance(icp, dict):
            return False
        if "industry" not in icp:
            return False

        # Validate target_count is a positive integer
        target_count = task["target_count"]
        if not isinstance(target_count, int):
            return False
        if target_count <= 0:
            return False

        # Validate exclusions is a list if present
        if "exclusions" in task:
            exclusions = task["exclusions"]
            if not isinstance(exclusions, list):
                return False

        return True

    def _register_tools(self) -> dict[str, Any]:
        """Register Hunter agent's lead discovery tools.

        Returns:
            Dictionary mapping tool names to callable functions.
        """
        return {
            "search_companies": self._search_companies,
            "enrich_company": self._enrich_company,
            "find_contacts": self._find_contacts,
            "score_fit": self._score_fit,
        }

    async def execute(self, task: dict[str, Any]) -> AgentResult:  # noqa: ARG002
        """Execute the hunter agent's primary task.

        Args:
            task: Task specification with parameters.

        Returns:
            AgentResult with success status and output data.
        """
        return AgentResult(success=True, data=[])

    async def _search_companies(
        self,
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Search for companies matching ICP criteria.

        Args:
            query: Search query string.
            limit: Maximum number of results to return.

        Returns:
            List of matching companies.

        Raises:
            ValueError: If limit is less than or equal to zero.
        """
        # Return empty list for empty or whitespace-only queries
        if not query or query.strip() == "":
            return []

        # Validate limit
        if limit <= 0:
            raise ValueError(f"limit must be greater than 0, got {limit}")

        logger.info(
            f"Searching for companies with query='{query}', limit={limit}",
        )

        # Mock company data
        mock_companies = [
            {
                "name": "GenTech Bio",
                "domain": "gentechbio.com",
                "description": "Leading biotechnology company specializing in gene therapy research and development.",
                "industry": "Biotechnology",
                "size": "Mid-market (100-500)",
                "geography": "North America",
                "website": "https://www.gentechbio.com",
            },
            {
                "name": "PharmaCorp Solutions",
                "domain": "pharmacorpsolutions.com",
                "description": "Pharmaceutical solutions provider focusing on drug discovery and clinical trials.",
                "industry": "Pharmaceuticals",
                "size": "Enterprise (500+)",
                "geography": "North America",
                "website": "https://www.pharmacorpsolutions.com",
            },
            {
                "name": "BioInnovate Labs",
                "domain": "bioinnovatelabs.com",
                "description": "Innovative biotech laboratory developing cutting-edge diagnostic tools.",
                "industry": "Biotechnology",
                "size": "Startup (1-50)",
                "geography": "Europe",
                "website": "https://www.bioinnovatelabs.com",
            },
        ]

        # Return results up to the limit
        return mock_companies[:limit]

    async def _enrich_company(
        self,
        company: dict[str, Any],
    ) -> dict[str, Any]:
        """Enrich company data with additional information.

        Args:
            company: Company data dictionary to enrich.

        Returns:
            Enriched company data with additional fields.
        """
        # Check cache using domain or name as key
        cache_key = company.get("domain") or company.get("name", "")
        if cache_key in self._company_cache:
            cached = self._company_cache[cache_key]
            # Type narrowing: cached value is always a dict when stored
            assert isinstance(cached, dict)
            return cached

        logger.info(
            f"Enriching company data for '{company.get('name', 'Unknown')}'",
        )

        # Copy original company data
        enriched = company.copy()

        # Add enrichment data
        enriched["technologies"] = ["Salesforce", "HubSpot", "Marketo"]
        enriched["linkedin_url"] = f"https://www.linkedin.com/company/{cache_key.replace('.', '')}"
        enriched["funding_stage"] = "Series C"
        enriched["founded_year"] = 2015
        enriched["revenue"] = "$10M - $50M"

        # Store in cache
        self._company_cache[cache_key] = enriched

        return enriched

    async def _find_contacts(
        self,
        company_name: str,
        roles: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Find contacts at a target company.

        Args:
            company_name: Name of the company to find contacts for.
            roles: Optional list of role keywords to filter by (case-insensitive).

        Returns:
            List of contacts at the company.
        """
        logger.info(
            f"Finding contacts for '{company_name}'"
            + (f" with roles: {roles}" if roles else ""),
        )

        # Mock contact data
        all_contacts = [
            {
                "name": "Sarah Johnson",
                "title": "CEO",
                "email": "sarah.johnson@testcompany.com",
                "linkedin_url": "https://www.linkedin.com/in/sarahjohnson",
                "seniority": "C-Level",
                "department": "Executive",
            },
            {
                "name": "Michael Chen",
                "title": "VP Sales",
                "email": "michael.chen@testcompany.com",
                "linkedin_url": "https://www.linkedin.com/in/michaelchen",
                "seniority": "VP-Level",
                "department": "Sales",
            },
            {
                "name": "Emily Rodriguez",
                "title": "Director of Marketing",
                "email": "emily.rodriguez@testcompany.com",
                "linkedin_url": "https://www.linkedin.com/in/emilyrodriguez",
                "seniority": "Director-Level",
                "department": "Marketing",
            },
            {
                "name": "David Kim",
                "title": "CTO",
                "email": "david.kim@testcompany.com",
                "linkedin_url": "https://www.linkedin.com/in/davidkim",
                "seniority": "C-Level",
                "department": "Engineering",
            },
        ]

        # Filter by roles if provided
        if roles:
            filtered_contacts = []
            for contact in all_contacts:
                title_lower = contact["title"].lower()
                # Check if any role keyword matches the title (case-insensitive)
                # Use word boundaries to avoid substring matches like "CTO" in "Director"
                if any(
                    role.lower() in title_lower.split()
                    or role.lower() in title_lower.replace(".", " ").split()
                    for role in roles
                ):
                    filtered_contacts.append(contact)
            return filtered_contacts

        return all_contacts

    async def _score_fit(self) -> tuple[float, list[Any], list[Any]]:
        """Score company fit against ICP.

        Returns:
            Tuple of (score, strengths, gaps).
        """
        return 0.0, [], []
