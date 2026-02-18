"""Tests for VerifierAgent module."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest


# --- Section 1: Class structure ---

def test_verifier_agent_has_name_and_description() -> None:
    """Test VerifierAgent has correct name and description."""
    from src.agents.verifier import VerifierAgent

    assert VerifierAgent.name == "Verifier"
    assert VerifierAgent.description == "Quality verification and compliance checking"


def test_verifier_agent_extends_base_agent() -> None:
    """Test VerifierAgent extends BaseAgent directly."""
    from src.agents.base import BaseAgent
    from src.agents.verifier import VerifierAgent

    assert issubclass(VerifierAgent, BaseAgent)


def test_verifier_agent_initializes_with_llm_and_user() -> None:
    """Test VerifierAgent initializes correctly."""
    from src.agents.base import AgentStatus
    from src.agents.verifier import VerifierAgent

    mock_llm = MagicMock()
    agent = VerifierAgent(llm_client=mock_llm, user_id="user-123")

    assert agent.llm == mock_llm
    assert agent.user_id == "user-123"
    assert agent.status == AgentStatus.IDLE


def test_verifier_agent_registers_verify_tool() -> None:
    """Test VerifierAgent registers a verify tool."""
    from src.agents.verifier import VerifierAgent

    mock_llm = MagicMock()
    agent = VerifierAgent(llm_client=mock_llm, user_id="user-123")

    assert "verify" in agent.tools


def test_verifier_agent_accepts_persona_builder() -> None:
    """Test VerifierAgent accepts persona_builder."""
    from src.agents.verifier import VerifierAgent

    mock_llm = MagicMock()
    mock_persona = MagicMock()
    agent = VerifierAgent(
        llm_client=mock_llm, user_id="user-123", persona_builder=mock_persona,
    )

    assert agent.persona_builder == mock_persona


# --- Section 2: VerificationPolicy ---

def test_verification_policy_research_brief() -> None:
    """Test RESEARCH_BRIEF policy has correct checks."""
    from src.agents.verifier import VERIFICATION_POLICIES

    policy = VERIFICATION_POLICIES["RESEARCH_BRIEF"]
    assert "source_exists" in policy.checks
    assert "data_freshness" in policy.checks
    assert "no_hallucination" in policy.checks
    assert "compliance" in policy.checks


def test_verification_policy_email_draft() -> None:
    """Test EMAIL_DRAFT policy has correct checks."""
    from src.agents.verifier import VERIFICATION_POLICIES

    policy = VERIFICATION_POLICIES["EMAIL_DRAFT"]
    assert "tone_match" in policy.checks
    assert "compliance" in policy.checks
    assert "recipient_appropriate" in policy.checks


def test_verification_policy_battle_card() -> None:
    """Test BATTLE_CARD policy has correct checks."""
    from src.agents.verifier import VERIFICATION_POLICIES

    policy = VERIFICATION_POLICIES["BATTLE_CARD"]
    assert "data_currency" in policy.checks
    assert "claim_supported" in policy.checks
    assert "balanced" in policy.checks


def test_verification_policy_strategy() -> None:
    """Test STRATEGY policy has correct checks."""
    from src.agents.verifier import VERIFICATION_POLICIES

    policy = VERIFICATION_POLICIES["STRATEGY"]
    assert "logical_consistency" in policy.checks
    assert "goal_alignment" in policy.checks
    assert "risk_assessment" in policy.checks


# --- Section 3: VerificationResult ---

def test_verification_result_creation() -> None:
    """Test VerificationResult with all fields."""
    from src.agents.verifier import VerificationResult

    result = VerificationResult(
        passed=True, issues=[], confidence=0.95, suggestions=[],
    )
    assert result.passed is True
    assert result.confidence == 0.95


def test_verification_result_with_issues() -> None:
    """Test VerificationResult captures issues."""
    from src.agents.verifier import VerificationResult

    result = VerificationResult(
        passed=False,
        issues=["Citation PMID:12345 not found"],
        confidence=0.3,
        suggestions=["Replace with verified citation"],
    )
    assert result.passed is False
    assert len(result.issues) == 1


def test_verification_result_to_dict() -> None:
    """Test VerificationResult serializes to dict."""
    from src.agents.verifier import VerificationResult

    result = VerificationResult(
        passed=True, issues=[], confidence=0.9,
        suggestions=["Consider adding timestamps"],
    )
    d = result.to_dict()
    assert d["passed"] is True
    assert d["confidence"] == 0.9
    assert isinstance(d["suggestions"], list)
