"""Exa tool implementations — thin wrappers around ExaEnrichmentProvider.

Each function delegates to a lazily-initialized singleton of
``ExaEnrichmentProvider``.  The provider already handles rate limiting
(100 req/min sliding window), circuit breaker state, and httpx
client lifecycle — so these wrappers are intentionally thin.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

_provider = None


def _get_provider():
    """Lazy-initialize the ExaEnrichmentProvider singleton."""
    global _provider
    if _provider is None:
        from src.agents.capabilities.enrichment_providers.exa_provider import (
            ExaEnrichmentProvider,
        )

        _provider = ExaEnrichmentProvider()
    return _provider


# ── Web Search ─────────────────────────────────────────────────────────


async def exa_search_web_impl(
    query: str,
    num_results: int = 10,
    depth: str = "fast",
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
) -> dict[str, Any]:
    """Search the web via Exa at configurable depth.

    Args:
        query: Search query string.
        num_results: Number of results to return.
        depth: Search depth — ``"instant"`` (<200ms), ``"fast"`` (<350ms),
            or ``"deep"`` (~3.5s, highest quality).
        include_domains: Only return results from these domains.
        exclude_domains: Exclude results from these domains.

    Returns:
        Dict with ``query``, ``depth``, ``results`` list, and ``count``.
    """
    try:
        provider = _get_provider()

        if depth == "instant":
            raw = await provider.search_instant(query, num_results)
        elif depth == "deep":
            raw = await provider.search_deep(
                query,
                num_results,
                include_domains=include_domains,
                exclude_domains=exclude_domains,
            )
        else:
            # Default: fast
            raw = await provider.search_fast(
                query,
                num_results,
                include_domains=include_domains,
                exclude_domains=exclude_domains,
            )

        results_list = [r.model_dump() for r in raw]
        return {
            "query": query,
            "depth": depth,
            "results": results_list,
            "count": len(results_list),
        }

    except Exception as e:
        logger.error(
            "exa_search_web_impl failed: query='%s' depth=%s error='%s'",
            query[:100],
            depth,
            str(e),
            exc_info=True,
        )
        return {"query": query, "error": str(e), "results": [], "count": 0}


# ── News Search ────────────────────────────────────────────────────────


async def exa_search_news_impl(
    query: str,
    num_results: int = 10,
    days_back: int = 30,
) -> dict[str, Any]:
    """Search recent news articles via Exa with date filtering.

    Args:
        query: News search query.
        num_results: Number of results to return.
        days_back: Only return news from the last N days.

    Returns:
        Dict with ``query``, ``results`` list, and ``count``.
    """
    try:
        provider = _get_provider()
        raw = await provider.search_news(query, num_results, days_back=days_back)
        results_list = [r.model_dump() for r in raw]
        return {
            "query": query,
            "results": results_list,
            "count": len(results_list),
        }

    except Exception as e:
        logger.error(
            "exa_search_news_impl failed: query='%s' error='%s'",
            query[:100],
            str(e),
            exc_info=True,
        )
        return {"query": query, "error": str(e), "results": [], "count": 0}


# ── Find Similar ───────────────────────────────────────────────────────


async def exa_find_similar_impl(
    url: str,
    num_results: int = 10,
    exclude_domains: list[str] | None = None,
) -> dict[str, Any]:
    """Find pages similar to a given URL (competitor/peer discovery).

    Args:
        url: The reference URL to find similar pages for.
        num_results: Number of results to return.
        exclude_domains: Domains to exclude from results.

    Returns:
        Dict with ``url``, ``results`` list, and ``count``.
    """
    try:
        provider = _get_provider()
        raw = await provider.find_similar(
            url, num_results, exclude_domains=exclude_domains
        )
        results_list = [r.model_dump() for r in raw]
        return {
            "url": url,
            "results": results_list,
            "count": len(results_list),
        }

    except Exception as e:
        logger.error(
            "exa_find_similar_impl failed: url='%s' error='%s'",
            url[:100],
            str(e),
            exc_info=True,
        )
        return {"url": url, "error": str(e), "results": [], "count": 0}


# ── Answer ─────────────────────────────────────────────────────────────


async def exa_answer_impl(
    question: str,
) -> dict[str, Any]:
    """Get a direct factual answer to a question via Exa.

    Args:
        question: The question to answer.

    Returns:
        Dict with ``question`` and ``answer`` string.
    """
    try:
        provider = _get_provider()
        result = await provider.answer(question)
        return {
            "question": question,
            "answer": result,
        }

    except Exception as e:
        logger.error(
            "exa_answer_impl failed: question='%s' error='%s'",
            question[:100],
            str(e),
            exc_info=True,
        )
        return {"question": question, "error": str(e), "answer": ""}


# ── Research ───────────────────────────────────────────────────────────


async def exa_research_impl(
    query: str,
) -> dict[str, Any]:
    """Run deep agentic research via Exa (up to 60s).

    Falls back to deep search if the ``/research`` endpoint is
    unavailable.

    Args:
        query: Research query string.

    Returns:
        Dict with ``query``, ``results`` list, and ``count``.
    """
    try:
        provider = _get_provider()
        raw = await provider.research(query)
        results_list = [r.model_dump() for r in raw]
        return {
            "query": query,
            "results": results_list,
            "count": len(results_list),
        }

    except Exception as e:
        logger.error(
            "exa_research_impl failed: query='%s' error='%s'",
            query[:100],
            str(e),
            exc_info=True,
        )
        return {"query": query, "error": str(e), "results": [], "count": 0}


# ── Get Contents ───────────────────────────────────────────────────────


async def exa_get_contents_impl(
    urls: list[str],
) -> dict[str, Any]:
    """Fetch full page contents for a list of URLs.

    Args:
        urls: List of URLs to retrieve contents for.

    Returns:
        Dict with ``urls``, ``results`` list, and ``count``.
    """
    try:
        provider = _get_provider()
        raw = await provider.get_contents(urls)
        results_list = [r.model_dump() for r in raw]
        return {
            "urls": urls,
            "results": results_list,
            "count": len(results_list),
        }

    except Exception as e:
        logger.error(
            "exa_get_contents_impl failed: urls=%s error='%s'",
            urls[:3],
            str(e),
            exc_info=True,
        )
        return {"urls": urls, "error": str(e), "results": [], "count": 0}
