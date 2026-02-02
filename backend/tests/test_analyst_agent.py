"""Tests for AnalystAgent module."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


@pytest.mark.asyncio
async def test_pubmed_search_returns_articles() -> None:
    """Test _pubmed_search returns list of articles from PubMed API."""
    from src.agents.analyst import AnalystAgent

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    # Mock httpx client response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "esearchresult": {"idlist": ["12345", "67890"], "count": "2"}
    }

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await agent._pubmed_search(query="cancer immunotherapy", max_results=10)

    assert result["count"] == 2
    assert len(result["pmids"]) == 2
    assert "12345" in result["pmids"]
    assert "67890" in result["pmids"]


@pytest.mark.asyncio
async def test_pubmed_search_handles_api_error() -> None:
    """Test _pubmed_search handles API errors gracefully."""
    from src.agents.analyst import AnalystAgent

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    # Mock httpx to raise an error
    mock_client = AsyncMock()
    mock_client.get.side_effect = httpx.HTTPStatusError(
        "Server error", request=MagicMock(), response=MagicMock()
    )

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await agent._pubmed_search(query="test query")

    assert "error" in result
    assert result["pmids"] == []


def test_analyst_agent_has_name_and_description() -> None:
    """Test AnalystAgent has correct name and description class attributes."""
    from src.agents.analyst import AnalystAgent

    assert AnalystAgent.name == "Analyst"
    assert AnalystAgent.description == "Scientific research agent for life sciences queries"


def test_analyst_agent_extends_base_agent() -> None:
    """Test AnalystAgent extends BaseAgent."""
    from src.agents.analyst import AnalystAgent
    from src.agents.base import BaseAgent

    assert issubclass(AnalystAgent, BaseAgent)


def test_analyst_agent_initializes_with_llm_and_user() -> None:
    """Test AnalystAgent initializes with llm_client, user_id, and _research_cache."""
    from src.agents.analyst import AnalystAgent
    from src.agents.base import AgentStatus

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    assert agent.llm == mock_llm
    assert agent.user_id == "user-123"
    assert agent.status == AgentStatus.IDLE
    assert hasattr(agent, "_research_cache")
    assert agent._research_cache == {}


def test_analyst_agent_registers_four_tools() -> None:
    """Test AnalystAgent._register_tools returns dict with 4 tools."""
    from src.agents.analyst import AnalystAgent

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    tools = agent.tools

    assert len(tools) == 4
    assert "pubmed_search" in tools
    assert "clinical_trials_search" in tools
    assert "fda_drug_search" in tools
    assert "chembl_search" in tools


# Task 5: PubMed article details fetcher tests


@pytest.mark.asyncio
async def test_pubmed_fetch_details_returns_article_metadata() -> None:
    """Test _pubmed_fetch_details returns article metadata."""
    from src.agents.analyst import AnalystAgent

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    # Mock httpx client response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "result": {
            "12345": {
                "title": "Test Article Title",
                "authors": [{"name": "Smith J"}],
                "pubdate": "2023 Jan",
                "source": "Nature",
            }
        }
    }

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await agent._pubmed_fetch_details(pmids=["12345"])

    assert len(result) == 1
    assert result["12345"]["title"] == "Test Article Title"
    assert result["12345"]["authors"][0]["name"] == "Smith J"


@pytest.mark.asyncio
async def test_pubmed_fetch_details_handles_empty_pmids() -> None:
    """Test _pubmed_fetch_details handles empty PMID list gracefully."""
    from src.agents.analyst import AnalystAgent

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._pubmed_fetch_details(pmids=[])

    assert result == {}


# Task 6: ClinicalTrials.gov search tests


@pytest.mark.asyncio
async def test_clinical_trials_search_returns_studies() -> None:
    """Test _clinical_trials_search returns studies from ClinicalTrials.gov API."""
    from src.agents.analyst import AnalystAgent

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    # Mock httpx client response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "studies": [
            {
                "protocolSection": {
                    "identificationModule": {"nctId": "NCT00000001"},
                    "statusModule": {"overallStatus": "Recruiting"},
                }
            },
            {
                "protocolSection": {
                    "identificationModule": {"nctId": "NCT00000002"},
                    "statusModule": {"overallStatus": "Completed"},
                }
            },
        ],
        "totalCount": 2,
    }

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await agent._clinical_trials_search(query="Alzheimer's disease", max_results=10)

    assert result["total_count"] == 2
    assert len(result["studies"]) == 2
    assert result["studies"][0]["nct_id"] == "NCT00000001"
    assert result["studies"][0]["status"] == "Recruiting"


@pytest.mark.asyncio
async def test_clinical_trials_search_handles_empty_results() -> None:
    """Test _clinical_trials_search handles empty results gracefully."""
    from src.agents.analyst import AnalystAgent

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"studies": [], "totalCount": 0}

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await agent._clinical_trials_search(query="obscure condition xyz")

    assert result["total_count"] == 0
    assert result["studies"] == []


# Task 7: FDA drug/device search tests


@pytest.mark.asyncio
async def test_fda_drug_search_returns_products() -> None:
    """Test _fda_drug_search returns drug products from OpenFDA API."""
    from src.agents.analyst import AnalystAgent

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    # Mock httpx client response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {
                "openfda": {
                    "brand_name": ["TestDrug"],
                    "generic_name": ["test ingredient"],
                    "manufacturer": ["Test Pharma Inc."],
                },
                "purpose": ["Treatment of test condition"],
            }
        ],
        "meta": {"total": 1},
    }

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await agent._fda_drug_search(drug_name="TestDrug", search_type="brand")

    assert result["total"] == 1
    assert len(result["products"]) == 1
    assert result["products"][0]["brand_name"] == "TestDrug"


@pytest.mark.asyncio
async def test_fda_drug_search_handles_device_search() -> None:
    """Test _fda_drug_search handles device searches."""
    from src.agents.analyst import AnalystAgent

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {
                "device_name": "TestDevice",
                "device_class": "2",
                "medical_specialty": "Cardiology",
            }
        ],
        "meta": {"total": 1},
    }

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await agent._fda_drug_search(drug_name="TestDevice", search_type="device")

    assert result["total"] == 1
    assert len(result["products"]) == 1
    assert result["products"][0]["device_name"] == "TestDevice"


# Task 8: ChEMBL search tests


@pytest.mark.asyncio
async def test_chembl_search_returns_molecules() -> None:
    """Test _chembl_search returns molecules from ChEMBL API."""
    from src.agents.analyst import AnalystAgent

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    # Mock httpx client response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "molecules": [
            {
                "molecule_chembl_id": "CHEMBL0001",
                "pref_name": "Test Molecule",
                "molecule_type": "Small molecule",
                "max_phase": 4,
                "therapeutic_area": "Oncology",
            }
        ],
        "page_meta": {"total_count": 1},
    }

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await agent._chembl_search(query="aspirin", max_results=10)

    assert result["total_count"] == 1
    assert len(result["molecules"]) == 1
    assert result["molecules"][0]["molecule_chembl_id"] == "CHEMBL0001"


def test_analyst_agent_validates_research_question() -> None:
    """Test validate_input requires 'query' field."""
    from src.agents.analyst import AnalystAgent

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    # Valid input
    assert agent.validate_input({"query": "cancer immunotherapy"}) is True

    # Invalid inputs
    assert agent.validate_input({}) is False
    assert agent.validate_input({"other": "field"}) is False
    assert agent.validate_input({"depth": "deep"}) is False


def test_analyst_agent_validates_depth_level() -> None:
    """Test validate_input checks depth level if provided."""
    from src.agents.analyst import AnalystAgent

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    # Valid depth levels
    assert agent.validate_input({"query": "test", "depth": "quick"}) is True
    assert agent.validate_input({"query": "test", "depth": "standard"}) is True
    assert agent.validate_input({"query": "test", "depth": "comprehensive"}) is True

    # Invalid depth level
    assert agent.validate_input({"query": "test", "depth": "invalid"}) is False


# Task 10: Execute method tests


@pytest.mark.asyncio
async def test_analyst_execute_generates_research_report() -> None:
    """Test execute generates structured research report."""
    from src.agents.analyst import AnalystAgent

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    # Mock the tools
    agent._pubmed_search = AsyncMock(return_value={"count": 2, "pmids": ["12345", "67890"]})
    agent._pubmed_fetch_details = AsyncMock(
        return_value={"12345": {"title": "Article 1"}, "67890": {"title": "Article 2"}}
    )
    agent._clinical_trials_search = AsyncMock(
        return_value={"total_count": 1, "studies": [{"nct_id": "NCT001", "status": "Recruiting"}]}
    )
    agent._fda_drug_search = AsyncMock(return_value={"total": 1, "products": [{"brand_name": "TestDrug"}]})
    agent._chembl_search = AsyncMock(return_value={"total_count": 1, "molecules": [{"molecule_chembl_id": "CHEMBL001"}]})

    task = {"query": "cancer immunotherapy", "depth": "comprehensive"}

    result = await agent.execute(task)

    assert result.success is True
    assert "query" in result.data
    assert result.data["query"] == "cancer immunotherapy"
    assert "pubmed_articles" in result.data
    assert "clinical_trials" in result.data
    assert "fda_products" in result.data
    assert "chembl_molecules" in result.data
    assert "timestamp" in result.data


@pytest.mark.asyncio
async def test_analyst_execute_with_quick_depth_skips_databases() -> None:
    """Test execute with 'quick' depth only searches PubMed."""
    from src.agents.analyst import AnalystAgent

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    agent._pubmed_search = AsyncMock(return_value={"count": 1, "pmids": ["123"]})
    agent._pubmed_fetch_details = AsyncMock(return_value={"123": {"title": "Test"}})
    agent._clinical_trials_search = AsyncMock()
    agent._fda_drug_search = AsyncMock()
    agent._chembl_search = AsyncMock()

    task = {"query": "test query", "depth": "quick"}

    result = await agent.execute(task)

    assert result.success is True
    agent._pubmed_search.assert_called_once()
    # Other tools should not be called for quick depth
    agent._clinical_trials_search.assert_not_awaited()
    agent._fda_drug_search.assert_not_awaited()
    agent._chembl_search.assert_not_awaited()


# Task 11: format_output tests


def test_analyst_format_output_adds_summary() -> None:
    """Test format_output adds summary statistics to report."""
    from src.agents.analyst import AnalystAgent

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    data = {
        "query": "test query",
        "pubmed_search": {"count": 10, "pmids": ["1", "2"]},
        "pubmed_articles": {"1": {"title": "A1"}, "2": {"title": "A2"}},
        "clinical_trials": {"total_count": 5, "studies": [{"nct_id": "NCT1"}]},
        "fda_products": {"total": 3, "products": [{"brand_name": "D1"}]},
        "chembl_molecules": {"total_count": 2, "molecules": [{"molecule_chembl_id": "C1"}]},
    }

    formatted = agent.format_output(data)

    assert "summary" in formatted
    assert formatted["summary"]["total_sources"] == 4
    assert formatted["summary"]["pubmed_article_count"] == 10
    assert formatted["summary"]["clinical_trials_count"] == 5
    assert formatted["summary"]["fda_products_count"] == 3
    assert formatted["summary"]["chembl_molecules_count"] == 2


# Task 12: Module export tests


def test_analyst_agent_exported_from_agents_module() -> None:
    """Test AnalystAgent is exported from agents module."""
    from src.agents import AnalystAgent

    assert AnalystAgent.name == "Analyst"


# Task 13: Integration tests


@pytest.mark.asyncio
async def test_full_analyst_agent_lifecycle_with_real_execution() -> None:
    """Integration test demonstrating complete Analyst agent lifecycle."""
    from src.agents import AnalystAgent
    from src.agents.base import AgentStatus

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    # Mock tools
    agent._pubmed_search = AsyncMock(return_value={"count": 1, "pmids": ["12345"]})
    agent._pubmed_fetch_details = AsyncMock(
        return_value={
            "12345": {
                "title": "Advances in Cancer Immunotherapy",
                "authors": [{"name": "Smith J"}],
                "pubdate": "2023 Jan",
            }
        }
    )
    agent._clinical_trials_search = AsyncMock(
        return_value={"total_count": 1, "studies": [{"nct_id": "NCT001", "status": "Recruiting"}]}
    )
    agent._fda_drug_search = AsyncMock(return_value={"total": 0, "products": []})
    agent._chembl_search = AsyncMock(return_value={"total_count": 0, "molecules": []})

    # Initial state
    assert agent.is_idle
    assert agent.total_tokens_used == 0

    # Run the agent
    task = {"query": "cancer immunotherapy", "depth": "standard"}
    result = await agent.run(task)

    # Verify successful execution
    assert result.success is True
    assert agent.is_complete
    assert result.execution_time_ms >= 0

    # Verify output structure
    assert "summary" in result.data
    assert result.data["query"] == "cancer immunotherapy"
    assert result.data["summary"]["pubmed_article_count"] == 1
    assert result.data["summary"]["clinical_trials_count"] == 1

    # Verify tools were called
    agent._pubmed_search.assert_called_once()
    agent._pubmed_fetch_details.assert_called_once_with(["12345"])

    # Test validation failure
    agent.status = AgentStatus.IDLE
    invalid_result = await agent.run({"no_query": "field"})
    assert invalid_result.success is False
    assert "validation" in (invalid_result.error or "").lower()
