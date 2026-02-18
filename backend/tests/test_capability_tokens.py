"""Tests for Delegation Capability Tokens — scoped agent permissions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.core.capability_tokens import (
    AGENT_PROFILES,
    DCTMinter,
    DelegationCapabilityToken,
)

# ---------------------------------------------------------------------------
# DCTMinter profile tests
# ---------------------------------------------------------------------------


class TestDCTMinterProfiles:
    """Verify minting works for all 8 agents and profiles are correct."""

    @pytest.mark.parametrize(
        "agent",
        ["hunter", "scout", "analyst", "strategist", "scribe", "operator", "verifier", "executor"],
    )
    def test_mints_token_for_known_agent(self, agent: str) -> None:
        minter = DCTMinter()
        token = minter.mint(delegatee=agent, goal_id="goal-1")
        assert token.delegatee == agent
        assert token.goal_id == "goal-1"
        assert len(token.token_id) > 0

    def test_hunter_can_read_exa(self) -> None:
        minter = DCTMinter()
        token = minter.mint(delegatee="hunter", goal_id="g1")
        assert token.can_perform("read_exa")

    def test_operator_can_send_email(self) -> None:
        minter = DCTMinter()
        token = minter.mint(delegatee="operator", goal_id="g1")
        assert token.can_perform("send_email")

    def test_verifier_read_everything_allows_read_pubmed(self) -> None:
        minter = DCTMinter()
        token = minter.mint(delegatee="verifier", goal_id="g1")
        assert token.can_perform("read_pubmed")

    def test_token_id_is_unique(self) -> None:
        minter = DCTMinter()
        t1 = minter.mint(delegatee="hunter", goal_id="g1")
        t2 = minter.mint(delegatee="hunter", goal_id="g1")
        assert t1.token_id != t2.token_id

    def test_profiles_constant_not_mutated(self) -> None:
        original_hunter = list(AGENT_PROFILES["hunter"]["allowed"])
        minter = DCTMinter()
        token = minter.mint(
            delegatee="hunter",
            goal_id="g1",
            additional_scope={"allowed_actions": ["extra_action"]},
        )
        assert "extra_action" in token.allowed_actions
        assert AGENT_PROFILES["hunter"]["allowed"] == original_hunter


# ---------------------------------------------------------------------------
# can_perform basic tests
# ---------------------------------------------------------------------------


class TestCanPerform:
    """Basic allow/deny/default-deny checks."""

    def test_allows_listed_action(self) -> None:
        token = DelegationCapabilityToken(
            token_id="t1",
            delegatee="test",
            goal_id=None,
            allowed_actions=["read_exa", "read_pubmed"],
            denied_actions=["send_email"],
        )
        assert token.can_perform("read_exa") is True

    def test_denies_listed_action(self) -> None:
        token = DelegationCapabilityToken(
            token_id="t1",
            delegatee="test",
            goal_id=None,
            allowed_actions=["read_exa"],
            denied_actions=["send_email"],
        )
        assert token.can_perform("send_email") is False

    def test_denies_unlisted_action(self) -> None:
        token = DelegationCapabilityToken(
            token_id="t1",
            delegatee="test",
            goal_id=None,
            allowed_actions=["read_exa"],
            denied_actions=["send_email"],
        )
        assert token.can_perform("delete_everything") is False


# ---------------------------------------------------------------------------
# Deny precedence
# ---------------------------------------------------------------------------


class TestDenyPrecedence:
    """Deny list wins when action appears in both lists."""

    def test_deny_wins_over_explicit_allow(self) -> None:
        token = DelegationCapabilityToken(
            token_id="t1",
            delegatee="test",
            goal_id=None,
            allowed_actions=["send_email"],
            denied_actions=["send_email"],
        )
        assert token.can_perform("send_email") is False

    def test_deny_wildcard_overrides_specific_allow(self) -> None:
        token = DelegationCapabilityToken(
            token_id="t1",
            delegatee="test",
            goal_id=None,
            allowed_actions=["write_crm"],
            denied_actions=["write_anything"],
        )
        assert token.can_perform("write_crm") is False


# ---------------------------------------------------------------------------
# Wildcard matching
# ---------------------------------------------------------------------------


class TestWildcardMatching:
    """Wildcard patterns like read_everything, write_anything, send_anything."""

    def test_read_everything_matches_read_prefix(self) -> None:
        token = DelegationCapabilityToken(
            token_id="t1",
            delegatee="test",
            goal_id=None,
            allowed_actions=["read_everything"],
            denied_actions=[],
        )
        assert token.can_perform("read_pubmed") is True
        assert token.can_perform("read_crm") is True

    def test_write_anything_blocks_write_prefix(self) -> None:
        token = DelegationCapabilityToken(
            token_id="t1",
            delegatee="test",
            goal_id=None,
            allowed_actions=[],
            denied_actions=["write_anything"],
        )
        assert token.can_perform("write_crm") is False

    def test_send_anything_blocks_send_prefix(self) -> None:
        token = DelegationCapabilityToken(
            token_id="t1",
            delegatee="test",
            goal_id=None,
            allowed_actions=[],
            denied_actions=["send_anything"],
        )
        assert token.can_perform("send_email") is False

    def test_wildcard_does_not_match_wrong_prefix(self) -> None:
        token = DelegationCapabilityToken(
            token_id="t1",
            delegatee="test",
            goal_id=None,
            allowed_actions=["read_everything"],
            denied_actions=[],
        )
        assert token.can_perform("write_crm") is False

    def test_wildcard_requires_nonempty_prefix(self) -> None:
        """A pattern like '_everything' should NOT match everything."""
        token = DelegationCapabilityToken(
            token_id="t1",
            delegatee="test",
            goal_id=None,
            allowed_actions=["_everything"],
            denied_actions=[],
        )
        assert token.can_perform("read_data") is False


# ---------------------------------------------------------------------------
# Token expiry
# ---------------------------------------------------------------------------


class TestTokenExpiry:
    """is_valid() checks time-based expiry."""

    def test_fresh_token_is_valid(self) -> None:
        token = DelegationCapabilityToken(
            token_id="t1",
            delegatee="test",
            goal_id=None,
            allowed_actions=["read_exa"],
            denied_actions=[],
            time_limit_seconds=300,
        )
        assert token.is_valid() is True

    def test_expired_token_is_invalid(self) -> None:
        token = DelegationCapabilityToken(
            token_id="t1",
            delegatee="test",
            goal_id=None,
            allowed_actions=["read_exa"],
            denied_actions=[],
            time_limit_seconds=60,
            created_at=datetime.now(UTC) - timedelta(seconds=120),
        )
        assert token.is_valid() is False

    def test_boundary_at_exactly_time_limit_is_invalid(self) -> None:
        """At exactly time_limit seconds elapsed, token should be invalid."""
        token = DelegationCapabilityToken(
            token_id="t1",
            delegatee="test",
            goal_id=None,
            allowed_actions=["read_exa"],
            denied_actions=[],
            time_limit_seconds=60,
            created_at=datetime.now(UTC) - timedelta(seconds=60),
        )
        assert token.is_valid() is False


# ---------------------------------------------------------------------------
# within_scope
# ---------------------------------------------------------------------------


class TestWithinScope:
    """Data scope restriction checks."""

    def test_empty_scope_allows_all(self) -> None:
        token = DelegationCapabilityToken(
            token_id="t1",
            delegatee="test",
            goal_id=None,
            allowed_actions=[],
            denied_actions=[],
            data_scope={},
        )
        assert token.within_scope("accounts", "acc-1") is True

    def test_missing_data_type_allows(self) -> None:
        token = DelegationCapabilityToken(
            token_id="t1",
            delegatee="test",
            goal_id=None,
            allowed_actions=[],
            denied_actions=[],
            data_scope={"accounts": ["acc-1"]},
        )
        assert token.within_scope("leads", "lead-99") is True

    def test_listed_id_allowed(self) -> None:
        token = DelegationCapabilityToken(
            token_id="t1",
            delegatee="test",
            goal_id=None,
            allowed_actions=[],
            denied_actions=[],
            data_scope={"accounts": ["acc-1", "acc-2"]},
        )
        assert token.within_scope("accounts", "acc-1") is True

    def test_unlisted_id_denied(self) -> None:
        token = DelegationCapabilityToken(
            token_id="t1",
            delegatee="test",
            goal_id=None,
            allowed_actions=[],
            denied_actions=[],
            data_scope={"accounts": ["acc-1"]},
        )
        assert token.within_scope("accounts", "acc-99") is False


# ---------------------------------------------------------------------------
# Unknown agent
# ---------------------------------------------------------------------------


class TestUnknownAgent:
    """DCTMinter raises ValueError for unrecognized agents."""

    def test_raises_value_error(self) -> None:
        minter = DCTMinter()
        with pytest.raises(ValueError):
            minter.mint(delegatee="nonexistent_agent", goal_id="g1")

    def test_error_message_lists_known_agents(self) -> None:
        minter = DCTMinter()
        with pytest.raises(ValueError, match="hunter"):
            minter.mint(delegatee="nonexistent_agent", goal_id="g1")


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------


class TestSerialization:
    """to_dict / from_dict preserve all fields."""

    def test_round_trip_preserves_all_fields(self) -> None:
        original = DelegationCapabilityToken(
            token_id="abc-123",
            delegatee="hunter",
            goal_id="goal-42",
            allowed_actions=["read_exa", "read_apollo"],
            denied_actions=["send_email"],
            data_scope={"accounts": ["acc-1"]},
            time_limit_seconds=600,
        )
        data = original.to_dict()
        restored = DelegationCapabilityToken.from_dict(data)

        assert restored.token_id == original.token_id
        assert restored.delegatee == original.delegatee
        assert restored.goal_id == original.goal_id
        assert restored.allowed_actions == original.allowed_actions
        assert restored.denied_actions == original.denied_actions
        assert restored.data_scope == original.data_scope
        assert restored.time_limit_seconds == original.time_limit_seconds
        assert restored.created_at == original.created_at

    def test_created_at_is_iso_string_in_dict(self) -> None:
        token = DelegationCapabilityToken(
            token_id="t1",
            delegatee="test",
            goal_id=None,
            allowed_actions=[],
            denied_actions=[],
        )
        data = token.to_dict()
        assert isinstance(data["created_at"], str)
        # Should parse back without error
        datetime.fromisoformat(data["created_at"])


# ---------------------------------------------------------------------------
# Additional scope merging
# ---------------------------------------------------------------------------


class TestAdditionalScope:
    """DCTMinter merges additional_scope into minted token."""

    def test_extra_allowed_appended(self) -> None:
        minter = DCTMinter()
        token = minter.mint(
            delegatee="hunter",
            goal_id="g1",
            additional_scope={"allowed_actions": ["special_read"]},
        )
        assert "special_read" in token.allowed_actions
        assert "read_exa" in token.allowed_actions  # original still present

    def test_extra_denied_appended(self) -> None:
        minter = DCTMinter()
        token = minter.mint(
            delegatee="hunter",
            goal_id="g1",
            additional_scope={"denied_actions": ["extra_deny"]},
        )
        assert "extra_deny" in token.denied_actions
        assert "send_email" in token.denied_actions  # original still present

    def test_data_scope_merged(self) -> None:
        minter = DCTMinter()
        token = minter.mint(
            delegatee="hunter",
            goal_id="g1",
            additional_scope={"data_scope": {"accounts": ["acc-1"]}},
        )
        assert token.data_scope == {"accounts": ["acc-1"]}

    def test_no_additional_scope_gives_empty_data_scope(self) -> None:
        minter = DCTMinter()
        token = minter.mint(delegatee="hunter", goal_id="g1")
        assert token.data_scope == {}


# ---------------------------------------------------------------------------
# Default deny
# ---------------------------------------------------------------------------


class TestDefaultDeny:
    """Actions not in allow list are denied by default."""

    def test_unlisted_action_denied(self) -> None:
        token = DelegationCapabilityToken(
            token_id="t1",
            delegatee="test",
            goal_id=None,
            allowed_actions=["read_exa"],
            denied_actions=[],
        )
        assert token.can_perform("write_crm") is False

    def test_empty_lists_deny_everything(self) -> None:
        token = DelegationCapabilityToken(
            token_id="t1",
            delegatee="test",
            goal_id=None,
            allowed_actions=[],
            denied_actions=[],
        )
        assert token.can_perform("read_anything_at_all") is False


# ---------------------------------------------------------------------------
# Agent name normalization
# ---------------------------------------------------------------------------


class TestAgentNameNormalization:
    """DCTMinter normalizes agent names for profile lookup."""

    def test_capitalized_name_works(self) -> None:
        minter = DCTMinter()
        token = minter.mint(delegatee="Hunter", goal_id="g1")
        assert token.can_perform("read_exa")
        assert token.delegatee == "Hunter"  # preserves original

    def test_hunter_pro_maps_to_hunter(self) -> None:
        minter = DCTMinter()
        token = minter.mint(delegatee="Hunter Pro", goal_id="g1")
        assert token.can_perform("read_exa")
        assert token.delegatee == "Hunter Pro"  # preserves original
