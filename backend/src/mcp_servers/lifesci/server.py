"""Life Sciences MCP Server definition."""

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from src.mcp_servers.lifesci.tools import (
    chembl_search_impl,
    clinical_trials_search_impl,
    fda_drug_search_impl,
    pubmed_fetch_details_impl,
    pubmed_search_impl,
)
from src.mcp_servers.middleware import enforce_dct

logger = logging.getLogger(__name__)

lifesci_mcp = FastMCP("aria-lifesci")


# ---------------------------------------------------------------------------
# PubMed tools
# ---------------------------------------------------------------------------


@lifesci_mcp.tool()
async def pubmed_search(
    query: str,
    max_results: int = 20,
    days_back: int | None = None,
    dct: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Search PubMed for biomedical literature.

    Returns matching article PMIDs, total count, and query metadata.
    Optionally filter to articles published within the last *days_back* days.
    """
    enforce_dct("pubmed_search", "read_pubmed", dct)
    return await pubmed_search_impl(query, max_results, days_back)


@lifesci_mcp.tool()
async def pubmed_fetch_details(
    pmids: list[str],
    dct: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch detailed metadata (title, authors, abstract) for PubMed articles.

    Accepts a list of PMIDs and returns a dict keyed by PMID with full
    article summaries.
    """
    enforce_dct("pubmed_fetch_details", "read_pubmed", dct)
    return await pubmed_fetch_details_impl(pmids)


# ---------------------------------------------------------------------------
# ClinicalTrials.gov
# ---------------------------------------------------------------------------


@lifesci_mcp.tool()
async def clinical_trials_search(
    query: str,
    max_results: int = 20,
    status: str | None = None,
    dct: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Search ClinicalTrials.gov for clinical studies.

    Returns study NCT IDs, titles, status, start dates, and conditions.
    Optionally filter by oversight status.
    """
    enforce_dct("clinical_trials_search", "read_clinicaltrials", dct)
    return await clinical_trials_search_impl(query, max_results, status)


# ---------------------------------------------------------------------------
# FDA (OpenFDA)
# ---------------------------------------------------------------------------


@lifesci_mcp.tool()
async def fda_drug_search(
    drug_name: str,
    search_type: str = "brand",
    max_results: int = 10,
    dct: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Search the OpenFDA API for drug labels or medical devices.

    *search_type* can be ``"brand"``, ``"generic"``, or ``"device"``.
    Returns product details including names, manufacturers, and purpose.
    """
    enforce_dct("fda_drug_search", "read_fda", dct)
    return await fda_drug_search_impl(drug_name, search_type, max_results)


# ---------------------------------------------------------------------------
# ChEMBL
# ---------------------------------------------------------------------------


@lifesci_mcp.tool()
async def chembl_search(
    query: str,
    search_type: str = "molecule",
    max_results: int = 20,
    dct: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Search the ChEMBL database for bioactive molecules, targets, or drugs.

    *search_type* can be ``"molecule"``, ``"target"``, or ``"drug"``.
    Returns molecule IDs, preferred names, types, max clinical phase, and
    therapeutic area.
    """
    enforce_dct("chembl_search", "read_chembl", dct)
    return await chembl_search_impl(query, search_type, max_results)
