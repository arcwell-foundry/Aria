"""Exa Web Intelligence MCP Server definition.

Exposes six tools for Exa web intelligence:
    - exa_search_web   — multi-depth web search (instant/fast/deep)
    - exa_search_news  — recent news with date filtering
    - exa_find_similar — competitor/peer page discovery
    - exa_answer       — direct factual answers
    - exa_research     — deep agentic research
    - exa_get_contents — full page content retrieval

All tools accept an optional ``dct`` parameter for DCT enforcement.
"""

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from src.mcp_servers.exa.tools import (
    exa_answer_impl,
    exa_find_similar_impl,
    exa_get_contents_impl,
    exa_research_impl,
    exa_search_news_impl,
    exa_search_web_impl,
)
from src.mcp_servers.middleware import enforce_dct

logger = logging.getLogger(__name__)

exa_mcp = FastMCP("aria-exa")


# ── exa_search_web ─────────────────────────────────────────────────────


@exa_mcp.tool()
async def exa_search_web(
    query: str,
    num_results: int = 10,
    depth: str = "fast",
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    dct: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Search the web via Exa at configurable depth.

    Supports three depth levels:
    - "instant": Sub-200ms for real-time chat interactions.
    - "fast" (default): <350ms for interactive workflows.
    - "deep": ~3.5s for highest quality, comprehensive results.

    Args:
        query: Search query string.
        num_results: Number of results to return (default 10).
        depth: Search depth — "instant", "fast", or "deep".
        include_domains: Only return results from these domains.
        exclude_domains: Exclude results from these domains.
        dct: Optional serialized DelegationCapabilityToken.

    Returns:
        Dict with query, depth, results list, and count.
    """
    enforce_dct("exa_search_web", "read_exa", dct)
    return await exa_search_web_impl(
        query=query,
        num_results=num_results,
        depth=depth,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
    )


# ── exa_search_news ────────────────────────────────────────────────────


@exa_mcp.tool()
async def exa_search_news(
    query: str,
    num_results: int = 10,
    days_back: int = 30,
    dct: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Search recent news articles via Exa with date filtering.

    Uses Exa's neural search with publishedDate filtering to find
    recent news, press releases, and announcements.

    Args:
        query: News search query.
        num_results: Number of results to return (default 10).
        days_back: Only return news from the last N days (default 30).
        dct: Optional serialized DelegationCapabilityToken.

    Returns:
        Dict with query, results list, and count.
    """
    enforce_dct("exa_search_news", "read_news_apis", dct)
    return await exa_search_news_impl(
        query=query,
        num_results=num_results,
        days_back=days_back,
    )


# ── exa_find_similar ───────────────────────────────────────────────────


@exa_mcp.tool()
async def exa_find_similar(
    url: str,
    num_results: int = 10,
    exclude_domains: list[str] | None = None,
    dct: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Find pages similar to a given URL for competitor or peer discovery.

    Useful for discovering competitors, alternative products, or related
    companies by providing a reference URL.

    Args:
        url: The reference URL to find similar pages for.
        num_results: Number of similar pages to return (default 10).
        exclude_domains: Domains to exclude from results.
        dct: Optional serialized DelegationCapabilityToken.

    Returns:
        Dict with url, results list, and count.
    """
    enforce_dct("exa_find_similar", "read_exa", dct)
    return await exa_find_similar_impl(
        url=url,
        num_results=num_results,
        exclude_domains=exclude_domains,
    )


# ── exa_answer ─────────────────────────────────────────────────────────


@exa_mcp.tool()
async def exa_answer(
    question: str,
    dct: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Get a direct factual answer to a question via Exa.

    Returns a concise answer synthesized from web sources rather than
    a list of search results.

    Args:
        question: The question to answer.
        dct: Optional serialized DelegationCapabilityToken.

    Returns:
        Dict with question and answer string.
    """
    enforce_dct("exa_answer", "read_exa", dct)
    return await exa_answer_impl(question=question)


# ── exa_research ───────────────────────────────────────────────────────


@exa_mcp.tool()
async def exa_research(
    query: str,
    dct: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run deep agentic research via Exa.

    Performs comprehensive research (up to 60s) using Exa's research
    endpoint. Falls back to deep search if the research endpoint is
    unavailable.

    Args:
        query: Research query string.
        dct: Optional serialized DelegationCapabilityToken.

    Returns:
        Dict with query, results list, and count.
    """
    enforce_dct("exa_research", "read_exa", dct)
    return await exa_research_impl(query=query)


# ── exa_get_contents ───────────────────────────────────────────────────


@exa_mcp.tool()
async def exa_get_contents(
    urls: list[str],
    dct: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch full page contents for a list of URLs.

    Retrieves the full text content for each URL, useful for extracting
    detailed information from pages discovered via search.

    Args:
        urls: List of URLs to retrieve contents for.
        dct: Optional serialized DelegationCapabilityToken.

    Returns:
        Dict with urls, results list, and count.
    """
    enforce_dct("exa_get_contents", "read_exa", dct)
    return await exa_get_contents_impl(urls=urls)
