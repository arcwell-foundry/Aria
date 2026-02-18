"""Standalone implementation functions for Life Sciences API calls.

Extracted from AnalystAgent so they can be exposed as MCP tools.
Each function is a module-level async function that uses a shared
lazy-initialized httpx.AsyncClient, a module-level cache, and
PubMed rate limiting (3 req/sec without API key).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

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

    try:
        client = _get_client()

        params: dict[str, str | int] = {
            "query.term": query,
            "pageSize": max_results,
        }

        if status:
            params["filter.oversightStatus"] = status

        response = await client.get(CLINICALTRIALS_API_URL, params=params)
        response.raise_for_status()

        data = response.json()

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

    except httpx.HTTPStatusError as e:
        logger.error("ClinicalTrials API error: %s", e)
        return {"error": str(e), "studies": [], "total_count": 0}
    except Exception as e:
        logger.error("ClinicalTrials search failed: %s", e)
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
