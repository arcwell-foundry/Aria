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


# --- Section 4: verify() method ---

@pytest.mark.asyncio
async def test_verify_passes_well_formed_research_output() -> None:
    """Test verify returns passed=True for well-formed output."""
    from src.agents.verifier import VERIFICATION_POLICIES, VerifierAgent

    mock_llm = MagicMock()
    llm_result = json.dumps({
        "passed": True, "issues": [], "confidence": 0.92, "suggestions": [],
    })
    resp = MagicMock()
    resp.text = llm_result
    resp.usage = None
    mock_llm.generate_response_with_thinking = AsyncMock(return_value=resp)

    agent = VerifierAgent(llm_client=mock_llm, user_id="user-123")
    agent_output = {
        "type": "research_brief",
        "content": "BioGenix Phase III trial NCT04123456 shows 67% ORR...",
        "sources": [{"pmid": "38123456", "title": "BioGenix Phase III results", "year": 2026}],
    }

    result = await agent.verify(agent_output, VERIFICATION_POLICIES["RESEARCH_BRIEF"])

    assert result.passed is True
    assert result.confidence >= 0.8


@pytest.mark.asyncio
async def test_verify_fails_hallucinated_citations() -> None:
    """Test verify catches hallucinated citations."""
    from src.agents.verifier import VERIFICATION_POLICIES, VerifierAgent

    mock_llm = MagicMock()
    llm_result = json.dumps({
        "passed": False,
        "issues": [
            "Citation PMID:99999999 does not appear to exist",
            "Data freshness: cited study from 2019 exceeds 30-day window",
        ],
        "confidence": 0.25,
        "suggestions": ["Remove unverifiable citation", "Use more recent source"],
    })
    resp = MagicMock()
    resp.text = llm_result
    resp.usage = None
    mock_llm.generate_response_with_thinking = AsyncMock(return_value=resp)

    agent = VerifierAgent(llm_client=mock_llm, user_id="user-123")
    agent_output = {
        "type": "research_brief",
        "content": "According to Smith et al. (PMID:99999999)...",
        "sources": [{"pmid": "99999999", "title": "Fabricated Study", "year": 2019}],
    }

    result = await agent.verify(agent_output, VERIFICATION_POLICIES["RESEARCH_BRIEF"])

    assert result.passed is False
    assert len(result.issues) >= 1
    assert result.confidence < 0.5


@pytest.mark.asyncio
async def test_verify_catches_compliance_violations() -> None:
    """Test verify catches off-label implications."""
    from src.agents.verifier import VERIFICATION_POLICIES, VerifierAgent

    mock_llm = MagicMock()
    llm_result = json.dumps({
        "passed": False,
        "issues": [
            "Off-label claim: 'effective for pediatric use' not in approved indications",
            "Missing required disclaimer for promotional content",
        ],
        "confidence": 0.15,
        "suggestions": ["Remove off-label claim", "Add medical disclaimer"],
    })
    resp = MagicMock()
    resp.text = llm_result
    resp.usage = None
    mock_llm.generate_response_with_thinking = AsyncMock(return_value=resp)

    agent = VerifierAgent(llm_client=mock_llm, user_id="user-123")
    agent_output = {
        "type": "email_draft",
        "content": "Our drug is effective for pediatric use and cures all symptoms...",
        "recipient": "dr.smith@hospital.org",
    }

    result = await agent.verify(agent_output, VERIFICATION_POLICIES["EMAIL_DRAFT"])

    assert result.passed is False
    assert any("off-label" in issue.lower() for issue in result.issues)


@pytest.mark.asyncio
async def test_verify_uses_extended_thinking() -> None:
    """Test verify calls generate_response_with_thinking (not generate_response)."""
    from src.agents.verifier import VERIFICATION_POLICIES, VerifierAgent

    mock_llm = MagicMock()
    resp = MagicMock()
    resp.text = json.dumps({"passed": True, "issues": [], "confidence": 0.88, "suggestions": []})
    resp.usage = None
    mock_llm.generate_response_with_thinking = AsyncMock(return_value=resp)
    mock_llm.generate_response = AsyncMock()

    agent = VerifierAgent(llm_client=mock_llm, user_id="user-123")
    await agent.verify({"type": "research_brief", "content": "Valid"}, VERIFICATION_POLICIES["RESEARCH_BRIEF"])

    mock_llm.generate_response_with_thinking.assert_awaited_once()
    mock_llm.generate_response.assert_not_awaited()


@pytest.mark.asyncio
async def test_verify_passes_user_id_for_cost_governor() -> None:
    """Test verify passes user_id for CostGovernor tracking."""
    from src.agents.verifier import VERIFICATION_POLICIES, VerifierAgent

    mock_llm = MagicMock()
    resp = MagicMock()
    resp.text = json.dumps({"passed": True, "issues": [], "confidence": 0.9, "suggestions": []})
    resp.usage = None
    mock_llm.generate_response_with_thinking = AsyncMock(return_value=resp)

    agent = VerifierAgent(llm_client=mock_llm, user_id="user-cost-verifier")
    await agent.verify({"type": "battle_card", "content": "Analysis"}, VERIFICATION_POLICIES["BATTLE_CARD"])

    call_kwargs = mock_llm.generate_response_with_thinking.call_args.kwargs
    assert call_kwargs["user_id"] == "user-cost-verifier"


@pytest.mark.asyncio
async def test_verify_uses_complex_thinking_effort() -> None:
    """Test verify uses 'complex' thinking effort."""
    from src.agents.verifier import VERIFICATION_POLICIES, VerifierAgent

    mock_llm = MagicMock()
    resp = MagicMock()
    resp.text = json.dumps({"passed": True, "issues": [], "confidence": 0.9, "suggestions": []})
    resp.usage = None
    mock_llm.generate_response_with_thinking = AsyncMock(return_value=resp)

    agent = VerifierAgent(llm_client=mock_llm, user_id="user-123")
    await agent.verify({"type": "strategy", "content": "Plan"}, VERIFICATION_POLICIES["STRATEGY"])

    call_kwargs = mock_llm.generate_response_with_thinking.call_args.kwargs
    assert call_kwargs["thinking_effort"] == "complex"


@pytest.mark.asyncio
async def test_verify_uses_persona_builder() -> None:
    """Test verify uses PersonaBuilder for skeptical reviewer persona."""
    from src.agents.verifier import VERIFICATION_POLICIES, VerifierAgent

    mock_llm = MagicMock()
    resp = MagicMock()
    resp.text = json.dumps({"passed": True, "issues": [], "confidence": 0.9, "suggestions": []})
    resp.usage = None
    mock_llm.generate_response_with_thinking = AsyncMock(return_value=resp)

    mock_persona_ctx = MagicMock()
    mock_persona_ctx.to_system_prompt.return_value = "You are ARIA's Verifier"
    mock_persona_builder = MagicMock()
    mock_persona_builder.build = AsyncMock(return_value=mock_persona_ctx)

    agent = VerifierAgent(
        llm_client=mock_llm, user_id="user-123", persona_builder=mock_persona_builder,
    )
    await agent.verify({"type": "research_brief", "content": "Content"}, VERIFICATION_POLICIES["RESEARCH_BRIEF"])

    mock_persona_builder.build.assert_called_once()
    call_kwargs = mock_llm.generate_response_with_thinking.call_args.kwargs
    assert call_kwargs["system_prompt"] == "You are ARIA's Verifier"


@pytest.mark.asyncio
async def test_verify_handles_llm_failure_gracefully() -> None:
    """Test verify fails conservatively when LLM errors."""
    from src.agents.verifier import VERIFICATION_POLICIES, VerifierAgent

    mock_llm = MagicMock()
    mock_llm.generate_response_with_thinking = AsyncMock(side_effect=RuntimeError("API error"))

    agent = VerifierAgent(llm_client=mock_llm, user_id="user-123")
    result = await agent.verify(
        {"type": "research_brief", "content": "Content"}, VERIFICATION_POLICIES["RESEARCH_BRIEF"],
    )

    assert result.passed is False
    assert len(result.issues) >= 1


@pytest.mark.asyncio
async def test_verify_handles_malformed_llm_response() -> None:
    """Test verify fails conservatively on non-JSON LLM output."""
    from src.agents.verifier import VERIFICATION_POLICIES, VerifierAgent

    mock_llm = MagicMock()
    resp = MagicMock()
    resp.text = "This is not valid JSON"
    resp.usage = None
    mock_llm.generate_response_with_thinking = AsyncMock(return_value=resp)

    agent = VerifierAgent(llm_client=mock_llm, user_id="user-123")
    result = await agent.verify(
        {"type": "research_brief", "content": "Content"}, VERIFICATION_POLICIES["RESEARCH_BRIEF"],
    )

    assert result.passed is False


# --- Section 5: execute() method ---

@pytest.mark.asyncio
async def test_execute_delegates_to_verify() -> None:
    """Test execute delegates to verify with task params."""
    from src.agents.base import AgentResult
    from src.agents.verifier import VerifierAgent

    mock_llm = MagicMock()
    resp = MagicMock()
    resp.text = json.dumps({"passed": True, "issues": [], "confidence": 0.9, "suggestions": []})
    resp.usage = None
    mock_llm.generate_response_with_thinking = AsyncMock(return_value=resp)

    agent = VerifierAgent(llm_client=mock_llm, user_id="user-123")
    task = {
        "agent_output": {"type": "research_brief", "content": "Valid output"},
        "policy_name": "RESEARCH_BRIEF",
    }

    result = await agent.execute(task)

    assert isinstance(result, AgentResult)
    assert result.success is True
    assert result.data["passed"] is True


@pytest.mark.asyncio
async def test_execute_returns_failed_verification_in_data() -> None:
    """Test execute succeeds but data.passed=False for failed verification."""
    from src.agents.verifier import VerifierAgent

    mock_llm = MagicMock()
    resp = MagicMock()
    resp.text = json.dumps({
        "passed": False, "issues": ["Issue found"], "confidence": 0.3, "suggestions": ["Fix it"],
    })
    resp.usage = None
    mock_llm.generate_response_with_thinking = AsyncMock(return_value=resp)

    agent = VerifierAgent(llm_client=mock_llm, user_id="user-123")
    task = {
        "agent_output": {"type": "email_draft", "content": "Bad content"},
        "policy_name": "EMAIL_DRAFT",
    }

    result = await agent.execute(task)

    assert result.success is True
    assert result.data["passed"] is False


@pytest.mark.asyncio
async def test_execute_validates_task_has_agent_output() -> None:
    """Test execute fails on missing agent_output."""
    from src.agents.verifier import VerifierAgent

    mock_llm = MagicMock()
    agent = VerifierAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent.run({"policy_name": "RESEARCH_BRIEF"})

    assert result.success is False
    assert "validation" in (result.error or "").lower()


# --- Section 6: Module exports ---

def test_verifier_exported_from_agents_module() -> None:
    """Test VerifierAgent is exported from agents module."""
    from src.agents import VerifierAgent

    assert VerifierAgent.name == "Verifier"


def test_all_includes_verifier_exports() -> None:
    """Test __all__ includes VerifierAgent and VerificationResult."""
    from src.agents import __all__

    assert "VerifierAgent" in __all__
    assert "VerificationResult" in __all__
