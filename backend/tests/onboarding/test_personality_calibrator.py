"""Tests for Personality Calibration from Onboarding Data (US-919).

Tests the PersonalityCalibrator which reads the Digital Twin writing fingerprint
and generates personality trait adjustments for ARIA's communication style.
Not mimicry -- ARIA adjusts directness, warmth, assertiveness, detail, and formality.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.onboarding.personality_calibrator import (
    PersonalityCalibration,
    PersonalityCalibrator,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

USER_ID = "user-calibration-test"


def _make_mock_db(fingerprint_data: dict | None = None) -> MagicMock:
    """Create a mock Supabase client with optional fingerprint data.

    Args:
        fingerprint_data: Writing style fingerprint dict to return,
            or None for no data.
    """
    db = MagicMock()

    # For _get_writing_fingerprint: select preferences from user_settings
    settings_result = MagicMock()
    if fingerprint_data is not None:
        settings_result.data = {
            "preferences": {
                "digital_twin": {
                    "writing_style": fingerprint_data,
                },
            },
        }
    else:
        settings_result.data = None

    db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
        settings_result
    )

    # For _store_calibration: update call
    db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

    return db


@pytest.fixture
def mock_episodic():
    """Mock EpisodicMemory."""
    memory = MagicMock()
    memory.store_episode = AsyncMock(return_value="episode-id")
    return memory


@pytest.fixture
def direct_fingerprint() -> dict:
    """Fingerprint for a direct, formal, data-driven writer."""
    return {
        "directness": 0.85,
        "warmth": 0.3,
        "assertiveness": 0.8,
        "formality_index": 0.9,
        "avg_sentence_length": 25,
        "paragraph_style": "long_detailed",
        "data_driven": True,
    }


@pytest.fixture
def casual_fingerprint() -> dict:
    """Fingerprint for a casual, warm, diplomatic writer."""
    return {
        "directness": 0.2,
        "warmth": 0.9,
        "assertiveness": 0.25,
        "formality_index": 0.15,
        "avg_sentence_length": 8,
        "paragraph_style": "short_punchy",
        "data_driven": False,
    }


@pytest.fixture
def calibrator_with_fingerprint(direct_fingerprint, mock_episodic):
    """Create PersonalityCalibrator with a direct writer fingerprint."""
    mock_db = _make_mock_db(direct_fingerprint)
    with (
        patch(
            "src.onboarding.personality_calibrator.SupabaseClient.get_client",
            return_value=mock_db,
        ),
        patch(
            "src.onboarding.personality_calibrator.EpisodicMemory",
            return_value=mock_episodic,
        ),
    ):
        yield PersonalityCalibrator()


@pytest.fixture
def calibrator_no_fingerprint(mock_episodic):
    """Create PersonalityCalibrator with no fingerprint data."""
    mock_db = _make_mock_db(None)
    with (
        patch(
            "src.onboarding.personality_calibrator.SupabaseClient.get_client",
            return_value=mock_db,
        ),
        patch(
            "src.onboarding.personality_calibrator.EpisodicMemory",
            return_value=mock_episodic,
        ),
    ):
        yield PersonalityCalibrator()


@pytest.fixture
def calibrator_casual(casual_fingerprint, mock_episodic):
    """Create PersonalityCalibrator with a casual writer fingerprint."""
    mock_db = _make_mock_db(casual_fingerprint)
    with (
        patch(
            "src.onboarding.personality_calibrator.SupabaseClient.get_client",
            return_value=mock_db,
        ),
        patch(
            "src.onboarding.personality_calibrator.EpisodicMemory",
            return_value=mock_episodic,
        ),
    ):
        yield PersonalityCalibrator()


# ---------------------------------------------------------------------------
# PersonalityCalibration model tests
# ---------------------------------------------------------------------------


class TestPersonalityCalibrationModel:
    """Tests for the PersonalityCalibration Pydantic model."""

    def test_default_values(self) -> None:
        """Default calibration has all traits at 0.5 (neutral)."""
        cal = PersonalityCalibration()
        assert cal.directness == 0.5
        assert cal.warmth == 0.5
        assert cal.assertiveness == 0.5
        assert cal.detail_orientation == 0.5
        assert cal.formality == 0.5
        assert cal.tone_guidance == ""
        assert cal.example_adjustments == []

    def test_custom_values(self) -> None:
        """Custom values are properly assigned."""
        cal = PersonalityCalibration(
            directness=0.9,
            warmth=0.2,
            assertiveness=0.8,
            detail_orientation=0.7,
            formality=0.85,
        )
        assert cal.directness == 0.9
        assert cal.warmth == 0.2
        assert cal.formality == 0.85

    def test_serialization(self) -> None:
        """Model serializes to dict correctly."""
        cal = PersonalityCalibration(directness=0.7, warmth=0.3)
        data = cal.model_dump()
        assert data["directness"] == 0.7
        assert data["warmth"] == 0.3
        assert "tone_guidance" in data
        assert "example_adjustments" in data


# ---------------------------------------------------------------------------
# calibrate() method tests
# ---------------------------------------------------------------------------


class TestCalibrateMethod:
    """Tests for the calibrate() method -- core calibration logic."""

    @pytest.mark.asyncio
    async def test_direct_writer_high_directness(
        self, calibrator_with_fingerprint: PersonalityCalibrator
    ) -> None:
        """Direct writer fingerprint produces directness > 0.7."""
        cal = await calibrator_with_fingerprint.calibrate(USER_ID)
        assert cal.directness > 0.7

    @pytest.mark.asyncio
    async def test_formal_writer_high_formality(
        self, calibrator_with_fingerprint: PersonalityCalibrator
    ) -> None:
        """Formal writer fingerprint produces formality > 0.7."""
        cal = await calibrator_with_fingerprint.calibrate(USER_ID)
        assert cal.formality > 0.7

    @pytest.mark.asyncio
    async def test_assertive_writer_high_assertiveness(
        self, calibrator_with_fingerprint: PersonalityCalibrator
    ) -> None:
        """Assertive writer fingerprint produces assertiveness > 0.7."""
        cal = await calibrator_with_fingerprint.calibrate(USER_ID)
        assert cal.assertiveness > 0.7

    @pytest.mark.asyncio
    async def test_data_driven_writer_detail_boosted(
        self, calibrator_with_fingerprint: PersonalityCalibrator
    ) -> None:
        """Data-driven writer with long sentences gets detail_orientation boosted."""
        cal = await calibrator_with_fingerprint.calibrate(USER_ID)
        assert cal.detail_orientation > 0.5

    @pytest.mark.asyncio
    async def test_casual_writer_low_formality(
        self, calibrator_casual: PersonalityCalibrator
    ) -> None:
        """Casual writer fingerprint produces formality < 0.3."""
        cal = await calibrator_casual.calibrate(USER_ID)
        assert cal.formality < 0.3

    @pytest.mark.asyncio
    async def test_warm_writer_high_warmth(
        self, calibrator_casual: PersonalityCalibrator
    ) -> None:
        """Warm writer fingerprint produces warmth > 0.7."""
        cal = await calibrator_casual.calibrate(USER_ID)
        assert cal.warmth > 0.7

    @pytest.mark.asyncio
    async def test_diplomatic_writer_low_directness(
        self, calibrator_casual: PersonalityCalibrator
    ) -> None:
        """Diplomatic writer fingerprint produces directness < 0.3."""
        cal = await calibrator_casual.calibrate(USER_ID)
        assert cal.directness < 0.3

    @pytest.mark.asyncio
    async def test_short_punchy_writer_low_detail(
        self, calibrator_casual: PersonalityCalibrator
    ) -> None:
        """Short, punchy writer gets lower detail_orientation."""
        cal = await calibrator_casual.calibrate(USER_ID)
        assert cal.detail_orientation < 0.5


# ---------------------------------------------------------------------------
# Tone guidance tests
# ---------------------------------------------------------------------------


class TestToneGuidance:
    """Tests for tone guidance generation -- prompt-ready strings."""

    @pytest.mark.asyncio
    async def test_tone_guidance_nonempty(
        self, calibrator_with_fingerprint: PersonalityCalibrator
    ) -> None:
        """Calibration produces non-empty tone guidance."""
        cal = await calibrator_with_fingerprint.calibrate(USER_ID)
        assert cal.tone_guidance != ""
        assert len(cal.tone_guidance) > 10

    @pytest.mark.asyncio
    async def test_direct_writer_tone_mentions_direct(
        self, calibrator_with_fingerprint: PersonalityCalibrator
    ) -> None:
        """Direct writer's tone guidance mentions directness."""
        cal = await calibrator_with_fingerprint.calibrate(USER_ID)
        assert "direct" in cal.tone_guidance.lower()

    @pytest.mark.asyncio
    async def test_formal_writer_tone_mentions_formal(
        self, calibrator_with_fingerprint: PersonalityCalibrator
    ) -> None:
        """Formal writer's tone guidance mentions formal language."""
        cal = await calibrator_with_fingerprint.calibrate(USER_ID)
        assert "formal" in cal.tone_guidance.lower()

    @pytest.mark.asyncio
    async def test_casual_writer_tone_mentions_casual(
        self, calibrator_casual: PersonalityCalibrator
    ) -> None:
        """Casual writer's tone guidance mentions casual/conversational."""
        cal = await calibrator_casual.calibrate(USER_ID)
        guidance_lower = cal.tone_guidance.lower()
        assert "casual" in guidance_lower or "conversational" in guidance_lower

    @pytest.mark.asyncio
    async def test_warm_writer_tone_mentions_warm(
        self, calibrator_casual: PersonalityCalibrator
    ) -> None:
        """Warm writer's tone guidance mentions warm/personal/rapport."""
        cal = await calibrator_casual.calibrate(USER_ID)
        guidance_lower = cal.tone_guidance.lower()
        assert "warm" in guidance_lower or "personal" in guidance_lower or "rapport" in guidance_lower

    @pytest.mark.asyncio
    async def test_example_adjustments_generated(
        self, calibrator_with_fingerprint: PersonalityCalibrator
    ) -> None:
        """Calibration produces example adjustments."""
        cal = await calibrator_with_fingerprint.calibrate(USER_ID)
        assert len(cal.example_adjustments) > 0


# ---------------------------------------------------------------------------
# Default calibration tests
# ---------------------------------------------------------------------------


class TestDefaultCalibration:
    """Tests for default calibration when no fingerprint exists."""

    @pytest.mark.asyncio
    async def test_default_calibration_returned(
        self, calibrator_no_fingerprint: PersonalityCalibrator
    ) -> None:
        """Missing fingerprint returns default calibration."""
        cal = await calibrator_no_fingerprint.calibrate(USER_ID)
        assert cal.directness == 0.5
        assert cal.warmth == 0.5
        assert cal.assertiveness == 0.5
        assert cal.detail_orientation == 0.5
        assert cal.formality == 0.5

    @pytest.mark.asyncio
    async def test_default_has_tone_guidance(
        self, calibrator_no_fingerprint: PersonalityCalibrator
    ) -> None:
        """Default calibration has generic tone guidance."""
        cal = await calibrator_no_fingerprint.calibrate(USER_ID)
        assert cal.tone_guidance != ""
        assert "balanced" in cal.tone_guidance.lower() or "professional" in cal.tone_guidance.lower()


# ---------------------------------------------------------------------------
# Storage tests
# ---------------------------------------------------------------------------


class TestCalibrationStorage:
    """Tests for storing and retrieving calibrations."""

    @pytest.mark.asyncio
    async def test_calibration_stored_in_digital_twin(
        self, calibrator_with_fingerprint: PersonalityCalibrator
    ) -> None:
        """Calibration is stored in user_settings digital_twin."""
        await calibrator_with_fingerprint.calibrate(USER_ID)

        # Verify db.table("user_settings").update() was called
        db = calibrator_with_fingerprint._db
        db.table.assert_any_call("user_settings")

    @pytest.mark.asyncio
    async def test_get_calibration_returns_stored(self, mock_episodic) -> None:
        """get_calibration retrieves stored calibration from DB."""
        stored_data = {
            "directness": 0.8,
            "warmth": 0.3,
            "assertiveness": 0.7,
            "detail_orientation": 0.6,
            "formality": 0.9,
            "tone_guidance": "Be direct.",
            "example_adjustments": [],
        }
        mock_db = MagicMock()
        result = MagicMock()
        result.data = {
            "preferences": {
                "digital_twin": {
                    "personality_calibration": stored_data,
                },
            },
        }
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
            result
        )

        with (
            patch(
                "src.onboarding.personality_calibrator.SupabaseClient.get_client",
                return_value=mock_db,
            ),
            patch(
                "src.onboarding.personality_calibrator.EpisodicMemory",
                return_value=mock_episodic,
            ),
        ):
            calibrator = PersonalityCalibrator()
            cal = await calibrator.get_calibration(USER_ID)

        assert cal is not None
        assert cal.directness == 0.8
        assert cal.formality == 0.9

    @pytest.mark.asyncio
    async def test_get_calibration_returns_none_when_missing(
        self, calibrator_no_fingerprint: PersonalityCalibrator
    ) -> None:
        """get_calibration returns None when no calibration stored."""
        cal = await calibrator_no_fingerprint.get_calibration(USER_ID)
        assert cal is None


# ---------------------------------------------------------------------------
# Episodic memory recording tests
# ---------------------------------------------------------------------------


class TestEpisodicRecording:
    """Tests for episodic memory event recording."""

    @pytest.mark.asyncio
    async def test_episodic_event_recorded(
        self, calibrator_with_fingerprint: PersonalityCalibrator, mock_episodic
    ) -> None:
        """Calibration records event to episodic memory."""
        await calibrator_with_fingerprint.calibrate(USER_ID)
        mock_episodic.store_episode.assert_called_once()

    @pytest.mark.asyncio
    async def test_episodic_event_type(
        self, calibrator_with_fingerprint: PersonalityCalibrator, mock_episodic
    ) -> None:
        """Episodic event has correct event_type."""
        await calibrator_with_fingerprint.calibrate(USER_ID)

        episode = mock_episodic.store_episode.call_args[0][0]
        assert episode.event_type == "onboarding_personality_calibrated"

    @pytest.mark.asyncio
    async def test_episodic_event_contains_traits(
        self, calibrator_with_fingerprint: PersonalityCalibrator, mock_episodic
    ) -> None:
        """Episodic event context includes calibration traits."""
        await calibrator_with_fingerprint.calibrate(USER_ID)

        episode = mock_episodic.store_episode.call_args[0][0]
        assert "directness" in episode.context
        assert "warmth" in episode.context
        assert "assertiveness" in episode.context
        assert "formality" in episode.context

    @pytest.mark.asyncio
    async def test_no_episodic_when_no_fingerprint(
        self, calibrator_no_fingerprint: PersonalityCalibrator, mock_episodic
    ) -> None:
        """Default calibration does not record episodic event."""
        await calibrator_no_fingerprint.calibrate(USER_ID)
        mock_episodic.store_episode.assert_not_called()


# ---------------------------------------------------------------------------
# Detail orientation inference tests
# ---------------------------------------------------------------------------


class TestDetailOrientationInference:
    """Tests for _infer_detail_orientation logic."""

    def test_long_sentences_boost_detail(self) -> None:
        """Long average sentences increase detail_orientation."""
        calibrator = PersonalityCalibrator.__new__(PersonalityCalibrator)
        score = calibrator._infer_detail_orientation({
            "avg_sentence_length": 25,
            "paragraph_style": "medium",
            "data_driven": False,
        })
        assert score > 0.5

    def test_short_sentences_lower_detail(self) -> None:
        """Short average sentences decrease detail_orientation."""
        calibrator = PersonalityCalibrator.__new__(PersonalityCalibrator)
        score = calibrator._infer_detail_orientation({
            "avg_sentence_length": 8,
            "paragraph_style": "medium",
            "data_driven": False,
        })
        assert score < 0.5

    def test_long_paragraphs_boost_detail(self) -> None:
        """Long detailed paragraphs increase detail_orientation."""
        calibrator = PersonalityCalibrator.__new__(PersonalityCalibrator)
        score = calibrator._infer_detail_orientation({
            "avg_sentence_length": 15,
            "paragraph_style": "long_detailed",
            "data_driven": False,
        })
        assert score > 0.5

    def test_short_punchy_paragraphs_lower_detail(self) -> None:
        """Short punchy paragraphs decrease detail_orientation."""
        calibrator = PersonalityCalibrator.__new__(PersonalityCalibrator)
        score = calibrator._infer_detail_orientation({
            "avg_sentence_length": 15,
            "paragraph_style": "short_punchy",
            "data_driven": False,
        })
        assert score < 0.5

    def test_data_driven_boosts_detail(self) -> None:
        """Data-driven writers get detail_orientation boost."""
        calibrator = PersonalityCalibrator.__new__(PersonalityCalibrator)
        score = calibrator._infer_detail_orientation({
            "avg_sentence_length": 15,
            "paragraph_style": "medium",
            "data_driven": True,
        })
        assert score > 0.5

    def test_all_boosters_max_at_1(self) -> None:
        """All boosts combined are clamped to 1.0."""
        calibrator = PersonalityCalibrator.__new__(PersonalityCalibrator)
        score = calibrator._infer_detail_orientation({
            "avg_sentence_length": 30,
            "paragraph_style": "long_detailed",
            "data_driven": True,
        })
        assert score <= 1.0

    def test_all_reducers_min_at_0(self) -> None:
        """All reductions combined are clamped to 0.0."""
        calibrator = PersonalityCalibrator.__new__(PersonalityCalibrator)
        score = calibrator._infer_detail_orientation({
            "avg_sentence_length": 5,
            "paragraph_style": "short_punchy",
            "data_driven": False,
        })
        assert score >= 0.0


# ---------------------------------------------------------------------------
# Readiness update tests
# ---------------------------------------------------------------------------


class TestReadinessUpdate:
    """Tests for readiness score updates during calibration."""

    @pytest.mark.asyncio
    async def test_readiness_updated_on_calibration(
        self, calibrator_with_fingerprint: PersonalityCalibrator
    ) -> None:
        """Calibration updates digital_twin readiness score."""
        mock_orch = MagicMock()
        mock_orch.update_readiness_scores = AsyncMock()

        with patch(
            "src.onboarding.orchestrator.OnboardingOrchestrator",
            return_value=mock_orch,
        ):
            await calibrator_with_fingerprint.calibrate(USER_ID)

            mock_orch.update_readiness_scores.assert_called_once()
            call_args = mock_orch.update_readiness_scores.call_args
            assert call_args[0][0] == USER_ID
            assert "digital_twin" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_readiness_not_updated_on_default(
        self, calibrator_no_fingerprint: PersonalityCalibrator
    ) -> None:
        """Default calibration does not update readiness."""
        mock_orch = MagicMock()
        mock_orch.update_readiness_scores = AsyncMock()

        with patch(
            "src.onboarding.orchestrator.OnboardingOrchestrator",
            return_value=mock_orch,
        ):
            await calibrator_no_fingerprint.calibrate(USER_ID)

            mock_orch.update_readiness_scores.assert_not_called()
