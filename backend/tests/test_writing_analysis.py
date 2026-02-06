"""Tests for WritingAnalysisService (US-906).

Covers:
- Empty samples return low-confidence fingerprint
- Multiple samples analyzed correctly (mock LLM)
- Fingerprint stored in user_settings
- Readiness score updated
- Episodic event recorded
- Get fingerprint returns stored data
- LLM parse failure produces fallback fingerprint
- Code-fenced JSON responses handled
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.onboarding.writing_analysis import (
    WritingAnalysisService,
    WritingStyleFingerprint,
)

# --- Model tests ---


class TestWritingStyleFingerprint:
    """Tests for the WritingStyleFingerprint Pydantic model."""

    def test_default_values(self):
        """Test that defaults produce a valid fingerprint."""
        fp = WritingStyleFingerprint()
        assert fp.avg_sentence_length == 0.0
        assert fp.paragraph_style == "medium"
        assert fp.formality_index == 0.5
        assert fp.confidence == 0.0
        assert fp.style_summary == ""

    def test_round_trip_serialization(self):
        """Test model_dump and reconstruction preserve all fields."""
        fp = WritingStyleFingerprint(
            avg_sentence_length=14.5,
            sentence_length_variance=3.2,
            paragraph_style="short_punchy",
            lexical_diversity=0.72,
            formality_index=0.8,
            vocabulary_sophistication="advanced",
            uses_em_dashes=True,
            uses_semicolons=False,
            exclamation_frequency="occasional",
            ellipsis_usage=True,
            opening_style="Hi [Name],",
            closing_style="Best regards",
            directness=0.7,
            warmth=0.6,
            assertiveness=0.8,
            data_driven=True,
            hedging_frequency="low",
            emoji_usage="rare",
            rhetorical_style="analytical",
            style_summary="Direct and data-driven writer.",
            confidence=0.85,
        )
        data = fp.model_dump()
        restored = WritingStyleFingerprint(**data)
        assert restored == fp

    def test_partial_construction(self):
        """Test creating fingerprint with only some fields."""
        fp = WritingStyleFingerprint(
            style_summary="Partial analysis.",
            confidence=0.4,
        )
        assert fp.style_summary == "Partial analysis."
        assert fp.confidence == 0.4
        # defaults fill in
        assert fp.directness == 0.5


# --- Service tests ---


def _make_llm_response() -> str:
    """Build a valid LLM JSON response for testing."""
    return json.dumps(
        {
            "avg_sentence_length": 16.2,
            "sentence_length_variance": 4.1,
            "paragraph_style": "medium",
            "lexical_diversity": 0.68,
            "formality_index": 0.75,
            "vocabulary_sophistication": "advanced",
            "uses_em_dashes": True,
            "uses_semicolons": True,
            "exclamation_frequency": "rare",
            "ellipsis_usage": False,
            "opening_style": "Hi [Name],",
            "closing_style": "Best,",
            "directness": 0.7,
            "warmth": 0.55,
            "assertiveness": 0.65,
            "data_driven": True,
            "hedging_frequency": "low",
            "emoji_usage": "never",
            "rhetorical_style": "analytical",
            "style_summary": "Direct, data-driven communicator with formal tone.",
            "confidence": 0.82,
        }
    )


def _make_service_with_mocks() -> tuple[WritingAnalysisService, MagicMock, MagicMock]:
    """Create a WritingAnalysisService with mocked LLM and DB.

    Returns:
        Tuple of (service, mock_llm, mock_db_client).
    """
    service = WritingAnalysisService.__new__(WritingAnalysisService)

    # Mock LLM
    mock_llm = AsyncMock()
    mock_llm.generate_response = AsyncMock(return_value=_make_llm_response())
    service.llm = mock_llm

    # Mock episodic
    mock_episodic = AsyncMock()
    mock_episodic.store_episode = AsyncMock(return_value="episode-id")
    service.episodic = mock_episodic

    # Mock DB client
    mock_db = MagicMock()
    mock_select_query = MagicMock()
    mock_select_query.eq.return_value = mock_select_query
    mock_select_query.maybe_single.return_value = mock_select_query
    mock_select_query.execute.return_value = MagicMock(data={"preferences": {}})
    mock_db.table.return_value.select.return_value = mock_select_query

    mock_update_query = MagicMock()
    mock_update_query.eq.return_value = mock_update_query
    mock_update_query.execute.return_value = MagicMock(data=[{}])
    mock_db.table.return_value.update.return_value = mock_update_query

    return service, mock_llm, mock_db


class TestWritingAnalysisServiceAnalyze:
    """Tests for WritingAnalysisService.analyze_samples."""

    @pytest.mark.asyncio
    async def test_empty_samples_returns_zero_confidence(self):
        """Empty sample list returns fingerprint with zero confidence."""
        service, _, _ = _make_service_with_mocks()
        fp = await service.analyze_samples("user-123", [])
        assert fp.confidence == 0.0
        assert fp.style_summary == "No samples provided yet."

    @pytest.mark.asyncio
    async def test_analyze_calls_llm_with_samples(self):
        """Service calls LLM with combined sample text."""
        service, mock_llm, mock_db = _make_service_with_mocks()

        samples = [
            "Hi John, I wanted to follow up on the Q3 pipeline review.",
            "Dear team, attached is the competitive analysis for Moderna.",
        ]

        with (
            patch("src.onboarding.writing_analysis.SupabaseClient") as mock_supa,
            patch("src.onboarding.writing_analysis.log_memory_operation", new_callable=AsyncMock),
        ):
            mock_supa.get_client.return_value = mock_db
            with patch.object(service, "_update_readiness", new_callable=AsyncMock):
                fp = await service.analyze_samples("user-123", samples)

        # LLM was called
        mock_llm.generate_response.assert_called_once()
        call_args = mock_llm.generate_response.call_args
        prompt_text = call_args[1].get("messages", call_args[0][0] if call_args[0] else [])[0][
            "content"
        ]
        assert "Hi John" in prompt_text
        assert "Moderna" in prompt_text

        # Fingerprint parsed correctly
        assert fp.confidence == 0.82
        assert fp.directness == 0.7
        assert fp.vocabulary_sophistication == "advanced"
        assert fp.uses_em_dashes is True

    @pytest.mark.asyncio
    async def test_analyze_stores_fingerprint_in_user_settings(self):
        """Fingerprint is stored in user_settings.preferences.digital_twin."""
        service, _, mock_db = _make_service_with_mocks()

        with (
            patch("src.onboarding.writing_analysis.SupabaseClient") as mock_supa,
            patch("src.onboarding.writing_analysis.log_memory_operation", new_callable=AsyncMock),
        ):
            mock_supa.get_client.return_value = mock_db
            with patch.object(service, "_update_readiness", new_callable=AsyncMock):
                await service.analyze_samples("user-123", ["Sample text here."])

        # Verify update was called on user_settings
        mock_db.table.assert_any_call("user_settings")
        update_call = mock_db.table.return_value.update
        assert update_call.called
        update_data = update_call.call_args[0][0]
        prefs = update_data["preferences"]
        assert "digital_twin" in prefs
        assert "writing_style" in prefs["digital_twin"]
        ws = prefs["digital_twin"]["writing_style"]
        assert ws["confidence"] == 0.82

    @pytest.mark.asyncio
    async def test_analyze_updates_readiness_score(self):
        """Readiness score for digital_twin is updated after analysis."""
        service, _, mock_db = _make_service_with_mocks()

        mock_orch = MagicMock()
        mock_orch.update_readiness_scores = AsyncMock()

        with (
            patch("src.onboarding.writing_analysis.SupabaseClient") as mock_supa,
            patch("src.onboarding.writing_analysis.log_memory_operation", new_callable=AsyncMock),
            patch(
                "src.onboarding.orchestrator.OnboardingOrchestrator",
                return_value=mock_orch,
            ),
        ):
            mock_supa.get_client.return_value = mock_db
            await service.analyze_samples("user-123", ["Sample text."])

        # Readiness updated: confidence 0.82 * 40 = 32.8
        mock_orch.update_readiness_scores.assert_called_once_with(
            "user-123", {"digital_twin": pytest.approx(32.8, abs=0.1)}
        )

    @pytest.mark.asyncio
    async def test_analyze_records_episodic_event(self):
        """Episodic memory event is recorded with sample count."""
        service, _, mock_db = _make_service_with_mocks()

        with (
            patch("src.onboarding.writing_analysis.SupabaseClient") as mock_supa,
            patch("src.onboarding.writing_analysis.log_memory_operation", new_callable=AsyncMock),
        ):
            mock_supa.get_client.return_value = mock_db
            with patch.object(service, "_update_readiness", new_callable=AsyncMock):
                await service.analyze_samples("user-123", ["one", "two", "three"])

        # Episodic store was called
        service.episodic.store_episode.assert_called_once()
        episode = service.episodic.store_episode.call_args[0][0]
        assert episode.event_type == "onboarding_writing_analyzed"
        assert episode.user_id == "user-123"
        assert episode.context["sample_count"] == 3
        assert episode.context["confidence"] == 0.82

    @pytest.mark.asyncio
    async def test_llm_parse_failure_returns_fallback(self):
        """LLM returning invalid JSON produces low-confidence fallback."""
        service, mock_llm, mock_db = _make_service_with_mocks()
        mock_llm.generate_response = AsyncMock(return_value="not valid json at all")

        with (
            patch("src.onboarding.writing_analysis.SupabaseClient") as mock_supa,
            patch("src.onboarding.writing_analysis.log_memory_operation", new_callable=AsyncMock),
        ):
            mock_supa.get_client.return_value = mock_db
            with patch.object(service, "_update_readiness", new_callable=AsyncMock):
                fp = await service.analyze_samples("user-123", ["Sample."])

        assert fp.confidence == 0.3
        assert "more samples" in fp.style_summary.lower()

    @pytest.mark.asyncio
    async def test_code_fenced_json_response_handled(self):
        """LLM response wrapped in markdown code fences is parsed correctly."""
        service, mock_llm, mock_db = _make_service_with_mocks()
        mock_llm.generate_response = AsyncMock(return_value=f"```json\n{_make_llm_response()}\n```")

        with (
            patch("src.onboarding.writing_analysis.SupabaseClient") as mock_supa,
            patch("src.onboarding.writing_analysis.log_memory_operation", new_callable=AsyncMock),
        ):
            mock_supa.get_client.return_value = mock_db
            with patch.object(service, "_update_readiness", new_callable=AsyncMock):
                fp = await service.analyze_samples("user-123", ["Sample."])

        assert fp.confidence == 0.82

    @pytest.mark.asyncio
    async def test_samples_capped_at_ten(self):
        """Only first 10 samples are included in LLM prompt."""
        service, mock_llm, mock_db = _make_service_with_mocks()
        samples = [f"Sample {i}" for i in range(15)]

        with (
            patch("src.onboarding.writing_analysis.SupabaseClient") as mock_supa,
            patch("src.onboarding.writing_analysis.log_memory_operation", new_callable=AsyncMock),
        ):
            mock_supa.get_client.return_value = mock_db
            with patch.object(service, "_update_readiness", new_callable=AsyncMock):
                await service.analyze_samples("user-123", samples)

        call_args = mock_llm.generate_response.call_args
        # Extract prompt from either positional or keyword args
        if call_args[1].get("messages"):
            prompt_text = call_args[1]["messages"][0]["content"]
        else:
            prompt_text = call_args[0][0][0]["content"]
        # Sample 0 through 9 should be present
        assert "Sample 9" in prompt_text
        # Sample 10+ should NOT be in the prompt
        assert "Sample 10" not in prompt_text

    @pytest.mark.asyncio
    async def test_readiness_capped_at_40(self):
        """Readiness from writing analysis never exceeds 40."""
        service, mock_llm, mock_db = _make_service_with_mocks()

        # Return confidence of 1.0
        high_confidence = json.dumps(
            {
                **json.loads(_make_llm_response()),
                "confidence": 1.0,
            }
        )
        mock_llm.generate_response = AsyncMock(return_value=high_confidence)

        mock_orch = MagicMock()
        mock_orch.update_readiness_scores = AsyncMock()

        with (
            patch("src.onboarding.writing_analysis.SupabaseClient") as mock_supa,
            patch("src.onboarding.writing_analysis.log_memory_operation", new_callable=AsyncMock),
            patch(
                "src.onboarding.orchestrator.OnboardingOrchestrator",
                return_value=mock_orch,
            ),
        ):
            mock_supa.get_client.return_value = mock_db
            await service.analyze_samples("user-123", ["Sample."])

        mock_orch.update_readiness_scores.assert_called_once_with(
            "user-123", {"digital_twin": 40.0}
        )


class TestWritingAnalysisServiceGetFingerprint:
    """Tests for WritingAnalysisService.get_fingerprint."""

    @pytest.mark.asyncio
    async def test_get_fingerprint_returns_stored_data(self):
        """Stored fingerprint is returned correctly."""
        service = WritingAnalysisService.__new__(WritingAnalysisService)

        stored_fp = WritingStyleFingerprint(
            avg_sentence_length=14.0,
            directness=0.8,
            style_summary="Test style.",
            confidence=0.9,
        )

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.eq.return_value = mock_query
        mock_query.maybe_single.return_value = mock_query
        mock_query.execute.return_value = MagicMock(
            data={
                "preferences": {
                    "digital_twin": {
                        "writing_style": stored_fp.model_dump(),
                    }
                }
            }
        )
        mock_db.table.return_value.select.return_value = mock_query

        with patch("src.onboarding.writing_analysis.SupabaseClient") as mock_supa:
            mock_supa.get_client.return_value = mock_db
            result = await service.get_fingerprint("user-123")

        assert result is not None
        assert result.directness == 0.8
        assert result.confidence == 0.9
        assert result.style_summary == "Test style."

    @pytest.mark.asyncio
    async def test_get_fingerprint_returns_none_when_not_stored(self):
        """Returns None when no fingerprint exists."""
        service = WritingAnalysisService.__new__(WritingAnalysisService)

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.eq.return_value = mock_query
        mock_query.maybe_single.return_value = mock_query
        mock_query.execute.return_value = MagicMock(data=None)
        mock_db.table.return_value.select.return_value = mock_query

        with patch("src.onboarding.writing_analysis.SupabaseClient") as mock_supa:
            mock_supa.get_client.return_value = mock_db
            result = await service.get_fingerprint("user-123")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_fingerprint_returns_none_on_empty_preferences(self):
        """Returns None when preferences exist but no digital_twin data."""
        service = WritingAnalysisService.__new__(WritingAnalysisService)

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.eq.return_value = mock_query
        mock_query.maybe_single.return_value = mock_query
        mock_query.execute.return_value = MagicMock(data={"preferences": {}})
        mock_db.table.return_value.select.return_value = mock_query

        with patch("src.onboarding.writing_analysis.SupabaseClient") as mock_supa:
            mock_supa.get_client.return_value = mock_db
            result = await service.get_fingerprint("user-123")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_fingerprint_handles_db_error_gracefully(self):
        """DB errors return None instead of raising."""
        service = WritingAnalysisService.__new__(WritingAnalysisService)

        with patch("src.onboarding.writing_analysis.SupabaseClient") as mock_supa:
            mock_supa.get_client.side_effect = Exception("DB down")
            result = await service.get_fingerprint("user-123")

        assert result is None
