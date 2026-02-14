"""AnalystAgent module for ARIA.

Provides scientific research capabilities using life sciences APIs
including PubMed, ClinicalTrials.gov, FDA, and ChEMBL.
"""

import asyncio
import logging
from datetime import UTC
from typing import TYPE_CHECKING, Any, cast

import httpx

from src.agents.skill_aware_agent import SkillAwareAgent

if TYPE_CHECKING:
    from src.core.llm import LLMClient
    from src.skills.index import SkillIndex
    from src.skills.orchestrator import SkillOrchestrator

logger = logging.getLogger(__name__)

# PubMed API endpoints
PUBMED_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
PUBMED_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

# ClinicalTrials.gov API endpoint
CLINICALTRIALS_API_URL = "https://clinicaltrials.gov/api/v2/studies"

# OpenFDA API endpoints
FDA_DRUG_API_URL = "https://api.fda.gov/drug/label.json"
FDA_DEVICE_API_URL = "https://api.fda.gov/device/510k.json"

# ChEMBL API endpoint
CHEMBL_API_URL = "https://www.ebi.ac.uk/chembl/api/data"


class AnalystAgent(SkillAwareAgent):
    """Scientific research agent for life sciences queries.

    The Analyst agent searches scientific databases to provide
    domain expertise, literature reviews, and data extraction
    from biomedical APIs. Now includes Exa web research for
    competitive analysis and general web intelligence.
    """

    name = "Analyst"
    description = "Scientific research agent for life sciences queries"
    agent_id = "analyst"

    # Rate limiting: PubMed allows 3 requests/second without API key
    _pubmed_rate_limit = 3
    _pubmem_last_call_time: float = 0.0

    def __init__(
        self,
        llm_client: "LLMClient",
        user_id: str,
        skill_orchestrator: "SkillOrchestrator | None" = None,
        skill_index: "SkillIndex | None" = None,
    ) -> None:
        """Initialize the Analyst agent.

        Args:
            llm_client: LLM client for reasoning and generation.
            user_id: ID of the user this agent is working for.
            skill_orchestrator: Optional orchestrator for multi-skill execution.
            skill_index: Optional index for skill discovery.
        """
        self._research_cache: dict[str, Any] = {}
        self._http_client: httpx.AsyncClient | None = None
        self._exa_provider: Any = None
        super().__init__(
            llm_client=llm_client,
            user_id=user_id,
            skill_orchestrator=skill_orchestrator,
            skill_index=skill_index,
        )

    def _get_exa_provider(self) -> Any:
        """Lazily initialize and return the ExaEnrichmentProvider."""
        if self._exa_provider is None:
            try:
                from src.agents.capabilities.enrichment_providers.exa_provider import (
                    ExaEnrichmentProvider,
                )

                self._exa_provider = ExaEnrichmentProvider()
                logger.info("AnalystAgent: ExaEnrichmentProvider initialized")
            except Exception as e:
                logger.warning("AnalystAgent: Failed to initialize ExaEnrichmentProvider: %s", e)
        return self._exa_provider

    def _register_tools(self) -> dict[str, Any]:
        """Register Analyst agent's research tools.

        Returns:
            Dictionary mapping tool names to callable functions.
        """
        return {
            "pubmed_search": self._pubmed_search,
            "clinical_trials_search": self._clinical_trials_search,
            "fda_drug_search": self._fda_drug_search,
            "chembl_search": self._chembl_search,
            "web_research": self._web_research,
            "answer_question": self._answer_question,
        }

    def validate_input(self, task: dict[str, Any]) -> bool:
        """Validate research task input before execution.

        Args:
            task: Task specification to validate.

        Returns:
            True if valid, False otherwise.
        """
        # Require 'query' field with research question
        if "query" not in task:
            return False

        query = task["query"]
        if not query or not isinstance(query, str):
            return False

        # Validate depth level if provided
        if "depth" in task:
            valid_depths = {"quick", "standard", "comprehensive"}
            if task["depth"] not in valid_depths:
                return False

        return True

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with timeout settings.

        Returns:
            Async HTTP client.
        """
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def execute(self, _task: dict[str, Any]) -> Any:
        """Execute the analyst agent's primary research task.

        Args:
            _task: Task specification with:
                - query: Research question (required)
                - depth: Research depth - "quick", "standard", or "comprehensive" (optional)

        Returns:
            AgentResult with structured research report.
        """
        # OODA ACT: Log skill consideration before native execution
        await self._log_skill_consideration()

        from datetime import datetime

        from src.agents.base import AgentResult

        query = _task["query"]
        depth = _task.get("depth", "standard")

        report: dict[str, Any] = {
            "query": query,
            "depth": depth,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Always search PubMed
        pubmed_result = await self._pubmed_search(query=query, max_results=20)
        report["pubmed_search"] = {
            "count": pubmed_result.get("count", 0),
            "pmids": pubmed_result.get("pmids", []),
        }

        # Fetch article details
        if pubmed_result.get("pmids"):
            details = await self._pubmed_fetch_details(pubmed_result["pmids"])
            report["pubmed_articles"] = details
        else:
            report["pubmed_articles"] = {}

        # Search other databases based on depth
        if depth in ("standard", "comprehensive"):
            # ClinicalTrials.gov
            trials_result = await self._clinical_trials_search(query=query)
            report["clinical_trials"] = trials_result

            # FDA
            fda_result = await self._fda_drug_search(drug_name=query, search_type="brand")
            report["fda_products"] = fda_result

        if depth == "comprehensive":
            # ChEMBL for molecule data
            chembl_result = await self._chembl_search(query=query)
            report["chembl_molecules"] = chembl_result

        return AgentResult(success=True, data=report)

    def format_output(self, data: Any) -> Any:
        """Format output data with summary statistics.

        Args:
            data: Raw research report data.

        Returns:
            Formatted research report with summary section.
        """
        if not isinstance(data, dict):
            return data

        summary = {
            "total_sources": 0,
            "pubmed_article_count": 0,
            "clinical_trials_count": 0,
            "fda_products_count": 0,
            "chembl_molecules_count": 0,
        }

        # Count PubMed articles
        if "pubmed_search" in data:
            summary["pubmed_article_count"] = data["pubmed_search"].get("count", 0)
            summary["total_sources"] += 1

        # Count clinical trials
        if "clinical_trials" in data:
            summary["clinical_trials_count"] = data["clinical_trials"].get("total_count", 0)
            summary["total_sources"] += 1

        # Count FDA products
        if "fda_products" in data:
            summary["fda_products_count"] = data["fda_products"].get("total", 0)
            summary["total_sources"] += 1

        # Count ChEMBL molecules
        if "chembl_molecules" in data:
            summary["chembl_molecules_count"] = data["chembl_molecules"].get("total_count", 0)
            summary["total_sources"] += 1

        # Add summary to data
        data["summary"] = summary

        return data

    async def _pubmed_search(
        self,
        query: str,
        max_results: int = 20,
        days_back: int | None = None,
    ) -> dict[str, Any]:
        """Search PubMed for articles matching the query.

        Args:
            query: Search query string.
            max_results: Maximum number of results to return.
            days_back: Optional filter to articles from last N days.

        Returns:
            Dictionary with count and list of PMIDs.
        """
        import time

        # Rate limiting
        current_time = time.time()
        time_since_last = current_time - self._pubmem_last_call_time
        min_interval = 1.0 / self._pubmed_rate_limit
        if time_since_last < min_interval:
            await asyncio.sleep(min_interval - time_since_last)

        # Check cache
        cache_key = f"pubmed:{query}:{max_results}:{days_back}"
        if cache_key in self._research_cache:
            logger.info(f"PubMed cache hit for query: {query}")
            return cast(dict[str, Any], self._research_cache[cache_key])

        try:
            client = await self._get_http_client()

            # Build search parameters
            params: dict[str, Any] = {
                "db": "pubmed",
                "term": query,
                "retmode": "json",
                "retmax": max_results,
                "sort": "relevance",
            }

            if days_back:
                # Add date filter
                params["datetype"] = "edat"
                params["reldate"] = days_back

            response = await client.get(PUBMED_ESEARCH_URL, params=params)
            response.raise_for_status()

            data = response.json()
            search_result = data.get("esearchresult", {})

            result = {
                "query": query,
                "count": int(search_result.get("count", 0)),
                "pmids": search_result.get("idlist", []),
                "retmax": int(search_result.get("retmax", 0)),
            }

            # Cache result
            self._research_cache[cache_key] = result
            self._pubmem_last_call_time = time.time()

            logger.info(
                f"PubMed search found {result['count']} articles for: {query}",
                extra={"query": query, "count": result["count"]},
            )

            return result

        except httpx.HTTPStatusError as e:
            logger.error(f"PubMed API error: {e}")
            return {"error": str(e), "pmids": [], "count": 0}
        except Exception as e:
            logger.error(f"PubMed search failed: {e}")
            return {"error": str(e), "pmids": [], "count": 0}

    async def _pubmed_fetch_details(self, pmids: list[str]) -> dict[str, Any]:
        """Fetch detailed metadata for PubMed articles.

        Args:
            pmids: List of PubMed IDs to fetch details for.

        Returns:
            Dictionary mapping PMID to article metadata.
        """
        import time

        # Rate limiting
        current_time = time.time()
        time_since_last = current_time - self._pubmem_last_call_time
        min_interval = 1.0 / self._pubmed_rate_limit
        if time_since_last < min_interval:
            await asyncio.sleep(min_interval - time_since_last)

        if not pmids:
            return {}

        # Check cache for batch
        cache_key = f"pubmed_details:{','.join(sorted(pmids))}"
        if cache_key in self._research_cache:
            logger.info(f"PubMed details cache hit for {len(pmids)} PMIDs")
            return cast(dict[str, Any], self._research_cache[cache_key])

        try:
            client = await self._get_http_client()

            params = {
                "db": "pubmed",
                "id": ",".join(pmids),
                "retmode": "json",
                "rettype": "abstract",
            }

            response = await client.get(PUBMED_ESUMMARY_URL, params=params)
            response.raise_for_status()

            data = response.json()
            result_data: dict[str, Any] = data.get("result", {})

            # Remove the "uids" key which contains the list, not the details
            if "uids" in result_data:
                del result_data["uids"]

            self._research_cache[cache_key] = result_data
            self._pubmem_last_call_time = time.time()

            logger.info(f"Fetched details for {len(result_data)} articles")

            return result_data

        except httpx.HTTPStatusError as e:
            logger.error(f"PubMed details API error: {e}")
            return {}
        except Exception as e:
            logger.error(f"PubMed details fetch failed: {e}")
            return {}

    async def _clinical_trials_search(
        self,
        query: str,
        max_results: int = 20,
        status: str | None = None,
    ) -> dict[str, Any]:
        """Search ClinicalTrials.gov for studies matching the query.

        Args:
            query: Search query string.
            max_results: Maximum number of results to return.
            status: Optional filter by study status.

        Returns:
            Dictionary with total_count and list of studies.
        """
        # Check cache
        cache_key = f"clinicaltrials:{query}:{max_results}:{status}"
        if cache_key in self._research_cache:
            logger.info(f"ClinicalTrials cache hit for query: {query}")
            return cast(dict[str, Any], self._research_cache[cache_key])

        try:
            client = await self._get_http_client()

            # Build parameters
            params: dict[str, str | int] = {
                "query.term": query,
                "pageSize": max_results,
            }

            if status:
                params["filter.oversightStatus"] = status

            response = await client.get(CLINICALTRIALS_API_URL, params=params)
            response.raise_for_status()

            data = response.json()

            # Transform studies to a cleaner format
            studies = []
            for study in data.get("studies", []):
                proto = study.get("protocolSection", {})
                id_module = proto.get("identificationModule", {})
                status_module = proto.get("statusModule", {})
                conditions_module = proto.get("conditionsModule", {})

                studies.append(
                    {
                        "nct_id": id_module.get("nctId"),
                        "title": id_module.get("briefTitle"),
                        "status": status_module.get("overallStatus"),
                        "start_date": status_module.get("startDate"),
                        "conditions": conditions_module.get("conditions", []),
                    }
                )

            result = {
                "query": query,
                "total_count": data.get("totalCount", 0),
                "studies": studies,
            }

            # Cache result
            self._research_cache[cache_key] = result

            logger.info(
                f"ClinicalTrials search found {result['total_count']} studies for: {query}",
                extra={"query": query, "count": result["total_count"]},
            )

            return result

        except httpx.HTTPStatusError as e:
            logger.error(f"ClinicalTrials API error: {e}")
            return {"error": str(e), "studies": [], "total_count": 0}
        except Exception as e:
            logger.error(f"ClinicalTrials search failed: {e}")
            return {"error": str(e), "studies": [], "total_count": 0}

    async def _fda_drug_search(
        self,
        drug_name: str,
        search_type: str = "brand",
        max_results: int = 10,
    ) -> dict[str, Any]:
        """Search OpenFDA API for drug or device information.

        Args:
            drug_name: Name of the drug or device to search.
            search_type: Type of search - "brand", "generic", or "device".
            max_results: Maximum number of results to return.

        Returns:
            Dictionary with total count and list of products/devices.
        """
        # Check cache
        cache_key = f"fda:{drug_name}:{search_type}:{max_results}"
        if cache_key in self._research_cache:
            logger.info(f"FDA cache hit for: {drug_name}")
            return cast(dict[str, Any], self._research_cache[cache_key])

        try:
            client = await self._get_http_client()

            # Determine API endpoint and search field
            if search_type == "device":
                url = FDA_DEVICE_API_URL
                search_field = "device_name"
            else:
                url = FDA_DRUG_API_URL
                search_field = (
                    "openfda.brand_name" if search_type == "brand" else "openfda.generic_name"
                )

            # Build parameters
            params: dict[str, str | int] = {
                "search": f"{search_field}:{drug_name}",
                "limit": max_results,
            }

            response = await client.get(url, params=params)
            response.raise_for_status()

            data = response.json()

            # Extract results
            results = data.get("results", [])
            products = []

            if search_type == "device":
                for item in results:
                    products.append(
                        {
                            "device_name": item.get("device_name"),
                            "device_class": item.get("device_class"),
                            "medical_specialty": item.get("medical_specialty_description"),
                        }
                    )
            else:
                for item in results:
                    openfda = item.get("openfda", {})
                    products.append(
                        {
                            "brand_name": openfda.get("brand_name", [""])[0]
                            if openfda.get("brand_name")
                            else None,
                            "generic_name": openfda.get("generic_name", [""])[0]
                            if openfda.get("generic_name")
                            else None,
                            "manufacturer": openfda.get("manufacturer_name", [""])[0]
                            if openfda.get("manufacturer_name")
                            else None,
                            "purpose": item.get("purpose", []),
                        }
                    )

            result = {
                "query": drug_name,
                "search_type": search_type,
                "total": data.get("meta", {}).get("total", 0),
                "products": products,
            }

            # Cache result
            self._research_cache[cache_key] = result

            logger.info(
                f"FDA search found {result['total']} {search_type} results for: {drug_name}",
            )

            return result

        except httpx.HTTPStatusError as e:
            logger.error(f"FDA API error: {e}")
            return {"error": str(e), "products": [], "total": 0}
        except Exception as e:
            logger.error(f"FDA search failed: {e}")
            return {"error": str(e), "products": [], "total": 0}

    async def _chembl_search(
        self,
        query: str,
        search_type: str = "molecule",
        max_results: int = 20,
    ) -> dict[str, Any]:
        """Search ChEMBL database for bioactive molecules.

        Args:
            query: Search query string (molecule name, target, etc.).
            search_type: Type of search - "molecule", "target", or "drug".
            max_results: Maximum number of results to return.

        Returns:
            Dictionary with total_count and list of molecules/targets.
        """
        # Check cache
        cache_key = f"chembl:{query}:{search_type}:{max_results}"
        if cache_key in self._research_cache:
            logger.info(f"ChEMBL cache hit for: {query}")
            return cast(dict[str, Any], self._research_cache[cache_key])

        try:
            client = await self._get_http_client()

            # Determine endpoint
            if search_type == "target":
                endpoint = f"{CHEMBL_API_URL}/target"
            elif search_type == "drug":
                endpoint = f"{CHEMBL_API_URL}/drug"
            else:  # molecule
                endpoint = f"{CHEMBL_API_URL}/molecule"

            # Build parameters - JSON format
            params: dict[str, str | int] = {
                "format": "json",
                "q": query,
                "limit": max_results,
            }

            response = await client.get(endpoint, params=params)
            response.raise_for_status()

            data = response.json()

            # Extract results - ChEMBL API returns various formats
            molecules = data.get("molecules", {})
            if isinstance(molecules, dict):
                molecule_list = molecules.get("molecule", [])
            else:
                molecule_list = molecules if isinstance(molecules, list) else []

            results = []
            for item in molecule_list[:max_results]:
                results.append(
                    {
                        "molecule_chembl_id": item.get("molecule_chembl_id"),
                        "pref_name": item.get("pref_name"),
                        "molecule_type": item.get("molecule_type"),
                        "max_phase": item.get("max_phase"),
                        "therapeutic_area": item.get("therapeutic_area"),
                    }
                )

            # Get total count from page_meta if available
            page_meta = data.get("page_meta", {})
            total_count = page_meta.get("total_count", len(results))

            result = {
                "query": query,
                "search_type": search_type,
                "total_count": total_count,
                "molecules": results,
            }

            # Cache result
            self._research_cache[cache_key] = result

            logger.info(
                f"ChEMBL search found {result['total_count']} molecules for: {query}",
            )

            return result

        except httpx.HTTPStatusError as e:
            logger.error(f"ChEMBL API error: {e}")
            return {"error": str(e), "molecules": [], "total_count": 0}
        except Exception as e:
            logger.error(f"ChEMBL search failed: {e}")
            return {"error": str(e), "molecules": [], "total_count": 0}

    async def _web_research(
        self,
        query: str,
        depth: str = "standard",
        max_results: int = 10,
    ) -> dict[str, Any]:
        """Perform web research using Exa for competitive analysis and general intel.

        Uses Exa's research endpoint for comprehensive depth or fast search
        for standard depth. Useful for battle card generation and competitive
        intelligence.

        Args:
            query: Research query string.
            depth: "standard" for fast search, "comprehensive" for deep research.
            max_results: Maximum number of results to return.

        Returns:
            Dictionary with query, results, and summary.
        """
        logger.info(f"Web research for: {query} (depth={depth})")

        exa = self._get_exa_provider()
        if not exa:
            logger.warning("ExaEnrichmentProvider not available for web research")
            return {"error": "Exa provider not available", "results": []}

        try:
            if depth == "comprehensive":
                results = await exa.research(query=query)
            else:
                results = await exa.search_fast(query=query, num_results=max_results)

            formatted_results = [
                {
                    "title": r.title,
                    "url": r.url,
                    "snippet": (r.text or "")[:500],
                    "published_date": r.published_date,
                    "score": r.score,
                }
                for r in results[:max_results]
            ]

            # Generate a brief summary of findings
            if formatted_results:
                summary_text = "\n".join([
                    f"- {r['title']}: {r['snippet'][:200]}"
                    for r in formatted_results[:5]
                ])
            else:
                summary_text = "No results found."

            result = {
                "query": query,
                "depth": depth,
                "result_count": len(formatted_results),
                "results": formatted_results,
                "summary": summary_text,
                "source": "exa_research" if depth == "comprehensive" else "exa_search",
            }

            logger.info(
                f"Web research returned {len(formatted_results)} results for: {query}",
            )

            return result

        except Exception as e:
            logger.error(f"Web research failed: {e}")
            return {"error": str(e), "results": []}

    async def _answer_question(
        self,
        question: str,
    ) -> dict[str, Any]:
        """Get a direct factual answer to a question using Exa.

        Useful for competitive questions, market data, and factual queries
        that need up-to-date information.

        Args:
            question: The question to answer.

        Returns:
            Dictionary with question, answer, and source.
        """
        logger.info(f"Answering question: {question[:100]}")

        exa = self._get_exa_provider()
        if not exa:
            logger.warning("ExaEnrichmentProvider not available for answer")
            return {"error": "Exa provider not available", "answer": ""}

        try:
            answer = await exa.answer(question=question)

            result = {
                "question": question,
                "answer": answer,
                "source": "exa_answer",
                "confidence": 0.8 if answer else 0.0,
            }

            logger.info(
                f"Answer returned {len(answer)} chars for: {question[:50]}",
            )

            return result

        except Exception as e:
            logger.error(f"Answer question failed: {e}")
            return {"error": str(e), "answer": ""}
