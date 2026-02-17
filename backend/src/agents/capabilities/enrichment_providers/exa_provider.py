"""Exa API enrichment provider.

Uses the Exa search API (https://exa.ai) for people search, company
intelligence, and publication discovery. Exa provides semantic search
over the web with structured content extraction — ideal for finding
LinkedIn profiles, bios, press mentions, and scientific publications.

Rate limited to 100 req/min via a sliding-window token bucket.

Search endpoints (Feb 2026):
- search_instant: Sub-200ms for real-time chat
- search_fast: <350ms for interactive workflows
- search_deep: ~3.5s for highest quality
- search_news: News with date filtering
- find_similar: Find similar pages (competitors)
- answer: Direct factual answer
- research: Deep agentic research
- get_contents: Get full page contents

Websets endpoints (Phase 3):
- create_webset: Create bulk entity discovery job
- get_webset: Get Webset status
- list_webset_items: List discovered entities
- create_enrichment: Add enrichment task to Webset
- register_webhook: Register webhook for Webset events
"""

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel

from src.agents.capabilities.enrichment_providers.base import (
    BaseEnrichmentProvider,
    CompanyEnrichment,
    PersonEnrichment,
    PublicationResult,
)
from src.core.config import settings
from src.core.resilience import exa_circuit_breaker

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result Models
# ---------------------------------------------------------------------------


class ExaSearchResult(BaseModel):
    """Standardized result from Exa search endpoints."""

    url: str
    title: str = ""
    text: str = ""
    published_date: str | None = None
    author: str | None = None
    score: float = 0.0


# ---------------------------------------------------------------------------
# Rate limiter (sliding window, 100 req/min)
# ---------------------------------------------------------------------------

_request_timestamps: list[float] = []
_rate_lock = asyncio.Lock()
_MAX_REQUESTS_PER_MINUTE = 100


async def _wait_for_rate_limit() -> None:
    """Block until a request slot is available within the rate window."""
    async with _rate_lock:
        now = time.monotonic()
        # Prune timestamps older than 60s
        while _request_timestamps and _request_timestamps[0] < now - 60:
            _request_timestamps.pop(0)

        if len(_request_timestamps) >= _MAX_REQUESTS_PER_MINUTE:
            # Wait until the oldest request expires
            wait_time = 60 - (now - _request_timestamps[0])
            if wait_time > 0:
                logger.debug("Exa rate limit: waiting %.1fs", wait_time)
                await asyncio.sleep(wait_time)

        _request_timestamps.append(time.monotonic())


# ---------------------------------------------------------------------------
# Provider implementation
# ---------------------------------------------------------------------------


class ExaEnrichmentProvider(BaseEnrichmentProvider):
    """Exa API enrichment provider.

    Provides people search, company intelligence, and publication
    discovery using Exa's semantic web search with content extraction.
    """

    provider_name: str = "exa"

    def __init__(self) -> None:
        self._api_key = settings.EXA_API_KEY
        self._base_url = "https://api.exa.ai"

        if not self._api_key:
            logger.warning(
                "ExaEnrichmentProvider initialized WITHOUT API key - all searches will return empty"
            )
        else:
            logger.info("ExaEnrichmentProvider initialized with API key")

    def _get_headers(self) -> dict[str, str]:
        """Build request headers with API key."""
        return {
            "x-api-key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ── People Search ─────────────────────────────────────────────────

    async def search_person(
        self,
        name: str,
        company: str = "",
        role: str = "",
    ) -> PersonEnrichment:
        """Search for a person via Exa and extract profile intelligence.

        Performs multiple targeted searches:
        1. LinkedIn profile search
        2. General web mentions
        3. Bio/about page search

        Args:
            name: Full name of the person.
            company: Company name for disambiguation.
            role: Role/title for disambiguation.

        Returns:
            PersonEnrichment with merged results from all searches.
        """
        import httpx

        enrichment = PersonEnrichment(
            provider=self.provider_name,
            name=name,
            company=company,
            title=role,
            enriched_at=datetime.now(UTC),
        )

        if not self._api_key:
            logger.warning("EXA_API_KEY not configured; skipping person search")
            return enrichment

        # Build search queries
        base_query = f"{name}"
        if company:
            base_query += f" {company}"
        if role:
            base_query += f" {role}"

        async with httpx.AsyncClient(
            timeout=30.0,
            headers=self._get_headers(),
        ) as client:
            # Search 1: LinkedIn profile
            linkedin_results = await self._exa_search(
                client,
                query=f"{name} {company} LinkedIn profile",
                num_results=3,
                include_domains=["linkedin.com"],
                use_autoprompt=True,
            )
            for result in linkedin_results:
                url = result.get("url", "")
                if "linkedin.com/in/" in url:
                    enrichment.linkedin_url = url
                    enrichment.social_profiles["linkedin"] = url
                    # Extract text content if available
                    text = result.get("text", "")
                    if text and not enrichment.bio:
                        enrichment.bio = text[:1000]
                    break

            # Search 2: Web mentions (news, press, bios)
            mention_results = await self._exa_search(
                client,
                query=base_query,
                num_results=10,
                exclude_domains=["linkedin.com"],
                use_autoprompt=True,
            )
            for result in mention_results:
                enrichment.web_mentions.append(
                    {
                        "title": result.get("title", ""),
                        "url": result.get("url", ""),
                        "snippet": (result.get("text", "") or "")[:500],
                        "published_date": result.get("publishedDate", ""),
                        "source": result.get("url", "").split("/")[2]
                        if len(result.get("url", "").split("/")) > 2
                        else "",
                    }
                )

            # Search 3: Bio / about page
            bio_results = await self._exa_search(
                client,
                query=f"{name} bio about background {company}",
                num_results=3,
                use_autoprompt=True,
            )
            for result in bio_results:
                text = result.get("text", "")
                if text and len(text) > len(enrichment.bio):
                    enrichment.bio = text[:2000]
                    break

        # Calculate confidence based on data completeness
        filled_fields = sum(
            1
            for v in [
                enrichment.linkedin_url,
                enrichment.bio,
                enrichment.web_mentions,
            ]
            if v
        )
        enrichment.confidence = min(0.90, 0.50 + (filled_fields * 0.15))

        return enrichment

    # ── Company Search ────────────────────────────────────────────────

    async def search_company(
        self,
        company_name: str,
    ) -> CompanyEnrichment:
        """Search for a company via Exa for news, funding, leadership.

        Performs targeted searches for:
        1. Company overview / about page
        2. Recent news and press releases
        3. Funding and financial information
        4. Leadership / team pages

        Args:
            company_name: Company name to search for.

        Returns:
            CompanyEnrichment with merged results.
        """
        import httpx

        enrichment = CompanyEnrichment(
            provider=self.provider_name,
            name=company_name,
            enriched_at=datetime.now(UTC),
        )

        if not self._api_key:
            logger.warning("EXA_API_KEY not configured; skipping company search")
            return enrichment

        async with httpx.AsyncClient(
            timeout=30.0,
            headers=self._get_headers(),
        ) as client:
            # Search 1: Company overview
            overview_results = await self._exa_search(
                client,
                query=f"{company_name} company overview about",
                num_results=5,
                use_autoprompt=True,
            )
            for result in overview_results:
                text = result.get("text", "")
                url = result.get("url", "")
                if text and not enrichment.description:
                    enrichment.description = text[:2000]
                if url and not enrichment.domain:
                    parts = url.split("/")
                    if len(parts) > 2:
                        enrichment.domain = parts[2]

            # Search 2: Recent news
            news_results = await self._exa_search(
                client,
                query=f"{company_name} news announcement",
                num_results=10,
                use_autoprompt=True,
            )
            for result in news_results:
                enrichment.recent_news.append(
                    {
                        "title": result.get("title", ""),
                        "url": result.get("url", ""),
                        "snippet": (result.get("text", "") or "")[:500],
                        "published_date": result.get("publishedDate", ""),
                    }
                )

            # Search 3: Funding
            funding_results = await self._exa_search(
                client,
                query=f"{company_name} funding series round investment",
                num_results=5,
                use_autoprompt=True,
            )
            for result in funding_results:
                text = result.get("text", "")
                if text:
                    enrichment.raw_data["funding_mentions"] = enrichment.raw_data.get(
                        "funding_mentions", []
                    )
                    enrichment.raw_data["funding_mentions"].append(
                        {
                            "title": result.get("title", ""),
                            "text": text[:500],
                            "url": result.get("url", ""),
                        }
                    )
                    # Extract funding info from first result
                    if not enrichment.latest_funding_round:
                        enrichment.latest_funding_round = result.get("title", "")[:200]
                    break

            # Search 4: Leadership / team
            team_results = await self._exa_search(
                client,
                query=f"{company_name} leadership team CEO executives",
                num_results=5,
                use_autoprompt=True,
            )
            for result in team_results:
                text = result.get("text", "")
                if text:
                    enrichment.raw_data["leadership_mentions"] = enrichment.raw_data.get(
                        "leadership_mentions", []
                    )
                    enrichment.raw_data["leadership_mentions"].append(
                        {
                            "title": result.get("title", ""),
                            "text": text[:500],
                            "url": result.get("url", ""),
                        }
                    )

        # Confidence based on data completeness
        filled = sum(
            1
            for v in [
                enrichment.description,
                enrichment.recent_news,
                enrichment.domain,
                enrichment.latest_funding_round,
            ]
            if v
        )
        enrichment.confidence = min(0.85, 0.40 + (filled * 0.12))

        return enrichment

    # ── Publication Search ────────────────────────────────────────────

    async def search_publications(
        self,
        person_name: str,
        therapeutic_area: str = "",
    ) -> list[PublicationResult]:
        """Search for publications and patents via Exa.

        Targets PubMed, Google Scholar, and patent databases.

        Args:
            person_name: Author name to search for.
            therapeutic_area: Optional therapeutic area filter.

        Returns:
            List of PublicationResult objects.
        """
        import httpx

        publications: list[PublicationResult] = []

        if not self._api_key:
            logger.warning("EXA_API_KEY not configured; skipping publication search")
            return publications

        query = f"{person_name} publication research paper"
        if therapeutic_area:
            query += f" {therapeutic_area}"

        async with httpx.AsyncClient(
            timeout=30.0,
            headers=self._get_headers(),
        ) as client:
            # Search academic sources
            results = await self._exa_search(
                client,
                query=query,
                num_results=15,
                include_domains=[
                    "pubmed.ncbi.nlm.nih.gov",
                    "scholar.google.com",
                    "ncbi.nlm.nih.gov",
                    "nature.com",
                    "sciencedirect.com",
                    "patents.google.com",
                ],
                use_autoprompt=True,
            )

            for result in results:
                pub = PublicationResult(
                    title=result.get("title", ""),
                    url=result.get("url", ""),
                    abstract=(result.get("text", "") or "")[:1000],
                    published_date=result.get("publishedDate", ""),
                    source=result.get("url", "").split("/")[2]
                    if len(result.get("url", "").split("/")) > 2
                    else "",
                    relevance_score=result.get("score", 0.0),
                )
                # Try to extract authors from text
                text = result.get("text", "")
                if person_name.lower() in text.lower():
                    pub.authors = [person_name]
                publications.append(pub)

            # Also search patents specifically
            patent_query = f"{person_name} patent"
            if therapeutic_area:
                patent_query += f" {therapeutic_area}"

            patent_results = await self._exa_search(
                client,
                query=patent_query,
                num_results=5,
                include_domains=["patents.google.com", "patentscope.wipo.int"],
                use_autoprompt=True,
            )

            for result in patent_results:
                pub = PublicationResult(
                    title=result.get("title", ""),
                    url=result.get("url", ""),
                    abstract=(result.get("text", "") or "")[:1000],
                    published_date=result.get("publishedDate", ""),
                    source="patent",
                    relevance_score=result.get("score", 0.0),
                )
                if person_name.lower() in (result.get("text", "") or "").lower():
                    pub.authors = [person_name]
                publications.append(pub)

        return publications

    # ── Health Check ──────────────────────────────────────────────────

    async def health_check(self) -> bool:
        """Verify Exa API connectivity.

        Returns:
            True if the API responds to a minimal search.
        """
        import httpx

        if not self._api_key:
            return False

        try:
            async with httpx.AsyncClient(
                timeout=10.0,
                headers=self._get_headers(),
            ) as client:
                resp = await client.post(
                    f"{self._base_url}/search",
                    json={
                        "query": "test",
                        "numResults": 1,
                        "useAutoprompt": False,
                    },
                )
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    # ── New Exa Endpoints (Feb 2026) ────────────────────────────────────

    async def search_instant(
        self,
        query: str,
        num_results: int = 5,
    ) -> list[ExaSearchResult]:
        """Sub-200ms search for real-time chat interactions.

        Args:
            query: Search query string.
            num_results: Number of results to request.

        Returns:
            List of ExaSearchResult objects.
        """
        logger.info("Exa search_instant: query='%s'", query[:100])

        if not self._api_key:
            logger.warning("EXA_API_KEY not configured; skipping instant search")
            return []

        try:
            exa_circuit_breaker.check()
        except Exception:
            logger.warning("Exa circuit breaker open — skipping instant search")
            return []

        try:
            async with httpx.AsyncClient(
                timeout=5.0,
                headers=self._get_headers(),
            ) as client:
                resp = await client.post(
                    f"{self._base_url}/search",
                    json={
                        "query": query,
                        "numResults": num_results,
                        "type": "auto",
                        "contents": {"text": {"maxCharacters": 1000}},
                    },
                )
                if resp.status_code != 200:
                    logger.error(
                        "Exa search_instant failed: status=%d query='%s'",
                        resp.status_code,
                        query[:100],
                    )
                    if resp.status_code >= 500:
                        exa_circuit_breaker.record_failure()
                    return []

                data = resp.json()
                results = [
                    ExaSearchResult(
                        url=r.get("url", ""),
                        title=r.get("title", ""),
                        text=r.get("text", ""),
                        published_date=r.get("publishedDate"),
                        score=r.get("score", 0.0),
                    )
                    for r in data.get("results", [])
                ]
                exa_circuit_breaker.record_success()
                logger.info("Exa search_instant: returned %d results", len(results))
                return results

        except Exception as e:
            exa_circuit_breaker.record_failure()
            logger.error(
                "Exa search_instant exception: query='%s' error='%s'",
                query[:100],
                str(e),
                exc_info=True,
            )
            return []

    async def search_fast(
        self,
        query: str,
        num_results: int = 10,
        *,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> list[ExaSearchResult]:
        """Fast search (<350ms) for interactive workflows.

        Args:
            query: Search query string.
            num_results: Number of results to request.
            include_domains: Only return results from these domains.
            exclude_domains: Exclude results from these domains.

        Returns:
            List of ExaSearchResult objects.
        """
        logger.info("Exa search_fast: query='%s'", query[:100])

        if not self._api_key:
            logger.warning("EXA_API_KEY not configured; skipping fast search")
            return []

        try:
            exa_circuit_breaker.check()
        except Exception:
            logger.warning("Exa circuit breaker open — skipping fast search")
            return []

        try:
            payload: dict[str, Any] = {
                "query": query,
                "numResults": num_results,
                "type": "auto",
                "contents": {"text": {"maxCharacters": 2000}},
            }
            if include_domains:
                payload["includeDomains"] = include_domains
            if exclude_domains:
                payload["excludeDomains"] = exclude_domains

            async with httpx.AsyncClient(
                timeout=10.0,
                headers=self._get_headers(),
            ) as client:
                resp = await client.post(f"{self._base_url}/search", json=payload)
                if resp.status_code != 200:
                    logger.error(
                        "Exa search_fast failed: status=%d query='%s'",
                        resp.status_code,
                        query[:100],
                    )
                    if resp.status_code >= 500:
                        exa_circuit_breaker.record_failure()
                    return []

                data = resp.json()
                results = [
                    ExaSearchResult(
                        url=r.get("url", ""),
                        title=r.get("title", ""),
                        text=r.get("text", ""),
                        published_date=r.get("publishedDate"),
                        score=r.get("score", 0.0),
                    )
                    for r in data.get("results", [])
                ]
                exa_circuit_breaker.record_success()
                logger.info("Exa search_fast: returned %d results", len(results))
                return results

        except Exception as e:
            exa_circuit_breaker.record_failure()
            logger.error(
                "Exa search_fast exception: query='%s' error='%s'",
                query[:100],
                str(e),
                exc_info=True,
            )
            return []

    async def search_deep(
        self,
        query: str,
        num_results: int = 10,
        *,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> list[ExaSearchResult]:
        """Deep search (~3.5s) for highest quality results.

        Uses Exa's deep search mode for comprehensive research.

        Args:
            query: Search query string.
            num_results: Number of results to request.
            include_domains: Only return results from these domains.
            exclude_domains: Exclude results from these domains.

        Returns:
            List of ExaSearchResult objects.
        """
        logger.info("Exa search_deep: query='%s'", query[:100])

        if not self._api_key:
            logger.warning("EXA_API_KEY not configured; skipping deep search")
            return []

        try:
            exa_circuit_breaker.check()
        except Exception:
            logger.warning("Exa circuit breaker open — skipping deep search")
            return []

        try:
            payload: dict[str, Any] = {
                "query": query,
                "numResults": num_results,
                "type": "neural",
                "useAutoprompt": True,
                "contents": {"text": {"maxCharacters": 3000}},
            }
            if include_domains:
                payload["includeDomains"] = include_domains
            if exclude_domains:
                payload["excludeDomains"] = exclude_domains

            async with httpx.AsyncClient(
                timeout=30.0,
                headers=self._get_headers(),
            ) as client:
                resp = await client.post(f"{self._base_url}/search", json=payload)
                if resp.status_code != 200:
                    logger.error(
                        "Exa search_deep failed: status=%d query='%s'",
                        resp.status_code,
                        query[:100],
                    )
                    if resp.status_code >= 500:
                        exa_circuit_breaker.record_failure()
                    return []

                data = resp.json()
                results = [
                    ExaSearchResult(
                        url=r.get("url", ""),
                        title=r.get("title", ""),
                        text=r.get("text", ""),
                        published_date=r.get("publishedDate"),
                        author=r.get("author"),
                        score=r.get("score", 0.0),
                    )
                    for r in data.get("results", [])
                ]
                exa_circuit_breaker.record_success()
                logger.info("Exa search_deep: returned %d results", len(results))
                return results

        except Exception as e:
            exa_circuit_breaker.record_failure()
            logger.error(
                "Exa search_deep exception: query='%s' error='%s'",
                query[:100],
                str(e),
                exc_info=True,
            )
            return []

    async def search_news(
        self,
        query: str,
        num_results: int = 10,
        *,
        days_back: int = 30,
    ) -> list[ExaSearchResult]:
        """Search for recent news with date filtering.

        Args:
            query: Search query string.
            num_results: Number of results to request.
            days_back: Only return news from the last N days.

        Returns:
            List of ExaSearchResult objects.
        """
        logger.info(
            "Exa search_news: query='%s' days_back=%d",
            query[:100],
            days_back,
        )

        if not self._api_key:
            logger.warning("EXA_API_KEY not configured; skipping news search")
            return []

        try:
            # Calculate start date filter
            from datetime import timedelta

            start_date = (datetime.now(UTC) - timedelta(days=days_back)).strftime("%Y-%m-%d")

            async with httpx.AsyncClient(
                timeout=20.0,
                headers=self._get_headers(),
            ) as client:
                resp = await client.post(
                    f"{self._base_url}/search",
                    json={
                        "query": query,
                        "numResults": num_results,
                        "type": "neural",
                        "useAutoprompt": True,
                        "startPublishedDate": start_date,
                        "contents": {"text": {"maxCharacters": 2000}},
                    },
                )
                if resp.status_code != 200:
                    logger.error(
                        "Exa search_news failed: status=%d query='%s'",
                        resp.status_code,
                        query[:100],
                    )
                    return []

                data = resp.json()
                results = [
                    ExaSearchResult(
                        url=r.get("url", ""),
                        title=r.get("title", ""),
                        text=r.get("text", ""),
                        published_date=r.get("publishedDate"),
                        author=r.get("author"),
                        score=r.get("score", 0.0),
                    )
                    for r in data.get("results", [])
                ]
                logger.info("Exa search_news: returned %d results", len(results))
                return results

        except Exception as e:
            logger.error(
                "Exa search_news exception: query='%s' error='%s'",
                query[:100],
                str(e),
                exc_info=True,
            )
            return []

    async def find_similar(
        self,
        url: str,
        num_results: int = 10,
        *,
        exclude_domains: list[str] | None = None,
    ) -> list[ExaSearchResult]:
        """Find similar pages to a given URL (competitor discovery).

        Args:
            url: The URL to find similar pages for.
            num_results: Number of results to request.
            exclude_domains: Domains to exclude (e.g., the original domain).

        Returns:
            List of ExaSearchResult objects for similar pages.
        """
        logger.info("Exa find_similar: url='%s'", url[:100])

        if not self._api_key:
            logger.warning("EXA_API_KEY not configured; skipping find_similar")
            return []

        try:
            payload: dict[str, Any] = {
                "url": url,
                "numResults": num_results,
                "contents": {"text": {"maxCharacters": 2000}},
            }
            if exclude_domains:
                payload["excludeDomains"] = exclude_domains

            async with httpx.AsyncClient(
                timeout=20.0,
                headers=self._get_headers(),
            ) as client:
                resp = await client.post(
                    f"{self._base_url}/findSimilar",
                    json=payload,
                )
                if resp.status_code != 200:
                    logger.error(
                        "Exa find_similar failed: status=%d url='%s'",
                        resp.status_code,
                        url[:100],
                    )
                    return []

                data = resp.json()
                results = [
                    ExaSearchResult(
                        url=r.get("url", ""),
                        title=r.get("title", ""),
                        text=r.get("text", ""),
                        published_date=r.get("publishedDate"),
                        score=r.get("score", 0.0),
                    )
                    for r in data.get("results", [])
                ]
                logger.info("Exa find_similar: returned %d results", len(results))
                return results

        except Exception as e:
            logger.error(
                "Exa find_similar exception: url='%s' error='%s'",
                url[:100],
                str(e),
                exc_info=True,
            )
            return []

    async def answer(
        self,
        question: str,
    ) -> str:
        """Get a direct factual answer to a question.

        Args:
            question: The question to answer.

        Returns:
            The answer string, or empty string on failure.
        """
        logger.info("Exa answer: question='%s'", question[:100])

        if not self._api_key:
            logger.warning("EXA_API_KEY not configured; skipping answer")
            return ""

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers=self._get_headers(),
            ) as client:
                resp = await client.post(
                    f"{self._base_url}/answer",
                    json={
                        "query": question,
                        "text": True,
                    },
                )
                if resp.status_code != 200:
                    logger.error(
                        "Exa answer failed: status=%d question='%s'",
                        resp.status_code,
                        question[:100],
                    )
                    return ""

                data = resp.json()
                answer_text = data.get("answer", "")
                logger.info(
                    "Exa answer: returned %d chars",
                    len(answer_text),
                )
                return answer_text

        except Exception as e:
            logger.error(
                "Exa answer exception: question='%s' error='%s'",
                question[:100],
                str(e),
                exc_info=True,
            )
            return ""

    async def research(
        self,
        query: str,
    ) -> list[ExaSearchResult]:
        """Deep agentic research (polling-based, up to 60s).

        Note: This uses the /research endpoint which may require polling.
        Falls back to deep search if research endpoint is unavailable.

        Args:
            query: Research query string.

        Returns:
            List of ExaSearchResult objects.
        """
        logger.info("Exa research: query='%s'", query[:100])

        if not self._api_key:
            logger.warning("EXA_API_KEY not configured; skipping research")
            return []

        try:
            async with httpx.AsyncClient(
                timeout=60.0,
                headers=self._get_headers(),
            ) as client:
                # Try the research endpoint
                resp = await client.post(
                    f"{self._base_url}/research",
                    json={
                        "query": query,
                        "numResults": 15,
                    },
                )

                # If research endpoint not available, fall back to deep search
                if resp.status_code == 404:
                    logger.info("Exa research endpoint not available, falling back to deep search")
                    return await self.search_deep(query, num_results=15)

                if resp.status_code != 200:
                    logger.error(
                        "Exa research failed: status=%d query='%s'",
                        resp.status_code,
                        query[:100],
                    )
                    return []

                data = resp.json()
                results = [
                    ExaSearchResult(
                        url=r.get("url", ""),
                        title=r.get("title", ""),
                        text=r.get("text", ""),
                        published_date=r.get("publishedDate"),
                        author=r.get("author"),
                        score=r.get("score", 0.0),
                    )
                    for r in data.get("results", [])
                ]
                logger.info("Exa research: returned %d results", len(results))
                return results

        except Exception as e:
            logger.error(
                "Exa research exception: query='%s' error='%s'",
                query[:100],
                str(e),
                exc_info=True,
            )
            return []

    async def get_contents(
        self,
        urls: list[str],
    ) -> list[ExaSearchResult]:
        """Get full page contents for a list of URLs.

        Args:
            urls: List of URLs to fetch contents for.

        Returns:
            List of ExaSearchResult objects with full text content.
        """
        logger.info("Exa get_contents: %d urls", len(urls))

        if not self._api_key:
            logger.warning("EXA_API_KEY not configured; skipping get_contents")
            return []

        if not urls:
            return []

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers=self._get_headers(),
            ) as client:
                resp = await client.post(
                    f"{self._base_url}/contents",
                    json={
                        "urls": urls,
                        "text": True,
                    },
                )
                if resp.status_code != 200:
                    logger.error(
                        "Exa get_contents failed: status=%d",
                        resp.status_code,
                    )
                    return []

                data = resp.json()
                results = [
                    ExaSearchResult(
                        url=r.get("url", ""),
                        title=r.get("title", ""),
                        text=r.get("text", ""),
                        published_date=r.get("publishedDate"),
                    )
                    for r in data.get("results", [])
                ]
                logger.info("Exa get_contents: returned %d results", len(results))
                return results

        except Exception as e:
            logger.error(
                "Exa get_contents exception: error='%s'",
                str(e),
                exc_info=True,
            )
            return []

    # ── Private helpers ───────────────────────────────────────────────

    async def _exa_search(
        self,
        client: Any,
        query: str,
        num_results: int = 10,
        *,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        use_autoprompt: bool = True,
        search_type: str = "auto",
    ) -> list[dict[str, Any]]:
        """Execute an Exa search with rate limiting and content extraction.

        Uses the ``/search`` endpoint with ``contents`` requested to get
        text snippets alongside URLs.

        Args:
            client: httpx.AsyncClient instance.
            query: Search query string.
            num_results: Number of results to request.
            include_domains: Only return results from these domains.
            exclude_domains: Exclude results from these domains.
            use_autoprompt: Let Exa optimise the query.
            search_type: Search type for logging (auto, neural, keyword).

        Returns:
            List of result dicts from the Exa response.
        """
        # Early return if no API key - log explicitly
        if not self._api_key:
            logger.warning(
                "EXA_API_KEY not configured; skipping search for query='%s'",
                query[:100],
            )
            return []

        # Log BEFORE call for diagnostics
        logger.info(
            "EXA: Calling search with query='%s', type=%s, num_results=%d",
            query[:100],
            search_type,
            num_results,
        )

        await _wait_for_rate_limit()

        payload: dict[str, Any] = {
            "query": query,
            "numResults": num_results,
            "useAutoprompt": use_autoprompt,
            "contents": {
                "text": {"maxCharacters": 2000},
            },
        }

        if include_domains:
            payload["includeDomains"] = include_domains
        if exclude_domains:
            payload["excludeDomains"] = exclude_domains

        try:
            exa_circuit_breaker.check()
        except Exception:
            logger.warning("Exa circuit breaker open — skipping search for '%s'", query[:100])
            return []

        try:
            resp = await client.post(
                f"{self._base_url}/search",
                json=payload,
            )
            if resp.status_code != 200:
                logger.error(
                    "EXA: Search failed with status=%d query='%s' response='%s'",
                    resp.status_code,
                    query[:100],
                    resp.text[:200],
                )
                if resp.status_code >= 500:
                    exa_circuit_breaker.record_failure()
                return []

            data = resp.json()
            results = data.get("results", [])

            exa_circuit_breaker.record_success()
            # Log AFTER success with result count
            logger.info(
                "EXA: Got %d results for query='%s'",
                len(results),
                query[:100],
            )
            return results

        except Exception as exc:
            exa_circuit_breaker.record_failure()
            # Log ERRORS with full context
            logger.error(
                "EXA: Exception for query='%s' error='%s'",
                query[:100],
                str(exc),
                exc_info=True,
            )
            return []

    # ── Websets API (Phase 3) ─────────────────────────────────────────────

    async def create_webset(
        self,
        search_query: str,
        entity_type: str = "company",
        external_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new Webset for bulk entity discovery.

        Websets are asynchronous bulk discovery jobs that find companies
        or people matching a query. Results are retrieved via polling
        or webhooks.

        Args:
            search_query: Natural language query for entity discovery.
            entity_type: Type of entity to find ('company' or 'person').
            external_id: Optional external ID to link to goal_id.

        Returns:
            Dict with Webset ID and status information.
        """
        logger.info(
            "Exa create_webset: query='%s' entity_type=%s",
            search_query[:100],
            entity_type,
        )

        if not self._api_key:
            logger.warning("EXA_API_KEY not configured; skipping webset creation")
            return {"id": "", "status": "failed", "error": "API key not configured"}

        await _wait_for_rate_limit()

        try:
            payload: dict[str, Any] = {
                "search": {
                    "query": search_query,
                    "entityType": entity_type,
                },
            }
            if external_id:
                payload["externalId"] = external_id

            async with httpx.AsyncClient(
                timeout=30.0,
                headers=self._get_headers(),
            ) as client:
                resp = await client.post(
                    f"{self._base_url}/websets/v0/websets",
                    json=payload,
                )
                if resp.status_code not in (200, 201):
                    logger.error(
                        "Exa create_webset failed: status=%d query='%s'",
                        resp.status_code,
                        search_query[:100],
                    )
                    return {
                        "id": "",
                        "status": "failed",
                        "error": f"API returned {resp.status_code}",
                    }

                data = resp.json()
                webset_id = data.get("id", "")
                status = data.get("status", "pending")
                items_count = data.get("itemsCount", 0)

                logger.info(
                    "Exa create_webset: created webset_id=%s status=%s",
                    webset_id,
                    status,
                )

                return {
                    "id": webset_id,
                    "status": status,
                    "items_count": items_count,
                    "created_at": data.get("createdAt"),
                }

        except Exception as e:
            logger.error(
                "Exa create_webset exception: query='%s' error='%s'",
                search_query[:100],
                str(e),
                exc_info=True,
            )
            return {"id": "", "status": "failed", "error": str(e)}

    async def get_webset(self, webset_id: str) -> dict[str, Any]:
        """Get Webset status and metadata.

        Args:
            webset_id: The Exa Webset ID.

        Returns:
            Dict with Webset status, item counts, and metadata.
        """
        logger.info("Exa get_webset: webset_id=%s", webset_id)

        if not self._api_key:
            logger.warning("EXA_API_KEY not configured; skipping webset get")
            return {"id": webset_id, "status": "unknown"}

        await _wait_for_rate_limit()

        try:
            async with httpx.AsyncClient(
                timeout=15.0,
                headers=self._get_headers(),
            ) as client:
                resp = await client.get(
                    f"{self._base_url}/websets/v0/websets/{webset_id}",
                )
                if resp.status_code != 200:
                    logger.error(
                        "Exa get_webset failed: status=%d webset_id=%s",
                        resp.status_code,
                        webset_id,
                    )
                    return {"id": webset_id, "status": "unknown"}

                data = resp.json()
                return {
                    "id": data.get("id", webset_id),
                    "status": data.get("status", "unknown"),
                    "items_count": data.get("itemsCount", 0),
                    "created_at": data.get("createdAt"),
                    "updated_at": data.get("updatedAt"),
                }

        except Exception as e:
            logger.error(
                "Exa get_webset exception: webset_id=%s error='%s'",
                webset_id,
                str(e),
                exc_info=True,
            )
            return {"id": webset_id, "status": "unknown", "error": str(e)}

    async def list_webset_items(
        self,
        webset_id: str,
        cursor: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """List items in a Webset with pagination.

        Args:
            webset_id: The Exa Webset ID.
            cursor: Pagination cursor for next page.
            limit: Maximum number of items to return.

        Returns:
            Dict with items list and pagination info.
        """
        logger.info(
            "Exa list_webset_items: webset_id=%s limit=%d",
            webset_id,
            limit,
        )

        if not self._api_key:
            logger.warning("EXA_API_KEY not configured; skipping webset items")
            return {"items": [], "next_cursor": None, "has_more": False}

        await _wait_for_rate_limit()

        try:
            params: dict[str, Any] = {"limit": limit}
            if cursor:
                params["cursor"] = cursor

            async with httpx.AsyncClient(
                timeout=30.0,
                headers=self._get_headers(),
            ) as client:
                resp = await client.get(
                    f"{self._base_url}/websets/v0/websets/{webset_id}/items",
                    params=params,
                )
                if resp.status_code != 200:
                    logger.error(
                        "Exa list_webset_items failed: status=%d webset_id=%s",
                        resp.status_code,
                        webset_id,
                    )
                    return {"items": [], "next_cursor": None, "has_more": False}

                data = resp.json()
                items = data.get("results", [])

                logger.info(
                    "Exa list_webset_items: returned %d items for webset_id=%s",
                    len(items),
                    webset_id,
                )

                return {
                    "items": items,
                    "next_cursor": data.get("nextCursor"),
                    "has_more": data.get("hasMore", False),
                }

        except Exception as e:
            logger.error(
                "Exa list_webset_items exception: webset_id=%s error='%s'",
                webset_id,
                str(e),
                exc_info=True,
            )
            return {"items": [], "next_cursor": None, "has_more": False}

    async def create_enrichment(
        self,
        webset_id: str,
        description: str,
        format: str = "text",
    ) -> dict[str, Any]:
        """Add enrichment task to process each Webset item.

        Enrichments run against each item in the Webset to extract
        additional data like contact info, funding, etc.

        Args:
            webset_id: The Exa Webset ID.
            description: Natural language description (1-5000 chars).
            format: Expected format ('text', 'email', 'phone', 'url', etc.).

        Returns:
            Dict with enrichment ID and status.
        """
        logger.info(
            "Exa create_enrichment: webset_id=%s format=%s",
            webset_id,
            format,
        )

        if not self._api_key:
            logger.warning("EXA_API_KEY not configured; skipping enrichment creation")
            return {"id": "", "status": "failed"}

        await _wait_for_rate_limit()

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers=self._get_headers(),
            ) as client:
                resp = await client.post(
                    f"{self._base_url}/websets/v0/websets/{webset_id}/enrichments",
                    json={
                        "description": description,
                        "format": format,
                    },
                )
                if resp.status_code not in (200, 201):
                    logger.error(
                        "Exa create_enrichment failed: status=%d webset_id=%s",
                        resp.status_code,
                        webset_id,
                    )
                    return {"id": "", "status": "failed"}

                data = resp.json()
                enrichment_id = data.get("id", "")

                logger.info(
                    "Exa create_enrichment: created enrichment_id=%s",
                    enrichment_id,
                )

                return {
                    "id": enrichment_id,
                    "webset_id": webset_id,
                    "status": data.get("status", "pending"),
                    "description": description,
                    "created_at": data.get("createdAt"),
                }

        except Exception as e:
            logger.error(
                "Exa create_enrichment exception: webset_id=%s error='%s'",
                webset_id,
                str(e),
                exc_info=True,
            )
            return {"id": "", "status": "failed", "error": str(e)}

    async def register_webhook(
        self,
        webhook_url: str,
        events: list[str] | None = None,
    ) -> dict[str, Any]:
        """Register webhook for Webset events.

        Webhooks provide real-time notifications when items are completed
        or when a Webset finishes processing.

        Args:
            webhook_url: URL to receive webhook POST requests.
            events: List of event types (default: webset.items.completed).

        Returns:
            Dict with webhook ID and secret for signature verification.
        """
        if events is None:
            events = ["webset.items.completed"]

        logger.info(
            "Exa register_webhook: url='%s' events=%s",
            webhook_url,
            events,
        )

        if not self._api_key:
            logger.warning("EXA_API_KEY not configured; skipping webhook registration")
            return {"id": "", "url": webhook_url, "secret": None}

        await _wait_for_rate_limit()

        try:
            async with httpx.AsyncClient(
                timeout=15.0,
                headers=self._get_headers(),
            ) as client:
                resp = await client.post(
                    f"{self._base_url}/websets/v0/webhooks",
                    json={
                        "url": webhook_url,
                        "events": events,
                    },
                )
                if resp.status_code not in (200, 201):
                    logger.error(
                        "Exa register_webhook failed: status=%d url='%s'",
                        resp.status_code,
                        webhook_url[:100],
                    )
                    return {"id": "", "url": webhook_url, "secret": None}

                data = resp.json()
                webhook_id = data.get("id", "")

                logger.info(
                    "Exa register_webhook: registered webhook_id=%s",
                    webhook_id,
                )

                return {
                    "id": webhook_id,
                    "url": webhook_url,
                    "events": events,
                    "secret": data.get("secret"),
                    "created_at": data.get("createdAt"),
                }

        except Exception as e:
            logger.error(
                "Exa register_webhook exception: url='%s' error='%s'",
                webhook_url[:100],
                str(e),
                exc_info=True,
            )
            return {"id": "", "url": webhook_url, "secret": None, "error": str(e)}
