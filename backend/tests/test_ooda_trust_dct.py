"""Tests for Trust + DCT wiring in OODALoop decide phase."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.core.ooda import OODALoop, OODAState, OODAPhase


class TestOODADecideTrustDCT:
    """Verify trust lookup and DCT minting in decide phase."""

    def _make_loop(self, trust_service=None, dct_minter=None):
        """Create OODALoop with mock deps."""
        return OODALoop(
            llm_client=MagicMock(),
            episodic_memory=MagicMock(),
            semantic_memory=MagicMock(),
            working_memory=MagicMock(user_id="u1"),
            user_id="u1",
            trust_service=trust_service,
            dct_minter=dct_minter,
        )

    @pytest.mark.asyncio
    async def test_trust_and_dct_stored_in_state(self):
        """After decide(), state has approval_level and capability_token."""
        trust = MagicMock()
        trust.get_approval_level = AsyncMock(return_value="EXECUTE_AND_NOTIFY")

        minter = MagicMock()
        fake_dct = MagicMock()
        fake_dct.to_dict.return_value = {"token_id": "t1", "delegatee": "analyst"}
        minter.mint.return_value = fake_dct

        loop = self._make_loop(trust_service=trust, dct_minter=minter)

        # Mock the LLM to return a valid decision JSON.
        loop.llm.generate_response = AsyncMock(
            return_value='{"action":"research","agent":"analyst","parameters":{}}'
        )

        state = OODAState(goal_id="g1", current_phase=OODAPhase.DECIDE)
        state.orientation = {"recommended_focus": "research"}

        state = await loop.decide(state, {"title": "Test goal"})

        assert state.approval_level == "EXECUTE_AND_NOTIFY"
        assert state.capability_token is not None
        assert state.capability_token["delegatee"] == "analyst"
        trust.get_approval_level.assert_called_once()
        minter.mint.assert_called_once_with(
            delegatee="analyst", goal_id="g1", time_limit=300
        )

    @pytest.mark.asyncio
    async def test_no_trust_service_uses_chars_approval(self):
        """Without trust service, approval_level comes from TaskCharacteristics."""
        loop = self._make_loop()
        loop.llm.generate_response = AsyncMock(
            return_value='{"action":"research","agent":"analyst","parameters":{}}'
        )

        state = OODAState(goal_id="g1", current_phase=OODAPhase.DECIDE)
        state.orientation = {"recommended_focus": "research"}
        state = await loop.decide(state, {"title": "Test"})

        # approval_level should be set from chars.approval_level
        assert state.approval_level is not None
        # Without trust service, it falls through to TaskCharacteristics default
        assert state.approval_level in (
            "AUTO_EXECUTE",
            "EXECUTE_AND_NOTIFY",
            "APPROVE_PLAN",
            "APPROVE_EACH",
        )

    @pytest.mark.asyncio
    async def test_trust_error_falls_back_to_chars(self):
        """If trust lookup fails, approval comes from TaskCharacteristics."""
        trust = MagicMock()
        trust.get_approval_level = AsyncMock(side_effect=RuntimeError("db down"))

        loop = self._make_loop(trust_service=trust)
        loop.llm.generate_response = AsyncMock(
            return_value='{"action":"research","agent":"analyst","parameters":{}}'
        )

        state = OODAState(goal_id="g1", current_phase=OODAPhase.DECIDE)
        state.orientation = {"recommended_focus": "research"}
        state = await loop.decide(state, {"title": "Test"})

        # Should still get an approval level (from chars fallback)
        assert state.approval_level is not None

    @pytest.mark.asyncio
    async def test_dct_minting_error_continues(self):
        """If DCT minting fails, decide() still completes without DCT."""
        minter = MagicMock()
        minter.mint.side_effect = RuntimeError("minting failed")

        loop = self._make_loop(dct_minter=minter)
        loop.llm.generate_response = AsyncMock(
            return_value='{"action":"research","agent":"analyst","parameters":{}}'
        )

        state = OODAState(goal_id="g1", current_phase=OODAPhase.DECIDE)
        state.orientation = {"recommended_focus": "research"}
        state = await loop.decide(state, {"title": "Test"})

        # Should still complete, just without DCT
        assert state.decision is not None
        assert state.capability_token is None

    @pytest.mark.asyncio
    async def test_act_passes_dct_to_executor(self):
        """act() passes capability_token and approval_level to agent_executor."""
        captured_kwargs = {}

        async def mock_executor(**kwargs):
            captured_kwargs.update(kwargs)
            return {"success": True}

        loop = self._make_loop()
        loop.agent_executor = mock_executor

        state = OODAState(goal_id="g1", current_phase=OODAPhase.ACT)
        state.decision = {
            "action": "research",
            "agent": "analyst",
            "parameters": {"query": "test"},
        }
        state.capability_token = {"token_id": "t1", "delegatee": "analyst"}
        state.approval_level = "EXECUTE_AND_NOTIFY"

        state = await loop.act(state, {"title": "Test"})

        assert captured_kwargs.get("capability_token") == {
            "token_id": "t1",
            "delegatee": "analyst",
        }
        assert captured_kwargs.get("approval_level") == "EXECUTE_AND_NOTIFY"
