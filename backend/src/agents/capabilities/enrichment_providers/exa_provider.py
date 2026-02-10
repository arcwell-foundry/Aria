"""Exa API enrichment provider.

Uses the Exa search API (https://exa.ai) for people search, company
intelligence, and publication discovery. Exa provides semantic search
over the web with structured content extraction — ideal for finding
LinkedIn profiles, bios, press mentions, and scientific publications.

Rate limited to 100 req/min via a sliding-window token bucket.
"""

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any

from src.agents.capabilities.enrichment_providers.base import (
    BaseEnrichmentProvider,
    CompanyEnrichment,
    PersonEnrichment,
    PublicationResult,
)
from src.core.config import settings

logger = logging.getLogger(__name__)

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

        Returns:
            List of result dicts from the Exa response.
        """
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
            resp = await client.post(
                f"{self._base_url}/search",
                json=payload,
            )
            if resp.status_code != 200:
                logger.warning(
                    "Exa search failed: %d %s",
                    resp.status_code,
                    resp.text[:200],
                )
                return []

            data = resp.json()
            return data.get("results", [])

        except Exception as exc:
            logger.warning("Exa search error: %s", exc)
            return []
