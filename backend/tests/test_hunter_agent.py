"""Tests for HunterAgent module."""

from typing import Any
from unittest.mock import MagicMock

import pytest


def test_hunter_agent_has_name_and_description() -> None:
    """Test HunterAgent has correct name and description class attributes."""
    from src.agents.hunter import HunterAgent

    assert HunterAgent.name == "Hunter Pro"
    assert HunterAgent.description == "Discovers and qualifies new leads based on ICP"


def test_hunter_agent_extends_base_agent() -> None:
    """Test HunterAgent extends BaseAgent."""
    from src.agents.base import BaseAgent
    from src.agents.hunter import HunterAgent

    assert issubclass(HunterAgent, BaseAgent)


def test_hunter_agent_initializes_with_llm_and_user() -> None:
    """Test HunterAgent initializes with llm_client, user_id, and _company_cache."""
    from src.agents.base import AgentStatus
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    assert agent.llm == mock_llm
    assert agent.user_id == "user-123"
    assert agent.status == AgentStatus.IDLE
    assert hasattr(agent, "_company_cache")
    assert agent._company_cache == {}


def test_hunter_agent_registers_tools() -> None:
    """Test HunterAgent._register_tools returns dict with 6 tools."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    tools = agent.tools

    assert len(tools) == 6
    assert "search_companies" in tools
    assert "enrich_company" in tools
    assert "find_contacts" in tools
    assert "score_fit" in tools
    assert "find_similar_companies" in tools
    assert "search_territory_leads" in tools


def test_validate_input_accepts_valid_task() -> None:
    """Test validate_input returns True for valid task with all required fields."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "icp": {"industry": "Biotechnology"},
        "target_count": 10,
    }

    assert agent.validate_input(task) is True


def test_validate_input_requires_icp() -> None:
    """Test validate_input returns False when icp is missing."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "target_count": 10,
    }

    assert agent.validate_input(task) is False


def test_validate_input_requires_target_count() -> None:
    """Test validate_input returns False when target_count is missing."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "icp": {"industry": "Biotechnology"},
    }

    assert agent.validate_input(task) is False


def test_validate_input_allows_optional_exclusions() -> None:
    """Test validate_input accepts valid task with optional exclusions list."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "icp": {"industry": "Biotechnology"},
        "target_count": 10,
        "exclusions": ["competitor1.com", "competitor2.com"],
    }

    assert agent.validate_input(task) is True


def test_validate_input_validates_icp_has_industry() -> None:
    """Test validate_input returns False when icp lacks industry field."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "icp": {"size": "large"},  # Missing industry
        "target_count": 10,
    }

    assert agent.validate_input(task) is False


def test_validate_input_validates_target_count_is_positive() -> None:
    """Test validate_input returns False when target_count is not positive."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    # Test with zero
    task_zero = {
        "icp": {"industry": "Biotechnology"},
        "target_count": 0,
    }
    assert agent.validate_input(task_zero) is False

    # Test with negative number
    task_negative = {
        "icp": {"industry": "Biotechnology"},
        "target_count": -5,
    }
    assert agent.validate_input(task_negative) is False


# Task 3: search_companies tool tests


@pytest.mark.asyncio
async def test_search_companies_returns_list() -> None:
    """Test search_companies returns a list."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._search_companies(query="biotechnology", limit=10)

    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_search_companies_respects_limit() -> None:
    """Test search_companies respects the limit parameter."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._search_companies(query="biotechnology", limit=2)

    assert len(result) == 2


@pytest.mark.asyncio
async def test_search_companies_returns_company_dicts() -> None:
    """Test search_companies returns company dictionaries with required fields."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._search_companies(query="biotechnology", limit=10)

    assert len(result) > 0
    company = result[0]
    assert "name" in company
    assert "domain" in company
    assert "description" in company
    assert "industry" in company
    assert "size" in company
    assert "geography" in company
    assert "website" in company


@pytest.mark.asyncio
async def test_search_companies_handles_empty_query() -> None:
    """Test search_companies returns empty list for empty/whitespace query."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    # Test with empty string
    result_empty = await agent._search_companies(query="", limit=10)
    assert result_empty == []

    # Test with whitespace
    result_whitespace = await agent._search_companies(query="   ", limit=10)
    assert result_whitespace == []


@pytest.mark.asyncio
async def test_search_companies_logs_searches(caplog: Any) -> None:
    """Test search_companies logs search queries."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    with caplog.at_level("INFO"):
        await agent._search_companies(query="biotechnology", limit=5)

    assert "Searching for companies" in caplog.text
    assert "biotechnology" in caplog.text


# Task 4: enrich_company tool tests


@pytest.mark.asyncio
async def test_enrich_company_adds_technologies() -> None:
    """Test enrich_company adds technologies list."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    company = {
        "name": "Test Company",
        "domain": "testcompany.com",
        "industry": "Biotechnology",
    }

    result = await agent._enrich_company(company)

    assert "technologies" in result
    assert isinstance(result["technologies"], list)
    assert len(result["technologies"]) > 0


@pytest.mark.asyncio
async def test_enrich_company_preserves_original_fields() -> None:
    """Test enrich_company preserves all original company fields."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    company = {
        "name": "Test Company",
        "domain": "testcompany.com",
        "description": "A test company",
        "industry": "Biotechnology",
        "size": "Mid-market",
    }

    result = await agent._enrich_company(company)

    assert result["name"] == "Test Company"
    assert result["domain"] == "testcompany.com"
    assert result["description"] == "A test company"
    assert result["industry"] == "Biotechnology"
    assert result["size"] == "Mid-market"


@pytest.mark.asyncio
async def test_enrich_company_adds_linkedin_url() -> None:
    """Test enrich_company adds linkedin_url field."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    company = {
        "name": "Test Company",
        "domain": "testcompany.com",
    }

    result = await agent._enrich_company(company)

    assert "linkedin_url" in result
    assert isinstance(result["linkedin_url"], str)
    assert len(result["linkedin_url"]) > 0


@pytest.mark.asyncio
async def test_enrich_company_caches_results() -> None:
    """Test enrich_company caches results and returns same object on cache hit."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    company = {
        "name": "Test Company",
        "domain": "testcompany.com",
    }

    result1 = await agent._enrich_company(company)
    result2 = await agent._enrich_company(company)

    # Should return the exact same object from cache
    assert result1 is result2
    # Verify cache was populated
    assert "testcompany.com" in agent._company_cache


@pytest.mark.asyncio
async def test_enrich_company_adds_funding_stage() -> None:
    """Test enrich_company adds funding_stage field."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    company = {
        "name": "Test Company",
        "domain": "testcompany.com",
    }

    result = await agent._enrich_company(company)

    assert "funding_stage" in result
    assert isinstance(result["funding_stage"], str)
    assert len(result["funding_stage"]) > 0


# Task 5: find_contacts tool tests


@pytest.mark.asyncio
async def test_find_contacts_returns_list() -> None:
    """Test find_contacts returns a list."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._find_contacts(company_name="Test Company")

    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_find_contacts_returns_contact_dicts() -> None:
    """Test find_contacts returns contact dictionaries with required fields."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._find_contacts(company_name="Test Company")

    assert len(result) > 0
    contact = result[0]
    assert "name" in contact
    assert "title" in contact
    assert "email" in contact
    assert "linkedin_url" in contact
    assert "seniority" in contact
    assert "department" in contact


@pytest.mark.asyncio
async def test_find_contacts_filters_by_roles() -> None:
    """Test find_contacts filters contacts by roles (case-insensitive)."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    # Test with CEO role (uppercase)
    result_ceo = await agent._find_contacts(company_name="Test Company", roles=["CEO"])
    assert len(result_ceo) == 1
    assert "CEO" in result_ceo[0]["title"] or "Chief Executive" in result_ceo[0]["title"]

    # Test with multiple roles
    result_multiple = await agent._find_contacts(
        company_name="Test Company", roles=["CEO", "CTO"]
    )
    assert len(result_multiple) == 2
    titles = [contact["title"] for contact in result_multiple]
    assert any("CEO" in t or "Chief Executive" in t for t in titles)
    assert any("CTO" in t or "Chief Technology" in t for t in titles)

    # Test with lowercase role
    result_lowercase = await agent._find_contacts(
        company_name="Test Company", roles=["sales"]
    )
    assert len(result_lowercase) > 0
    assert any("sales" in contact["title"].lower() for contact in result_lowercase)


@pytest.mark.asyncio
async def test_find_contacts_includes_seniority() -> None:
    """Test find_contacts includes seniority field for all contacts."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._find_contacts(company_name="Test Company")

    assert len(result) > 0
    for contact in result:
        assert "seniority" in contact
        assert isinstance(contact["seniority"], str)
        assert len(contact["seniority"]) > 0


@pytest.mark.asyncio
async def test_find_contacts_includes_department() -> None:
    """Test find_contacts includes department field for all contacts."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._find_contacts(company_name="Test Company")

    assert len(result) > 0
    for contact in result:
        assert "department" in contact
        assert isinstance(contact["department"], str)
        assert len(contact["department"]) > 0


# Task 6: score_fit tool tests


@pytest.mark.asyncio
async def test_score_fit_returns_tuple() -> None:
    """Test score_fit returns a tuple of (score, reasons, gaps)."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    company = {"name": "Test Corp", "industry": "Biotechnology", "size": "Mid-market"}
    icp = {"industry": "Biotechnology", "size": "Mid-market", "geography": "North America"}

    result = await agent._score_fit(company=company, icp=icp)

    assert isinstance(result, tuple)
    assert len(result) == 3
    assert isinstance(result[0], float)  # score
    assert isinstance(result[1], list)  # fit_reasons
    assert isinstance(result[2], list)  # gaps


@pytest.mark.asyncio
async def test_score_fit_perfect_match() -> None:
    """Test score_fit returns 100.0 for perfect match with no gaps."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    company = {
        "name": "Test Corp",
        "industry": "Biotechnology",
        "size": "Mid-market",
        "geography": "North America",
        "technologies": ["Salesforce", "HubSpot", "Marketo"],
    }
    icp = {
        "industry": "Biotechnology",
        "size": "Mid-market",
        "geography": "North America",
        "technologies": ["Salesforce", "HubSpot", "Marketo"],
    }

    score, fit_reasons, gaps = await agent._score_fit(company=company, icp=icp)

    assert score == 100.0
    assert len(fit_reasons) > 0
    assert len(gaps) == 0


@pytest.mark.asyncio
async def test_score_fit_partial_match() -> None:
    """Test score_fit returns partial score with both reasons and gaps."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    company = {
        "name": "Test Corp",
        "industry": "Biotechnology",
        "size": "Enterprise",  # Mismatch
        "geography": "Europe",  # Mismatch
        "technologies": ["Salesforce"],
    }
    icp = {
        "industry": "Biotechnology",
        "size": "Mid-market",
        "geography": "North America",
        "technologies": ["Salesforce", "HubSpot", "Marketo"],
    }

    score, fit_reasons, gaps = await agent._score_fit(company=company, icp=icp)

    assert 0 < score < 100
    assert len(fit_reasons) > 0
    assert len(gaps) > 0


@pytest.mark.asyncio
async def test_score_fit_no_match() -> None:
    """Test score_fit returns low score with 3+ gaps for poor match."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    company = {
        "name": "Test Corp",
        "industry": "Retail",  # Mismatch
        "size": "Startup",  # Mismatch
        "geography": "Asia",  # Mismatch
        "technologies": ["Shopify"],
    }
    icp = {
        "industry": "Biotechnology",
        "size": "Mid-market",
        "geography": "North America",
        "technologies": ["Salesforce", "HubSpot", "Marketo"],
    }

    score, fit_reasons, gaps = await agent._score_fit(company=company, icp=icp)

    assert score < 50
    assert len(gaps) >= 3


@pytest.mark.asyncio
async def test_score_fit_technology_overlap() -> None:
    """Test score_fit calculates proportional technology overlap."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    company = {
        "name": "Test Corp",
        "industry": "Biotechnology",
        "size": "Mid-market",
        "geography": "North America",
        "technologies": ["Salesforce", "HubSpot"],  # 2 out of 3
    }
    icp = {
        "industry": "Biotechnology",
        "size": "Mid-market",
        "geography": "North America",
        "technologies": ["Salesforce", "HubSpot", "Marketo"],
    }

    score, fit_reasons, gaps = await agent._score_fit(company=company, icp=icp)

    # Technology overlap is 15% weight, 2/3 overlap = ~10 points
    # Industry match (40%) + size match (25%) + geography match (20%) + tech overlap (10%) = 95
    assert score > 90
    assert score < 100
    assert len(gaps) == 1  # Only missing Marketo


# Task 7: execute method tests


@pytest.mark.asyncio
async def test_execute_returns_agent_result() -> None:
    """Test execute returns an AgentResult instance."""
    from src.agents.base import AgentResult
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "icp": {"industry": "Biotechnology"},
        "target_count": 2,
    }

    result = await agent.execute(task)

    assert isinstance(result, AgentResult)
    assert result.success is True


@pytest.mark.asyncio
async def test_execute_returns_scored_leads() -> None:
    """Test execute returns leads with fit_score in data."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "icp": {"industry": "Biotechnology"},
        "target_count": 2,
    }

    result = await agent.execute(task)

    assert result.success is True
    assert isinstance(result.data, list)
    assert len(result.data) > 0
    lead = result.data[0]
    assert "fit_score" in lead
    assert isinstance(lead["fit_score"], float)


@pytest.mark.asyncio
async def test_execute_respects_target_count() -> None:
    """Test execute returns at most target_count leads."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "icp": {"industry": "Biotechnology"},
        "target_count": 2,
    }

    result = await agent.execute(task)

    assert result.success is True
    assert len(result.data) <= 2


@pytest.mark.asyncio
async def test_execute_filters_exclusions() -> None:
    """Test execute filters out excluded companies."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "icp": {"industry": "Biotechnology"},
        "target_count": 5,
        "exclusions": ["gentechbio.com", "bioinnovatelabs.com"],
    }

    result = await agent.execute(task)

    assert result.success is True
    # Verify no excluded domains in results
    for lead in result.data:
        assert lead["company"]["domain"] not in ["gentechbio.com", "bioinnovatelabs.com"]


@pytest.mark.asyncio
async def test_execute_enriches_companies() -> None:
    """Test execute enriches companies with additional data."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "icp": {"industry": "Biotechnology"},
        "target_count": 2,
    }

    result = await agent.execute(task)

    assert result.success is True
    assert len(result.data) > 0
    company = result.data[0]["company"]
    # Check for enrichment fields
    assert "technologies" in company
    assert "linkedin_url" in company
    assert "funding_stage" in company


@pytest.mark.asyncio
async def test_execute_finds_contacts() -> None:
    """Test execute finds contacts for each company."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "icp": {"industry": "Biotechnology"},
        "target_count": 2,
    }

    result = await agent.execute(task)

    assert result.success is True
    assert len(result.data) > 0
    lead = result.data[0]
    assert "contacts" in lead
    assert isinstance(lead["contacts"], list)
    assert len(lead["contacts"]) > 0
    contact = lead["contacts"][0]
    assert "name" in contact
    assert "title" in contact
    assert "email" in contact


@pytest.mark.asyncio
async def test_execute_scores_leads() -> None:
    """Test execute scores leads and includes fit_reasons and gaps."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "icp": {"industry": "Biotechnology"},
        "target_count": 2,
    }

    result = await agent.execute(task)

    assert result.success is True
    assert len(result.data) > 0
    lead = result.data[0]
    assert "fit_score" in lead
    assert "fit_reasons" in lead
    assert "gaps" in lead
    assert isinstance(lead["fit_score"], float)
    assert isinstance(lead["fit_reasons"], list)
    assert isinstance(lead["gaps"], list)


@pytest.mark.asyncio
async def test_execute_ranks_by_fit_score() -> None:
    """Test execute returns leads sorted by fit_score descending."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "icp": {"industry": "Biotechnology"},
        "target_count": 3,
    }

    result = await agent.execute(task)

    assert result.success is True
    if len(result.data) >= 2:
        # Verify scores are in descending order
        scores = [lead["fit_score"] for lead in result.data]
        assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_execute_includes_source() -> None:
    """Test execute includes source field in leads."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "icp": {"industry": "Biotechnology"},
        "target_count": 2,
    }

    result = await agent.execute(task)

    assert result.success is True
    assert len(result.data) > 0
    lead = result.data[0]
    assert "source" in lead
    assert lead["source"] == "hunter_pro"


# Task 8: Integration tests


@pytest.mark.asyncio
async def test_full_hunter_workflow() -> None:
    """Test complete end-to-end Hunter agent workflow with realistic ICP.

    Verifies:
    - Agent state transitions from IDLE to RUNNING to COMPLETE
    - Lead structure has all required fields
    - Company enrichment adds technologies, linkedin_url, funding_stage
    - Contacts are found with name, title, email, seniority, department
    - Scoring produces fit_score, fit_reasons, and gaps
    - Exclusions are properly filtered out
    """
    from src.agents.base import AgentStatus
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    # Verify initial state
    assert agent.status == AgentStatus.IDLE

    # Define realistic ICP
    task = {
        "icp": {
            "industry": "Biotechnology",
            "size": "Mid-market (100-500)",
            "geography": "North America",
            "technologies": ["Salesforce", "HubSpot"],
        },
        "target_count": 2,
        "exclusions": ["bioinnovatelabs.com"],  # Exclude EU company
    }

    # Execute via run() to test full lifecycle
    result = await agent.run(task)

    # Verify final state
    assert agent.status == AgentStatus.COMPLETE
    assert result.success is True

    # Verify lead structure
    leads = result.data
    assert isinstance(leads, list)
    assert len(leads) > 0

    for lead in leads:
        # Check top-level fields
        assert "company" in lead
        assert "contacts" in lead
        assert "fit_score" in lead
        assert "fit_reasons" in lead
        assert "gaps" in lead
        assert "source" in lead

        # Check company enrichment
        company = lead["company"]
        assert "technologies" in company
        assert "linkedin_url" in company
        assert "funding_stage" in company
        assert isinstance(company["technologies"], list)
        assert len(company["technologies"]) > 0

        # Check contacts
        contacts = lead["contacts"]
        assert isinstance(contacts, list)
        assert len(contacts) > 0
        for contact in contacts:
            assert "name" in contact
            assert "title" in contact
            assert "email" in contact
            assert "seniority" in contact
            assert "department" in contact

        # Check scoring
        assert isinstance(lead["fit_score"], float)
        assert 0 <= lead["fit_score"] <= 100
        assert isinstance(lead["fit_reasons"], list)
        assert isinstance(lead["gaps"], list)

        # Check source
        assert lead["source"] == "hunter_pro"

    # Verify exclusions were filtered
    domains = [lead["company"]["domain"] for lead in leads]
    assert "bioinnovatelabs.com" not in domains


@pytest.mark.asyncio
async def test_hunter_agent_handles_validation_failure() -> None:
    """Test that invalid input returns failed result with validation error.

    Verifies that when validate_input returns False:
    - Agent status transitions to FAILED
    - AgentResult has success=False
    - Error message indicates validation failure
    """
    from src.agents.base import AgentStatus
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    # Test with missing required field (no icp)
    invalid_task = {
        "target_count": 5,
    }

    result = await agent.run(invalid_task)

    # Verify failure state
    assert agent.status == AgentStatus.FAILED
    assert result.success is False
    assert result.error == "Input validation failed"
    assert result.data is None


@pytest.mark.asyncio
async def test_hunter_agent_caches_enrichment() -> None:
    """Test that company enrichment cache is populated and reused across runs.

    Verifies:
    - Cache is empty before first enrichment
    - Cache is populated after first enrichment
    - Same enriched company object is returned on cache hit
    - Cache works across multiple execute calls
    """
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    # Verify cache starts empty
    assert agent._company_cache == {}

    # Execute task - should populate cache
    task = {
        "icp": {"industry": "Biotechnology"},
        "target_count": 2,
    }

    result1 = await agent.execute(task)
    assert result1.success is True

    # Cache should now contain entries for the companies
    # Note: mock_companies has domains gentechbio.com, pharmacorpsolutions.com, bioinnovatelabs.com
    # With target_count=2, we might get up to 2 companies cached
    assert len(agent._company_cache) > 0

    # Get the first cached company for verification
    first_domain = list(agent._company_cache.keys())[0]
    first_cached = agent._company_cache[first_domain]

    # Execute again with same task
    result2 = await agent.execute(task)
    assert result2.success is True

    # Cache should still contain the same entries
    assert len(agent._company_cache) > 0
    assert first_domain in agent._company_cache

    # Verify the cached object is the same (identity check)
    # This proves cache is being reused, not re-enriched
    assert agent._company_cache[first_domain] is first_cached

    # Verify enrichment fields are present in cached data
    assert "technologies" in first_cached
    assert "linkedin_url" in first_cached
    assert "funding_stage" in first_cached
