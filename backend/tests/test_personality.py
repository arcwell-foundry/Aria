"""Tests for personality module."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.companion.personality import (
    OpinionResult,
    PersonalityProfile,
    PersonalityService,
    TraitLevel,
)


# ── TraitLevel Tests ─────────────────────────────────────────────────────────


def test_trait_level_enum_values() -> None:
    """Test TraitLevel enum has expected values."""
    assert TraitLevel.LOW == 1
    assert TraitLevel.MODERATE == 2
    assert TraitLevel.HIGH == 3


def test_trait_level_can_be_used_as_int() -> None:
    """Test TraitLevel can be compared as an integer."""
    assert TraitLevel.LOW < TraitLevel.MODERATE
    assert TraitLevel.MODERATE < TraitLevel.HIGH
    assert int(TraitLevel.HIGH) == 3


# ── PersonalityProfile Tests ─────────────────────────────────────────────────


def test_default_profile_returned() -> None:
    """Test that default profile has expected values."""
    profile = PersonalityProfile()

    # Default ARIA personality
    assert profile.directness == 3  # HIGH
    assert profile.warmth == 2  # MODERATE
    assert profile.assertiveness == 2  # MODERATE
    assert profile.humor == 2  # MODERATE
    assert profile.formality == 1  # LOW
    assert profile.adapted_for_user is False
    assert profile.adaptation_notes == ""


def test_profile_validation_rejects_invalid_values() -> None:
    """Test that profile rejects trait values outside 1-3 range."""
    with pytest.raises(ValueError, match="directness must be between 1 and 3"):
        PersonalityProfile(directness=0)

    with pytest.raises(ValueError, match="warmth must be between 1 and 3"):
        PersonalityProfile(warmth=4)


def test_profile_to_dict() -> None:
    """Test PersonalityProfile.to_dict serializes correctly."""
    profile = PersonalityProfile(
        directness=3,
        warmth=2,
        assertiveness=2,
        humor=1,
        formality=3,
        adapted_for_user=True,
        adaptation_notes="Increased formality for enterprise user",
    )

    data = profile.to_dict()

    assert data["directness"] == 3
    assert data["warmth"] == 2
    assert data["assertiveness"] == 2
    assert data["humor"] == 1
    assert data["formality"] == 3
    assert data["adapted_for_user"] is True
    assert data["adaptation_notes"] == "Increased formality for enterprise user"


def test_profile_from_dict() -> None:
    """Test PersonalityProfile.from_dict creates correct instance."""
    data = {
        "directness": 2,
        "warmth": 3,
        "assertiveness": 1,
        "humor": 2,
        "formality": 2,
        "adapted_for_user": True,
        "adaptation_notes": "Test notes",
    }

    profile = PersonalityProfile.from_dict(data)

    assert profile.directness == 2
    assert profile.warmth == 3
    assert profile.assertiveness == 1
    assert profile.humor == 2
    assert profile.formality == 2
    assert profile.adapted_for_user is True
    assert profile.adaptation_notes == "Test notes"


def test_profile_from_dict_with_defaults() -> None:
    """Test PersonalityProfile.from_dict uses defaults for missing fields."""
    profile = PersonalityProfile.from_dict({})

    assert profile.directness == 3  # Default
    assert profile.warmth == 2
    assert profile.assertiveness == 2
    assert profile.humor == 2
    assert profile.formality == 1
    assert profile.adapted_for_user is False
    assert profile.adaptation_notes == ""


# ── OpinionResult Tests ──────────────────────────────────────────────────────


def test_opinion_result_default_values() -> None:
    """Test OpinionResult has sensible defaults."""
    result = OpinionResult(has_opinion=True)

    assert result.has_opinion is True
    assert result.opinion == ""
    assert result.confidence == 0.0
    assert result.supporting_evidence == []
    assert result.should_push_back is False
    assert result.pushback_reason == ""


def test_opinion_result_to_dict() -> None:
    """Test OpinionResult.to_dict serializes correctly."""
    result = OpinionResult(
        has_opinion=True,
        opinion="This approach has risks",
        confidence=0.85,
        supporting_evidence=["Evidence 1", "Evidence 2"],
        should_push_back=True,
        pushback_reason="Previous failures with similar approach",
    )

    data = result.to_dict()

    assert data["has_opinion"] is True
    assert data["opinion"] == "This approach has risks"
    assert data["confidence"] == 0.85
    assert data["supporting_evidence"] == ["Evidence 1", "Evidence 2"]
    assert data["should_push_back"] is True
    assert data["pushback_reason"] == "Previous failures with similar approach"


def test_opinion_result_from_dict() -> None:
    """Test OpinionResult.from_dict creates correct instance."""
    data = {
        "has_opinion": True,
        "opinion": "Test opinion",
        "confidence": 0.75,
        "supporting_evidence": ["Fact 1"],
        "should_push_back": True,
        "pushback_reason": "Test reason",
    }

    result = OpinionResult.from_dict(data)

    assert result.has_opinion is True
    assert result.opinion == "Test opinion"
    assert result.confidence == 0.75
    assert result.supporting_evidence == ["Fact 1"]
    assert result.should_push_back is True
    assert result.pushback_reason == "Test reason"


# ── PersonalityService Tests ─────────────────────────────────────────────────


@pytest.fixture
def mock_supabase_client() -> MagicMock:
    """Create a mock SupabaseClient for testing."""
    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    return mock_client


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Create a mock LLMClient for testing."""
    mock = MagicMock()
    mock.generate_response = AsyncMock()
    return mock


@pytest.fixture
def mock_semantic_memory() -> MagicMock:
    """Create a mock SemanticMemory for testing."""
    mock = MagicMock()
    mock.search_facts = AsyncMock(return_value=[])
    return mock


@pytest.fixture
def mock_episodic_memory() -> MagicMock:
    """Create a mock EpisodicMemory for testing."""
    mock = MagicMock()
    mock.semantic_search = AsyncMock(return_value=[])
    return mock


class TestPersonalityService:
    """Tests for PersonalityService class."""

    @pytest.mark.asyncio
    async def test_get_profile_returns_default_when_not_found(
        self,
        mock_supabase_client: MagicMock,
    ) -> None:
        """Test that get_profile returns default profile when user has none."""
        # Setup mock to return empty data
        mock_table = MagicMock()
        mock_table.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_supabase_client.table.return_value = mock_table

        with (
            patch(
                "src.companion.personality.SupabaseClient.get_client",
                return_value=mock_supabase_client,
            ),
            patch("src.companion.personality.LLMClient"),
            patch("src.companion.personality.SemanticMemory"),
            patch("src.companion.personality.EpisodicMemory"),
        ):
            service = PersonalityService()
            profile = await service.get_profile("user-123")

        assert profile.directness == 3
        assert profile.warmth == 2
        assert profile.adapted_for_user is False

    @pytest.mark.asyncio
    async def test_get_profile_returns_stored_profile(
        self,
        mock_supabase_client: MagicMock,
    ) -> None:
        """Test that get_profile returns stored profile when it exists."""
        # Setup mock to return stored profile
        mock_table = MagicMock()
        mock_table.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "directness": 2,
                    "warmth": 3,
                    "assertiveness": 1,
                    "humor": 2,
                    "formality": 3,
                    "adapted_for_user": True,
                    "adaptation_notes": "Custom profile",
                }
            ]
        )
        mock_supabase_client.table.return_value = mock_table

        with (
            patch(
                "src.companion.personality.SupabaseClient.get_client",
                return_value=mock_supabase_client,
            ),
            patch("src.companion.personality.LLMClient"),
            patch("src.companion.personality.SemanticMemory"),
            patch("src.companion.personality.EpisodicMemory"),
        ):
            service = PersonalityService()
            profile = await service.get_profile("user-123")

        assert profile.directness == 2
        assert profile.warmth == 3
        assert profile.assertiveness == 1
        assert profile.adapted_for_user is True
        assert profile.adaptation_notes == "Custom profile"

    @pytest.mark.asyncio
    async def test_opinion_formation_without_facts_returns_none(
        self,
        mock_supabase_client: MagicMock,
        mock_semantic_memory: MagicMock,
    ) -> None:
        """Test that opinion formation returns None when no facts found."""
        mock_semantic_memory.search_facts = AsyncMock(return_value=[])

        with (
            patch(
                "src.companion.personality.SupabaseClient.get_client",
                return_value=mock_supabase_client,
            ),
            patch("src.companion.personality.LLMClient"),
            patch(
                "src.companion.personality.SemanticMemory",
                return_value=mock_semantic_memory,
            ),
            patch("src.companion.personality.EpisodicMemory"),
        ):
            service = PersonalityService()
            result = await service.form_opinion("user-123", "Some topic")

        assert result is None

    @pytest.mark.asyncio
    async def test_opinion_formation_with_facts(
        self,
        mock_supabase_client: MagicMock,
        mock_semantic_memory: MagicMock,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test opinion formation when facts exist."""
        from src.memory.semantic import FactSource, SemanticFact

        # Create mock facts
        now = datetime.now(UTC)
        facts = [
            SemanticFact(
                id="fact-1",
                user_id="user-123",
                subject="Lonza",
                predicate="pricing",
                object="Premium pricing strategy",
                confidence=0.9,
                source=FactSource.USER_STATED,
                valid_from=now,
            ),
        ]
        mock_semantic_memory.search_facts = AsyncMock(return_value=facts)

        # Mock LLM response
        opinion_json = json.dumps({
            "has_opinion": True,
            "opinion": "Lonza uses premium pricing",
            "confidence": 0.85,
            "supporting_evidence": ["Lonza pricing Premium pricing strategy"],
            "should_push_back": False,
            "pushback_reason": "",
        })
        mock_llm_client.generate_response = AsyncMock(return_value=opinion_json)

        with (
            patch(
                "src.companion.personality.SupabaseClient.get_client",
                return_value=mock_supabase_client,
            ),
            patch("src.companion.personality.LLMClient", return_value=mock_llm_client),
            patch(
                "src.companion.personality.SemanticMemory",
                return_value=mock_semantic_memory,
            ),
            patch("src.companion.personality.EpisodicMemory"),
        ):
            service = PersonalityService()
            result = await service.form_opinion("user-123", "Lonza pricing")

        assert result is not None
        assert result.has_opinion is True
        assert "Lonza" in result.opinion
        assert result.confidence > 0

    @pytest.mark.asyncio
    async def test_pushback_not_generated_when_not_warranted(
        self,
        mock_supabase_client: MagicMock,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test pushback is not generated when should_push_back is False."""
        opinion = OpinionResult(
            has_opinion=True,
            opinion="This is fine",
            confidence=0.7,
            supporting_evidence=[],
            should_push_back=False,
            pushback_reason="",
        )

        with (
            patch(
                "src.companion.personality.SupabaseClient.get_client",
                return_value=mock_supabase_client,
            ),
            patch("src.companion.personality.LLMClient", return_value=mock_llm_client),
            patch("src.companion.personality.SemanticMemory"),
            patch("src.companion.personality.EpisodicMemory"),
        ):
            service = PersonalityService()
            pushback = await service.generate_pushback(
                "user-123",
                "User statement",
                opinion,
            )

        assert pushback is None
        # LLM should not be called
        mock_llm_client.generate_response.assert_not_called()

    @pytest.mark.asyncio
    async def test_pushback_generation(
        self,
        mock_supabase_client: MagicMock,
        mock_llm_client: MagicMock,
        mock_episodic_memory: MagicMock,
    ) -> None:
        """Test pushback is generated when warranted."""
        opinion = OpinionResult(
            has_opinion=True,
            opinion="This approach has failed before",
            confidence=0.9,
            supporting_evidence=["Past project failure in Q2"],
            should_push_back=True,
            pushback_reason="Similar approach failed previously",
        )

        mock_llm_client.generate_response = AsyncMock(
            return_value="Honestly? I'd push back on that. We tried this in Q2 and it didn't work out."
        )

        with (
            patch(
                "src.companion.personality.SupabaseClient.get_client",
                return_value=mock_supabase_client,
            ),
            patch("src.companion.personality.LLMClient", return_value=mock_llm_client),
            patch("src.companion.personality.SemanticMemory"),
            patch(
                "src.companion.personality.EpisodicMemory",
                return_value=mock_episodic_memory,
            ),
        ):
            service = PersonalityService()
            pushback = await service.generate_pushback(
                "user-123",
                "Let's try approach X",
                opinion,
            )

        assert pushback is not None
        assert "Honestly" in pushback or "push back" in pushback.lower()

    @pytest.mark.asyncio
    async def test_opinion_stored_in_db(
        self,
        mock_supabase_client: MagicMock,
    ) -> None:
        """Test that opinions are correctly persisted to database."""
        opinion = OpinionResult(
            has_opinion=True,
            opinion="Test opinion",
            confidence=0.8,
            supporting_evidence=["Evidence 1"],
            should_push_back=False,
            pushback_reason="",
        )

        mock_table = MagicMock()
        mock_table.insert.return_value.execute.return_value = MagicMock(data=[{"id": "opinion-123"}])
        mock_supabase_client.table.return_value = mock_table

        with (
            patch(
                "src.companion.personality.SupabaseClient.get_client",
                return_value=mock_supabase_client,
            ),
            patch("src.companion.personality.LLMClient"),
            patch("src.companion.personality.SemanticMemory"),
            patch("src.companion.personality.EpisodicMemory"),
        ):
            service = PersonalityService()
            opinion_id = await service.record_opinion(
                "user-123",
                "Test topic",
                opinion,
            )

        assert opinion_id is not None
        mock_table.insert.assert_called_once()
        call_args = mock_table.insert.call_args[0][0]
        assert call_args["user_id"] == "user-123"
        assert call_args["topic"] == "Test topic"
        assert call_args["opinion"] == "Test opinion"

    @pytest.mark.asyncio
    async def test_update_pushback_outcome(
        self,
        mock_supabase_client: MagicMock,
    ) -> None:
        """Test updating pushback outcome."""
        mock_table = MagicMock()
        mock_table.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "opinion-123"}]
        )
        mock_supabase_client.table.return_value = mock_table

        with (
            patch(
                "src.companion.personality.SupabaseClient.get_client",
                return_value=mock_supabase_client,
            ),
            patch("src.companion.personality.LLMClient"),
            patch("src.companion.personality.SemanticMemory"),
            patch("src.companion.personality.EpisodicMemory"),
        ):
            service = PersonalityService()
            await service.update_pushback_outcome("opinion-123", user_accepted=True)

        mock_table.update.assert_called_once()
        call_args = mock_table.update.call_args[0][0]
        assert call_args["user_accepted_pushback"] is True

    @pytest.mark.asyncio
    async def test_adapt_personality_reduces_assertiveness(
        self,
        mock_supabase_client: MagicMock,
    ) -> None:
        """Test personality adaptation reduces assertiveness for low acceptance."""
        # Mock different tables with different responses
        table_calls: list[str] = []

        def mock_table_factory(table_name: str) -> MagicMock:
            table_calls.append(table_name)
            mock_table = MagicMock()

            if table_name == "companion_opinions":
                # Opinions table - low acceptance rate data
                mock_result = MagicMock(
                    data=[
                        {"user_accepted_pushback": False},
                        {"user_accepted_pushback": False},
                        {"user_accepted_pushback": False},
                        {"user_accepted_pushback": True},
                        {"user_accepted_pushback": False},
                    ]
                )
                # Build the chain: select -> eq -> not_.is_ -> order -> limit -> execute
                # MagicMock handles any attribute access, so just set the final execute
                mock_table.select.return_value.eq.return_value.not_.is_.return_value.order.return_value.limit.return_value.execute.return_value = mock_result
            elif table_name == "companion_personality_profiles":
                # Profile table - no stored profile (return default)
                mock_table.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[]
                )

            mock_table.upsert.return_value.execute.return_value = MagicMock(data=[{}])
            return mock_table

        mock_supabase_client.table.side_effect = mock_table_factory

        with (
            patch(
                "src.companion.personality.SupabaseClient.get_client",
                return_value=mock_supabase_client,
            ),
            patch("src.companion.personality.LLMClient"),
            patch("src.companion.personality.SemanticMemory"),
            patch("src.companion.personality.EpisodicMemory"),
        ):
            service = PersonalityService()
            profile = await service.adapt_personality("user-123")

        # Verify the opinions table was accessed
        assert "companion_opinions" in table_calls, f"Tables accessed: {table_calls}"

        # With 20% acceptance, assertiveness should decrease
        assert profile.assertiveness < 2  # Default is 2
        assert profile.adapted_for_user is True
