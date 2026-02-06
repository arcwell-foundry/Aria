"""Tests for US-914: First Conversation Generator (Intelligence Demonstration)."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.onboarding.first_conversation import (
    FirstConversationGenerator,
    FirstConversationMessage,
)

# --- Fixtures ---


def _mock_execute(data: Any) -> MagicMock:
    """Build a mock .execute() result."""
    result = MagicMock()
    result.data = data
    return result


def _build_chain(execute_return: Any) -> MagicMock:
    """Build a fluent Supabase query chain ending in .execute()."""
    chain = MagicMock()
    chain.select.return_value = chain
    chain.insert.return_value = chain
    chain.update.return_value = chain
    chain.eq.return_value = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain
    chain.maybe_single.return_value = chain
    chain.single.return_value = chain
    chain.execute.return_value = _mock_execute(execute_return)
    return chain


SAMPLE_FACTS: list[dict[str, Any]] = [
    {
        "fact": "Acme Pharma has 500 employees",
        "confidence": 0.95,
        "source": "enrichment_website",
        "metadata": {"category": "company"},
    },
    {
        "fact": "CEO is Jane Smith, appointed 2023",
        "confidence": 0.92,
        "source": "enrichment_website",
        "metadata": {"category": "leadership"},
    },
    {
        "fact": "Main product is XR-200 oncology platform",
        "confidence": 0.90,
        "source": "document_upload",
        "metadata": {"category": "product"},
    },
    {
        "fact": "Series C funding of $120M in Q2 2024",
        "confidence": 0.88,
        "source": "enrichment_news",
        "metadata": {"category": "funding"},
    },
    {
        "fact": "Competitor BioGenX launched rival therapy last month",
        "confidence": 0.82,
        "source": "enrichment_news",
        "metadata": {"category": "competitive"},
    },
    {
        "fact": "Partnership with Roche for distribution",
        "confidence": 0.85,
        "source": "enrichment_website",
        "metadata": {"category": "partnership"},
    },
]

SAMPLE_GAPS: list[dict[str, Any]] = [
    {
        "task": "Identify pricing model for XR-200",
        "metadata": {"type": "knowledge_gap", "priority": "high"},
    },
    {
        "task": "Map key decision makers in sales org",
        "metadata": {"type": "knowledge_gap", "priority": "critical"},
    },
]


@pytest.fixture()
def mock_db() -> MagicMock:
    """Create a mock Supabase client."""
    return MagicMock()


@pytest.fixture()
def generator(mock_db: MagicMock) -> FirstConversationGenerator:
    """Create a FirstConversationGenerator with mocked DB."""
    with patch("src.onboarding.first_conversation.SupabaseClient") as mock_cls:
        mock_cls.get_client.return_value = mock_db
        gen = FirstConversationGenerator()
    return gen


def _setup_db_for_generate(
    mock_db: MagicMock,
    facts: list[dict[str, Any]] | None = None,
    profile: dict[str, Any] | None = None,
    company: dict[str, Any] | None = None,
    gaps: list[dict[str, Any]] | None = None,
    goal: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
) -> None:
    """Wire up mock_db.table() calls for the full generate flow."""

    def table_router(table_name: str) -> MagicMock:
        if table_name == "memory_semantic":
            return _build_chain(facts if facts is not None else SAMPLE_FACTS)
        if table_name == "user_profiles":
            return _build_chain(
                profile
                if profile is not None
                else {"full_name": "Jane Smith", "company_id": "comp-1"}
            )
        if table_name == "companies":
            return _build_chain(
                company
                if company is not None
                else {
                    "settings": {
                        "classification": {
                            "company_type": "pharma",
                            "segment": "mid-market",
                        }
                    }
                }
            )
        if table_name == "memory_prospective":
            return _build_chain(gaps if gaps is not None else SAMPLE_GAPS)
        if table_name == "goals":
            return _build_chain(
                goal if goal is not None else {"title": "Prepare for Pfizer meeting next week"}
            )
        if table_name == "user_settings":
            return _build_chain(settings)
        if table_name in ("conversations", "messages"):
            return _build_chain([{"id": "conv-1"}])
        return _build_chain(None)

    mock_db.table.side_effect = table_router


# --- Message generation with facts ---


@pytest.mark.asyncio()
async def test_generate_produces_message_with_facts(
    generator: FirstConversationGenerator,
    mock_db: MagicMock,
) -> None:
    """Generate produces a FirstConversationMessage referencing available facts."""
    _setup_db_for_generate(mock_db)

    with (
        patch.object(
            generator._llm,
            "generate_response",
            new_callable=AsyncMock,
            return_value="Hi Jane, I've been looking into Acme Pharma...",
        ),
        patch("src.memory.episodic.EpisodicMemory"),
    ):
        message = await generator.generate("user-1")

    assert isinstance(message, FirstConversationMessage)
    assert message.content
    assert message.facts_referenced > 0
    assert message.confidence_level in ("high", "moderate", "limited")
    assert message.suggested_next_action


@pytest.mark.asyncio()
async def test_generate_high_confidence_with_many_facts(
    generator: FirstConversationGenerator,
    mock_db: MagicMock,
) -> None:
    """Confidence is 'high' when more than 15 facts are available."""
    many_facts = SAMPLE_FACTS * 3  # 18 facts
    _setup_db_for_generate(mock_db, facts=many_facts)

    with (
        patch.object(
            generator._llm,
            "generate_response",
            new_callable=AsyncMock,
            return_value="Hi Jane, impressive research pipeline...",
        ),
        patch("src.memory.episodic.EpisodicMemory"),
    ):
        message = await generator.generate("user-1")

    assert message.confidence_level == "high"


@pytest.mark.asyncio()
async def test_generate_moderate_confidence_with_some_facts(
    generator: FirstConversationGenerator,
    mock_db: MagicMock,
) -> None:
    """Confidence is 'moderate' when 6-15 facts are available."""
    _setup_db_for_generate(mock_db, facts=SAMPLE_FACTS)  # 6 facts

    with (
        patch.object(
            generator._llm,
            "generate_response",
            new_callable=AsyncMock,
            return_value="Hi Jane, I've gathered some initial findings...",
        ),
        patch("src.memory.episodic.EpisodicMemory"),
    ):
        message = await generator.generate("user-1")

    assert message.confidence_level == "moderate"


# --- Surprising fact identification ---


@pytest.mark.asyncio()
async def test_identify_surprising_fact_calls_llm(
    generator: FirstConversationGenerator,
) -> None:
    """Surprising fact identification sends facts to LLM and returns result."""
    with patch.object(
        generator._llm,
        "generate_response",
        new_callable=AsyncMock,
        return_value="Series C funding of $120M in Q2 2024",
    ) as mock_llm:
        result = await generator._identify_surprising_fact(SAMPLE_FACTS, {"company_type": "pharma"})

    assert result == "Series C funding of $120M in Q2 2024"
    mock_llm.assert_called_once()


@pytest.mark.asyncio()
async def test_identify_surprising_fact_returns_none_with_no_facts(
    generator: FirstConversationGenerator,
) -> None:
    """Returns None when no facts are available."""
    result = await generator._identify_surprising_fact([], None)
    assert result is None


@pytest.mark.asyncio()
async def test_identify_surprising_fact_falls_back_on_llm_failure(
    generator: FirstConversationGenerator,
) -> None:
    """Falls back to highest-confidence fact when LLM call fails."""
    with patch.object(
        generator._llm,
        "generate_response",
        new_callable=AsyncMock,
        side_effect=Exception("API error"),
    ):
        result = await generator._identify_surprising_fact(SAMPLE_FACTS, None)

    assert result == SAMPLE_FACTS[0]["fact"]


# --- Style calibration ---


def test_style_guidance_direct_formal(
    generator: FirstConversationGenerator,
) -> None:
    """Direct + formal style produces appropriate guidance."""
    style = {"directness": 0.8, "formality_index": 0.8}
    guidance = generator._build_style_guidance(style)

    assert "direct" in guidance.lower()
    assert "formal" in guidance.lower()


def test_style_guidance_warm_casual(
    generator: FirstConversationGenerator,
) -> None:
    """Warm + casual style produces appropriate guidance."""
    style = {"directness": 0.2, "formality_index": 0.2}
    guidance = generator._build_style_guidance(style)

    assert "warm" in guidance.lower() or "diplomatic" in guidance.lower()
    assert "casual" in guidance.lower() or "conversational" in guidance.lower()


def test_style_guidance_default_when_none(
    generator: FirstConversationGenerator,
) -> None:
    """Default balanced style when no Digital Twin data available."""
    guidance = generator._build_style_guidance(None)
    assert "balanced" in guidance.lower()


def test_style_guidance_default_when_middle_values(
    generator: FirstConversationGenerator,
) -> None:
    """Default balanced style when values are in the middle range."""
    style = {"directness": 0.5, "formality_index": 0.5}
    guidance = generator._build_style_guidance(style)
    assert "balanced" in guidance.lower()


# --- Message storage ---


@pytest.mark.asyncio()
async def test_store_first_message_creates_conversation_and_message(
    generator: FirstConversationGenerator,
    mock_db: MagicMock,
) -> None:
    """First message is stored as conversation + message in DB."""
    conv_chain = _build_chain([{"id": "conv-123"}])
    msg_chain = _build_chain([{"id": "msg-456"}])

    def table_router(table_name: str) -> MagicMock:
        if table_name == "conversations":
            return conv_chain
        if table_name == "messages":
            return msg_chain
        return _build_chain(None)

    mock_db.table.side_effect = table_router

    message = FirstConversationMessage(
        content="Hi Jane, I noticed something interesting...",
        memory_delta={"facts_stated": ["fact1"]},
        suggested_next_action="Review company profile",
        facts_referenced=5,
        confidence_level="moderate",
    )

    await generator._store_first_message("user-1", message)

    # Verify conversation was created
    conv_chain.insert.assert_called_once()
    insert_data = conv_chain.insert.call_args[0][0]
    assert insert_data["user_id"] == "user-1"
    assert insert_data["metadata"]["type"] == "first_conversation"

    # Verify message was created
    msg_chain.insert.assert_called_once()
    msg_data = msg_chain.insert.call_args[0][0]
    assert msg_data["conversation_id"] == "conv-123"
    assert msg_data["role"] == "assistant"
    assert msg_data["metadata"]["type"] == "first_conversation"
    assert msg_data["metadata"]["facts_referenced"] == 5


@pytest.mark.asyncio()
async def test_store_first_message_handles_db_failure(
    generator: FirstConversationGenerator,
    mock_db: MagicMock,
) -> None:
    """Store gracefully handles database failures."""
    mock_db.table.side_effect = Exception("DB error")

    message = FirstConversationMessage(
        content="Hi there",
        memory_delta={},
        suggested_next_action="Review",
        facts_referenced=0,
        confidence_level="limited",
    )

    # Should not raise
    await generator._store_first_message("user-1", message)


# --- Memory delta structure ---


def test_memory_delta_groups_by_confidence(
    generator: FirstConversationGenerator,
) -> None:
    """Memory delta groups facts into confidence tiers."""
    facts: list[dict[str, Any]] = [
        {"fact": "Stated fact", "confidence": 0.97},
        {"fact": "Inferred fact", "confidence": 0.85},
        {"fact": "Uncertain fact", "confidence": 0.65},
    ]

    delta = generator._build_memory_delta(facts, None, [])

    assert "Stated fact" in delta["facts_stated"]
    assert "Inferred fact" in delta["facts_inferred"]
    assert "Uncertain fact" in delta["facts_uncertain"]


def test_memory_delta_includes_classification(
    generator: FirstConversationGenerator,
) -> None:
    """Memory delta includes company classification data."""
    classification = {"company_type": "cdmo", "segment": "enterprise"}

    delta = generator._build_memory_delta([], classification, [])

    assert delta["classification"]["company_type"] == "cdmo"


def test_memory_delta_includes_gaps(
    generator: FirstConversationGenerator,
) -> None:
    """Memory delta includes knowledge gap descriptions."""
    gaps: list[dict[str, Any]] = [
        {"task": "Find pricing model"},
        {"task": "Map decision makers"},
    ]

    delta = generator._build_memory_delta([], None, gaps)

    assert "Find pricing model" in delta["gaps"]
    assert "Map decision makers" in delta["gaps"]


# --- Zero-facts graceful handling ---


@pytest.mark.asyncio()
async def test_generate_with_zero_facts(
    generator: FirstConversationGenerator,
    mock_db: MagicMock,
) -> None:
    """Generates a limited-confidence message gracefully with no facts."""
    _setup_db_for_generate(
        mock_db,
        facts=[],
        profile={"full_name": "Bob Jones", "company_id": None},
        company=None,
        gaps=[],
        goal=None,
        settings=None,
    )

    with (
        patch.object(
            generator._llm,
            "generate_response",
            new_callable=AsyncMock,
            return_value="Hi Bob, I'm getting set up and ready to learn...",
        ),
        patch("src.memory.episodic.EpisodicMemory"),
    ):
        message = await generator.generate("user-2")

    assert message.confidence_level == "limited"
    assert message.facts_referenced == 0
    assert message.content


# --- Fallback message ---


@pytest.mark.asyncio()
async def test_fallback_message_on_llm_failure(
    generator: FirstConversationGenerator,
    mock_db: MagicMock,
) -> None:
    """Fallback message is generated when LLM fails."""
    _setup_db_for_generate(mock_db)

    with (
        patch.object(
            generator._llm,
            "generate_response",
            new_callable=AsyncMock,
            side_effect=Exception("LLM unavailable"),
        ),
        patch("src.memory.episodic.EpisodicMemory"),
    ):
        message = await generator.generate("user-1")

    assert message.content
    assert "Hi Jane" in message.content
    assert "findings" in message.content.lower() or "gathered" in message.content.lower()


def test_fallback_message_with_no_user_name(
    generator: FirstConversationGenerator,
) -> None:
    """Fallback message works without a user name."""
    result = generator._build_fallback_message("", [], [], "")
    assert result.startswith("Hi,")


def test_fallback_message_with_goal(
    generator: FirstConversationGenerator,
) -> None:
    """Fallback message includes goal when available."""
    result = generator._build_fallback_message(
        "Jane", SAMPLE_FACTS, [], "Prepare for Pfizer meeting"
    )
    assert "Pfizer meeting" in result


def test_fallback_message_with_gaps(
    generator: FirstConversationGenerator,
) -> None:
    """Fallback message mentions learning areas when gaps exist."""
    result = generator._build_fallback_message("Jane", [], SAMPLE_GAPS, "")
    assert "learn more" in result.lower()


# --- Episodic event recording ---


@pytest.mark.asyncio()
async def test_episodic_event_recorded(
    generator: FirstConversationGenerator,
    mock_db: MagicMock,
) -> None:
    """Episodic memory event is recorded after generation."""
    _setup_db_for_generate(mock_db)
    mock_episodic = MagicMock()
    mock_episodic.store_episode = AsyncMock()

    with (
        patch.object(
            generator._llm,
            "generate_response",
            new_callable=AsyncMock,
            return_value="Hi Jane...",
        ),
        patch(
            "src.memory.episodic.EpisodicMemory",
            return_value=mock_episodic,
        ),
    ):
        await generator.generate("user-1")

    mock_episodic.store_episode.assert_called_once()
    episode = mock_episodic.store_episode.call_args[0][0]
    assert episode.event_type == "first_conversation_delivered"
    assert episode.user_id == "user-1"
    assert "insights" in episode.content


@pytest.mark.asyncio()
async def test_episodic_failure_does_not_block_generation(
    generator: FirstConversationGenerator,
    mock_db: MagicMock,
) -> None:
    """Generation succeeds even if episodic recording fails."""
    _setup_db_for_generate(mock_db)
    mock_episodic = MagicMock()
    mock_episodic.store_episode = AsyncMock(side_effect=Exception("Graphiti down"))

    with (
        patch.object(
            generator._llm,
            "generate_response",
            new_callable=AsyncMock,
            return_value="Hi Jane...",
        ),
        patch(
            "src.memory.episodic.EpisodicMemory",
            return_value=mock_episodic,
        ),
    ):
        message = await generator.generate("user-1")

    assert message.content == "Hi Jane..."


# --- Data fetcher edge cases ---


@pytest.mark.asyncio()
async def test_get_classification_returns_none_when_no_company(
    generator: FirstConversationGenerator,
    mock_db: MagicMock,
) -> None:
    """Classification returns None when user has no company_id."""
    mock_db.table.return_value = _build_chain({"full_name": "Test", "company_id": None})

    result = await generator._get_classification("user-1")
    assert result is None


@pytest.mark.asyncio()
async def test_get_writing_style_returns_none_when_no_settings(
    generator: FirstConversationGenerator,
    mock_db: MagicMock,
) -> None:
    """Writing style returns None when no user settings exist."""
    mock_db.table.return_value = _build_chain(None)

    result = await generator._get_writing_style("user-1")
    assert result is None


@pytest.mark.asyncio()
async def test_get_writing_style_extracts_digital_twin(
    generator: FirstConversationGenerator,
    mock_db: MagicMock,
) -> None:
    """Writing style extracts Digital Twin style from nested preferences."""
    mock_db.table.return_value = _build_chain(
        {
            "preferences": {
                "digital_twin": {
                    "writing_style": {
                        "directness": 0.8,
                        "formality_index": 0.3,
                    }
                }
            }
        }
    )

    result = await generator._get_writing_style("user-1")

    assert result is not None
    assert result["directness"] == 0.8
    assert result["formality_index"] == 0.3
