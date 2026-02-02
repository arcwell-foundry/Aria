"""Tests for HunterAgent module."""

import pytest
from unittest.mock import MagicMock


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


def test_hunter_agent_registers_four_tools() -> None:
    """Test HunterAgent._register_tools returns dict with 4 tools."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    tools = agent.tools

    assert len(tools) == 4
    assert "search_companies" in tools
    assert "enrich_company" in tools
    assert "find_contacts" in tools
    assert "score_fit" in tools


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
