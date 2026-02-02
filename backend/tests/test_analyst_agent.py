"""Tests for AnalystAgent module."""

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


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
        "esearchresult": {
            "idlist": ["12345", "67890"],
            "count": "2"
        }
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
