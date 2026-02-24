"""Tests for the Life Sciences MCP server."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mcp_servers.lifesci.server import lifesci_mcp
from src.mcp_servers.middleware import DCTViolation


def _extract_dict(result: Any) -> dict[str, Any]:
    """Extract the dict payload from a FastMCP call_tool result.

    FastMCP.call_tool with ``convert_result=True`` returns either:
    - A ``(list[TextContent], dict)`` tuple when the tool has a typed return
      (unstructured content + structured output).
    - A ``list[TextContent]`` when there is no output schema.

    This helper handles both forms.
    """
    if isinstance(result, tuple):
        # Structured output path: second element is the dict
        return result[1]
    if isinstance(result, dict):
        return result
    # Fallback: list of content blocks
    assert isinstance(result, list), f"Expected list/tuple/dict, got {type(result)}"
    assert len(result) >= 1, "Expected at least one content block"
    return json.loads(result[0].text)


@pytest.fixture(autouse=True)
def _clear_research_cache() -> None:
    """Clear the lifesci module-level research cache between tests."""
    from src.mcp_servers.lifesci import tools as lifesci_tools

    lifesci_tools._research_cache.clear()


# ── Tool discovery ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lifesci_lists_six_tools() -> None:
    """The lifesci server should expose exactly 6 tools."""
    tools = await lifesci_mcp.list_tools()
    names = {t.name for t in tools}
    assert len(tools) == 6
    assert names == {
        "pubmed_search",
        "pubmed_fetch_details",
        "clinical_trials_search",
        "fda_drug_search",
        "chembl_search",
        "uspto_patent_search",
    }


# ── PubMed search ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pubmed_search_returns_results(
    pubmed_search_response: dict[str, Any],
) -> None:
    """pubmed_search should return pmids and count from the PubMed API."""
    mock_response = MagicMock()
    mock_response.json.return_value = pubmed_search_response
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.is_closed = False

    with patch("src.mcp_servers.lifesci.tools._get_client", return_value=mock_client):
        raw = await lifesci_mcp.call_tool("pubmed_search", {"query": "CRISPR"})

    result = _extract_dict(raw)
    assert "pmids" in result
    assert result["pmids"] == ["12345678", "87654321"]
    assert result["count"] == 42


# ── PubMed fetch details ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pubmed_fetch_details_returns_articles(
    pubmed_summary_response: dict[str, Any],
) -> None:
    """pubmed_fetch_details should return article metadata keyed by PMID."""
    mock_response = MagicMock()
    mock_response.json.return_value = pubmed_summary_response
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.is_closed = False

    with patch("src.mcp_servers.lifesci.tools._get_client", return_value=mock_client):
        raw = await lifesci_mcp.call_tool(
            "pubmed_fetch_details", {"pmids": ["12345678"]}
        )

    result = _extract_dict(raw)
    assert "12345678" in result
    assert result["12345678"]["title"] == "CRISPR advances in oncology"


# ── ClinicalTrials.gov ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_clinical_trials_returns_studies() -> None:
    """clinical_trials_search should parse studies from the CT.gov API."""
    ct_api_response = {
        "totalCount": 1,
        "studies": [
            {
                "protocolSection": {
                    "identificationModule": {
                        "nctId": "NCT001",
                        "briefTitle": "Test",
                    },
                    "statusModule": {"overallStatus": "Recruiting"},
                    "conditionsModule": {"conditions": ["Cancer"]},
                }
            }
        ],
    }

    mock_response = MagicMock()
    mock_response.json.return_value = ct_api_response
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.is_closed = False

    with patch("src.mcp_servers.lifesci.tools._get_client", return_value=mock_client):
        raw = await lifesci_mcp.call_tool(
            "clinical_trials_search", {"query": "cancer"}
        )

    result = _extract_dict(raw)
    assert result["total_count"] == 1
    assert len(result["studies"]) == 1
    assert result["studies"][0]["nct_id"] == "NCT001"


# ── DCT enforcement (server-side) ────────────────────────────────────


@pytest.mark.asyncio
async def test_pubmed_search_with_valid_dct(
    analyst_dct,  # noqa: ANN001
    pubmed_search_response: dict[str, Any],
) -> None:
    """An analyst DCT (which has read_pubmed) should be accepted."""
    mock_response = MagicMock()
    mock_response.json.return_value = pubmed_search_response
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.is_closed = False

    with patch("src.mcp_servers.lifesci.tools._get_client", return_value=mock_client):
        # Should not raise -- analyst is allowed read_pubmed
        raw = await lifesci_mcp.call_tool(
            "pubmed_search",
            {"query": "CRISPR", "dct": analyst_dct.to_dict()},
        )

    result = _extract_dict(raw)
    assert "pmids" in result


@pytest.mark.asyncio
async def test_pubmed_search_with_denied_dct(scout_dct) -> None:  # noqa: ANN001
    """A scout DCT should be denied read_pubmed (not in scout's allowed actions)."""
    from mcp.server.fastmcp.exceptions import ToolError

    with pytest.raises(ToolError) as exc_info:
        await lifesci_mcp.call_tool(
            "pubmed_search",
            {"query": "CRISPR", "dct": scout_dct.to_dict()},
        )

    # The underlying cause should be a DCTViolation
    assert isinstance(exc_info.value.__cause__, DCTViolation)
    violation = exc_info.value.__cause__
    assert violation.tool_name == "pubmed_search"
    assert violation.delegatee == "scout"
