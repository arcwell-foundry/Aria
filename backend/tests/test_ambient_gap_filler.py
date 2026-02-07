"""Tests for US-925: Continuous Onboarding Loop (Ambient Gap Filling).

Tests cover:
- Readiness threshold detection: domains below 60% trigger prompts
- Anti-nagging spacing: minimum 3 days between prompts
- Weekly limit enforcement: max 2 prompts per week
- Priority domain selection: lowest score domain chosen first
- Prompt generation per domain: natural, non-intrusive text
- Prompt storage and retrieval for chat service pickup
- Outcome tracking: engaged, dismissed, deferred
- Procedural memory integration: outcomes feed learning
- All-above-threshold: no prompt generated
- Edge cases: no onboarding state, empty readiness
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.onboarding.ambient_gap_filler import AmbientGapFiller

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_supabase() -> MagicMock:
    """Create a mock Supabase client."""
    mock = MagicMock()
    mock_response = MagicMock()
    mock_response.data = []
    mock.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response
    mock.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_response
    mock.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = mock_response
    mock.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.maybe_single.return_value.execute.return_value = mock_response
    mock.table.return_value.insert.return_value.execute.return_value = mock_response
    mock.table.return_value.update.return_value.eq.return_value.execute.return_value = mock_response
    return mock


@pytest.fixture
def filler(mock_supabase: MagicMock) -> AmbientGapFiller:
    """Create an AmbientGapFiller with mocked DB."""
    with patch("src.onboarding.ambient_gap_filler.SupabaseClient") as mock_cls:
        mock_cls.get_client.return_value = mock_supabase
        svc = AmbientGapFiller()
    return svc


# ---------------------------------------------------------------------------
# Threshold detection
# ---------------------------------------------------------------------------


class TestThresholdDetection:
    """Test readiness sub-score threshold detection."""

    @pytest.mark.asyncio
    async def test_all_scores_above_threshold_returns_none(self, filler: AmbientGapFiller) -> None:
        """When all readiness scores >= 60, no prompt generated."""
        with patch.object(
            filler,
            "_get_readiness",
            return_value={
                "corporate_memory": 80.0,
                "digital_twin": 70.0,
                "relationship_graph": 65.0,
                "integrations": 90.0,
                "goal_clarity": 75.0,
                "overall": 76.0,
            },
        ):
            result = await filler.check_and_generate("user-123")
            assert result is None

    @pytest.mark.asyncio
    async def test_one_score_below_threshold_generates_prompt(
        self, filler: AmbientGapFiller
    ) -> None:
        """When one domain is below 60, a prompt is generated for that domain."""
        with (
            patch.object(
                filler,
                "_get_readiness",
                return_value={
                    "corporate_memory": 80.0,
                    "digital_twin": 40.0,
                    "relationship_graph": 65.0,
                    "integrations": 90.0,
                    "goal_clarity": 75.0,
                    "overall": 70.0,
                },
            ),
            patch.object(filler, "_get_last_prompt_time", return_value=None),
            patch.object(filler, "_get_weekly_prompt_count", return_value=0),
            patch.object(filler, "_store_pending_prompt", new_callable=AsyncMock),
            patch.object(filler, "_record_prompt_generated", new_callable=AsyncMock),
        ):
            result = await filler.check_and_generate("user-123")

            assert result is not None
            assert result["domain"] == "digital_twin"
            assert result["type"] == "ambient_gap_fill"
            assert result["score"] == 40.0

    @pytest.mark.asyncio
    async def test_picks_lowest_score_domain(self, filler: AmbientGapFiller) -> None:
        """When multiple domains are below threshold, picks the lowest."""
        with (
            patch.object(
                filler,
                "_get_readiness",
                return_value={
                    "corporate_memory": 30.0,
                    "digital_twin": 45.0,
                    "relationship_graph": 55.0,
                    "integrations": 10.0,
                    "goal_clarity": 75.0,
                    "overall": 43.0,
                },
            ),
            patch.object(filler, "_get_last_prompt_time", return_value=None),
            patch.object(filler, "_get_weekly_prompt_count", return_value=0),
            patch.object(filler, "_store_pending_prompt", new_callable=AsyncMock),
            patch.object(filler, "_record_prompt_generated", new_callable=AsyncMock),
        ):
            result = await filler.check_and_generate("user-123")

            assert result is not None
            assert result["domain"] == "integrations"
            assert result["score"] == 10.0


# ---------------------------------------------------------------------------
# Anti-nagging spacing
# ---------------------------------------------------------------------------


class TestSpacingEnforcement:
    """Test minimum spacing between prompts."""

    @pytest.mark.asyncio
    async def test_too_soon_since_last_prompt_returns_none(self, filler: AmbientGapFiller) -> None:
        """If last prompt was < 3 days ago, returns None."""
        recent_time = datetime.now(UTC) - timedelta(days=1)
        with (
            patch.object(
                filler,
                "_get_readiness",
                return_value={
                    "corporate_memory": 20.0,
                    "digital_twin": 40.0,
                    "relationship_graph": 65.0,
                    "integrations": 90.0,
                    "goal_clarity": 75.0,
                    "overall": 58.0,
                },
            ),
            patch.object(filler, "_get_last_prompt_time", return_value=recent_time),
        ):
            result = await filler.check_and_generate("user-123")
            assert result is None

    @pytest.mark.asyncio
    async def test_enough_time_since_last_prompt_generates(self, filler: AmbientGapFiller) -> None:
        """If last prompt was >= 3 days ago, generates a prompt."""
        old_time = datetime.now(UTC) - timedelta(days=4)
        with (
            patch.object(
                filler,
                "_get_readiness",
                return_value={
                    "corporate_memory": 20.0,
                    "digital_twin": 70.0,
                    "relationship_graph": 65.0,
                    "integrations": 90.0,
                    "goal_clarity": 75.0,
                    "overall": 64.0,
                },
            ),
            patch.object(filler, "_get_last_prompt_time", return_value=old_time),
            patch.object(filler, "_get_weekly_prompt_count", return_value=0),
            patch.object(filler, "_store_pending_prompt", new_callable=AsyncMock),
            patch.object(filler, "_record_prompt_generated", new_callable=AsyncMock),
        ):
            result = await filler.check_and_generate("user-123")
            assert result is not None
            assert result["domain"] == "corporate_memory"

    @pytest.mark.asyncio
    async def test_no_previous_prompt_generates(self, filler: AmbientGapFiller) -> None:
        """If no previous prompt exists, generates one."""
        with (
            patch.object(
                filler,
                "_get_readiness",
                return_value={
                    "corporate_memory": 50.0,
                    "digital_twin": 70.0,
                    "relationship_graph": 65.0,
                    "integrations": 90.0,
                    "goal_clarity": 75.0,
                    "overall": 70.0,
                },
            ),
            patch.object(filler, "_get_last_prompt_time", return_value=None),
            patch.object(filler, "_get_weekly_prompt_count", return_value=0),
            patch.object(filler, "_store_pending_prompt", new_callable=AsyncMock),
            patch.object(filler, "_record_prompt_generated", new_callable=AsyncMock),
        ):
            result = await filler.check_and_generate("user-123")
            assert result is not None


# ---------------------------------------------------------------------------
# Weekly limit
# ---------------------------------------------------------------------------


class TestWeeklyLimit:
    """Test max 2 prompts per week enforcement."""

    @pytest.mark.asyncio
    async def test_weekly_limit_reached_returns_none(self, filler: AmbientGapFiller) -> None:
        """If 2+ prompts sent this week, returns None."""
        with (
            patch.object(
                filler,
                "_get_readiness",
                return_value={
                    "corporate_memory": 20.0,
                    "digital_twin": 40.0,
                    "relationship_graph": 65.0,
                    "integrations": 90.0,
                    "goal_clarity": 75.0,
                    "overall": 58.0,
                },
            ),
            patch.object(filler, "_get_last_prompt_time", return_value=None),
            patch.object(filler, "_get_weekly_prompt_count", return_value=2),
        ):
            result = await filler.check_and_generate("user-123")
            assert result is None

    @pytest.mark.asyncio
    async def test_below_weekly_limit_generates(self, filler: AmbientGapFiller) -> None:
        """If < 2 prompts this week, generates a prompt."""
        with (
            patch.object(
                filler,
                "_get_readiness",
                return_value={
                    "corporate_memory": 20.0,
                    "digital_twin": 70.0,
                    "relationship_graph": 65.0,
                    "integrations": 90.0,
                    "goal_clarity": 75.0,
                    "overall": 64.0,
                },
            ),
            patch.object(filler, "_get_last_prompt_time", return_value=None),
            patch.object(filler, "_get_weekly_prompt_count", return_value=1),
            patch.object(filler, "_store_pending_prompt", new_callable=AsyncMock),
            patch.object(filler, "_record_prompt_generated", new_callable=AsyncMock),
        ):
            result = await filler.check_and_generate("user-123")
            assert result is not None


# ---------------------------------------------------------------------------
# Prompt generation per domain
# ---------------------------------------------------------------------------


class TestPromptGeneration:
    """Test natural prompt generation per readiness domain."""

    @pytest.mark.asyncio
    async def test_digital_twin_prompt(self, filler: AmbientGapFiller) -> None:
        """Digital twin domain generates writing-style prompt."""
        result = await filler._generate_prompt("digital_twin", 40.0)
        assert result["domain"] == "digital_twin"
        assert "writing style" in result["prompt"].lower() or "email" in result["prompt"].lower()
        assert result["type"] == "ambient_gap_fill"

    @pytest.mark.asyncio
    async def test_corporate_memory_prompt(self, filler: AmbientGapFiller) -> None:
        """Corporate memory domain generates product-related prompt."""
        result = await filler._generate_prompt("corporate_memory", 30.0)
        assert result["domain"] == "corporate_memory"
        assert "company" in result["prompt"].lower() or "product" in result["prompt"].lower()

    @pytest.mark.asyncio
    async def test_relationship_graph_prompt(self, filler: AmbientGapFiller) -> None:
        """Relationship graph domain generates contacts prompt."""
        result = await filler._generate_prompt("relationship_graph", 25.0)
        assert result["domain"] == "relationship_graph"
        assert "contact" in result["prompt"].lower() or "people" in result["prompt"].lower()

    @pytest.mark.asyncio
    async def test_integrations_prompt(self, filler: AmbientGapFiller) -> None:
        """Integrations domain generates connection prompt."""
        result = await filler._generate_prompt("integrations", 15.0)
        assert result["domain"] == "integrations"
        assert "connect" in result["prompt"].lower() or "calendar" in result["prompt"].lower()

    @pytest.mark.asyncio
    async def test_goal_clarity_prompt(self, filler: AmbientGapFiller) -> None:
        """Goal clarity domain generates goal-related prompt."""
        result = await filler._generate_prompt("goal_clarity", 20.0)
        assert result["domain"] == "goal_clarity"
        assert "goal" in result["prompt"].lower() or "working on" in result["prompt"].lower()

    @pytest.mark.asyncio
    async def test_unknown_domain_generates_fallback(self, filler: AmbientGapFiller) -> None:
        """Unknown domain generates a generic fallback prompt."""
        result = await filler._generate_prompt("unknown_domain", 30.0)
        assert result["domain"] == "unknown_domain"
        assert len(result["prompt"]) > 0


# ---------------------------------------------------------------------------
# Pending prompt retrieval
# ---------------------------------------------------------------------------


class TestPendingPromptRetrieval:
    """Test retrieving pending prompts for chat service."""

    @pytest.mark.asyncio
    async def test_get_pending_returns_prompt(
        self, filler: AmbientGapFiller, mock_supabase: MagicMock
    ) -> None:
        """Returns the oldest pending prompt."""
        prompt_data = {
            "id": "prompt-123",
            "domain": "digital_twin",
            "prompt": "Forward me some emails",
            "score": 40.0,
            "status": "pending",
        }
        mock_response = MagicMock()
        mock_response.data = prompt_data
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.maybe_single.return_value.execute.return_value = mock_response

        result = await filler.get_pending_prompt("user-123")
        assert result is not None
        assert result["id"] == "prompt-123"

    @pytest.mark.asyncio
    async def test_get_pending_returns_none_when_empty(
        self, filler: AmbientGapFiller, mock_supabase: MagicMock
    ) -> None:
        """Returns None when no pending prompts exist."""
        mock_response = MagicMock()
        mock_response.data = None
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.maybe_single.return_value.execute.return_value = mock_response

        result = await filler.get_pending_prompt("user-123")
        assert result is None


# ---------------------------------------------------------------------------
# Outcome tracking
# ---------------------------------------------------------------------------


class TestOutcomeTracking:
    """Test recording prompt engagement outcomes."""

    @pytest.mark.asyncio
    async def test_record_engaged_outcome(
        self, filler: AmbientGapFiller, mock_supabase: MagicMock
    ) -> None:
        """Records 'engaged' outcome and updates prompt status."""
        await filler.record_outcome("user-123", "prompt-123", "engaged")
        mock_supabase.table.return_value.update.assert_called()

    @pytest.mark.asyncio
    async def test_record_dismissed_outcome(
        self, filler: AmbientGapFiller, mock_supabase: MagicMock
    ) -> None:
        """Records 'dismissed' outcome."""
        await filler.record_outcome("user-123", "prompt-123", "dismissed")
        mock_supabase.table.return_value.update.assert_called()

    @pytest.mark.asyncio
    async def test_record_deferred_outcome(
        self, filler: AmbientGapFiller, mock_supabase: MagicMock
    ) -> None:
        """Records 'deferred' outcome."""
        await filler.record_outcome("user-123", "prompt-123", "deferred")
        mock_supabase.table.return_value.update.assert_called()

    @pytest.mark.asyncio
    async def test_outcome_stores_to_procedural_memory(
        self, filler: AmbientGapFiller, mock_supabase: MagicMock
    ) -> None:
        """Engaged outcomes create procedural memory entries."""
        mock_prompt_response = MagicMock()
        mock_prompt_response.data = {
            "id": "prompt-123",
            "domain": "digital_twin",
            "prompt": "Forward me some emails",
            "score": 40.0,
            "status": "delivered",
        }
        mock_supabase.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = mock_prompt_response

        await filler.record_outcome("user-123", "prompt-123", "engaged")

        # Verify insert was called (for procedural memory)
        insert_calls = mock_supabase.table.return_value.insert.call_args_list
        assert len(insert_calls) > 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_no_readiness_data_returns_none(self, filler: AmbientGapFiller) -> None:
        """If readiness service returns empty, no prompt generated."""
        with patch.object(filler, "_get_readiness", return_value={}):
            result = await filler.check_and_generate("user-123")
            assert result is None

    @pytest.mark.asyncio
    async def test_readiness_error_returns_none(self, filler: AmbientGapFiller) -> None:
        """If readiness fetch fails, returns None gracefully."""
        with patch.object(filler, "_get_readiness", side_effect=Exception("DB error")):
            result = await filler.check_and_generate("user-123")
            assert result is None

    @pytest.mark.asyncio
    async def test_overall_key_excluded_from_domain_check(self, filler: AmbientGapFiller) -> None:
        """The 'overall' key should not be treated as a domain."""
        with patch.object(
            filler,
            "_get_readiness",
            return_value={
                "corporate_memory": 80.0,
                "digital_twin": 70.0,
                "relationship_graph": 65.0,
                "integrations": 90.0,
                "goal_clarity": 75.0,
                "overall": 30.0,  # Below threshold but should be excluded
            },
        ):
            result = await filler.check_and_generate("user-123")
            assert result is None

    @pytest.mark.asyncio
    async def test_confidence_modifier_excluded_from_domain_check(
        self, filler: AmbientGapFiller
    ) -> None:
        """The 'confidence_modifier' string key should not be treated as a domain."""
        with patch.object(
            filler,
            "_get_readiness",
            return_value={
                "corporate_memory": 80.0,
                "digital_twin": 70.0,
                "relationship_graph": 65.0,
                "integrations": 90.0,
                "goal_clarity": 75.0,
                "overall": 76.0,
                "confidence_modifier": "high",
            },
        ):
            result = await filler.check_and_generate("user-123")
            assert result is None
