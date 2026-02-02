"""AnalystAgent module for ARIA.

Provides scientific research capabilities using life sciences APIs
including PubMed, ClinicalTrials.gov, FDA, and ChEMBL.
"""

import asyncio
import logging
from typing import Any, cast

import httpx

from src.agents.base import BaseAgent

logger = logging.getLogger(__name__)

# PubMed API endpoints
PUBMED_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
PUBMED_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


class AnalystAgent(BaseAgent):
    """Scientific research agent for life sciences queries.

    The Analyst agent searches scientific databases to provide
    domain expertise, literature reviews, and data extraction
    from biomedical APIs.
    """

    name = "Analyst"
    description = "Scientific research agent for life sciences queries"

    # Rate limiting: PubMed allows 3 requests/second without API key
    _pubmed_rate_limit = 3
    _pubmem_last_call_time: float = 0.0

    def __init__(self, llm_client: Any, user_id: str) -> None:
        """Initialize the Analyst agent.

        Args:
            llm_client: LLM client for reasoning and generation.
            user_id: ID of the user this agent is working for.
        """
        self._research_cache: dict[str, Any] = {}
        self._http_client: httpx.AsyncClient | None = None
        super().__init__(llm_client=llm_client, user_id=user_id)

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
        }

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with timeout settings.

        Returns:
            Async HTTP client.
        """
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def execute(self, _task: dict[str, Any] | None = None) -> Any:
        """Execute the analyst agent's primary task.

        Args:
            task: Task specification with parameters.

        Returns:
            AgentResult with success status and output data.
        """
        from src.agents.base import AgentResult

        return AgentResult(success=True, data={})

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

    async def _clinical_trials_search(self, query: str, max_results: int = 20) -> dict[str, Any]:
        """Search ClinicalTrials.gov for studies matching the query.

        Args:
            query: Search query string.
            max_results: Maximum number of results to return.

        Returns:
            Dictionary with search results.
        """
        raise NotImplementedError("ClinicalTrials search will be implemented in Task 6")

    async def _fda_drug_search(self, drug_name: str, search_type: str = "brand") -> dict[str, Any]:
        """Search OpenFDA API for drug or device information.

        Args:
            drug_name: Name of the drug or device to search.
            search_type: Type of search - "brand", "generic", or "device".

        Returns:
            Dictionary with search results.
        """
        raise NotImplementedError("FDA search will be implemented in Task 7")

    async def _chembl_search(self, query: str, max_results: int = 20) -> dict[str, Any]:
        """Search ChEMBL database for bioactive molecules.

        Args:
            query: Search query string.
            max_results: Maximum number of results to return.

        Returns:
            Dictionary with search results.
        """
        raise NotImplementedError("ChEMBL search will be implemented in Task 8")
