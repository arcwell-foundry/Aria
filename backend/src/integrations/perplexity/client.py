"""Perplexity API client for real-time web intelligence.

Perplexity's Sonar models provide real-time web search with citations,
ideal for market intelligence and competitive analysis.

Model options:
- sonar: Fast, lightweight model for quick queries (~1s)
- sonar-pro: Deeper research with more comprehensive results (~3s)
"""

import logging
from typing import Any

import httpx

from src.core.config import settings

logger = logging.getLogger(__name__)


class PerplexityClient:
    """Client for Perplexity API - real-time web intelligence with citations.

    Provides search and research methods that return answers with source
    citations, ideal for competitive intelligence and market research.
    """

    BASE_URL = "https://api.perplexity.ai"

    def __init__(self) -> None:
        """Initialize the Perplexity client."""
        self._api_key = settings.PERPLEXITY_API_KEY
        if not self._api_key:
            logger.warning(
                "PerplexityClient initialized WITHOUT API key - all searches will fail"
            )
        else:
            logger.info("PerplexityClient initialized with API key")

    @property
    def is_configured(self) -> bool:
        """Check if the client has a valid API key."""
        return bool(self._api_key)

    async def search(
        self,
        query: str,
        model: str = "sonar",
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        """Real-time web search with answer and citations.

        Args:
            query: Search query string.
            model: Model to use - "sonar" (fast) or "sonar-pro" (deeper).
            max_tokens: Maximum tokens in response.

        Returns:
            Dict with:
                - answer: The generated answer text
                - citations: List of source URLs
                - model: Model used
                - query: Original query
                - usage: Token usage info

        Raises:
            ValueError: If API key not configured.
            httpx.HTTPStatusError: If API returns error.
        """
        if not self._api_key:
            raise ValueError("PERPLEXITY_API_KEY not configured")

        logger.info("Perplexity search: query='%s' model=%s", query[:100], model)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": query}],
                    "return_citations": True,
                    "return_related_questions": False,
                    "max_tokens": max_tokens,
                },
            )
            response.raise_for_status()
            data = response.json()

            # Extract answer from response
            content = data["choices"][0]["message"]["content"]
            citations = data.get("citations", [])

            logger.info(
                "Perplexity search: returned %d chars, %d citations",
                len(content),
                len(citations),
            )

            return {
                "answer": content,
                "citations": citations,
                "model": model,
                "query": query,
                "usage": data.get("usage", {}),
            }

    async def research(self, query: str, max_tokens: int = 2048) -> dict[str, Any]:
        """Deep research for competitive analysis using sonar-pro.

        Uses the sonar-pro model for more comprehensive results with
        deeper analysis and more sources.

        Args:
            query: Research query string.
            max_tokens: Maximum tokens in response.

        Returns:
            Same structure as search(), with more comprehensive results.
        """
        return await self.search(query, model="sonar-pro", max_tokens=max_tokens)

    async def health_check(self) -> bool:
        """Verify Perplexity API connectivity.

        Returns:
            True if the API responds successfully.
        """
        if not self._api_key:
            return False

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "sonar",
                        "messages": [{"role": "user", "content": "test"}],
                        "max_tokens": 10,
                    },
                )
                return response.status_code == 200
        except Exception as e:
            logger.warning("Perplexity health check failed: %s", e)
            return False


# Singleton client instance
_client: PerplexityClient | None = None


def get_perplexity_client() -> PerplexityClient:
    """Get the singleton Perplexity client instance.

    Returns:
        PerplexityClient instance (may not be configured if API key missing).
    """
    global _client
    if _client is None:
        _client = PerplexityClient()
    return _client
