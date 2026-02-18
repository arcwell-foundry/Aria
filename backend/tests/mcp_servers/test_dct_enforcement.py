"""Tests for DCT enforcement middleware across all servers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from src.core.capability_tokens import DelegationCapabilityToken
from src.mcp_servers.middleware import DCTViolation, enforce_dct


# ── Authorized action ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enforce_dct_allows_authorized_action(analyst_dct) -> None:  # noqa: ANN001
    """An analyst DCT should allow read_pubmed without raising."""
    # enforce_dct is sync, but test is async for consistency with the suite
    enforce_dct("pubmed_search", "read_pubmed", analyst_dct.to_dict())
    # No exception means pass


# ── Unauthorized action ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enforce_dct_denies_unauthorized_action(scout_dct) -> None:  # noqa: ANN001
    """A scout DCT should deny write_crm (not in scout's allowed actions)."""
    with pytest.raises(DCTViolation):
        enforce_dct("crm_write", "write_crm", scout_dct.to_dict())


# ── Expired token ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enforce_dct_expired_raises(expired_dct) -> None:  # noqa: ANN001
    """An expired DCT should be rejected regardless of action permissions."""
    with pytest.raises(DCTViolation):
        enforce_dct("pubmed_search", "read_pubmed", expired_dct.to_dict())


# ── None (fail-open) ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enforce_dct_none_fails_open() -> None:
    """When _dct is None the middleware should fail-open (no exception)."""
    enforce_dct("any_tool", "any_action", None)
    # No exception means pass


# ── Deny wins over allow ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enforce_dct_denied_action_wins_over_allowed() -> None:
    """When an action appears in both allowed and denied lists, deny wins."""
    dct = DelegationCapabilityToken(
        token_id=str(uuid.uuid4()),
        delegatee="test-agent",
        goal_id="test-goal",
        allowed_actions=["read_exa"],
        denied_actions=["read_exa"],
        time_limit_seconds=300,
        created_at=datetime.now(UTC),
    )

    with pytest.raises(DCTViolation):
        enforce_dct("exa_search_web", "read_exa", dct.to_dict())


# ── DCTViolation attributes ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_dct_violation_attributes(scout_dct) -> None:  # noqa: ANN001
    """DCTViolation should expose tool_name, delegatee, and action attributes."""
    with pytest.raises(DCTViolation) as exc_info:
        enforce_dct("crm_write", "write_crm", scout_dct.to_dict())

    violation = exc_info.value
    assert violation.tool_name == "crm_write"
    assert violation.delegatee == "scout"
    assert violation.action == "write_crm"
    # Verify the string representation is informative
    assert "scout" in str(violation)
    assert "write_crm" in str(violation)
    assert "crm_write" in str(violation)
