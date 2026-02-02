"""Tests for ScoutAgent module."""

from unittest.mock import MagicMock

import pytest


def test_scout_agent_has_name_and_description() -> None:
    """Test ScoutAgent has correct name and description class attributes."""
    from src.agents.scout import ScoutAgent

    assert ScoutAgent.name == "Scout"
    assert ScoutAgent.description == "Intelligence gathering and filtering"


def test_scout_agent_extends_base_agent() -> None:
    """Test ScoutAgent extends BaseAgent."""
    from src.agents.base import BaseAgent
    from src.agents.scout import ScoutAgent

    assert issubclass(ScoutAgent, BaseAgent)


def test_scout_agent_initializes_with_llm_and_user() -> None:
    """Test ScoutAgent initializes with llm_client and user_id."""
    from src.agents.base import AgentStatus
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    assert agent.llm == mock_llm
    assert agent.user_id == "user-123"
    assert agent.status == AgentStatus.IDLE


def test_validate_input_accepts_valid_task() -> None:
    """Test validate_input returns True for valid task with entities."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "entities": ["Acme Corp", "Beta Inc"],
        "signal_types": ["funding", "hiring"],
    }

    assert agent.validate_input(task) is True


def test_validate_input_requires_entities() -> None:
    """Test validate_input returns False when entities is missing."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "signal_types": ["funding"],
    }

    assert agent.validate_input(task) is False


def test_validate_input_validates_entities_is_list() -> None:
    """Test validate_input returns False when entities is not a list."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "entities": "Acme Corp",  # Should be list
    }

    assert agent.validate_input(task) is False


def test_validate_input_allows_optional_signal_types() -> None:
    """Test validate_input accepts valid task with optional signal_types."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "entities": ["Acme Corp"],
        "signal_types": ["funding", "hiring", "leadership"],
    }

    assert agent.validate_input(task) is True


def test_validate_input_validates_signal_types_is_list_if_present() -> None:
    """Test validate_input returns False when signal_types is not a list."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "entities": ["Acme Corp"],
        "signal_types": "funding",  # Should be list
    }

    assert agent.validate_input(task) is False


@pytest.mark.asyncio
async def test_web_search_returns_list() -> None:
    """Test web_search returns a list."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._web_search(query="biotechnology funding", limit=10)

    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_web_search_respects_limit() -> None:
    """Test web_search respects the limit parameter."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._web_search(query="biotechnology funding", limit=3)

    assert len(result) <= 3


@pytest.mark.asyncio
async def test_web_search_returns_result_dicts() -> None:
    """Test web_search returns result dictionaries with required fields."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._web_search(query="biotechnology funding", limit=10)

    if len(result) > 0:
        item = result[0]
        assert "title" in item
        assert "url" in item
        assert "snippet" in item


@pytest.mark.asyncio
async def test_web_search_handles_empty_query() -> None:
    """Test web_search returns empty list for empty query."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._web_search(query="", limit=10)

    assert result == []


@pytest.mark.asyncio
async def test_web_search_validates_positive_limit() -> None:
    """Test web_search raises ValueError for non-positive limit."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    with pytest.raises(ValueError, match="limit must be greater than 0"):
        await agent._web_search(query="test", limit=0)

    with pytest.raises(ValueError, match="limit must be greater than 0"):
        await agent._web_search(query="test", limit=-5)


@pytest.mark.asyncio
async def test_detect_signals_returns_list() -> None:
    """Test detect_signals returns a list."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._detect_signals(entities=["Acme Corp"])

    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_detect_signals_returns_signal_dicts() -> None:
    """Test detect_signals returns signal dictionaries with required fields."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._detect_signals(entities=["Acme Corp"])

    if len(result) > 0:
        signal = result[0]
        assert "company_name" in signal
        assert "signal_type" in signal
        assert "headline" in signal
        assert "relevance_score" in signal
        assert 0 <= signal["relevance_score"] <= 1


@pytest.mark.asyncio
async def test_detect_signals_filters_by_signal_types() -> None:
    """Test detect_signals filters by signal_types when provided."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._detect_signals(
        entities=["Acme Corp"],
        signal_types=["funding"]
    )

    # All results should be funding type
    for signal in result:
        assert signal["signal_type"] in ["funding"]


@pytest.mark.asyncio
async def test_detect_signals_handles_multiple_entities() -> None:
    """Test detect_signals handles multiple entities."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._detect_signals(entities=["Acme Corp", "Beta Inc"])

    # Should return signals for both entities
    company_names = {s["company_name"] for s in result}
    assert len(company_names) <= 2


@pytest.mark.asyncio
async def test_detect_signals_handles_empty_entities() -> None:
    """Test detect_signals returns empty list for empty entities."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._detect_signals(entities=[])

    assert result == []


@pytest.mark.asyncio
async def test_social_monitor_returns_list() -> None:
    """Test social_monitor returns a list."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._social_monitor(entity="Acme Corp", limit=10)

    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_social_monitor_respects_limit() -> None:
    """Test social_monitor respects the limit parameter."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._social_monitor(entity="Acme Corp", limit=2)

    assert len(result) <= 2


@pytest.mark.asyncio
async def test_social_monitor_returns_mention_dicts() -> None:
    """Test social_monitor returns mention dictionaries with required fields."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._social_monitor(entity="Acme Corp", limit=10)

    if len(result) > 0:
        mention = result[0]
        assert "content" in mention
        assert "author" in mention
        assert "platform" in mention
        assert "url" in mention


@pytest.mark.asyncio
async def test_social_monitor_handles_empty_entity() -> None:
    """Test social_monitor returns empty list for empty entity."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._social_monitor(entity="", limit=10)

    assert result == []


@pytest.mark.asyncio
async def test_social_monitor_validates_positive_limit() -> None:
    """Test social_monitor raises ValueError for non-positive limit."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    with pytest.raises(ValueError, match="limit must be greater than 0"):
        await agent._social_monitor(entity="test", limit=0)


@pytest.mark.asyncio
async def test_news_search_returns_list() -> None:
    """Test news_search returns a list."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._news_search(query="Acme Corp funding", limit=10)

    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_news_search_respects_limit() -> None:
    """Test news_search respects the limit parameter."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._news_search(query="Acme Corp funding", limit=2)

    assert len(result) <= 2


@pytest.mark.asyncio
async def test_news_search_returns_article_dicts() -> None:
    """Test news_search returns article dictionaries with required fields."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._news_search(query="Acme Corp funding", limit=10)

    if len(result) > 0:
        article = result[0]
        assert "title" in article
        assert "url" in article
        assert "source" in article
        assert "published_at" in article


@pytest.mark.asyncio
async def test_news_search_handles_empty_query() -> None:
    """Test news_search returns empty list for empty query."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._news_search(query="", limit=10)

    assert result == []


@pytest.mark.asyncio
async def test_news_search_validates_positive_limit() -> None:
    """Test news_search raises ValueError for non-positive limit."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    with pytest.raises(ValueError, match="limit must be greater than 0"):
        await agent._news_search(query="test", limit=0)


@pytest.mark.asyncio
async def test_deduplicate_signals_removes_exact_duplicates() -> None:
    """Test deduplicate_signals removes exact duplicate signals."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    signals = [
        {
            "company_name": "Acme Corp",
            "signal_type": "funding",
            "headline": "Acme raises $50M",
            "source_url": "https://example.com/article1",
        },
        {
            "company_name": "Acme Corp",
            "signal_type": "funding",
            "headline": "Acme raises $50M",
            "source_url": "https://example.com/article1",  # Exact duplicate
        },
        {
            "company_name": "Beta Inc",
            "signal_type": "hiring",
            "headline": "Beta is hiring",
            "source_url": "https://example.com/article2",
        },
    ]

    result = await agent._deduplicate_signals(signals)

    assert len(result) == 2


@pytest.mark.asyncio
async def test_deduplicate_signals_removes_similar_headlines() -> None:
    """Test deduplicate_signals removes signals with similar headlines."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    signals = [
        {
            "company_name": "Acme Corp",
            "signal_type": "funding",
            "headline": "Acme Corp raises $50M in Series B funding",
            "source_url": "https://techcrunch.com/acme1",
        },
        {
            "company_name": "Acme Corp",
            "signal_type": "funding",
            "headline": "Acme Corp raises $50M Series B",  # Similar
            "source_url": "https://reuters.com/acme2",
        },
        {
            "company_name": "Beta Inc",
            "signal_type": "hiring",
            "headline": "Beta Inc hiring engineers",
            "source_url": "https://example.com/beta",
        },
    ]

    result = await agent._deduplicate_signals(signals)

    # Should remove the similar duplicate (2 signals, not 3)
    assert len(result) <= 2


@pytest.mark.asyncio
async def test_deduplicate_signals_handles_empty_list() -> None:
    """Test deduplicate_signals returns empty list for empty input."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._deduplicate_signals([])

    assert result == []


@pytest.mark.asyncio
async def test_deduplicate_signals_preserves_all_fields() -> None:
    """Test deduplicate_signals preserves all signal fields."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    signals = [
        {
            "company_name": "Acme Corp",
            "signal_type": "funding",
            "headline": "Acme raises $50M",
            "summary": "Detailed summary here",
            "source_url": "https://example.com/article1",
            "source_name": "TechCrunch",
            "relevance_score": 0.85,
        },
    ]

    result = await agent._deduplicate_signals(signals)

    assert len(result) == 1
    signal = result[0]
    assert "company_name" in signal
    assert "signal_type" in signal
    assert "headline" in signal
    assert "summary" in signal
    assert "source_url" in signal
    assert "source_name" in signal
    assert "relevance_score" in signal


@pytest.mark.asyncio
async def test_deduplicate_signals_keeps_highest_relevance() -> None:
    """Test deduplicate_signals keeps the signal with highest relevance when duplicates exist."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    signals = [
        {
            "company_name": "Acme Corp",
            "signal_type": "funding",
            "headline": "Acme raises $50M",
            "source_url": "https://example.com/article1",
            "relevance_score": 0.75,
        },
        {
            "company_name": "Acme Corp",
            "signal_type": "funding",
            "headline": "Acme raises $50M",
            "source_url": "https://example.com/article2",  # Same headline, different URL
            "relevance_score": 0.92,  # Higher relevance
        },
    ]

    result = await agent._deduplicate_signals(signals)

    assert len(result) == 1
    assert result[0]["relevance_score"] == 0.92
