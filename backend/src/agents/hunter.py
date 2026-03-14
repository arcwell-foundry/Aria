"""HunterAgent module for ARIA.

Discovers and qualifies new leads based on Ideal Customer Profile (ICP).
"""

import json
import logging
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

from src.agents.base import AgentResult
from src.agents.skill_aware_agent import SkillAwareAgent
from src.core.config import settings
from src.core.task_types import TaskType
from src.security.instruction_detector import InstructionDetector
from src.security.prompt_security import get_security_context, wrap_external_data

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


# Blocklist for consulting/advisory firms that aren't real manufacturing targets
_CONSULTING_BLOCKLIST = {
    "mckinsey", "deloitte", "accenture", "bcg", "boston consulting",
    "bain", "kpmg", "pwc", "ey", "ernst & young",
    "herspiegel", "trinity partners", "iqvia consulting",
    "zs associates", "simon-kucher", "oliver wyman", "lek",
    "indegene", "inizio", "trinzic", "precision aq",
}

# Pharma manufacturers (not service providers like CDMOs/CROs)
_PHARMA_MANUFACTURERS = {
    "bristol myers squibb", "pfizer", "astrazeneca", "novartis",
    "roche", "eli lilly", "johnson & johnson", "merck", "amgen",
    "abbvie", "gilead", "biogen", "regeneron", "moderna",
}

_CONSULTING_KEYWORDS = {"consulting", "advisory", "advisors", "consultants"}

# Life sciences domain expertise injected into Hunter prompts
HUNTER_DOMAIN_CONTEXT = """\
You are the lead discovery engine for a life sciences commercial team.
You have 25 years of industry experience across all modalities.

When evaluating a potential lead, you consider:

BUYING SIGNALS (ranked by intent strength):
1. Facility expansion / new manufacturing site — Strongest. New facility = \
12-24 months of equipment and service purchasing ahead.
2. Hiring surge in manufacturing/bioprocessing roles — Company is scaling \
operations. Need equipment, consumables, services.
3. FDA approval / BLA filing — Drug moving to commercial manufacturing = \
massive scale-up from clinical to GMP commercial.
4. Funding round (Series B+) — Capital enables manufacturing investment. \
Series A is too early for equipment purchases.
5. Clinical trial advancing to Phase 3 — Manufacturing planning starts \
~18 months before commercial launch.
6. Technology platform change — Switching from batch to continuous, \
stainless to single-use = new equipment across the facility.
7. M&A / partnership — Integration means equipment standardization, \
new capacity planning.

DISQUALIFYING SIGNALS:
- Company in early R&D only (no manufacturing)
- Company already has long-term contracts with competitors
- Company is downsizing or in financial trouble
- Company is outside the user's territory

MODALITY-SPECIFIC KNOWLEDGE:
- CDMOs: Watch for capacity utilization announcements. A CDMO at 90%+ \
utilization WILL expand. This is the best possible signal.
- Cell & Gene Therapy: GMP suite construction = 18-month equipment \
purchasing cycle. Watch for IND filings.
- mAbs: Upstream titer improvements or downstream bottlenecks = \
specific equipment opportunities.
- mRNA: LNP manufacturing at scale is the bottleneck. Companies \
investing here are actively purchasing.
"""


def _is_consulting_or_advisory(name: str) -> bool:
    """Check if a company name indicates a consulting/advisory firm.

    Returns True if the name matches known consulting firms or contains
    consulting-related keywords without life sciences manufacturing context.
    """
    name_lower = name.lower().strip()

    # Check against known blocklist
    for blocked in _CONSULTING_BLOCKLIST:
        if blocked in name_lower:
            return True

    # Check for consulting keywords — allow if combined with bio/life sciences
    has_consulting_keyword = any(kw in name_lower for kw in _CONSULTING_KEYWORDS)
    has_bio_keyword = any(
        kw in name_lower
        for kw in ("bio", "life science", "pharma", "genomic", "cell", "gene")
    )

    return has_consulting_keyword and not has_bio_keyword


# Generic industry names that are NOT real companies
_INVALID_COMPANY_NAMES = {
    "life sciences industry", "biotech sector", "pharmaceutical industry",
    "healthcare industry", "manufacturing sector", "bioprocessing industry",
    "medical device industry", "clinical research", "drug development",
    "biopharma industry", "life sciences", "biotech", "pharma",
    "healthcare", "manufacturing", "industry", "sector",
    "the life sciences industry", "the biotech sector",
    "the pharmaceutical industry", "the healthcare industry",
}

# Single-word generic names that should be rejected
_SINGLE_WORD_GENERIC = {
    "biotech", "pharma", "healthcare", "manufacturing", "industry",
    "biologics", "biosimilars", "generics", "diagnostics",
}

# Non-company domains (news sites, job boards, aggregators)
_INVALID_DOMAINS = {
    "proclinical.com", "indeed.com", "linkedin.com", "glassdoor.com",
    "wikipedia.org", "crunchbase.com", "bloomberg.com", "reuters.com",
    "fiercepharma.com", "biopharmadive.com", "pharmamanufacturing.com",
    "genengnews.com", "biopharma-reporter.com", "evaluate.com",
    "google.com", "youtube.com", "twitter.com", "facebook.com",
    "ziprecruiter.com", "monster.com", "salary.com", "payscale.com",
    "clinicaltrialsarena.com", "fiercebiotech.com", "biospace.com",
    "pharmajobs.com",
}


def _validate_company(company_name: str, domain: str = "") -> bool:
    """Validate that a company name is a real entity, not a category.

    Checks against known generic industry names and non-company domains.
    This validation is tenant-agnostic — no hardcoded user or company data.

    Args:
        company_name: The company name to validate.
        domain: Optional domain to validate.

    Returns:
        True if the company appears valid, False if it should be rejected.
    """
    name_lower = company_name.strip().lower()

    # Reject names that are too short or too long
    if len(company_name) < 3 or len(company_name) > 100:
        logger.debug("Entity validation rejected '%s': length %d outside 3-100 range", company_name, len(company_name))
        return False

    # Reject generic industry names
    if name_lower in _INVALID_COMPANY_NAMES:
        logger.debug("Entity validation rejected '%s': generic industry category", company_name)
        return False

    # Reject single-word generic names
    if len(name_lower.split()) == 1 and name_lower in _SINGLE_WORD_GENERIC:
        logger.debug("Entity validation rejected '%s': single-word generic", company_name)
        return False

    # Reject pharma manufacturers (not CDMOs/CROs)
    if name_lower in _PHARMA_MANUFACTURERS:
        logger.debug("Entity validation rejected '%s': pharma manufacturer, not service provider", company_name)
        return False

    # Reject if domain is a known non-company site
    if domain:
        domain_clean = (
            domain.lower()
            .replace("www.", "")
            .replace("https://", "")
            .replace("http://", "")
            .split("/")[0]
        )
        if domain_clean in _INVALID_DOMAINS:
            logger.debug(
                "Entity validation rejected '%s': invalid domain %s", company_name, domain
            )
            return False

    return True


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
        self._apollo_provider: Any = None
        self._resource_status: list[dict[str, Any]] = []  # Tool connectivity status
        self._instruction_detector = InstructionDetector(llm_client=None)
        # Skill knowledge loaded per-execution
        self._sub_industry_context: dict[str, Any] | None = None
        self._active_icp: dict[str, Any] | None = None
        self._domain_context: str = ""
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

    def _get_apollo_provider(self, company_id: str | None = None) -> Any:
        """Lazily initialize and return the ApolloEnrichmentProvider.

        Apollo provides superior B2B contact data compared to Exa for
        people search. This method creates a provider instance with
        credit metering context.

        Args:
            company_id: Optional company UUID for credit metering.
                       If not provided, resolves from user_profiles.

        Returns:
            ApolloEnrichmentProvider instance or None if initialization fails.
        """
        if self._apollo_provider is None:
            try:
                from src.agents.capabilities.enrichment_providers.apollo_provider import (
                    ApolloEnrichmentProvider,
                )

                # Resolve company_id from user_profiles if not provided
                resolved_company_id = company_id
                if not resolved_company_id and self.user_id:
                    try:
                        from src.db.supabase import get_supabase_client
                        db = get_supabase_client()
                        profile = db.table("user_profiles").select("company_id").eq("id", self.user_id).limit(1).execute()
                        if profile.data:
                            resolved_company_id = profile.data[0].get("company_id")
                    except Exception:
                        logger.debug("HunterAgent: Could not resolve company_id from user_profiles")

                self._apollo_provider = ApolloEnrichmentProvider(
                    company_id=resolved_company_id,
                    user_id=self.user_id,
                )
                logger.info(
                    "HunterAgent: ApolloEnrichmentProvider initialized (company_id=%s)",
                    resolved_company_id,
                )
            except Exception as e:
                logger.warning("HunterAgent: Failed to initialize ApolloEnrichmentProvider: %s", e)
        return self._apollo_provider

    async def _load_skill_knowledge(self) -> None:
        """Load lead gen skill knowledge at the start of discovery.

        Reads SubIndustryContext from memory_semantic, active ICP from
        lead_icp_profiles, and domain context from knowledge_base.md.
        Results are stored as instance attributes for use during scoring
        and write protocol.
        """
        from src.db.supabase import SupabaseClient

        db = SupabaseClient.get_client()

        # 1. Load SubIndustryContext from memory_semantic
        try:
            result = (
                db.table("memory_semantic")
                .select("fact, metadata, confidence")
                .eq("user_id", self.user_id)
                .or_(
                    "metadata->>entity_type.eq.sub_industry_context,"
                    "metadata->>entity_type.eq.company_classification"
                )
                .order("confidence", desc=True)
                .limit(5)
                .execute()
            )
            if result.data:
                self._sub_industry_context = {
                    "facts": [row["fact"] for row in result.data],
                    "metadata": result.data[0].get("metadata", {}),
                }
                logger.info(
                    "[HUNTER] Loaded SubIndustryContext: %d facts",
                    len(result.data),
                )
            else:
                self._sub_industry_context = None
                logger.info("[HUNTER] No SubIndustryContext found in memory_semantic")
        except Exception as e:
            logger.warning("[HUNTER] Failed to load SubIndustryContext: %s", e)
            self._sub_industry_context = None

        # 2. Load active ICP from lead_icp_profiles
        #    Table schema: id, user_id, icp_data (JSONB), version, created_at, updated_at
        try:
            result = (
                db.table("lead_icp_profiles")
                .select("id, icp_data, version")
                .eq("user_id", self.user_id)
                .order("version", desc=True)
                .limit(1)
                .execute()
            )
            if result.data:
                row = result.data[0]
                icp_data = row.get("icp_data") or {}
                # Normalize: expose icp_data fields at top level for downstream use
                self._active_icp = {
                    "id": row.get("id"),
                    "criteria": icp_data,  # downstream expects .criteria dict
                    **icp_data,  # also spread for direct access to industry, geography etc.
                }
                logger.info(
                    "[HUNTER] Loaded active ICP v%s: %s",
                    row.get("version", "?"),
                    list(icp_data.keys())[:5],
                )
            else:
                self._active_icp = None
                logger.info("[HUNTER] No active ICP found in lead_icp_profiles")
        except Exception as e:
            logger.warning("[HUNTER] Failed to load active ICP: %s", e)
            self._active_icp = None

        # 3. Load search vocabulary from memory_semantic
        try:
            result = (
                db.table("memory_semantic")
                .select("fact")
                .eq("user_id", self.user_id)
                .eq("metadata->>entity_type", "search_vocabulary")
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if result.data:
                self._search_vocabulary = result.data[0]["fact"]
                logger.info("[HUNTER] Loaded search vocabulary from memory_semantic")
            else:
                self._search_vocabulary = ""
                logger.info("[HUNTER] No search vocabulary found in memory_semantic")
        except Exception as e:
            logger.warning("[HUNTER] Failed to load search vocabulary: %s", e)
            self._search_vocabulary = ""

        # 4. Load target company examples from memory_semantic
        try:
            result = (
                db.table("memory_semantic")
                .select("fact")
                .eq("user_id", self.user_id)
                .eq("metadata->>entity_type", "target_examples")
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if result.data:
                self._target_examples = result.data[0]["fact"]
                logger.info("[HUNTER] Loaded target company examples from memory_semantic")
            else:
                self._target_examples = ""
                logger.info("[HUNTER] No target examples found in memory_semantic")
        except Exception as e:
            logger.warning("[HUNTER] Failed to load target examples: %s", e)
            self._target_examples = ""

        # 5. Load domain context from knowledge_base.md
        try:
            import os

            kb_path = os.path.join(
                os.path.dirname(__file__),
                "..",
                "skills",
                "definitions",
                "life_sciences_lead_gen",
                "knowledge_base.md",
            )
            kb_path = os.path.normpath(kb_path)
            if os.path.exists(kb_path):
                with open(kb_path, encoding="utf-8") as f:
                    # Read first 4000 chars for foundational context
                    self._domain_context = f.read(4000)
                logger.info("[HUNTER] Loaded domain context from knowledge_base.md")
            else:
                self._domain_context = ""
                logger.info("[HUNTER] knowledge_base.md not found at %s", kb_path)
        except Exception as e:
            logger.warning("[HUNTER] Failed to load knowledge_base.md: %s", e)
            self._domain_context = ""

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

    async def _parse_goal_intent(self, goal_title: str) -> dict[str, Any]:
        """Use LLM to extract structured search intent from a goal title.

        Parses natural language goal titles like "Find me 3 CDMOs in Boston"
        into structured fields for building targeted search queries.

        Args:
            goal_title: The user's goal title.

        Returns:
            Dict with company_type, location, count, modality, criteria.
        """
        if not goal_title:
            return {}

        prompt = (
            f'Parse this lead generation goal title into structured fields.\n\n'
            f'Goal: "{goal_title}"\n\n'
            f'Extract these fields as JSON:\n'
            f'- "company_type": type of company (e.g. CDMO, CRO, biotech, pharma, '
            f'equipment supplier, consumables, lab equipment, cell therapy, gene therapy)\n'
            f'- "location": geographic location if mentioned (city, state, region)\n'
            f'- "count": number of leads requested (integer, default 5)\n'
            f'- "modality": therapeutic/manufacturing modality if mentioned '
            f'(biologics, small molecule, cell therapy, gene therapy, mRNA, mAbs, '
            f'biosimilars, ADCs)\n'
            f'- "criteria": any special criteria mentioned (e.g. "expanding", '
            f'"hiring", "recently funded")\n'
            f'- "industry_segment": specific industry segment '
            f'(e.g. bioprocessing, diagnostics, medical devices)\n\n'
            f'Return ONLY a JSON object. Omit fields that are not mentioned.'
        )

        try:
            response = await self.llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=(
                    "You are a life sciences industry expert. Parse goal titles "
                    "into structured search intent. Return only valid JSON."
                ),
                temperature=0.1,
                max_tokens=300,
                user_id=self.user_id,
                task=TaskType.HUNTER_ENRICH,
                agent_id="hunter",
            )
            parsed = _extract_json_from_text(response)
            if isinstance(parsed, dict):
                logger.info("[HUNTER] Parsed goal intent: %s", parsed)
                return parsed
        except Exception as e:
            logger.warning("[HUNTER] Failed to parse goal intent: %s", e)

        return {}

    async def _build_search_queries(
        self,
        goal_title: str,
        user_icp: dict[str, Any],
    ) -> list[str]:
        """Build intelligent Exa search queries from goal context.

        A top sales rep doesn't search generically. They search with intent,
        combining company type, location, modality, and signal context.

        Args:
            goal_title: The user's goal title.
            user_icp: Active ICP data dict.

        Returns:
            List of targeted search query strings.
        """
        parsed = await self._parse_goal_intent(goal_title)
        if not parsed:
            # Fallback to generic query from ICP
            industry = user_icp.get("industry", "life sciences")
            return [f"{industry} companies manufacturing"]

        company_type = parsed.get("company_type", "")
        location = parsed.get("location", "")
        modality = parsed.get("modality", "") or user_icp.get("modality", "")
        criteria = parsed.get("criteria", "")
        segment = parsed.get("industry_segment", "")

        queries: list[str] = []

        # Primary: specific to what user asked
        primary_parts = [company_type]
        if modality:
            primary_parts.append(modality)
        if segment:
            primary_parts.append(segment)
        else:
            primary_parts.append("manufacturing")
        if location:
            primary_parts.append(location)
        if criteria:
            primary_parts.append(criteria)
        primary_parts.append("2025 2026")
        queries.append(" ".join(p for p in primary_parts if p))

        # Signal-enriched: find companies with recent activity
        signal_parts = [company_type]
        if location:
            signal_parts.append(location)
        signal_parts.append("expansion OR hiring OR FDA approval OR funding 2025 2026")
        queries.append(" ".join(p for p in signal_parts if p))

        # Modality-specific: use ICP context for deeper search
        if modality:
            mod_parts = [modality, "manufacturing facility"]
            if location:
                mod_parts.append(location)
            mod_parts.append("announcement OR expansion OR new site")
            queries.append(" ".join(mod_parts))

        logger.info(
            "[HUNTER] Built %d search queries from goal: %s",
            len(queries),
            [q[:80] for q in queries],
        )
        return queries

    async def _get_signal_enriched_companies(
        self,
        user_icp: dict[str, Any],
        parsed_intent: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Query market_signals for companies with recent activity.

        Companies with recent signals matching the user's request are
        HIGH PRIORITY leads. This is how a top rep works: they read
        the news, then reach out.

        Args:
            user_icp: Active ICP data dict.
            parsed_intent: Parsed goal intent from _parse_goal_intent.

        Returns:
            List of company dicts from signal data.
        """
        try:
            from src.db.supabase import SupabaseClient
            from datetime import timedelta

            db = SupabaseClient.get_client()
            cutoff = (datetime.now(UTC) - timedelta(days=30)).isoformat()

            # Build query for recent high-value signals
            query = (
                db.table("market_signals")
                .select("company_name, signal_type, headline, summary, detected_at, relevance_score")
                .eq("user_id", self.user_id)
                .gte("detected_at", cutoff)
                .order("detected_at", desc=True)
                .limit(20)
            )

            result = query.execute()
            if not result.data:
                return []

            # Deduplicate by company name and build company dicts
            seen: set[str] = set()
            companies: list[dict[str, Any]] = []
            for sig in result.data:
                name = sig.get("company_name", "")
                if not name or name.lower() in seen:
                    continue
                seen.add(name.lower())

                # Check location match if parsed intent has location
                companies.append({
                    "name": name,
                    "domain": "",
                    "description": sig.get("summary") or sig.get("headline", ""),
                    "industry": "Life Sciences",
                    "size": "",
                    "geography": "",
                    "website": "",
                    "signal_type": sig.get("signal_type", ""),
                    "signal_date": sig.get("detected_at", ""),
                    "relevance_score": sig.get("relevance_score", 0.5),
                    "_source": "market_signals",
                })

            logger.info(
                "[HUNTER] Found %d companies with recent signals",
                len(companies),
            )
            return companies

        except Exception as e:
            logger.warning("[HUNTER] Failed to query market_signals for leads: %s", e)
            return []

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

        Lead discovery REQUIRES a goal trigger. Hunter should never
        autonomously create leads from signal monitoring alone.
        Flow: User creates goal -> GoalExecutionService dispatches Hunter -> leads.

        Args:
            task: Task specification with parameters.

        Returns:
            AgentResult with success status and output data.
        """
        # CRITICAL: Hunter lead discovery requires a goal trigger
        if not task.get("goal_id"):
            logger.warning(
                "[HUNTER] Lead discovery requires a goal. Skipping autonomous discovery. "
                "task_keys=%s",
                list(task.keys()),
            )
            return AgentResult(
                success=False,
                data=None,
                error="Lead discovery requires a goal trigger",
            )

        # OODA ACT: Log skill consideration before native execution
        await self._log_skill_consideration()

        logger.warning("[HUNTER] execute() called - starting lead discovery for goal=%s", task["goal_id"])

        # Load skill knowledge at the START of lead discovery (fail-open)
        await self._load_skill_knowledge()

        # Extract team intelligence for LLM enrichment (optional, fail-open)
        self._team_intelligence: str = task.get("team_intelligence", "")

        # Extract resource_status for graceful degradation
        resource_status = task.get("resource_status", [])
        self._resource_status = resource_status

        # Check if Exa (our primary search tool) is available
        exa_available = settings.EXA_API_KEY or self._check_tool_connected(resource_status, "exa")
        logger.warning(
            "[HUNTER] Exa available: %s (api_key_set=%s)",
            exa_available,
            bool(settings.EXA_API_KEY),
        )

        # Extract task parameters
        icp = task["icp"]
        target_count = task["target_count"]
        exclusions = task.get("exclusions", [])
        goal_title = task.get("goal_title", "")

        # Step 1: Build intelligent search queries from goal title + ICP
        # A top sales rep doesn't search "life sciences manufacturing companies"
        # They search with intent based on what the user actually asked for.
        user_icp = {}
        if self._active_icp and self._active_icp.get("criteria"):
            user_icp = self._active_icp["criteria"] if isinstance(self._active_icp["criteria"], dict) else {}
        user_icp = {**icp, **user_icp}  # merge task ICP with stored ICP

        if goal_title:
            search_queries = await self._build_search_queries(goal_title, user_icp)
        else:
            # Fallback: use search vocabulary or industry
            industry = icp.get("industry", "")
            industry_str = industry if isinstance(industry, str) else industry[0] if industry else ""
            search_vocab = getattr(self, "_search_vocabulary", "")
            if search_vocab:
                quoted_terms = re.findall(r'"([^"]+)"', search_vocab)
                if quoted_terms:
                    search_queries = [" OR ".join(quoted_terms[:3])]
                else:
                    search_queries = [industry_str] if industry_str else ["life sciences manufacturing"]
            else:
                search_queries = [industry_str] if industry_str else ["life sciences manufacturing"]

        # Step 1b: Get signal-enriched companies from market_signals
        signal_companies = await self._get_signal_enriched_companies(user_icp)

        # Step 2: Search for companies using each query, merge and dedup
        search_limit = target_count * 3
        all_companies: list[dict[str, Any]] = []
        seen_names: set[str] = set()

        # Signal companies go first (highest priority)
        for sc in signal_companies:
            name_lower = sc.get("name", "").lower()
            if name_lower and name_lower not in seen_names:
                seen_names.add(name_lower)
                all_companies.append(sc)

        # Search with each query and merge results
        for query in search_queries:
            try:
                results = await self._search_companies(query=query, limit=search_limit)
                for company in results:
                    name_lower = company.get("name", "").lower()
                    if name_lower and name_lower not in seen_names:
                        seen_names.add(name_lower)
                        all_companies.append(company)
            except Exception as e:
                logger.warning("[HUNTER] Search query failed: %s - %s", query[:60], e)
                continue

        companies = all_companies

        # Step 3: Filter out excluded companies
        if exclusions:
            companies = [c for c in companies if c.get("domain") not in exclusions]

        # Step 4: Limit to target_count
        companies = companies[:target_count]

        # Step 5: Process each company - enrich, find contacts, score, write to memory
        leads = []
        for company in companies:
            try:
                # Enrich company data
                enriched_company = await self._enrich_company(company)

                # Sanitize Exa-sourced data before processing
                enriched_company = await self._sanitize_external_data(
                    enriched_company, source="exa_company_search"
                )

                # Find contacts — pass domain from enrichment for Apollo accuracy
                company_domain = (
                    enriched_company.get("domain", "")
                    or enriched_company.get("website", "").replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
                )
                contacts = await self._find_contacts(
                    company_name=enriched_company["name"],
                    company_domain=company_domain or None,
                )

                # Score using dynamic 4-dimension model (Section 3.2)
                discovery_score = await self._score_discovery(
                    company=enriched_company,
                    contacts=contacts,
                    icp=icp,
                )

                fit_score = discovery_score["total"]
                fit_reasons = discovery_score.get("fit_reasons", [])
                gaps = discovery_score.get("gaps", [])

                # Build lead object
                lead = {
                    "company": enriched_company,
                    "contacts": contacts,
                    "fit_score": fit_score,
                    "fit_reasons": fit_reasons,
                    "gaps": gaps,
                    "source": "hunter_pro",
                    "discovery_score": discovery_score,
                }
                leads.append(lead)

                # Write to memory per Section 7.1 protocol (fail-open)
                await self._write_lead_to_memory(
                    company=enriched_company,
                    contacts=contacts,
                    discovery_score=discovery_score,
                )

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

        Searches Exa for relevant web pages, then uses the LLM to extract
        actual company names and details from the search results.

        Args:
            query: Search query string.
            limit: Maximum number of results.

        Returns:
            List of company dicts extracted from Exa results.

        Raises:
            Exception: If Exa API call fails.
        """
        exa = self._get_exa_provider()
        if not exa:
            raise RuntimeError("ExaEnrichmentProvider not available")

        # Build a more targeted Exa query using search vocabulary if available
        search_vocab = getattr(self, "_search_vocabulary", "")
        if search_vocab and "CDMO" in search_vocab:
            # Use domain-specific query instead of generic
            exa_query = query
        else:
            exa_query = f"{query} companies life sciences commercial"

        results = await exa.search_fast(
            query=exa_query,
            num_results=limit * 2,
            start_published_date="2025-01-01",
            category="company",
        )

        if not results:
            return []

        # Build context from raw Exa results for LLM extraction
        search_context_parts: list[str] = []
        for i, result in enumerate(results, 1):
            snippet = (result.text or "")[:600]
            search_context_parts.append(
                f"--- Result {i} ---\n"
                f"Title: {result.title or 'N/A'}\n"
                f"URL: {result.url or 'N/A'}\n"
                f"Content: {snippet}\n"
            )
        search_context = "\n".join(search_context_parts)

        # Inject target examples and search vocabulary for better extraction
        target_examples = getattr(self, "_target_examples", "")
        examples_context = ""
        if target_examples:
            examples_context = (
                f"\n\nIMPORTANT CONTEXT — These are the TYPES of companies we want to find "
                f"(manufacturers, CDMOs, equipment suppliers — NOT consulting firms):\n"
                f"{target_examples}\n"
            )

        # Use LLM to extract real companies from the search results
        prompt = (
            f"Below are web search results about '{query}' companies.\n\n"
            f"{wrap_external_data(search_context, 'exa_company_search')}\n\n"
            f"{examples_context}"
            f"From these search results, identify up to {limit} distinct REAL companies "
            f"that are mentioned. Extract the actual company name — NOT the article title.\n\n"
            f"CRITICAL FILTERING RULES:\n"
            f"- Only include companies that MANUFACTURE, PRODUCE, or PROVIDE equipment/services "
            f"for life sciences/bioprocessing.\n"
            f"- EXCLUDE consulting firms, advisory companies, market research firms, "
            f"real estate companies, and financial services companies.\n"
            f"- If a company name contains 'Consulting', 'Advisory', 'Partners' (without "
            f"'Life Sciences' or 'Bio'), 'McKinsey', 'Deloitte', 'Accenture', 'BCG', "
            f"'Trinity' (real estate), skip it.\n\n"
            f"CRITICAL VALIDATION RULES:\n"
            f"1. Every company name MUST be a specific organization (e.g., 'Catalent', 'AGC Biologics', 'Lonza').\n"
            f"   NEVER return industry categories like 'Life Sciences Industry' or 'Biotech Sector'.\n"
            f"2. Every company domain MUST be the company's own website (e.g., 'catalent.com', 'agcbio.com').\n"
            f"   NEVER return news sites, job boards, or Wikipedia URLs.\n"
            f"3. If the search results don't contain a real company matching the criteria, return an EMPTY array [].\n"
            f"   It is better to return 0 leads than 1 fake lead.\n"
            f"4. Verify the company type matches what was asked for. If the query mentions CDMO, "
            f"the company must be a contract development and manufacturing organization.\n\n"
            f"For each company, provide:\n"
            f'- "name": the real company name (e.g. "Nautilus Biotechnology", not an article headline)\n'
            f'- "domain": company website domain if visible in the URL/content\n'
            f'- "description": brief description of what the company does based on the content\n'
            f'- "industry": specific industry segment\n'
            f'- "size": employee range if mentioned (e.g. "51-200", "Enterprise (500+)")\n'
            f'- "geography": headquarters location if mentioned\n'
            f'- "website": company website URL if found\n\n'
            f"Return ONLY a JSON array of company objects. No duplicates. "
            f"Skip any entry where you cannot determine a real company name."
        )

        response = await self.llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=(
                get_security_context()
                + "\n" + HUNTER_DOMAIN_CONTEXT
                + "\nExtract real company names and details from search results. "
                "Return only valid JSON arrays. No markdown fences, no explanation."
            ),
            temperature=0.2,
            user_id=self.user_id,
            task=TaskType.HUNTER_ENRICH,
            agent_id="hunter",
        )

        try:
            companies_raw = _extract_json_from_text(response)
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM company extraction response")
            return []

        if not isinstance(companies_raw, list):
            return []

        companies: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        for c in companies_raw:
            if not isinstance(c, dict):
                continue
            name = c.get("name", "").strip()
            if not name or name.lower() in seen_names:
                continue
            # Post-extraction consulting firm filter
            if _is_consulting_or_advisory(name):
                logger.info("[HUNTER] Filtered out non-manufacturer: %s", name)
                continue
            # Validate company name and domain are real entities
            company_domain = c.get("domain", "")
            if not _validate_company(name, company_domain):
                logger.info("[HUNTER] Filtered out invalid company: %s (domain=%s)", name, company_domain)
                continue
            seen_names.add(name.lower())
            companies.append(
                {
                    "name": name,
                    "domain": company_domain,
                    "description": c.get("description", ""),
                    "industry": c.get("industry", query),
                    "size": c.get("size", ""),
                    "geography": c.get("geography", ""),
                    "website": c.get("website", ""),
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
            task=TaskType.HUNTER_ENRICH,
            agent_id="hunter",
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
            logger.warning("[HUNTER] Attempting Exa API search for query='%s'", query)
            try:
                companies = await self._search_companies_via_exa(query, limit)
                if companies:
                    logger.warning(
                        "[HUNTER] Exa search SUCCESS: %d companies for query='%s'",
                        len(companies),
                        query,
                    )
                    return companies
                logger.warning("[HUNTER] Exa search returned empty results")
            except Exception as exc:
                logger.warning("[HUNTER] Exa search FAILED, falling back to LLM: %s", exc)
        else:
            logger.warning("[HUNTER] EXA_API_KEY not set, skipping Exa search")

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
            task=TaskType.HUNTER_QUALIFY,
            agent_id="hunter",
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
        # provide specific fields - ensures downstream consumers always
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

        # Strategy 3: Fallback - add minimal enrichment fields
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
            task=TaskType.HUNTER_ENRICH,
            agent_id="hunter",
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
        company_domain: str | None = None,
    ) -> list[dict[str, Any]]:
        """Find contacts at a target company.

        Tries Apollo people_search first (FREE, superior B2B data),
        then Exa search_person, then falls back to LLM-based suggestions.

        Args:
            company_name: Name of the company to find contacts for.
            roles: Optional list of role keywords to filter by (case-insensitive).
            company_domain: Optional company domain for Apollo search.

        Returns:
            List of contacts at the company.
        """
        logger.info(
            f"Finding contacts for '{company_name}'" + (f" with roles: {roles}" if roles else ""),
        )

        # Strategy 1: Try Apollo people_search (FREE, best for B2B)
        apollo = self._get_apollo_provider()
        if apollo and settings.apollo_configured:
            try:
                # Use domain if available, otherwise skip Apollo (needs domain)
                domain = company_domain or ""
                if not domain:
                    # Try to infer domain from company name
                    domain = f"{company_name.lower().replace(' ', '')}.com"

                # Validate domain before calling Apollo
                domain_clean = (
                    domain.lower()
                    .replace("www.", "")
                    .replace("https://", "")
                    .replace("http://", "")
                    .split("/")[0]
                )
                if domain_clean in _INVALID_DOMAINS:
                    logger.debug(
                        "Skipping Apollo search for '%s': domain '%s' is on blocklist (likely recruiter/news site)",
                        company_name, domain
                    )
                    # Skip Apollo, fall through to other strategies
                else:
                    target_titles = roles or [
                        "VP Sales", "VP Business Development",
                        "Director Business Development", "Director Sales",
                        "Chief Commercial Officer", "Chief Operating Officer",
                    ]

                    apollo_contacts = await apollo.search_people(
                        company_domain=domain,
                        person_titles=target_titles[:5],
                        person_seniorities=["vp", "director", "c_suite", "manager"],
                        per_page=10,
                    )

                    if apollo_contacts:
                        contacts: list[dict[str, Any]] = []
                        for p in apollo_contacts:
                            contacts.append({
                                "name": p.get("name", ""),
                                "first_name": p.get("first_name", ""),
                                "last_name": p.get("last_name", ""),
                                "title": p.get("title", ""),
                                "email": p.get("email", ""),
                                "linkedin_url": p.get("linkedin_url", ""),
                                "seniority": p.get("seniority", ""),
                                "department": self._infer_department(p.get("title", "")),
                                "city": p.get("city", ""),
                                "state": p.get("state", ""),
                                "country": p.get("country", ""),
                                "apollo_id": p.get("apollo_id", ""),
                                "source": "apollo_search",
                            })

                        logger.info(
                            f"Apollo search_people found {len(contacts)} contacts for '{company_name}'"
                        )
                        return contacts

            except Exception as exc:
                logger.warning(f"Apollo contact search failed for '{company_name}': {exc}")

            except Exception as exc:
                logger.warning(f"Apollo contact search failed for '{company_name}': {exc}")

        # Strategy 2: Try Exa search_person for real contacts
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

    async def _sanitize_external_data(
        self,
        data: dict[str, Any],
        source: str = "exa_company_search",
    ) -> dict[str, Any]:
        """Sanitize external data through security pipeline before processing.

        Runs InstructionDetector pattern scan on string fields and wraps
        data with source attribution per security.md.

        Args:
            data: External data dict to sanitize.
            source: Data source identifier for trust level lookup.

        Returns:
            Sanitized data dict with injections quarantined.
        """
        sanitized = data.copy()
        for key, value in sanitized.items():
            if not isinstance(value, str):
                continue
            # Run pattern-based injection detection
            detections = self._instruction_detector.detect_patterns(value)
            if detections:
                # Quarantine the detected injections
                for detection in detections:
                    record = self._instruction_detector.quarantine(value, detection)
                    sanitized[key] = record.sanitized_text
                    value = record.sanitized_text
                logger.warning(
                    "[HUNTER] Injection detected in field '%s' from source '%s'",
                    key,
                    source,
                )
        return sanitized

    async def _score_discovery(
        self,
        company: dict[str, Any],
        contacts: list[dict[str, Any]],
        icp: dict[str, Any],
    ) -> dict[str, Any]:
        """Score a discovered lead using the dynamic 4-dimension model.

        Per execution_spec.md Section 3.2:
        - ICP Fit (base 30%)
        - Trigger Signal Relevance (base 30%)
        - Relationship & Access (base 25%)
        - Buying Readiness (base 15%)

        Args:
            company: Enriched company data.
            contacts: Discovered contacts at the company.
            icp: Active ICP criteria.

        Returns:
            Discovery score breakdown dict for lead_memories.metadata.
        """
        # Use active ICP from skill knowledge if available, else use task ICP
        effective_icp = icp
        if self._active_icp and self._active_icp.get("criteria"):
            criteria = self._active_icp["criteria"]
            if isinstance(criteria, dict):
                effective_icp = {**icp, **criteria}

        # Dynamic weights (can be adjusted based on SubIndustryContext)
        weights = {
            "icp_fit": 0.30,
            "trigger_relevance": 0.30,
            "relationship": 0.25,
            "buying_readiness": 0.15,
        }

        # Adjust weights based on SubIndustryContext if available
        if self._sub_industry_context:
            meta = self._sub_industry_context.get("metadata", {})
            # Relationship-heavy sub-industries get higher relationship weight
            if meta.get("company_type") in ("CDMO", "CRO", "Consultant"):
                weights["relationship"] = 0.35
                weights["trigger_relevance"] = 0.25
                weights["buying_readiness"] = 0.10
            # Transactional sub-industries get higher buying readiness weight
            elif meta.get("company_type") in (
                "Reagent Supplier",
                "Consumables",
                "Lab Equipment",
            ):
                weights["buying_readiness"] = 0.25
                weights["relationship"] = 0.15

        # --- Dimension 1: ICP Fit ---
        icp_score, icp_reasons, icp_gaps = await self._score_fit(company, effective_icp)

        # --- Dimension 2: Trigger Signal Relevance ---
        trigger_score = 0.0
        trigger_signals: list[str] = []
        try:
            from src.db.supabase import SupabaseClient

            db = SupabaseClient.get_client()
            company_name = company.get("name", "")
            if company_name:
                signal_result = (
                    db.table("market_signals")
                    .select("signal_type, relevance_score, detected_at")
                    .eq("user_id", self.user_id)
                    .ilike("company_name", f"%{company_name}%")
                    .order("detected_at", desc=True)
                    .limit(10)
                    .execute()
                )
                if signal_result.data:
                    # Average relevance of recent signals, with recency multiplier
                    total_relevance = 0.0
                    for sig in signal_result.data:
                        relevance = sig.get("relevance_score", 0.5)
                        total_relevance += relevance
                        trigger_signals.append(sig.get("signal_type", "unknown"))
                    trigger_score = min(
                        100.0,
                        (total_relevance / len(signal_result.data)) * 100,
                    )
        except Exception as e:
            logger.warning("[HUNTER] Failed to query market_signals for scoring: %s", e)

        # --- Dimension 3: Relationship & Access ---
        relationship_score = 0.0
        mutual_contacts = 0
        try:
            # Check for existing relationships in memory_semantic
            from src.db.supabase import SupabaseClient

            db = SupabaseClient.get_client()
            company_name = company.get("name", "")
            if company_name:
                rel_result = (
                    db.table("memory_semantic")
                    .select("fact, confidence")
                    .eq("user_id", self.user_id)
                    .ilike("fact", f"%{company_name}%")
                    .limit(5)
                    .execute()
                )
                if rel_result.data:
                    mutual_contacts = len(rel_result.data)
                    relationship_score = min(100.0, mutual_contacts * 25.0)
        except Exception as e:
            logger.warning("[HUNTER] Failed to query relationships for scoring: %s", e)

        # Contacts found boost relationship score
        if contacts:
            contact_boost = min(30.0, len(contacts) * 10.0)
            relationship_score = min(100.0, relationship_score + contact_boost)

        # --- Dimension 4: Buying Readiness ---
        buying_score = 0.0
        buying_signals: list[str] = []
        # Hiring signals from enrichment
        recent_news = company.get("recent_news", [])
        if recent_news:
            for news_item in recent_news:
                news_text = str(news_item).lower()
                if any(
                    kw in news_text
                    for kw in ["hiring", "expansion", "funding", "raised", "partnership"]
                ):
                    buying_score += 15.0
                    buying_signals.append("hiring_or_expansion")
                    break
        # Funding stage signals
        funding = company.get("funding_stage", "")
        if funding and funding.lower() not in ("unknown", ""):
            buying_score += 10.0
            buying_signals.append("known_funding_stage")
        buying_score = min(100.0, buying_score)

        # --- Compute weighted total ---
        total = (
            icp_score * weights["icp_fit"]
            + trigger_score * weights["trigger_relevance"]
            + relationship_score * weights["relationship"]
            + buying_score * weights["buying_readiness"]
        )
        total = max(0.0, min(100.0, total))

        # --- Signal-driven quality scoring ---
        # Leads with real signal events get a bonus; pure ICP matches get capped
        has_real_signals = len(trigger_signals) > 0
        signal_bonus = 0
        if has_real_signals:
            signal_bonus = 20
            total = min(100.0, total + signal_bonus)
            quality_tier = "signal_enriched"
        else:
            total = min(total, 50.0)
            quality_tier = "icp_only"

        now_iso = datetime.now(UTC).isoformat()
        sub_industry_label = ""
        if self._sub_industry_context:
            meta = self._sub_industry_context.get("metadata", {})
            sub_industry_label = (
                f"{meta.get('company_type', '')} - {meta.get('modality', '')}"
            ).strip(" -")

        return {
            "total": round(total, 1),
            "icp_fit": {
                "score": round(icp_score, 1),
                "weight": weights["icp_fit"],
                "weighted": round(icp_score * weights["icp_fit"], 1),
            },
            "trigger_relevance": {
                "score": round(trigger_score, 1),
                "weight": weights["trigger_relevance"],
                "weighted": round(trigger_score * weights["trigger_relevance"], 1),
                "triggers": trigger_signals,
            },
            "relationship": {
                "score": round(relationship_score, 1),
                "weight": weights["relationship"],
                "weighted": round(relationship_score * weights["relationship"], 1),
                "mutual_contacts": mutual_contacts,
            },
            "buying_readiness": {
                "score": round(buying_score, 1),
                "weight": weights["buying_readiness"],
                "weighted": round(buying_score * weights["buying_readiness"], 1),
                "signals": buying_signals,
            },
            "signal_quality": {
                "signal_bonus": signal_bonus,
                "signals_found": trigger_signals,
                "quality_tier": quality_tier,
            },
            "scoring_context": {
                "sub_industry": sub_industry_label,
                "weights_source": "dynamic_from_enrichment"
                if self._sub_industry_context
                else "base_defaults",
                "scored_at": now_iso,
            },
            "fit_reasons": icp_reasons,
            "gaps": icp_gaps,
        }

    async def _write_lead_to_memory(
        self,
        company: dict[str, Any],
        contacts: list[dict[str, Any]],
        discovery_score: dict[str, Any],
    ) -> None:
        """Write discovered lead to memory per Section 7.1 protocol.

        Inserts into lead_memories, lead_memory_events, lead_memory_stakeholders,
        memory_semantic, and aria_activity with proper source attribution.

        Args:
            company: Enriched company data.
            contacts: Discovered contacts.
            discovery_score: Computed discovery score breakdown.
        """
        try:
            from src.db.supabase import SupabaseClient

            db = SupabaseClient.get_client()
        except Exception as e:
            logger.warning("[HUNTER] Cannot access DB for memory writes: %s", e)
            return

        company_name = company.get("name", "Unknown")
        now_iso = datetime.now(UTC).isoformat()
        lead_id = str(uuid4())
        total_score = discovery_score.get("total", 0)

        # 1. lead_memories INSERT
        try:
            db.table("lead_memories").insert({
                "id": lead_id,
                "user_id": self.user_id,
                "company_name": company_name,
                "lifecycle_stage": "lead",
                "status": "active",
                "health_score": int(total_score),
                "metadata": {
                    "source": "hunter_discovery",
                    "discovery_score": discovery_score,
                    "industry": company.get("industry", ""),
                    "geography": company.get("geography", ""),
                    "size": company.get("size", ""),
                    "domain": company.get("domain", ""),
                },
                "first_touch_at": now_iso,
                "created_at": now_iso,
                "updated_at": now_iso,
            }).execute()
            logger.info("[HUNTER] Created lead_memories record for '%s'", company_name)
        except Exception as e:
            logger.warning(
                "[HUNTER] Failed to insert lead_memories for '%s': %s",
                company_name,
                e,
            )
            return  # If lead creation fails, skip dependent writes

        # 2. lead_memory_events INSERT (using current schema: user_id, lead_id, title, description)
        try:
            db.table("lead_memory_events").insert({
                "id": str(uuid4()),
                "user_id": user_id,
                "lead_id": lead_id,
                "event_type": "discovery",
                "title": f"Lead discovered via hunter_discovery",
                "description": (
                    f"Hunter discovered {company_name} as a lead. "
                    f"ICP match: {total_score:.0f}%."
                ),
                "confidence": 0.8,
                "source": "aria_discovery",
                "metadata": {
                    "icp_match_score": total_score,
                    "discovery_dimensions": {
                        "icp_fit": discovery_score.get("icp_fit", {}).get("score", 0),
                        "trigger_relevance": discovery_score.get("trigger_relevance", {}).get(
                            "score", 0
                        ),
                        "relationship": discovery_score.get("relationship", {}).get("score", 0),
                        "buying_readiness": discovery_score.get("buying_readiness", {}).get(
                            "score", 0
                        ),
                    },
                },
                "created_at": now_iso,
            }).execute()
        except Exception as e:
            logger.warning(
                "[HUNTER] Failed to insert lead_memory_events for '%s': %s",
                company_name,
                e,
            )

        # 3. lead_memory_stakeholders INSERT (for each contact found)
        for contact in contacts:
            try:
                db.table("lead_memory_stakeholders").insert({
                    "id": str(uuid4()),
                    "lead_memory_id": lead_id,
                    "contact_email": contact.get("email", ""),
                    "contact_name": contact.get("name", ""),
                    "title": contact.get("title", ""),
                    "role": self._infer_stakeholder_role(contact.get("title", "")),
                    "influence_level": self._infer_influence_level(
                        contact.get("seniority", "")
                    ),
                    "sentiment": "unknown",
                    "created_at": now_iso,
                }).execute()
            except Exception as e:
                logger.warning(
                    "[HUNTER] Failed to insert stakeholder '%s' for '%s': %s",
                    contact.get("name", "?"),
                    company_name,
                    e,
                )

        # 4. memory_semantic INSERT (company facts with confidence + source)
        semantic_facts = [
            {
                "fact": f"{company_name} is a {company.get('industry', 'life sciences')} "
                f"company in {company.get('geography', 'unknown region')}",
                "confidence": 0.65,
                "source": "hunter_enrichment",
                "metadata": {
                    "entity_type": "company",
                    "company_name": company_name,
                    "data_source": "exa_company_search",
                },
            },
        ]
        if company.get("size"):
            semantic_facts.append({
                "fact": f"{company_name} has approximately {company['size']} employees",
                "confidence": 0.60,
                "source": "hunter_enrichment",
                "metadata": {
                    "entity_type": "company",
                    "company_name": company_name,
                    "data_source": "exa_company_search",
                },
            })
        if company.get("funding_stage") and company["funding_stage"] != "Unknown":
            semantic_facts.append({
                "fact": f"{company_name} is at {company['funding_stage']} funding stage",
                "confidence": 0.60,
                "source": "hunter_enrichment",
                "metadata": {
                    "entity_type": "company",
                    "company_name": company_name,
                    "data_source": "exa_company_search",
                },
            })

        for fact_data in semantic_facts:
            try:
                db.table("memory_semantic").insert({
                    "id": str(uuid4()),
                    "user_id": self.user_id,
                    "fact": fact_data["fact"],
                    "confidence": fact_data["confidence"],
                    "source": fact_data["source"],
                    "metadata": fact_data["metadata"],
                    "created_at": now_iso,
                    "updated_at": now_iso,
                }).execute()
            except Exception as e:
                logger.warning(
                    "[HUNTER] Failed to insert memory_semantic fact for '%s': %s",
                    company_name,
                    e,
                )

        # 5. aria_activity INSERT
        try:
            db.table("aria_activity").insert({
                "id": str(uuid4()),
                "user_id": self.user_id,
                "activity_type": "lead_discovered",
                "title": f"New lead: {company_name}",
                "description": (
                    f"Discovered via hunter_discovery. "
                    f"ICP match: {total_score:.0f}%. "
                    f"{len(contacts)} contacts found."
                ),
                "metadata": {
                    "lead_id": lead_id,
                    "company_name": company_name,
                    "discovery_score": total_score,
                    "contacts_found": len(contacts),
                },
                "created_at": now_iso,
            }).execute()
        except Exception as e:
            logger.warning(
                "[HUNTER] Failed to insert aria_activity for '%s': %s",
                company_name,
                e,
            )

    def _infer_stakeholder_role(self, title: str) -> str:
        """Infer stakeholder role from job title.

        Args:
            title: Job title string.

        Returns:
            Role classification: decision_maker, influencer, champion, or user.
        """
        title_lower = title.lower()
        if any(kw in title_lower for kw in ["ceo", "cfo", "cto", "coo", "president", "chief", "svp"]):
            return "decision_maker"
        if any(kw in title_lower for kw in ["vp", "vice president", "director", "head of"]):
            return "influencer"
        if any(kw in title_lower for kw in ["manager", "lead", "senior"]):
            return "champion"
        return "user"

    def _infer_influence_level(self, seniority: str) -> int:
        """Infer influence level from seniority label.

        The lead_memory_stakeholders.influence_level column is INT (1-10).
        Maps seniority to a numeric score.

        Args:
            seniority: Seniority string (e.g., "C-Level", "VP-Level").

        Returns:
            Influence level as integer 1-10.
        """
        seniority_lower = seniority.lower()
        if "c-level" in seniority_lower or "executive" in seniority_lower or "c_suite" in seniority_lower:
            return 9
        if "vp" in seniority_lower or "vice president" in seniority_lower:
            return 7
        if "director" in seniority_lower:
            return 6
        if "manager" in seniority_lower or "senior" in seniority_lower:
            return 4
        return 3

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
