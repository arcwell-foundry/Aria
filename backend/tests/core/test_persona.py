"""Tests for PersonaBuilder — centralized system prompt assembly.

Covers all 6 layers, caching, feedback storage, and cross-agent consistency.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.persona import (
    LAYER_1_CORE_IDENTITY,
    LAYER_2_PERSONALITY_TRAITS,
    LAYER_3_ANTI_PATTERNS,
    PersonaBuilder,
    PersonaContext,
    PersonaRequest,
    get_persona_builder,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def builder() -> PersonaBuilder:
    return PersonaBuilder()


def _mock_calibration(tone_guidance: str = "Be direct.", example_adjustments: list[str] | None = None):
    """Return a mock PersonalityCalibration."""
    cal = MagicMock()
    cal.tone_guidance = tone_guidance
    cal.example_adjustments = example_adjustments or ["Say 'I recommend' not 'perhaps consider'"]
    return cal


def _mock_fingerprint():
    """Return a mock WritingStyleFingerprint."""
    fp = MagicMock()
    fp.average_sentence_length = 14.5
    return fp


def _mock_aria_config(role: str = "bd_sales", areas: list[str] | None = None):
    """Return a mock ARIA config dict."""
    return {
        "role": role,
        "custom_role_description": None,
        "domain_focus": {
            "therapeutic_areas": areas or ["oncology"],
            "modalities": [],
            "geographies": ["US"],
        },
        "competitor_watchlist": ["Novartis"],
    }


def _patch_l4_dependencies(
    calibration=None,
    fingerprint=None,
    style_guidelines=None,
    aria_config=None,
    preferences=None,
    calibration_error=None,
    fingerprint_error=None,
    config_error=None,
    db_error=None,
):
    """Context manager that patches all 4 L4 data sources.

    Since _cached_user_context does local imports, we patch the source modules.
    """
    import contextlib

    @contextlib.asynccontextmanager
    async def _ctx():
        with (
            patch("src.onboarding.personality_calibrator.PersonalityCalibrator.get_calibration",
                  new_callable=AsyncMock,
                  side_effect=calibration_error,
                  return_value=calibration) as _mock_cal,
            patch("src.memory.digital_twin.DigitalTwin.get_fingerprint",
                  new_callable=AsyncMock,
                  side_effect=fingerprint_error,
                  return_value=fingerprint) as _mock_fp,
            patch("src.memory.digital_twin.DigitalTwin.get_style_guidelines",
                  new_callable=AsyncMock,
                  return_value=style_guidelines or "") as _mock_style,
            patch("src.services.aria_config_service.ARIAConfigService.get_config",
                  new_callable=AsyncMock,
                  side_effect=config_error,
                  return_value=aria_config or {}) as _mock_config,
            patch("src.db.supabase.SupabaseClient.get_client") as mock_db,
        ):
            if db_error:
                mock_db.side_effect = db_error
            else:
                mock_result = MagicMock()
                mock_result.data = {"preferences": preferences or {}}
                mock_db.return_value.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = mock_result
            yield

    return _ctx()


# ---------------------------------------------------------------------------
# TestPersonaBuilder
# ---------------------------------------------------------------------------

class TestPersonaBuilder:
    """Tests for the main build() flow."""

    @pytest.mark.asyncio
    async def test_build_returns_all_six_layers(self, builder: PersonaBuilder) -> None:
        """All six layer fields should be populated (L4-L6 may be empty strings)."""
        with patch.object(builder, "_cached_user_context", new_callable=AsyncMock, return_value=""):
            ctx = await builder.build(PersonaRequest(user_id="u1"))

        assert ctx.core_identity == LAYER_1_CORE_IDENTITY
        assert ctx.personality_traits == LAYER_2_PERSONALITY_TRAITS
        assert ctx.anti_patterns == LAYER_3_ANTI_PATTERNS
        assert isinstance(ctx.user_context, str)
        assert isinstance(ctx.agent_context, str)
        assert isinstance(ctx.relationship_context, str)
        assert ctx.user_id == "u1"

    @pytest.mark.asyncio
    async def test_layers_1_3_are_static(self, builder: PersonaBuilder) -> None:
        """L1-L3 are the same regardless of user_id or agent."""
        with patch.object(builder, "_cached_user_context", new_callable=AsyncMock, return_value=""):
            ctx_a = await builder.build(PersonaRequest(user_id="u1", agent_name="scribe"))
            ctx_b = await builder.build(PersonaRequest(user_id="u2", agent_name="hunter"))

        assert ctx_a.core_identity == ctx_b.core_identity
        assert ctx_a.personality_traits == ctx_b.personality_traits
        assert ctx_a.anti_patterns == ctx_b.anti_patterns

    @pytest.mark.asyncio
    async def test_layer_4_includes_calibration(self, builder: PersonaBuilder) -> None:
        """Tone guidance from PersonalityCalibration appears in L4."""
        cal = _mock_calibration(tone_guidance="Be concise and warm.")

        async with _patch_l4_dependencies(calibration=cal):
            result = await builder._cached_user_context.__wrapped__(builder, "u1")

        assert "Be concise and warm." in result

    @pytest.mark.asyncio
    async def test_layer_4_includes_writing_style(self, builder: PersonaBuilder) -> None:
        """DigitalTwin style guidelines appear in L4 when fingerprint exists."""
        fp = _mock_fingerprint()

        async with _patch_l4_dependencies(
            fingerprint=fp,
            style_guidelines="Use medium-length sentences.",
        ):
            result = await builder._cached_user_context.__wrapped__(builder, "u1")

        assert "Writing Style Fingerprint" in result
        assert "Use medium-length sentences." in result

    @pytest.mark.asyncio
    async def test_layer_4_includes_aria_config(self, builder: PersonaBuilder) -> None:
        """ARIA role and domain focus appear in L4."""
        config = _mock_aria_config(role="bd_sales", areas=["oncology"])

        async with _patch_l4_dependencies(aria_config=config):
            result = await builder._cached_user_context.__wrapped__(builder, "u1")

        assert "bd_sales" in result
        assert "oncology" in result

    @pytest.mark.asyncio
    async def test_layer_4_includes_persona_overrides(self, builder: PersonaBuilder) -> None:
        """Feedback-stored overrides appear in L4."""
        async with _patch_l4_dependencies(
            preferences={
                "persona_overrides": {
                    "tone_adjustments": ["be more concise"],
                    "anti_patterns": ["never mention competitors"],
                }
            }
        ):
            result = await builder._cached_user_context.__wrapped__(builder, "u1")

        assert "be more concise" in result
        assert "never mention competitors" in result

    @pytest.mark.asyncio
    async def test_layer_4_graceful_on_no_data(self, builder: PersonaBuilder) -> None:
        """L4 returns empty string when all sources fail or return None."""
        async with _patch_l4_dependencies(
            calibration_error=Exception("DB down"),
            fingerprint_error=Exception("Graphiti down"),
            config_error=Exception("Config fail"),
            db_error=Exception("Supabase down"),
        ):
            result = await builder._cached_user_context.__wrapped__(builder, "u1")

        assert result == ""

    @pytest.mark.asyncio
    async def test_layer_4_caching(self, builder: PersonaBuilder) -> None:
        """Second call within TTL should use cached L4."""
        mock_ctx = "## Communication Style Calibration\n\nBe direct."

        with patch.object(builder, "_cached_user_context", new_callable=AsyncMock, return_value=mock_ctx):
            ctx1 = await builder.build(PersonaRequest(user_id="u1"))
            ctx2 = await builder.build(PersonaRequest(user_id="u1"))

        # Both should have the same user_context
        assert ctx1.user_context == ctx2.user_context
        assert ctx1.user_context == mock_ctx

    @pytest.mark.asyncio
    async def test_layer_5_agent_context(self, builder: PersonaBuilder) -> None:
        """Agent name and task description appear in L5."""
        with patch.object(builder, "_cached_user_context", new_callable=AsyncMock, return_value=""):
            ctx = await builder.build(
                PersonaRequest(
                    user_id="u1",
                    agent_name="strategist",
                    agent_role_description="Creates competitive battle cards",
                    task_description="Generate battle card for BioGenix vs Novartis",
                    output_format="json",
                )
            )

        assert "Strategist" in ctx.agent_context
        assert "battle card" in ctx.agent_context.lower()
        assert "json" in ctx.agent_context.lower()

    @pytest.mark.asyncio
    async def test_layer_5_empty_without_agent(self, builder: PersonaBuilder) -> None:
        """L5 is empty when agent_name is None."""
        with patch.object(builder, "_cached_user_context", new_callable=AsyncMock, return_value=""):
            ctx = await builder.build(PersonaRequest(user_id="u1"))

        assert ctx.agent_context == ""

    @pytest.mark.asyncio
    async def test_layer_6_opt_in(self, builder: PersonaBuilder) -> None:
        """L6 is empty when include_relationship_context is False (default)."""
        with patch.object(builder, "_cached_user_context", new_callable=AsyncMock, return_value=""):
            ctx = await builder.build(PersonaRequest(user_id="u1"))

        assert ctx.relationship_context == ""

    @pytest.mark.asyncio
    async def test_layer_6_queries_memory(self, builder: PersonaBuilder) -> None:
        """L6 queries MemoryQueryService when enabled."""
        mock_results = [
            {
                "id": "m1",
                "memory_type": "episodic",
                "content": "Met Dr. Smith at BioGenix last week",
                "confidence": 0.9,
            }
        ]

        with patch.object(builder, "_cached_user_context", new_callable=AsyncMock, return_value=""):
            with patch("src.api.routes.memory.MemoryQueryService") as MockMem:
                MockMem.return_value.query = AsyncMock(return_value=mock_results)

                ctx = await builder.build(
                    PersonaRequest(
                        user_id="u1",
                        include_relationship_context=True,
                        recipient_name="Dr. Smith",
                        account_name="BioGenix",
                    )
                )

        assert "Dr. Smith" in ctx.relationship_context
        assert "BioGenix" in ctx.relationship_context

    @pytest.mark.asyncio
    async def test_to_system_prompt_joins_layers(self, builder: PersonaBuilder) -> None:
        """Non-empty layers are joined with double newlines."""
        ctx = PersonaContext(
            core_identity="L1",
            personality_traits="L2",
            anti_patterns="L3",
            user_context="L4",
            agent_context="L5",
            relationship_context="L6",
            user_id="u1",
        )
        prompt = ctx.to_system_prompt()

        assert "L1\n\nL2\n\nL3\n\nL4\n\nL5\n\nL6" == prompt

    @pytest.mark.asyncio
    async def test_to_system_prompt_skips_empty(self, builder: PersonaBuilder) -> None:
        """Empty layers are omitted from the joined prompt."""
        ctx = PersonaContext(
            core_identity="L1",
            personality_traits="L2",
            anti_patterns="L3",
            user_context="",
            agent_context="",
            relationship_context="",
            user_id="u1",
        )
        prompt = ctx.to_system_prompt()

        assert prompt == "L1\n\nL2\n\nL3"
        assert "\n\n\n" not in prompt

    @pytest.mark.asyncio
    async def test_anti_patterns_present(self, builder: PersonaBuilder) -> None:
        """L3 includes key anti-patterns."""
        assert "doesn't" in LAYER_3_ANTI_PATTERNS
        assert 'As an AI' in LAYER_3_ANTI_PATTERNS
        assert 'enthusiasm' in LAYER_3_ANTI_PATTERNS
        assert 'emojis' in LAYER_3_ANTI_PATTERNS


# ---------------------------------------------------------------------------
# TestUpdatePersonaFromFeedback
# ---------------------------------------------------------------------------

class TestUpdatePersonaFromFeedback:
    """Tests for persona feedback storage."""

    @pytest.mark.asyncio
    async def test_tone_adjustment_stored(self, builder: PersonaBuilder) -> None:
        """Tone adjustment feedback is appended to persona_overrides."""
        mock_result = MagicMock()
        mock_result.data = {"preferences": {"persona_overrides": {"tone_adjustments": []}}}
        mock_table = MagicMock()
        mock_table.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = mock_result
        mock_table.update.return_value.eq.return_value.execute.return_value = MagicMock()

        with patch("src.db.supabase.SupabaseClient.get_client") as mock_db:
            mock_db.return_value.table.return_value = mock_table
            with patch("src.core.persona.invalidate_cache"):
                await builder.update_persona_from_feedback(
                    user_id="u1",
                    feedback_type="tone_adjustment",
                    feedback_data={"adjustment": "be more concise"},
                )

        # Verify the update was called with the adjustment
        update_call = mock_table.update.call_args
        prefs = update_call[0][0]["preferences"]
        assert "be more concise" in prefs["persona_overrides"]["tone_adjustments"]

    @pytest.mark.asyncio
    async def test_anti_pattern_stored(self, builder: PersonaBuilder) -> None:
        """Anti-pattern feedback is appended to persona_overrides."""
        mock_result = MagicMock()
        mock_result.data = {"preferences": {"persona_overrides": {"anti_patterns": []}}}
        mock_table = MagicMock()
        mock_table.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = mock_result
        mock_table.update.return_value.eq.return_value.execute.return_value = MagicMock()

        with patch("src.db.supabase.SupabaseClient.get_client") as mock_db:
            mock_db.return_value.table.return_value = mock_table
            with patch("src.core.persona.invalidate_cache"):
                await builder.update_persona_from_feedback(
                    user_id="u1",
                    feedback_type="anti_pattern",
                    feedback_data={"pattern": "never use bullet points"},
                )

        update_call = mock_table.update.call_args
        prefs = update_call[0][0]["preferences"]
        assert "never use bullet points" in prefs["persona_overrides"]["anti_patterns"]

    @pytest.mark.asyncio
    async def test_cache_invalidated(self, builder: PersonaBuilder) -> None:
        """L4 cache is cleared after feedback update."""
        mock_result = MagicMock()
        mock_result.data = {"preferences": {}}
        mock_table = MagicMock()
        mock_table.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = mock_result
        mock_table.update.return_value.eq.return_value.execute.return_value = MagicMock()

        with patch("src.db.supabase.SupabaseClient.get_client") as mock_db:
            mock_db.return_value.table.return_value = mock_table
            with patch("src.core.persona.invalidate_cache") as mock_invalidate:
                await builder.update_persona_from_feedback(
                    user_id="u1",
                    feedback_type="tone_adjustment",
                    feedback_data={"adjustment": "test"},
                )

        mock_invalidate.assert_called_once_with(
            "_cached_user_context", key="persona_l4:u1"
        )

    @pytest.mark.asyncio
    async def test_get_persona_description(self, builder: PersonaBuilder) -> None:
        """Returns dict with identity, traits, adaptations, current_agent."""
        with patch.object(builder, "_cached_user_context", new_callable=AsyncMock, return_value="Custom tone."):
            desc = await builder.get_persona_description("u1")

        assert "identity" in desc
        assert "traits" in desc
        assert "adaptations" in desc
        assert "current_agent" in desc
        assert "Custom tone." in desc["adaptations"]


# ---------------------------------------------------------------------------
# TestConsistencyAcrossAgents
# ---------------------------------------------------------------------------

class TestConsistencyAcrossAgents:
    """Integration tests for cross-agent persona consistency."""

    @pytest.mark.asyncio
    async def test_same_user_consistent_persona(self, builder: PersonaBuilder) -> None:
        """Build for strategist and scribe: L1-L4 must be identical, L5 differs."""
        mock_l4 = "## User Configuration\n\nrole: bd_sales"

        with patch.object(builder, "_cached_user_context", new_callable=AsyncMock, return_value=mock_l4):
            ctx_strategist = await builder.build(
                PersonaRequest(
                    user_id="u1",
                    agent_name="strategist",
                    task_description="Generate battle card",
                )
            )
            ctx_scribe = await builder.build(
                PersonaRequest(
                    user_id="u1",
                    agent_name="scribe",
                    task_description="Draft follow-up email",
                )
            )

        # L1-L4 identical
        assert ctx_strategist.core_identity == ctx_scribe.core_identity
        assert ctx_strategist.personality_traits == ctx_scribe.personality_traits
        assert ctx_strategist.anti_patterns == ctx_scribe.anti_patterns
        assert ctx_strategist.user_context == ctx_scribe.user_context

        # L5 differs
        assert ctx_strategist.agent_context != ctx_scribe.agent_context
        assert "Strategist" in ctx_strategist.agent_context
        assert "Scribe" in ctx_scribe.agent_context


# ---------------------------------------------------------------------------
# TestSingleton
# ---------------------------------------------------------------------------

class TestSingleton:
    """Tests for get_persona_builder singleton."""

    def test_singleton_returns_same_instance(self) -> None:
        """get_persona_builder returns the same instance on repeated calls."""
        # Reset singleton for test isolation
        import src.core.persona as persona_mod
        persona_mod._persona_builder = None

        b1 = get_persona_builder()
        b2 = get_persona_builder()
        assert b1 is b2

        # Clean up
        persona_mod._persona_builder = None
