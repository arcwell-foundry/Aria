"""Standalone implementation functions for Life Sciences API calls.

Extracted from AnalystAgent so they can be exposed as MCP tools.
Each function is a module-level async function that uses a shared
lazy-initialized httpx.AsyncClient, a module-level cache, and
PubMed rate limiting (3 req/sec without API key).
"""

from __future__ import annotations

import asyncio
import json as _json_mod
import logging
import subprocess
import time
from typing import Any
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------
PUBMED_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
CLINICALTRIALS_API_URL = "https://clinicaltrials.gov/api/v2/studies"
FDA_DRUG_API_URL = "https://api.fda.gov/drug/label.json"
FDA_DEVICE_API_URL = "https://api.fda.gov/device/510k.json"
CHEMBL_API_URL = "https://www.ebi.ac.uk/chembl/api/data"
# NOTE: The old developer.uspto.gov IBD API was retired in 2025.
# Patent search now uses Google Patents as primary source.
GOOGLE_PATENTS_XHR_URL = "https://patents.google.com/xhr/query"
USPTO_USER_AGENT = "ARIA-Intelligence/1.0 (support@aria-intel.com)"

# ---------------------------------------------------------------------------
# Module-level shared state
# ---------------------------------------------------------------------------
_http_client: httpx.AsyncClient | None = None
_research_cache: dict[str, Any] = {}

# PubMed rate limiting: 3 requests per second
_PUBMED_RATE_LIMIT = 3
_pubmed_last_call_time: float = 0.0


def _get_client() -> httpx.AsyncClient:
    """Return a lazy-initialized module-level httpx.AsyncClient."""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=30.0)
    return _http_client


async def _curl_get_json(
    url: str,
    params: dict[str, Any] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """Fetch JSON via curl subprocess as a fallback for TLS-fingerprint blocks.

    Some government APIs (e.g. ClinicalTrials.gov) block Python HTTP clients
    via bot-detection / TLS fingerprinting while allowing curl.  This function
    shells out to curl as a reliable fallback.

    Args:
        url: The URL to GET.
        params: Optional query parameters.
        timeout: Curl timeout in seconds.

    Returns:
        Parsed JSON dict.

    Raises:
        RuntimeError: If curl fails or returns non-JSON.
    """
    if params:
        url = f"{url}?{urlencode(params, doseq=True)}"

    result = await asyncio.to_thread(
        subprocess.run,
        ["curl", "-s", "-f", "--max-time", str(timeout), url],
        capture_output=True,
        text=True,
        timeout=timeout + 5,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"curl failed (exit {result.returncode}): {result.stderr[:200]}"
        )

    return _json_mod.loads(result.stdout)


async def _pubmed_rate_limit() -> None:
    """Enforce PubMed's 3 req/sec rate limit, sleeping if needed."""
    global _pubmed_last_call_time
    current_time = time.time()
    time_since_last = current_time - _pubmed_last_call_time
    min_interval = 1.0 / _PUBMED_RATE_LIMIT
    if time_since_last < min_interval:
        await asyncio.sleep(min_interval - time_since_last)


def _update_pubmed_timestamp() -> None:
    """Record the timestamp of the most recent PubMed call."""
    global _pubmed_last_call_time
    _pubmed_last_call_time = time.time()


# ---------------------------------------------------------------------------
# PubMed search
# ---------------------------------------------------------------------------
async def pubmed_search_impl(
    query: str,
    max_results: int = 20,
    days_back: int | None = None,
) -> dict[str, Any]:
    """Search PubMed for articles matching *query*.

    Args:
        query: Search query string.
        max_results: Maximum number of results to return.
        days_back: Optional filter to articles from last N days.

    Returns:
        Dict with ``query``, ``count``, ``pmids``, and ``retmax``.
    """
    await _pubmed_rate_limit()

    cache_key = f"pubmed:{query}:{max_results}:{days_back}"
    if cache_key in _research_cache:
        logger.info("PubMed cache hit for query: %s", query)
        return _research_cache[cache_key]

    try:
        client = _get_client()

        params: dict[str, Any] = {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": max_results,
            "sort": "relevance",
        }

        if days_back:
            params["datetype"] = "edat"
            params["reldate"] = days_back

        response = await client.get(PUBMED_ESEARCH_URL, params=params)
        response.raise_for_status()

        data = response.json()
        search_result = data.get("esearchresult", {})

        result: dict[str, Any] = {
            "query": query,
            "count": int(search_result.get("count", 0)),
            "pmids": search_result.get("idlist", []),
            "retmax": int(search_result.get("retmax", 0)),
        }

        _research_cache[cache_key] = result
        _update_pubmed_timestamp()

        logger.info(
            "PubMed search found %d articles for: %s",
            result["count"],
            query,
        )

        return result

    except httpx.HTTPStatusError as e:
        logger.error("PubMed API error: %s", e)
        return {"error": str(e), "pmids": [], "count": 0}
    except Exception as e:
        logger.error("PubMed search failed: %s", e)
        return {"error": str(e), "pmids": [], "count": 0}


# ---------------------------------------------------------------------------
# PubMed fetch details
# ---------------------------------------------------------------------------
async def pubmed_fetch_details_impl(
    pmids: list[str],
) -> dict[str, Any]:
    """Fetch detailed metadata for PubMed articles.

    Args:
        pmids: List of PubMed IDs to fetch details for.

    Returns:
        Dict mapping each PMID to its article metadata.
    """
    if not pmids:
        return {}

    await _pubmed_rate_limit()

    cache_key = f"pubmed_details:{','.join(sorted(pmids))}"
    if cache_key in _research_cache:
        logger.info("PubMed details cache hit for %d PMIDs", len(pmids))
        return _research_cache[cache_key]

    try:
        client = _get_client()

        params: dict[str, str] = {
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

        _research_cache[cache_key] = result_data
        _update_pubmed_timestamp()

        logger.info("Fetched details for %d articles", len(result_data))

        return result_data

    except httpx.HTTPStatusError as e:
        logger.error("PubMed details API error: %s", e)
        return {}
    except Exception as e:
        logger.error("PubMed details fetch failed: %s", e)
        return {}


# ---------------------------------------------------------------------------
# ClinicalTrials.gov search
# ---------------------------------------------------------------------------
async def clinical_trials_search_impl(
    query: str,
    max_results: int = 20,
    status: str | None = None,
) -> dict[str, Any]:
    """Search ClinicalTrials.gov for studies matching *query*.

    Args:
        query: Search query string.
        max_results: Maximum number of results to return.
        status: Optional filter by study oversight status.

    Returns:
        Dict with ``query``, ``total_count``, and ``studies`` list.
    """
    cache_key = f"clinicaltrials:{query}:{max_results}:{status}"
    if cache_key in _research_cache:
        logger.info("ClinicalTrials cache hit for query: %s", query)
        return _research_cache[cache_key]

    params: dict[str, str | int] = {
        "query.term": query,
        "pageSize": max_results,
    }

    if status:
        params["filter.oversightStatus"] = status

    # ClinicalTrials.gov blocks Python HTTP clients via TLS fingerprinting,
    # returning 403 for httpx/requests while allowing curl.  Try httpx first
    # for speed, then fall back to curl subprocess.
    data: dict[str, Any] | None = None

    try:
        client = _get_client()
        response = await client.get(CLINICALTRIALS_API_URL, params=params)
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        logger.info(
            "ClinicalTrials.gov httpx request failed (%s), falling back to curl",
            exc,
        )

    if data is None:
        try:
            data = await _curl_get_json(CLINICALTRIALS_API_URL, params)
        except Exception as curl_exc:
            logger.error("ClinicalTrials.gov curl fallback also failed: %s", curl_exc)
            return {"error": str(curl_exc), "studies": [], "total_count": 0}

    try:
        studies: list[dict[str, Any]] = []
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

        result: dict[str, Any] = {
            "query": query,
            "total_count": data.get("totalCount", 0),
            "studies": studies,
        }

        _research_cache[cache_key] = result

        logger.info(
            "ClinicalTrials search found %d studies for: %s",
            result["total_count"],
            query,
        )

        return result

    except Exception as e:
        logger.error("ClinicalTrials response parsing failed: %s", e)
        return {"error": str(e), "studies": [], "total_count": 0}


# ---------------------------------------------------------------------------
# FDA drug / device search
# ---------------------------------------------------------------------------
async def fda_drug_search_impl(
    drug_name: str,
    search_type: str = "brand",
    max_results: int = 10,
) -> dict[str, Any]:
    """Search OpenFDA API for drug or device information.

    Args:
        drug_name: Name of the drug or device to search.
        search_type: ``"brand"``, ``"generic"``, or ``"device"``.
        max_results: Maximum number of results to return.

    Returns:
        Dict with ``query``, ``search_type``, ``total``, and ``products``.
    """
    cache_key = f"fda:{drug_name}:{search_type}:{max_results}"
    if cache_key in _research_cache:
        logger.info("FDA cache hit for: %s", drug_name)
        return _research_cache[cache_key]

    try:
        client = _get_client()

        if search_type == "device":
            url = FDA_DEVICE_API_URL
            search_field = "device_name"
        else:
            url = FDA_DRUG_API_URL
            search_field = (
                "openfda.brand_name" if search_type == "brand" else "openfda.generic_name"
            )

        params: dict[str, str | int] = {
            "search": f"{search_field}:{drug_name}",
            "limit": max_results,
        }

        response = await client.get(url, params=params)
        response.raise_for_status()

        data = response.json()

        results = data.get("results", [])
        products: list[dict[str, Any]] = []

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
                        "brand_name": (
                            openfda.get("brand_name", [""])[0]
                            if openfda.get("brand_name")
                            else None
                        ),
                        "generic_name": (
                            openfda.get("generic_name", [""])[0]
                            if openfda.get("generic_name")
                            else None
                        ),
                        "manufacturer": (
                            openfda.get("manufacturer_name", [""])[0]
                            if openfda.get("manufacturer_name")
                            else None
                        ),
                        "purpose": item.get("purpose", []),
                    }
                )

        result: dict[str, Any] = {
            "query": drug_name,
            "search_type": search_type,
            "total": data.get("meta", {}).get("total", 0),
            "products": products,
        }

        _research_cache[cache_key] = result

        logger.info(
            "FDA search found %d %s results for: %s",
            result["total"],
            search_type,
            drug_name,
        )

        return result

    except httpx.HTTPStatusError as e:
        logger.error("FDA API error: %s", e)
        return {"error": str(e), "products": [], "total": 0}
    except Exception as e:
        logger.error("FDA search failed: %s", e)
        return {"error": str(e), "products": [], "total": 0}


# ---------------------------------------------------------------------------
# ChEMBL search
# ---------------------------------------------------------------------------
async def chembl_search_impl(
    query: str,
    search_type: str = "molecule",
    max_results: int = 20,
) -> dict[str, Any]:
    """Search ChEMBL database for bioactive molecules, targets, or drugs.

    Args:
        query: Search query string (molecule name, target, etc.).
        search_type: ``"molecule"``, ``"target"``, or ``"drug"``.
        max_results: Maximum number of results to return.

    Returns:
        Dict with ``query``, ``search_type``, ``total_count``, and ``molecules``.
    """
    cache_key = f"chembl:{query}:{search_type}:{max_results}"
    if cache_key in _research_cache:
        logger.info("ChEMBL cache hit for: %s", query)
        return _research_cache[cache_key]

    try:
        client = _get_client()

        if search_type == "target":
            endpoint = f"{CHEMBL_API_URL}/target"
        elif search_type == "drug":
            endpoint = f"{CHEMBL_API_URL}/drug"
        else:
            endpoint = f"{CHEMBL_API_URL}/molecule"

        params: dict[str, str | int] = {
            "format": "json",
            "q": query,
            "limit": max_results,
        }

        response = await client.get(endpoint, params=params)
        response.raise_for_status()

        data = response.json()

        # ChEMBL API returns various formats
        molecules = data.get("molecules", {})
        if isinstance(molecules, dict):
            molecule_list = molecules.get("molecule", [])
        else:
            molecule_list = molecules if isinstance(molecules, list) else []

        results: list[dict[str, Any]] = []
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

        page_meta = data.get("page_meta", {})
        total_count = page_meta.get("total_count", len(results))

        result: dict[str, Any] = {
            "query": query,
            "search_type": search_type,
            "total_count": total_count,
            "molecules": results,
        }

        _research_cache[cache_key] = result

        logger.info(
            "ChEMBL search found %d molecules for: %s",
            result["total_count"],
            query,
        )

        return result

    except httpx.HTTPStatusError as e:
        logger.error("ChEMBL API error: %s", e)
        return {"error": str(e), "molecules": [], "total_count": 0}
    except Exception as e:
        logger.error("ChEMBL search failed: %s", e)
        return {"error": str(e), "molecules": [], "total_count": 0}


# ---------------------------------------------------------------------------
# USPTO patent search
# ---------------------------------------------------------------------------

# Google Patents is the most reliable free patent search since the old
# developer.uspto.gov/ibd-api was retired and PatentsView requires an
# API key.  Uses httpx with browser-like headers (Google Patents
# requires browser User-Agent and times out plain curl).


async def _search_google_patents(
    query: str, max_results: int = 20
) -> list[dict[str, Any]]:
    """Search Google Patents via its XHR endpoint (public, no auth).

    Uses httpx with browser headers (Google Patents blocks plain curl).
    Falls back gracefully if blocked.

    Args:
        query: Patent search query.
        max_results: Maximum results.

    Returns:
        List of patent dicts.
    """
    try:
        async with httpx.AsyncClient(
            timeout=20.0,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json",
            },
        ) as client:
            resp = await client.get(
                GOOGLE_PATENTS_XHR_URL,
                params={
                    "url": f"q={query}&oq={query}&num={min(max_results, 100)}",
                },
            )
            if resp.status_code != 200:
                logger.info("Google Patents returned %d", resp.status_code)
                return []
            data = resp.json()
    except Exception as exc:
        logger.info("Google Patents request failed: %s", exc)
        return []

    patents: list[dict[str, Any]] = []
    clusters = data.get("results", {}).get("cluster", [])
    for cluster in clusters:
        for result in cluster.get("result", []):
            patent = result.get("patent", {})
            if not patent:
                continue

            pub_number = patent.get("publication_number", "")
            title = patent.get("title", "")
            # Remove HTML tags from title if present
            if "<" in title:
                import re
                title = re.sub(r"<[^>]+>", "", title)

            snippet = result.get("snippet", "")
            if "<" in snippet:
                import re
                snippet = re.sub(r"<[^>]+>", "", snippet)

            assignee = ""
            assignee_list = patent.get("assignee", [])
            if assignee_list:
                assignee = assignee_list[0] if isinstance(assignee_list[0], str) else ""

            patents.append({
                "title": title,
                "application_number": patent.get("application_number", ""),
                "publication_number": pub_number,
                "applicant": assignee,
                "filed_date": patent.get("filing_date", ""),
                "publication_date": patent.get("publication_date", ""),
                "abstract": snippet[:500],
                "patent_url": f"https://patents.google.com/patent/{pub_number}",
            })

    return patents


async def _search_exa_patents(query: str, max_results: int = 20) -> list[dict[str, Any]]:
    """Search for patents via the Exa API (if available).

    Uses domain-filtered web search against patents.google.com.

    Args:
        query: Patent search query.
        max_results: Maximum results.

    Returns:
        List of patent dicts.
    """
    try:
        from src.agents.capabilities.enrichment_providers.exa_provider import (
            ExaEnrichmentProvider,
        )
    except ImportError:
        return []

    try:
        exa = ExaEnrichmentProvider()
        results = await exa.search_fast(
            query=f"patent {query}",
            num_results=max_results,
            include_domains=["patents.google.com"],
        )

        patents: list[dict[str, Any]] = []
        for r in results:
            url = r.get("url", "")
            # Extract publication number from Google Patents URL
            pub_number = ""
            if "patents.google.com/patent/" in url:
                pub_number = url.split("/patent/")[1].split("/")[0]

            patents.append({
                "title": r.get("title", ""),
                "application_number": "",
                "publication_number": pub_number,
                "applicant": r.get("author", ""),
                "filed_date": "",
                "publication_date": r.get("published_date", ""),
                "abstract": (r.get("text", "") or r.get("highlights", ""))[:500],
                "patent_url": url,
            })

        return patents

    except Exception as exc:
        logger.warning("Exa patent search failed: %s", exc)
        return []


async def uspto_patent_search_impl(
    query: str,
    max_results: int = 20,
) -> dict[str, Any]:
    """Search for US patent publications.

    Tries multiple sources in order:
    1. Google Patents XHR API (public, no auth)
    2. Exa web search filtered to patents.google.com
    3. Returns empty result with informational note

    The legacy USPTO IBD API (developer.uspto.gov/ibd-api) was retired
    in 2025.  PatentsView requires an API key with suspended grants.

    Args:
        query: Search query string (e.g. ``"CAR-T cell therapy"``).
        max_results: Maximum number of results to return (max 100).

    Returns:
        Dict with ``query``, ``total_count``, and ``patents`` list.
    """
    cache_key = f"uspto:{query}:{max_results}"
    if cache_key in _research_cache:
        logger.info("USPTO cache hit for query: %s", query)
        return _research_cache[cache_key]

    patents: list[dict[str, Any]] = []
    source = "none"

    # Strategy 1: Google Patents XHR
    patents = await _search_google_patents(query, max_results)
    if patents:
        source = "google_patents"

    # Strategy 2: Exa domain-filtered search
    if not patents:
        patents = await _search_exa_patents(query, max_results)
        if patents:
            source = "exa"

    if not patents:
        logger.warning(
            "No patent results for '%s' from any source. "
            "USPTO IBD API is retired; PatentsView requires an API key.",
            query,
        )

    result: dict[str, Any] = {
        "query": query,
        "total_count": len(patents),
        "patents": patents,
        "source": source,
    }

    if patents:
        _research_cache[cache_key] = result

    logger.info(
        "Patent search found %d results for '%s' via %s",
        len(patents),
        query,
        source,
    )

    return result
