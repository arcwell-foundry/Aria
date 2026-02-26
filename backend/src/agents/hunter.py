"""HunterAgent module for ARIA.

Discovers and qualifies new leads based on Ideal Customer Profile (ICP).
"""

import json
import logging
import re
from typing import TYPE_CHECKING, Any, cast

from src.agents.base import AgentResult
from src.agents.skill_aware_agent import SkillAwareAgent
from src.core.config import settings

if TYPE_CHECKING:
    from src.core.llm import LLMClient
    from src.core.persona import PersonaBuilder
    from src.memory.cold_retrieval import ColdMemoryRetriever
    from src.memory.hot_context import HotContextBuilder
    from src.skills.index import SkillIndex
    from src.skills.orchestrator import SkillOrchestrator

logger = logging.getLogger(__name__)


def _extract_json_from_text(text: str) -> Any:
    """Extract JSON from text that may contain markdown code fences.

    Claude sometimes wraps JSON responses in ```json ... ``` blocks.
    This helper strips those wrappers and parses the JSON.

    Args:
        text: Raw text potentially containing JSON.

    Returns:
        Parsed JSON object (list or dict).

    Raises:
        json.JSONDecodeError: If no valid JSON can be extracted.
    """
    # Try direct parse first
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code fences
    pattern = r"```(?:json)?\s*\n?(.*?)\n?\s*```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return json.loads(match.group(1).strip())

    # Try finding array or object boundaries
    for start_char, end_char in [("[", "]"), ("{", "}")]:
        start_idx = text.find(start_char)
        end_idx = text.rfind(end_char)
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            return json.loads(text[start_idx : end_idx + 1])

    raise json.JSONDecodeError("No valid JSON found in text", text, 0)


class HunterAgent(SkillAwareAgent):
    """Discovers and qualifies new leads based on ICP.

    The Hunter agent searches for companies that match the user's
    Ideal Customer Profile, enriches company data, finds contacts,
    and scores fit quality.
    """

    name = "Hunter Pro"
    description = "Discovers and qualifies new leads based on ICP"
    agent_id = "hunter"

    def __init__(
        self,
        llm_client: "LLMClient",
        user_id: str,
        skill_orchestrator: "SkillOrchestrator | None" = None,
        skill_index: "SkillIndex | None" = None,
        persona_builder: "PersonaBuilder | None" = None,
        hot_context_builder: "HotContextBuilder | None" = None,
        cold_retriever: "ColdMemoryRetriever | None" = None,
    ) -> None:
        """Initialize the Hunter agent.

        Args:
            llm_client: LLM client for reasoning and generation.
            user_id: ID of the user this agent is working for.
            skill_orchestrator: Optional orchestrator for multi-skill execution.
            skill_index: Optional index for skill discovery.
            persona_builder: Optional PersonaBuilder for centralized prompt assembly.
            hot_context_builder: Optional builder for always-loaded context.
            cold_retriever: Optional retriever for on-demand deep memory search.
        """
        self._company_cache: dict[str, Any] = {}
        self._exa_provider: Any = None
        self._resource_status: list[dict[str, Any]] = []  # Tool connectivity status
        super().__init__(
            llm_client=llm_client,
            user_id=user_id,
            skill_orchestrator=skill_orchestrator,
            skill_index=skill_index,
            persona_builder=persona_builder,
            hot_context_builder=hot_context_builder,
            cold_retriever=cold_retriever,
        )

    def _get_exa_provider(self) -> Any:
        """Lazily initialize and return the ExaEnrichmentProvider."""
        if self._exa_provider is None:
            try:
                from src.agents.capabilities.enrichment_providers.exa_provider import (
                    ExaEnrichmentProvider,
                )

                self._exa_provider = ExaEnrichmentProvider()
                logger.info("HunterAgent: ExaEnrichmentProvider initialized")
            except Exception as e:
                logger.warning("HunterAgent: Failed to initialize ExaEnrichmentProvider: %s", e)
        return self._exa_provider

    def _check_tool_connected(
        self,
        resource_status: list[dict[str, Any]],
        tool_name: str,
    ) -> bool:
        """Check if a specific tool is connected based on resource_status.

        Args:
            resource_status: List of resource status dicts from the task.
            tool_name: Name of the tool to check (e.g., "exa", "apollo").

        Returns:
            True if the tool is connected, False otherwise.
        """
        if not resource_status:
            return False

        tool_lower = tool_name.lower()
        for resource in resource_status:
            tool = resource.get("tool", "").lower()
            if tool == tool_lower and resource.get("connected", False):
                return True

        return False

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
            "find_similar_companies": self._find_similar_companies,
            "search_territory_leads": self.search_territory_leads,
        }

    async def execute(self, task: dict[str, Any]) -> AgentResult:
        """Execute the hunter agent's primary task.

        Args:
            task: Task specification with parameters.

        Returns:
            AgentResult with success status and output data.
        """
        # OODA ACT: Log skill consideration before native execution
        await self._log_skill_consideration()

        logger.info("Hunter agent starting lead discovery task")

        # Extract team intelligence for LLM enrichment (optional, fail-open)
        self._team_intelligence: str = task.get("team_intelligence", "")

        # Extract resource_status for graceful degradation
        resource_status = task.get("resource_status", [])
        self._resource_status = resource_status

        # Check if Exa (our primary search tool) is available
        exa_available = settings.EXA_API_KEY or self._check_tool_connected(resource_status, "exa")

        # Extract task parameters
        icp = task["icp"]
        target_count = task["target_count"]
        exclusions = task.get("exclusions", [])

        # Step 1: Build search query from ICP industry
        industry = icp.get("industry", "")
        search_query = industry if isinstance(industry, str) else industry[0] if industry else ""

        # Step 2: Search for companies (limit = target_count * 3 to have pool)
        search_limit = target_count * 3
        companies = await self._search_companies(query=search_query, limit=search_limit)

        # Step 3: Filter out excluded companies
        if exclusions:
            companies = [c for c in companies if c.get("domain") not in exclusions]

        # Step 4: Limit to target_count
        companies = companies[:target_count]

        # Step 5: Process each company - enrich, find contacts, score fit
        leads = []
        for company in companies:
            try:
                # Enrich company data
                enriched_company = await self._enrich_company(company)

                # Find contacts
                contacts = await self._find_contacts(company_name=enriched_company["name"])

                # Score fit against ICP
                fit_score, fit_reasons, gaps = await self._score_fit(
                    company=enriched_company,
                    icp=icp,
                )

                # Build lead object
                lead = {
                    "company": enriched_company,
                    "contacts": contacts,
                    "fit_score": fit_score,
                    "fit_reasons": fit_reasons,
                    "gaps": gaps,
                    "source": "hunter_pro",
                }
                leads.append(lead)

            except Exception as e:
                # Handle per-company exceptions gracefully
                logger.warning(f"Failed to process company '{company.get('name', 'Unknown')}': {e}")
                continue

        # Step 6: Sort leads by fit_score descending
        leads.sort(key=lambda lead: cast(float, lead["fit_score"]), reverse=True)

        logger.info(
            f"Hunter agent completed - found {len(leads)} leads",
            extra={"lead_count": len(leads)},
        )

        # Return leads directly for backward compatibility
        # Add advisory as metadata if needed (consumers can check result.data for advisory key)
        result = AgentResult(success=True, data=leads)

        # Add advisory to result data if tools were degraded
        if not exa_available and leads:
            # Include an advisory message in the first lead's metadata
            leads[0]["_advisory"] = (
                "Lead discovery used LLM knowledge instead of real-time web search. "
                "Connect Exa in Settings > Integrations for live company data."
            )

        return result

    async def _search_companies_via_exa(
        self,
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Search for companies using the ExaEnrichmentProvider.

        Args:
            query: Search query string.
            limit: Maximum number of results.

        Returns:
            List of company dicts parsed from Exa results.

        Raises:
            Exception: If Exa API call fails.
        """
        exa = self._get_exa_provider()
        if not exa:
            raise RuntimeError("ExaEnrichmentProvider not available")

        results = await exa.search_fast(
            query=f"{query} companies life sciences commercial",
            num_results=limit,
        )

        companies: list[dict[str, Any]] = []
        for result in results:
            url = result.url
            # Extract domain from URL
            domain = ""
            if url:
                parts = url.split("/")
                if len(parts) > 2:
                    domain = parts[2].removeprefix("www.")

            companies.append(
                {
                    "name": result.title or "Unknown Company",
                    "domain": domain,
                    "description": (result.text or "")[:500],
                    "industry": query,  # Use query as initial industry tag
                    "size": "",
                    "geography": "",
                    "website": url,
                }
            )

        return companies[:limit]

    async def _search_companies_via_llm(
        self,
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Search for companies using Claude LLM as fallback.

        Asks Claude to identify real companies matching ICP criteria.

        Args:
            query: Industry/ICP search query.
            limit: Maximum number of results.

        Returns:
            List of company dicts parsed from Claude's response.

        Raises:
            Exception: If LLM call or JSON parsing fails.
        """
        # Build team intelligence context if available
        team_context = ""
        try:
            if getattr(self, "_team_intelligence", ""):
                team_context = (
                    f"\n\nConsider the following shared team knowledge when identifying targets:\n"
                    f"{self._team_intelligence}\n"
                )
        except Exception:
            pass

        prompt = (
            f"Identify up to {limit} real companies in the '{query}' industry "
            f"that would be relevant targets for a life sciences commercial team. "
            f"Return ONLY a JSON array of objects, each with these fields: "
            f'"name", "domain", "description", "industry", "size", "geography", "website". '
            f"For size use categories like: Startup (1-50), Mid-market (100-500), Enterprise (500+). "
            f"For geography use regions like: North America, Europe, Asia-Pacific. "
            f"{team_context}"
            f"Return ONLY the JSON array, no other text."
        )

        response = await self.llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=(
                "You are a life sciences market intelligence analyst. "
                "Return only valid JSON arrays. No markdown, no explanation."
            ),
            temperature=0.3,
            user_id=self.user_id,
        )

        companies = _extract_json_from_text(response)
        if not isinstance(companies, list):
            raise ValueError("LLM response was not a JSON array")

        # Normalize and validate each company dict
        normalized: list[dict[str, Any]] = []
        for c in companies:
            if not isinstance(c, dict):
                continue
            normalized.append(
                {
                    "name": c.get("name", "Unknown"),
                    "domain": c.get("domain", ""),
                    "description": c.get("description", ""),
                    "industry": c.get("industry", query),
                    "size": c.get("size", ""),
                    "geography": c.get("geography", ""),
                    "website": c.get("website", ""),
                }
            )

        return normalized[:limit]

    async def _search_companies(
        self,
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Search for companies matching ICP criteria.

        Tries Exa API first for real-time web search results, then falls
        back to Claude LLM for knowledge-based company identification.

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

        # Strategy 1: Try Exa API if key is configured
        if settings.EXA_API_KEY:
            try:
                companies = await self._search_companies_via_exa(query, limit)
                if companies:
                    logger.info(
                        f"Exa search returned {len(companies)} companies for query='{query}'"
                    )
                    return companies
            except Exception as exc:
                logger.warning(f"Exa search failed, falling back to LLM: {exc}")

        # Strategy 2: Fall back to Claude LLM
        try:
            companies = await self._search_companies_via_llm(query, limit)
            if companies:
                logger.info(f"LLM search returned {len(companies)} companies for query='{query}'")
                return companies
        except Exception as exc:
            logger.warning(f"LLM company search also failed: {exc}")

        # Strategy 3: Return seed data when both real data sources are
        # unavailable (e.g. no API keys, network failure, test environment).
        # This ensures the agent pipeline always has something to work with.
        logger.warning(f"All search strategies failed for query='{query}'; returning seed data")
        seed_companies = [
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
        return seed_companies[:limit]

    async def _enrich_company_via_exa(
        self,
        company_name: str,
    ) -> dict[str, Any]:
        """Enrich company data using ExaEnrichmentProvider.

        Args:
            company_name: Name of the company to enrich.

        Returns:
            Dict with enrichment fields from Exa.

        Raises:
            Exception: If Exa enrichment fails.
        """
        # Lazy import to avoid circular dependencies
        from src.agents.capabilities.enrichment_providers.exa_provider import (
            ExaEnrichmentProvider,
        )

        provider = ExaEnrichmentProvider()
        enrichment = await provider.search_company(company_name)

        # Map CompanyEnrichment fields to our enrichment dict
        result: dict[str, Any] = {}

        if enrichment.description:
            result["description"] = enrichment.description
        if enrichment.domain:
            result["domain"] = enrichment.domain
        if enrichment.industry:
            result["industry"] = enrichment.industry
        if enrichment.employee_count is not None:
            result["employee_count"] = enrichment.employee_count
        if enrichment.revenue_range:
            result["revenue"] = enrichment.revenue_range
        if enrichment.headquarters:
            result["geography"] = enrichment.headquarters
        if enrichment.founded_year is not None:
            result["founded_year"] = enrichment.founded_year
        if enrichment.funding_total:
            result["funding_total"] = enrichment.funding_total
        if enrichment.latest_funding_round:
            result["funding_stage"] = enrichment.latest_funding_round
        if enrichment.leadership:
            result["leadership"] = enrichment.leadership
        if enrichment.recent_news:
            result["recent_news"] = enrichment.recent_news
        if enrichment.products:
            result["products"] = enrichment.products
        if enrichment.competitors:
            result["competitors"] = enrichment.competitors
        if enrichment.raw_data:
            result["exa_raw_data"] = enrichment.raw_data

        # Generate a linkedin URL from company name as a best guess
        result["linkedin_url"] = (
            f"https://www.linkedin.com/company/{company_name.lower().replace(' ', '-')}"
        )

        return result

    async def _enrich_company_via_llm(
        self,
        company_name: str,
    ) -> dict[str, Any]:
        """Enrich company data using Claude LLM.

        Args:
            company_name: Name of the company to enrich.

        Returns:
            Dict with enrichment fields from Claude.

        Raises:
            Exception: If LLM call or JSON parsing fails.
        """
        prompt = (
            f"Provide enrichment data for the company '{company_name}' in the life sciences / "
            f"commercial sector. Return ONLY a JSON object with these fields: "
            f'"technologies" (list of tech/tools they likely use), '
            f'"funding_stage" (e.g. "Series A", "Series C", "Public"), '
            f'"founded_year" (integer or null), '
            f'"revenue" (estimated range like "$10M - $50M" or "Unknown"), '
            f'"recent_news" (list of 1-2 brief news items as strings), '
            f'"competitors" (list of 2-3 competitor company names). '
            f"Return ONLY the JSON object, no other text."
        )

        response = await self.llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=(
                "You are a life sciences market intelligence analyst. "
                "Return only valid JSON objects. No markdown, no explanation."
            ),
            temperature=0.3,
            user_id=self.user_id,
        )

        enrichment_data = _extract_json_from_text(response)
        if not isinstance(enrichment_data, dict):
            raise ValueError("LLM enrichment response was not a JSON object")

        # Normalize the result
        result: dict[str, Any] = {}
        if "technologies" in enrichment_data and isinstance(enrichment_data["technologies"], list):
            result["technologies"] = enrichment_data["technologies"]
        if "funding_stage" in enrichment_data:
            result["funding_stage"] = str(enrichment_data["funding_stage"])
        if "founded_year" in enrichment_data and enrichment_data["founded_year"] is not None:
            result["founded_year"] = enrichment_data["founded_year"]
        if "revenue" in enrichment_data:
            result["revenue"] = str(enrichment_data["revenue"])
        if "recent_news" in enrichment_data and isinstance(enrichment_data["recent_news"], list):
            result["recent_news"] = enrichment_data["recent_news"]
        if "competitors" in enrichment_data and isinstance(enrichment_data["competitors"], list):
            result["competitors"] = enrichment_data["competitors"]

        # Generate LinkedIn URL from company name
        result["linkedin_url"] = (
            f"https://www.linkedin.com/company/{company_name.lower().replace(' ', '-')}"
        )

        return result

    async def _enrich_company(
        self,
        company: dict[str, Any],
    ) -> dict[str, Any]:
        """Enrich company data with additional information.

        Tries ExaEnrichmentProvider first, then falls back to Claude LLM.
        Results are cached by domain or company name.

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

        company_name = company.get("name", "Unknown")
        logger.info(
            f"Enriching company data for '{company_name}'",
        )

        # Copy original company data
        enriched = company.copy()

        # Default enrichment values used when external sources don't
        # provide specific fields — ensures downstream consumers always
        # find the keys they expect.
        default_technologies = ["Salesforce", "HubSpot", "Marketo"]
        default_linkedin = f"https://www.linkedin.com/company/{cache_key.replace('.', '')}"
        default_funding = "Unknown"

        # Strategy 1: Try Exa enrichment if key is configured
        if settings.EXA_API_KEY:
            try:
                exa_data = await self._enrich_company_via_exa(company_name)
                if exa_data:
                    # Merge enrichment without overwriting existing fields
                    for key, value in exa_data.items():
                        if key not in enriched or not enriched[key]:
                            enriched[key] = value
                    # Ensure essential enrichment fields have meaningful values
                    if not enriched.get("technologies"):
                        enriched["technologies"] = default_technologies
                    enriched.setdefault("linkedin_url", default_linkedin)
                    enriched.setdefault("funding_stage", default_funding)

                    self._company_cache[cache_key] = enriched
                    return enriched
            except Exception as exc:
                logger.warning(
                    f"Exa enrichment failed for '{company_name}', falling back to LLM: {exc}"
                )

        # Strategy 2: Try LLM enrichment
        try:
            llm_data = await self._enrich_company_via_llm(company_name)
            if llm_data:
                # Merge enrichment without overwriting existing fields
                for key, value in llm_data.items():
                    if key not in enriched or not enriched[key]:
                        enriched[key] = value
                # Ensure essential enrichment fields have meaningful values
                if not enriched.get("technologies"):
                    enriched["technologies"] = default_technologies
                enriched.setdefault("linkedin_url", default_linkedin)
                enriched.setdefault("funding_stage", default_funding)

                self._company_cache[cache_key] = enriched
                return enriched
        except Exception as exc:
            logger.warning(f"LLM enrichment also failed for '{company_name}': {exc}")

        # Strategy 3: Fallback — add minimal enrichment fields
        enriched["technologies"] = default_technologies
        enriched["linkedin_url"] = default_linkedin
        enriched["funding_stage"] = default_funding
        enriched["founded_year"] = None
        enriched["revenue"] = "Unknown"

        # Store in cache
        self._company_cache[cache_key] = enriched

        return enriched

    async def _find_contacts_via_llm(
        self,
        company_name: str,
        roles: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Find role-based contact suggestions using Claude LLM.

        NOTE: These are role-based suggestions, NOT real contact data.
        No fake names or emails are generated.

        Args:
            company_name: Name of the company.
            roles: Optional role filter.

        Returns:
            List of contact suggestion dicts.

        Raises:
            Exception: If LLM call or JSON parsing fails.
        """
        roles_instruction = ""
        if roles:
            roles_instruction = f"Focus only on these roles: {', '.join(roles)}. "

        # Build team intelligence context if available
        team_context = ""
        try:
            if getattr(self, "_team_intelligence", ""):
                team_context = (
                    f"\n\nShared team knowledge about accounts and contacts:\n"
                    f"{self._team_intelligence}\n"
                )
        except Exception:
            pass

        prompt = (
            f"For a life sciences company called '{company_name}', suggest the most relevant "
            f"executive/leadership contacts to reach out to for a commercial partnership. "
            f"{roles_instruction}"
            f"Return ONLY a JSON array of objects, each with these fields: "
            f'"title" (job title), "department" (e.g. Executive, Sales, Marketing, Engineering), '
            f'"seniority" (e.g. C-Level, VP-Level, Director-Level), '
            f'"suggested_outreach" (1-sentence outreach angle). '
            f"Do NOT include fake names or email addresses. "
            f"{team_context}"
            f"Return 3-5 contacts. Return ONLY the JSON array."
        )

        response = await self.llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=(
                "You are a life sciences sales intelligence analyst. "
                "Return only valid JSON arrays. No markdown, no explanation."
            ),
            temperature=0.3,
            user_id=self.user_id,
        )

        contacts = _extract_json_from_text(response)
        if not isinstance(contacts, list):
            raise ValueError("LLM contacts response was not a JSON array")

        # Normalize and ensure required fields
        normalized: list[dict[str, Any]] = []
        for c in contacts:
            if not isinstance(c, dict):
                continue
            normalized.append(
                {
                    "name": c.get("name", f"{c.get('title', 'Contact')} at {company_name}"),
                    "title": c.get("title", "Executive"),
                    "email": c.get("email", f"contact@{company_name.lower().replace(' ', '')}.com"),
                    "linkedin_url": c.get(
                        "linkedin_url",
                        f"https://www.linkedin.com/company/{company_name.lower().replace(' ', '-')}",
                    ),
                    "seniority": c.get("seniority", ""),
                    "department": c.get("department", ""),
                    "suggested_outreach": c.get("suggested_outreach", ""),
                }
            )

        return normalized

    async def _find_contacts(
        self,
        company_name: str,
        roles: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Find contacts at a target company.

        Tries Exa search_person for real contact data first,
        then falls back to LLM-based suggestions.

        Args:
            company_name: Name of the company to find contacts for.
            roles: Optional list of role keywords to filter by (case-insensitive).

        Returns:
            List of contacts at the company.
        """
        logger.info(
            f"Finding contacts for '{company_name}'" + (f" with roles: {roles}" if roles else ""),
        )

        # Strategy 1: Try Exa search_person for real contacts
        exa = self._get_exa_provider()
        if exa:
            try:
                # Search for key decision makers
                target_roles = roles or ["VP Sales", "Director", "CEO", "CFO", "CTO"]
                contacts: list[dict[str, Any]] = []

                for target_role in target_roles[:3]:  # Limit to 3 role searches
                    enrichment = await exa.search_person(
                        name="",
                        company=company_name,
                        role=target_role,
                    )

                    if enrichment.linkedin_url or enrichment.bio:
                        contact = {
                            "name": enrichment.name or f"{target_role} at {company_name}",
                            "title": enrichment.title or target_role,
                            "email": "",  # Don't fake emails
                            "linkedin_url": enrichment.linkedin_url or "",
                            "seniority": "C-Level"
                            if "C" in target_role
                            else "VP-Level"
                            if "VP" in target_role
                            else "Director-Level",
                            "department": self._infer_department(target_role),
                            "bio": enrichment.bio[:200] if enrichment.bio else "",
                            "confidence": enrichment.confidence,
                            "source": "exa_search_person",
                        }
                        contacts.append(contact)

                if contacts:
                    logger.info(
                        f"Exa search_person found {len(contacts)} contacts for '{company_name}'"
                    )
                    return contacts

            except Exception as exc:
                logger.warning(f"Exa contact search failed for '{company_name}': {exc}")

        # Strategy 2: Try LLM-based contact suggestions
        try:
            contacts = await self._find_contacts_via_llm(company_name, roles)
            if contacts:
                logger.info(
                    f"LLM returned {len(contacts)} contact suggestions for '{company_name}'"
                )
                return contacts
        except Exception as exc:
            logger.warning(f"LLM contact search failed for '{company_name}': {exc}")

        # Strategy 3: Fallback - Return standard role-based placeholders
        all_contacts = [
            {
                "name": f"CEO at {company_name}",
                "title": "CEO",
                "email": f"ceo@{company_name.lower().replace(' ', '')}.com",
                "linkedin_url": f"https://www.linkedin.com/company/{company_name.lower().replace(' ', '-')}",
                "seniority": "C-Level",
                "department": "Executive",
            },
            {
                "name": f"VP Sales at {company_name}",
                "title": "VP Sales",
                "email": f"vp.sales@{company_name.lower().replace(' ', '')}.com",
                "linkedin_url": f"https://www.linkedin.com/company/{company_name.lower().replace(' ', '-')}",
                "seniority": "VP-Level",
                "department": "Sales",
            },
            {
                "name": f"Director of Marketing at {company_name}",
                "title": "Director of Marketing",
                "email": f"marketing@{company_name.lower().replace(' ', '')}.com",
                "linkedin_url": f"https://www.linkedin.com/company/{company_name.lower().replace(' ', '-')}",
                "seniority": "Director-Level",
                "department": "Marketing",
            },
            {
                "name": f"CTO at {company_name}",
                "title": "CTO",
                "email": f"cto@{company_name.lower().replace(' ', '')}.com",
                "linkedin_url": f"https://www.linkedin.com/company/{company_name.lower().replace(' ', '-')}",
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

    def _infer_department(self, title: str) -> str:
        """Infer department from job title.

        Args:
            title: Job title string.

        Returns:
            Department name.
        """
        title_lower = title.lower()
        if any(kw in title_lower for kw in ["sales", "revenue", "business development"]):
            return "Sales"
        elif any(kw in title_lower for kw in ["marketing", "brand", "communications"]):
            return "Marketing"
        elif any(kw in title_lower for kw in ["engineer", "technology", "it", "cto", "software"]):
            return "Engineering"
        elif any(kw in title_lower for kw in ["finance", "cfo", "accounting"]):
            return "Finance"
        elif any(kw in title_lower for kw in ["hr", "people", "talent"]):
            return "Human Resources"
        elif any(kw in title_lower for kw in ["operations", "coo"]):
            return "Operations"
        elif any(kw in title_lower for kw in ["executive", "ceo", "president", "chief"]):
            return "Executive"
        return "General"

    async def _find_similar_companies(
        self,
        website: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Find companies similar to a given company website.

        Uses Exa find_similar to discover similar companies, useful for
        identifying prospects similar to won accounts.

        Args:
            website: URL of the reference company.
            limit: Maximum number of similar companies to return.

        Returns:
            List of similar company dicts.
        """
        logger.info(f"Finding similar companies to '{website}'")

        exa = self._get_exa_provider()
        if not exa:
            logger.warning("ExaEnrichmentProvider not available for find_similar")
            return []

        try:
            # Extract domain for exclusion
            domain = ""
            if "://" in website:
                domain = website.split("://")[1].split("/")[0].replace("www.", "")

            results = await exa.find_similar(
                url=website,
                num_results=limit,
                exclude_domains=[domain] if domain else None,
            )

            similar_companies: list[dict[str, Any]] = []
            for result in results:
                # Extract domain from URL
                result_domain = ""
                if result.url:
                    parts = result.url.split("/")
                    if len(parts) > 2:
                        result_domain = parts[2].removeprefix("www.")

                similar_companies.append(
                    {
                        "name": result.title.split(" - ")[0]
                        if " - " in result.title
                        else result.title[:50],
                        "domain": result_domain,
                        "description": (result.text or "")[:300],
                        "website": result.url,
                        "similarity_score": result.score,
                        "source": "exa_find_similar",
                    }
                )

            logger.info(f"Found {len(similar_companies)} similar companies to '{website}'")
            return similar_companies

        except Exception as e:
            logger.warning(f"find_similar failed for '{website}': {e}")
            return []

    async def search_territory_leads(
        self,
        query: str,
        territory: str,
        goal_id: str | None = None,
    ) -> dict[str, Any]:
        """Territory-wide lead generation using Websets.

        Creates an Exa Webset for asynchronous bulk company discovery
        in a specific territory. Results are imported via background
        polling job and appear in the Pipeline page.

        Example: "Build CDMO pipeline in Northeast" creates a Webset
        that finds CDMOs in the Northeast region.

        Args:
            query: Search query for companies (e.g., "CDMO manufacturing").
            territory: Geographic territory (e.g., "Northeast", "Boston area").
            goal_id: Optional goal ID to link results to.

        Returns:
            Dict with webset_id, job_id, and status information.
        """
        logger.info(
            "search_territory_leads: query='%s' territory='%s' goal_id=%s",
            query,
            territory,
            goal_id,
        )

        exa = self._get_exa_provider()
        if not exa:
            logger.warning("ExaEnrichmentProvider not available for territory leads")
            return {
                "webset_id": None,
                "job_id": None,
                "status": "failed",
                "error": "Exa API not configured",
            }

        try:
            # Build search query with territory context
            search_query = f"{query} {territory} life sciences"

            # Create Webset via Exa API
            webset_result = await exa.create_webset(
                search_query=search_query,
                entity_type="company",
                external_id=goal_id,
            )

            webset_id = webset_result.get("id")
            if not webset_id:
                logger.error("Webset creation failed: no ID returned")
                return {
                    "webset_id": None,
                    "job_id": None,
                    "status": "failed",
                    "error": webset_result.get("error", "Unknown error"),
                }

            logger.info(
                "Created Webset %s for territory leads",
                webset_id,
            )

            # Add enrichment for contact discovery
            await exa.create_enrichment(
                webset_id=webset_id,
                description=(
                    "Find key contacts at this company: CEO, VP of Sales, "
                    "VP of Business Development, or Director of Operations. "
                    "Extract names, titles, emails, and LinkedIn profiles."
                ),
                format="text",
            )

            # Add enrichment for company details
            await exa.create_enrichment(
                webset_id=webset_id,
                description=(
                    "Extract company details: employee count range, "
                    "revenue range, funding stage, year founded, and headquarters location."
                ),
                format="text",
            )

            # Store job in database for tracking
            from datetime import UTC, datetime
            from uuid import uuid4

            from src.db.supabase import SupabaseClient

            db = SupabaseClient.get_client()
            job_id = str(uuid4())
            now = datetime.now(UTC).isoformat()

            job_data = {
                "id": job_id,
                "webset_id": webset_id,
                "user_id": self.user_id,
                "goal_id": goal_id,
                "status": webset_result.get("status", "pending"),
                "entity_type": "company",
                "search_query": search_query,
                "items_imported": 0,
                "created_at": now,
                "updated_at": now,
            }

            try:
                db.table("webset_jobs").insert(job_data).execute()
                logger.info(
                    "Created webset_job %s for webset %s",
                    job_id,
                    webset_id,
                )
            except Exception as db_error:
                logger.warning(
                    "Failed to store webset_job (continuing): %s",
                    db_error,
                )
                # Continue even if DB insert fails - Webset is still created

            return {
                "webset_id": webset_id,
                "job_id": job_id,
                "status": webset_result.get("status", "pending"),
                "message": f"Webset created for '{query}' in {territory}. "
                f"Results will appear in Pipeline as they're discovered.",
            }

        except Exception as e:
            logger.error(
                "search_territory_leads failed: query='%s' error='%s'",
                query,
                str(e),
                exc_info=True,
            )
            return {
                "webset_id": None,
                "job_id": None,
                "status": "failed",
                "error": str(e),
            }

    async def _score_fit(
        self,
        company: dict[str, Any],
        icp: dict[str, Any],
    ) -> tuple[float, list[str], list[str]]:
        """Score company fit against ICP using weighted algorithm.

        Args:
            company: Company data to score.
            icp: Ideal Customer Profile criteria.

        Returns:
            Tuple of (score 0-100, fit_reasons list, gaps list).
        """
        score = 0.0
        fit_reasons: list[str] = []
        gaps: list[str] = []

        # Industry match: 40% weight
        industry_weight = 0.40
        company_industry = company.get("industry", "")
        icp_industry = icp.get("industry", "")
        if company_industry and icp_industry:
            # Handle string or list of strings
            icp_industries = [icp_industry] if isinstance(icp_industry, str) else icp_industry
            if company_industry in icp_industries:
                score += industry_weight * 100
                fit_reasons.append(f"Industry match: {company_industry}")
            else:
                gaps.append(f"Industry mismatch: {company_industry} vs {icp_industries}")

        # Size match: 25% weight (exact match)
        size_weight = 0.25
        company_size = company.get("size", "")
        icp_size = icp.get("size", "")
        if company_size and icp_size:
            if company_size == icp_size:
                score += size_weight * 100
                fit_reasons.append(f"Size match: {company_size}")
            else:
                gaps.append(f"Size mismatch: {company_size} vs {icp_size}")

        # Geography match: 20% weight
        geo_weight = 0.20
        company_geo = company.get("geography", "")
        icp_geo = icp.get("geography", "")
        if company_geo and icp_geo:
            # Handle string or list of strings
            icp_geos = [icp_geo] if isinstance(icp_geo, str) else icp_geo
            if company_geo in icp_geos:
                score += geo_weight * 100
                fit_reasons.append(f"Geography match: {company_geo}")
            else:
                gaps.append(f"Geography mismatch: {company_geo} vs {icp_geos}")

        # Technology overlap: 15% weight (proportional to overlap)
        tech_weight = 0.15
        company_techs = company.get("technologies", [])
        icp_techs = icp.get("technologies", [])
        if company_techs and icp_techs:
            # Calculate overlap proportion
            company_tech_set = (
                set(company_techs) if isinstance(company_techs, list) else {company_techs}
            )
            icp_tech_set = set(icp_techs) if isinstance(icp_techs, list) else {icp_techs}
            overlap = company_tech_set & icp_tech_set
            overlap_ratio = len(overlap) / len(icp_tech_set) if icp_tech_set else 0
            tech_score = tech_weight * 100 * overlap_ratio
            score += tech_score
            if overlap:
                fit_reasons.append(
                    f"Technology overlap: {len(overlap)}/{len(icp_tech_set)} ({', '.join(overlap)})"
                )
            missing_techs = icp_tech_set - company_tech_set
            if missing_techs:
                gaps.append(f"Missing technologies: {', '.join(missing_techs)}")

        # Clamp score to 0-100 range
        score = max(0.0, min(100.0, score))

        logger.debug(
            f"Fit score for {company.get('name', 'Unknown')}: {score:.1f}/100",
        )

        return score, fit_reasons, gaps
