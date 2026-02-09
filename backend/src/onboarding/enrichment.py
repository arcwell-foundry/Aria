"""Company Enrichment Engine for onboarding (US-903).

Runs asynchronously after company discovery (US-902) to build deep
Corporate Memory. Multi-source research, LLM classification, causal
graph seeding, and knowledge gap detection.

Architecture:
    1. Orchestrator — coordinates research tasks, reports progress
    2. Research modules — individual data sources (web, clinical trials, news, leadership)
    3. Knowledge processor — classifies, extracts entities, seeds causal graph, identifies gaps
"""

import asyncio
import json
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import httpx
from pydantic import BaseModel

from src.core.config import settings
from src.core.llm import LLMClient
from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


class EnrichmentStage(str, Enum):
    """Stages of the enrichment pipeline."""

    QUEUED = "queued"
    CLASSIFYING = "classifying"
    RESEARCHING = "researching"
    EXTRACTING = "extracting"
    SEEDING_GRAPH = "seeding_graph"
    IDENTIFYING_GAPS = "identifying_gaps"
    COMPLETE = "complete"
    FAILED = "failed"


class EnrichmentProgress(BaseModel):
    """Progress report for the enrichment pipeline."""

    stage: EnrichmentStage
    percentage: float  # 0-100
    facts_discovered: int = 0
    entities_extracted: int = 0
    gaps_identified: int = 0
    message: str = ""


class CompanyClassification(BaseModel):
    """LLM-derived classification of a life sciences company."""

    company_type: str  # Biotech, Large Pharma, CDMO, CRO, etc.
    primary_modality: str  # Biologics, Small Molecule, Cell Therapy, etc.
    company_posture: str  # Buyer or Seller of services
    therapeutic_areas: list[str] = []
    likely_pain_points: list[str] = []
    confidence: float = 0.0


class DiscoveredFact(BaseModel):
    """A structured fact extracted from research data."""

    fact: str
    source: str  # "website", "clinical_trials", "news", "leadership", "inferred"
    confidence: float  # 0.0 - 1.0
    category: str  # "product", "pipeline", "leadership", "financial", etc.
    entities: list[str] = []
    timestamp: str | None = None


class CausalHypothesis(BaseModel):
    """A causal inference generated from discovered facts."""

    premise: str
    inference: str
    confidence: float = 0.55
    source: str = "inferred_during_onboarding"


class KnowledgeGap(BaseModel):
    """An identified gap in the company knowledge profile."""

    domain: str  # "leadership", "pipeline", "financial", etc.
    description: str
    priority: str  # "high", "medium", "low"
    suggested_agent: str  # "analyst", "scout", "hunter"
    suggested_action: str


class EnrichmentResult(BaseModel):
    """Complete result of the enrichment pipeline."""

    classification: CompanyClassification
    facts: list[DiscoveredFact] = []
    hypotheses: list[CausalHypothesis] = []
    gaps: list[KnowledgeGap] = []
    quality_score: float = 0.0  # 0-100
    research_sources_used: list[str] = []


class CompanyEnrichmentEngine:
    """Deep company research engine for onboarding.

    Runs asynchronously after company discovery (US-902).
    Builds Corporate Memory through multi-source research,
    LLM classification, causal graph seeding, and gap detection.
    """

    def __init__(self) -> None:
        """Initialize enrichment engine with database and LLM clients."""
        self._db = SupabaseClient.get_client()
        self._llm = LLMClient()
        self._progress_callback: Callable[..., Any] | None = None

    async def enrich_company(
        self,
        company_id: str,
        company_name: str,
        website: str,
        user_id: str,
        progress_callback: Callable[..., Any] | None = None,
    ) -> EnrichmentResult:
        """Run full enrichment pipeline for a company.

        This is the main entry point. Runs asynchronously and
        reports progress via callback (for WebSocket push).

        Args:
            company_id: UUID of the company record.
            company_name: Name of the company.
            website: Company website URL.
            user_id: UUID of the user who registered the company.
            progress_callback: Optional async callback for progress updates.

        Returns:
            Complete enrichment result with facts, hypotheses, and gaps.

        Raises:
            Exception: If enrichment fails critically (logged and re-raised).
        """
        self._progress_callback = progress_callback
        result = EnrichmentResult(
            classification=CompanyClassification(
                company_type="Unknown",
                primary_modality="Unknown",
                company_posture="Unknown",
            )
        )

        try:
            # Stage 1: LLM Classification
            await self._report_progress(
                EnrichmentProgress(
                    stage=EnrichmentStage.CLASSIFYING,
                    percentage=5,
                    message=f"Analyzing {company_name}...",
                )
            )
            result.classification = await self._classify_company(company_name, website)

            # Stage 2: Parallel Research
            await self._report_progress(
                EnrichmentProgress(
                    stage=EnrichmentStage.RESEARCHING,
                    percentage=15,
                    message="Researching across multiple sources...",
                )
            )
            raw_research, sources_used = await self._run_research_modules(
                company_name, website, result.classification
            )
            result.research_sources_used = sources_used

            # Stage 3: Entity & Fact Extraction
            await self._report_progress(
                EnrichmentProgress(
                    stage=EnrichmentStage.EXTRACTING,
                    percentage=50,
                    facts_discovered=len(raw_research),
                    message=f"Extracted {len(raw_research)} data points, processing...",
                )
            )
            result.facts = await self._extract_facts(raw_research, company_name)

            # Stage 4: Causal Graph Seeding
            await self._report_progress(
                EnrichmentProgress(
                    stage=EnrichmentStage.SEEDING_GRAPH,
                    percentage=70,
                    facts_discovered=len(result.facts),
                    message="Building intelligence graph...",
                )
            )
            result.hypotheses = await self._generate_causal_hypotheses(result.facts)

            # Stage 5: Knowledge Gap Identification
            await self._report_progress(
                EnrichmentProgress(
                    stage=EnrichmentStage.IDENTIFYING_GAPS,
                    percentage=85,
                    facts_discovered=len(result.facts),
                    message="Identifying knowledge gaps...",
                )
            )
            result.gaps = await self._identify_knowledge_gaps(result.facts, result.classification)

            # Stage 6: Store everything
            result.quality_score = self._calculate_quality_score(result)
            await self._store_results(company_id, user_id, result)

            # Stage 7: Update readiness score
            await self._update_readiness(user_id, result.quality_score)

            # Stage 8: Generate Memory Delta for frontend display
            try:
                from src.memory.delta_presenter import MemoryDeltaPresenter

                presenter = MemoryDeltaPresenter()
                deltas = await presenter.generate_delta(
                    user_id=user_id,
                    domain="corporate_memory",
                )
                # Store delta in onboarding_state.step_data for frontend consumption
                delta_data = [d.model_dump() for d in deltas]
                from src.db.supabase import SupabaseClient

                db = SupabaseClient.get_client()
                state_result = (
                    db.table("onboarding_state")
                    .select("step_data")
                    .eq("user_id", user_id)
                    .maybe_single()
                    .execute()
                )
                if state_result.data:
                    step_data = state_result.data.get("step_data", {})
                    step_data["enrichment_delta"] = delta_data
                    db.table("onboarding_state").update({"step_data": step_data}).eq(
                        "user_id", user_id
                    ).execute()
            except Exception as e:
                logger.warning(
                    "Memory Delta generation after enrichment failed",
                    extra={"user_id": user_id, "error": str(e)},
                )

            await self._report_progress(
                EnrichmentProgress(
                    stage=EnrichmentStage.COMPLETE,
                    percentage=100,
                    facts_discovered=len(result.facts),
                    entities_extracted=sum(len(f.entities) for f in result.facts),
                    gaps_identified=len(result.gaps),
                    message=(
                        f"Research complete — discovered {len(result.facts)} "
                        f"facts about {company_name}"
                    ),
                )
            )

            # Record episodic memory
            await self._record_episodic(user_id, company_name, result)

            return result

        except Exception as e:
            logger.error(f"Enrichment failed for {company_name}: {e}", exc_info=True)
            await self._report_progress(
                EnrichmentProgress(
                    stage=EnrichmentStage.FAILED,
                    percentage=0,
                    message="Research encountered an issue — will retry automatically",
                )
            )
            raise

    async def _classify_company(self, company_name: str, website: str) -> CompanyClassification:
        """Use LLM to classify company type, modality, and posture.

        Args:
            company_name: Name of the company.
            website: Company website URL.

        Returns:
            Classification result with type, modality, posture, and pain points.
        """
        prompt = f"""Classify this life sciences company.

Company: {company_name}
Website: {website}

Provide a JSON response with:
{{
    "company_type": "one of: Biotech, Large Pharma, CDMO, CRO, Cell/Gene Therapy, Diagnostics, Medical Device, Healthcare Tech",
    "primary_modality": "one of: Biologics, Small Molecule, Cell Therapy, Gene Therapy, ADC, Biosimilars, Diagnostics, Services, Platform, Mixed",
    "company_posture": "Buyer or Seller (of services — CDMOs/CROs are Sellers, pharma/biotech are Buyers)",
    "therapeutic_areas": ["list of likely therapeutic focus areas"],
    "likely_pain_points": ["3-5 pain points based on company type and modality"],
    "confidence": 0.0-1.0
}}

Be specific. Use your knowledge of the life sciences industry.
Respond ONLY with the JSON object, no additional text."""

        response = await self._llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.3,
        )
        try:
            data = json.loads(response)
            return CompanyClassification(**data)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Classification parse failed: {e}")
            return CompanyClassification(
                company_type="Unknown",
                primary_modality="Unknown",
                company_posture="Unknown",
                confidence=0.0,
            )

    async def _run_research_modules(
        self,
        company_name: str,
        website: str,
        classification: CompanyClassification,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """Run all research modules in parallel.

        Args:
            company_name: Name of the company.
            website: Company website URL.
            classification: LLM-derived company classification.

        Returns:
            Tuple of (aggregated raw research data, list of source names used).
        """
        tasks = [
            self._research_website(website),
            self._research_news(company_name),
            self._research_clinical_trials(company_name, classification),
            self._research_leadership(company_name),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_data: list[dict[str, Any]] = []
        sources_used: list[str] = []
        source_names = ["website", "news", "clinical_trials", "leadership"]

        for i, res in enumerate(results):
            if isinstance(res, BaseException):
                logger.warning(f"Research module {source_names[i]} failed: {res}")
                continue
            if res:
                all_data.extend(res)
                sources_used.append(source_names[i])

        return all_data, sources_used

    async def _research_website(self, website: str) -> list[dict[str, Any]]:
        """Extract content from company website via Exa API.

        Args:
            website: Company website URL.

        Returns:
            List of extracted page data dicts.
        """
        results: list[dict[str, Any]] = []
        try:
            if not settings.EXA_API_KEY:
                logger.info("Exa API key not configured, skipping website research")
                return results

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.exa.ai/search",
                    headers={"x-api-key": settings.EXA_API_KEY},
                    json={
                        "query": f"site:{website}",
                        "numResults": 10,
                        "type": "auto",
                        "contents": {"text": {"maxCharacters": 3000}},
                    },
                    timeout=30.0,
                )
                if response.status_code == 200:
                    data = response.json()
                    for item in data.get("results", []):
                        results.append(
                            {
                                "source": "website",
                                "url": item.get("url", ""),
                                "title": item.get("title", ""),
                                "content": item.get("text", ""),
                            }
                        )

            logger.info(f"Website research found {len(results)} pages")
        except Exception as e:
            logger.warning(f"Website research failed: {e}")

        return results

    async def _research_news(self, company_name: str) -> list[dict[str, Any]]:
        """Search for recent news about the company via Exa.

        Args:
            company_name: Name of the company.

        Returns:
            List of news article data dicts.
        """
        results: list[dict[str, Any]] = []
        try:
            if not settings.EXA_API_KEY:
                logger.info("Exa API key not configured, skipping news research")
                return results

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.exa.ai/search",
                    headers={"x-api-key": settings.EXA_API_KEY},
                    json={
                        "query": (f"{company_name} life sciences news funding partnership"),
                        "numResults": 10,
                        "type": "neural",
                        "useAutoprompt": True,
                        "contents": {"text": {"maxCharacters": 2000}},
                    },
                    timeout=30.0,
                )
                if response.status_code == 200:
                    data = response.json()
                    for item in data.get("results", []):
                        results.append(
                            {
                                "source": "news",
                                "url": item.get("url", ""),
                                "title": item.get("title", ""),
                                "content": item.get("text", ""),
                                "published_date": item.get("publishedDate"),
                            }
                        )

            logger.info(f"News research found {len(results)} articles")
        except Exception as e:
            logger.warning(f"News research failed: {e}")

        return results

    async def _research_clinical_trials(
        self, company_name: str, _classification: CompanyClassification
    ) -> list[dict[str, Any]]:
        """Query ClinicalTrials.gov for active trials.

        Args:
            company_name: Name of the company (used as sponsor query).
            _classification: Company classification (reserved for future
                filtering by therapeutic area).

        Returns:
            List of clinical trial data dicts.
        """
        results: list[dict[str, Any]] = []
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://clinicaltrials.gov/api/v2/studies",
                    params={
                        "query.spons": company_name,
                        "filter.overallStatus": (
                            "RECRUITING,ACTIVE_NOT_RECRUITING,ENROLLING_BY_INVITATION"
                        ),
                        "pageSize": 20,
                        "format": "json",
                    },
                    timeout=30.0,
                )
                if response.status_code == 200:
                    data = response.json()
                    for study in data.get("studies", []):
                        protocol = study.get("protocolSection", {})
                        id_module = protocol.get("identificationModule", {})
                        status_module = protocol.get("statusModule", {})
                        design_module = protocol.get("designModule", {})
                        results.append(
                            {
                                "source": "clinical_trials",
                                "nct_id": id_module.get("nctId", ""),
                                "title": id_module.get("briefTitle", ""),
                                "status": status_module.get("overallStatus", ""),
                                "phase": design_module.get("phases", []),
                                "content": id_module.get("briefTitle", ""),
                            }
                        )

            logger.info(f"Clinical trials research found {len(results)} studies")
        except Exception as e:
            logger.warning(f"Clinical trials research failed: {e}")

        return results

    async def _research_leadership(self, company_name: str) -> list[dict[str, Any]]:
        """Identify C-suite and leadership team via web research.

        Args:
            company_name: Name of the company.

        Returns:
            List of leadership research data dicts.
        """
        results: list[dict[str, Any]] = []
        try:
            if not settings.EXA_API_KEY:
                logger.info("Exa API key not configured, skipping leadership research")
                return results

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.exa.ai/search",
                    headers={"x-api-key": settings.EXA_API_KEY},
                    json={
                        "query": (f"{company_name} leadership team CEO executive management"),
                        "numResults": 5,
                        "type": "neural",
                        "contents": {"text": {"maxCharacters": 2000}},
                    },
                    timeout=30.0,
                )
                if response.status_code == 200:
                    data = response.json()
                    for item in data.get("results", []):
                        results.append(
                            {
                                "source": "leadership",
                                "url": item.get("url", ""),
                                "title": item.get("title", ""),
                                "content": item.get("text", ""),
                            }
                        )

            logger.info(f"Leadership research found {len(results)} results")
        except Exception as e:
            logger.warning(f"Leadership research failed: {e}")

        return results

    async def _extract_facts(
        self, raw_research: list[dict[str, Any]], company_name: str
    ) -> list[DiscoveredFact]:
        """Use LLM to extract structured facts from raw research data.

        Args:
            raw_research: List of raw research data dicts from all modules.
            company_name: Name of the company being researched.

        Returns:
            List of structured DiscoveredFact instances.
        """
        if not raw_research:
            return []

        # Batch research content for LLM processing
        research_text = ""
        for item in raw_research[:20]:  # Cap at 20 items
            source = item.get("source", "unknown")
            content = str(item.get("content", ""))[:1000]
            research_text += f"\n[{source}] {item.get('title', '')}: {content}\n"

        prompt = f"""Extract structured facts about {company_name} from this research data.

{research_text}

For each fact, provide a JSON array:
[
  {{
    "fact": "clear statement of fact",
    "source": "website|clinical_trials|news|leadership",
    "confidence": 0.0-1.0,
    "category": "product|pipeline|leadership|financial|partnership|regulatory|competitive|manufacturing",
    "entities": ["entity names mentioned"]
  }}
]

Extract ALL meaningful facts. Be specific. Include numbers, dates, names where available.
Aim for 15-30 facts if the data supports it. Only include facts with evidence in the source data.
Respond ONLY with the JSON array, no additional text."""

        response = await self._llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=3000,
            temperature=0.3,
        )
        try:
            facts_data = json.loads(response)
            return [DiscoveredFact(**f) for f in facts_data]
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Fact extraction parse failed: {e}")
            return []

    async def _generate_causal_hypotheses(
        self, facts: list[DiscoveredFact]
    ) -> list[CausalHypothesis]:
        """Generate causal hypotheses from discovered facts.

        For each major fact, generates 1-2 business implications.
        Tagged as inferred_during_onboarding with 0.50-0.60 confidence.

        Args:
            facts: List of discovered facts to generate hypotheses from.

        Returns:
            List of causal hypotheses with premise, inference, and confidence.
        """
        if not facts:
            return []

        # Select high-confidence facts for hypothesis generation
        key_facts = [f for f in facts if f.confidence >= 0.6][:15]
        if not key_facts:
            key_facts = facts[:10]

        facts_text = "\n".join(
            f"- [{f.category}] {f.fact} (confidence: {f.confidence})" for f in key_facts
        )

        prompt = f"""Based on these facts about a life sciences company, generate causal hypotheses.

Facts:
{facts_text}

For each major fact, generate 1-2 business implications that would be useful for a sales team.

Format as JSON array:
[
  {{
    "premise": "the observed fact",
    "inference": "the business implication or likely next action",
    "confidence": 0.50-0.60
  }}
]

Examples of good hypotheses:
- "Series C funding -> hiring ramp likely -> pipeline generation need"
- "FDA breakthrough designation -> accelerated timeline -> increased vendor needs"
- "New manufacturing facility -> capacity expansion -> CDMO contract opportunities"

Generate 5-10 hypotheses. Be specific to life sciences business dynamics.
Respond ONLY with the JSON array, no additional text."""

        response = await self._llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0.5,
        )
        try:
            hyp_data = json.loads(response)
            return [
                CausalHypothesis(
                    premise=h["premise"],
                    inference=h["inference"],
                    confidence=h.get("confidence", 0.55),
                    source="inferred_during_onboarding",
                )
                for h in hyp_data
            ]
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Hypothesis generation parse failed: {e}")
            return []

    async def _identify_knowledge_gaps(
        self,
        facts: list[DiscoveredFact],
        _classification: CompanyClassification,
    ) -> list[KnowledgeGap]:
        """Compare discovered facts against ideal company profile.

        Identifies what we DON'T know and creates tasks for agents.

        Args:
            facts: List of discovered facts.
            _classification: Company classification (reserved for
                type-specific gap templates).

        Returns:
            List of knowledge gaps with suggested agent actions.
        """
        # Define ideal profile domains and expected data points
        ideal_domains: dict[str, list[str]] = {
            "leadership": ["CEO", "CTO/CSO", "CFO", "VP Sales", "VP BD"],
            "pipeline": ["active programs", "development stage", "therapeutic areas"],
            "financial": ["funding status", "revenue range", "runway"],
            "competitive": [
                "direct competitors",
                "market position",
                "differentiation",
            ],
            "manufacturing": [
                "production capability",
                "capacity",
                "technology platforms",
            ],
            "partnership": ["key partners", "collaboration agreements"],
            "regulatory": [
                "approved products",
                "pending submissions",
                "FDA interactions",
            ],
        }

        # Check what categories we have facts for
        found_categories = {f.category for f in facts}
        fact_text = " ".join(f.fact.lower() for f in facts)

        agent_map: dict[str, tuple[str, str]] = {
            "leadership": ("analyst", "Research leadership team"),
            "pipeline": ("analyst", "Research product pipeline"),
            "financial": ("scout", "Monitor financial news and filings"),
            "competitive": ("analyst", "Identify and analyze competitors"),
            "manufacturing": ("analyst", "Research manufacturing capabilities"),
            "partnership": ("scout", "Monitor partnership announcements"),
            "regulatory": ("scout", "Monitor regulatory filings and approvals"),
        }

        high_priority_domains = {"leadership", "pipeline", "competitive"}

        gaps: list[KnowledgeGap] = []
        for domain, expected in ideal_domains.items():
            has_facts = domain in found_categories or any(
                kw.lower() in fact_text for kw in expected
            )
            if not has_facts:
                agent, action = agent_map.get(domain, ("analyst", f"Research {domain}"))
                gaps.append(
                    KnowledgeGap(
                        domain=domain,
                        description=(f"No information found about {domain}: {', '.join(expected)}"),
                        priority="high" if domain in high_priority_domains else "medium",
                        suggested_agent=agent,
                        suggested_action=f"{action} within 48 hours",
                    )
                )

        return gaps

    def _calculate_quality_score(self, result: EnrichmentResult) -> float:
        """Calculate enrichment completeness score (0-100).

        Args:
            result: The enrichment result to score.

        Returns:
            Quality score from 0-100 based on completeness.
        """
        score = 0.0

        # Classification quality (20 points)
        if result.classification.confidence > 0.7:
            score += 20
        elif result.classification.confidence > 0.4:
            score += 10

        # Fact quantity (30 points)
        fact_count = len(result.facts)
        if fact_count >= 20:
            score += 30
        elif fact_count >= 10:
            score += 20
        elif fact_count >= 5:
            score += 10

        # Category diversity (20 points)
        categories = {f.category for f in result.facts}
        category_score = min(20, len(categories) * 3)
        score += category_score

        # Hypothesis quality (15 points)
        if len(result.hypotheses) >= 5:
            score += 15
        elif len(result.hypotheses) >= 2:
            score += 8

        # Gap coverage — fewer gaps = better (15 points)
        high_gaps = [g for g in result.gaps if g.priority == "high"]
        if len(high_gaps) == 0:
            score += 15
        elif len(high_gaps) <= 2:
            score += 8

        return min(100.0, score)

    async def _store_results(self, company_id: str, user_id: str, result: EnrichmentResult) -> None:
        """Store enrichment results in Corporate Memory and Semantic Memory.

        Args:
            company_id: UUID of the company.
            user_id: UUID of the user.
            result: Complete enrichment result.
        """
        # Store classification in company settings
        try:
            self._db.table("companies").update(
                {
                    "settings": {
                        "classification": result.classification.model_dump(),
                        "enrichment_quality_score": result.quality_score,
                        "enriched_at": datetime.now(UTC).isoformat(),
                    }
                }
            ).eq("id", company_id).execute()
        except Exception as e:
            logger.warning(f"Failed to update company settings: {e}")

        # Store facts in semantic memory
        for fact in result.facts:
            try:
                self._db.table("memory_semantic").insert(
                    {
                        "user_id": user_id,
                        "fact": fact.fact,
                        "confidence": fact.confidence,
                        "source": f"enrichment_{fact.source}",
                        "metadata": {
                            "category": fact.category,
                            "entities": fact.entities,
                            "company_id": company_id,
                        },
                    }
                ).execute()
            except Exception as e:
                logger.warning(f"Failed to store fact: {e}")

        # Store hypotheses in semantic memory and Graphiti knowledge graph
        for hyp in result.hypotheses:
            try:
                self._db.table("memory_semantic").insert(
                    {
                        "user_id": user_id,
                        "fact": f"{hyp.premise} -> {hyp.inference}",
                        "confidence": hyp.confidence,
                        "source": hyp.source,
                        "metadata": {
                            "type": "causal_hypothesis",
                            "company_id": company_id,
                        },
                    }
                ).execute()
            except Exception as e:
                logger.warning(f"Failed to store hypothesis in Supabase: {e}")

            # Also store in Graphiti for temporal knowledge graph traversal
            try:
                from src.db.graphiti import GraphitiClient

                await GraphitiClient.add_episode(
                    name=f"causal_{hyp.premise[:40]}",
                    episode_body=(
                        f"Causal hypothesis: {hyp.premise} → {hyp.inference}. "
                        f"Confidence: {hyp.confidence}"
                    ),
                    source_description="inferred_during_onboarding_enrichment",
                    reference_time=datetime.now(UTC),
                )
            except Exception as e:
                logger.warning(f"Failed to store hypothesis in Graphiti: {e}")

        # Record activity for feed
        try:
            from src.services.activity_service import ActivityService

            await ActivityService().record(
                user_id=user_id,
                agent="scout",
                activity_type="enrichment_complete",
                title="Researched company background",
                description=(
                    f"ARIA researched the company — discovered {len(result.facts)} facts "
                    f"about their {result.classification.company_type} business"
                ),
                confidence=0.85,
                related_entity_type="company",
                related_entity_id=company_id,
                metadata={
                    "fact_count": len(result.facts),
                    "company_type": result.classification.company_type,
                },
            )
        except Exception as e:
            logger.warning("Failed to record enrichment activity: %s", e)

        # Store knowledge gaps as Prospective Memory tasks
        for gap in result.gaps:
            try:
                self._db.table("prospective_memories").insert(
                    {
                        "user_id": user_id,
                        "task": gap.suggested_action,
                        "due_date": None,
                        "status": "pending",
                        "metadata": {
                            "type": "knowledge_gap",
                            "domain": gap.domain,
                            "priority": gap.priority,
                            "suggested_agent": gap.suggested_agent,
                            "company_id": company_id,
                        },
                    }
                ).execute()
            except Exception as e:
                logger.warning(f"Failed to store knowledge gap: {e}")

    async def _update_readiness(self, user_id: str, quality_score: float) -> None:
        """Update corporate_memory readiness sub-score.

        Enrichment alone can bring corporate_memory to max 60.
        Remaining 40 comes from documents, user corrections, etc.

        Args:
            user_id: UUID of the user.
            quality_score: Enrichment quality score (0-100).
        """
        try:
            from src.onboarding.orchestrator import OnboardingOrchestrator

            orch = OnboardingOrchestrator()
            readiness = min(60.0, quality_score * 0.6)
            await orch.update_readiness_scores(user_id, {"corporate_memory": readiness})
        except Exception as e:
            logger.warning(f"Failed to update readiness: {e}")

    async def _record_episodic(
        self, user_id: str, company_name: str, result: EnrichmentResult
    ) -> None:
        """Record enrichment completion in episodic memory.

        Args:
            user_id: UUID of the user.
            company_name: Name of the company.
            result: Complete enrichment result.
        """
        try:
            from src.memory.episodic import Episode, EpisodicMemory

            memory = EpisodicMemory()
            now = datetime.now(UTC)
            episode = Episode(
                id=str(uuid.uuid4()),
                user_id=user_id,
                event_type="onboarding_enrichment_complete",
                content=(
                    f"Enrichment completed for {company_name} — "
                    f"discovered {len(result.facts)} facts, "
                    f"identified {len(result.gaps)} gaps"
                ),
                participants=[],
                occurred_at=now,
                recorded_at=now,
                context={
                    "company": company_name,
                    "facts_discovered": len(result.facts),
                    "hypotheses_generated": len(result.hypotheses),
                    "gaps_identified": len(result.gaps),
                    "quality_score": result.quality_score,
                    "classification": result.classification.model_dump(),
                },
            )
            await memory.store_episode(episode)
        except Exception as e:
            logger.warning(f"Failed to record episodic event: {e}")

    async def _report_progress(self, progress: EnrichmentProgress) -> None:
        """Report progress via callback (for WebSocket push).

        Args:
            progress: Current progress state.
        """
        if self._progress_callback:
            try:
                await self._progress_callback(progress.model_dump())
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")
        logger.info(
            "Enrichment progress: %s - %.0f%% - %s",
            progress.stage,
            progress.percentage,
            progress.message,
        )
