"""Tests for skill-aware agent base class."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.base import AgentResult, BaseAgent
from src.agents.skill_aware_agent import (
    AGENT_SKILLS,
    SkillAnalysis,
    SkillAwareAgent,
)


# ---------------------------------------------------------------------------
# Helper: Concrete test subclass of SkillAwareAgent
# ---------------------------------------------------------------------------


class _TestAgent(SkillAwareAgent):
    """Concrete subclass used in tests."""

    agent_id = "hunter"
    name = "Test Hunter"
    description = "A test hunter agent"

    def _register_tools(self) -> dict[str, Any]:
        """Return empty tool registry."""
        return {}

    async def execute(self, task: dict[str, Any]) -> AgentResult:
        """Return a simple success result."""
        return AgentResult(success=True, data={"native": True})


# ===========================================================================
# 1. SkillAnalysis dataclass tests
# ===========================================================================


def test_skill_analysis_dataclass_exists() -> None:
    """Test that SkillAnalysis can be instantiated with all fields."""
    analysis = SkillAnalysis(
        skills_needed=True,
        recommended_skills=["pdf", "docx"],
        reasoning="Document generation required",
    )
    assert analysis.skills_needed is True
    assert analysis.recommended_skills == ["pdf", "docx"]
    assert analysis.reasoning == "Document generation required"


def test_skill_analysis_defaults() -> None:
    """Test SkillAnalysis with minimal / falsy values."""
    analysis = SkillAnalysis(
        skills_needed=False,
        recommended_skills=[],
        reasoning="",
    )
    assert analysis.skills_needed is False
    assert analysis.recommended_skills == []
    assert analysis.reasoning == ""


# ===========================================================================
# 2. AGENT_SKILLS mapping tests
# ===========================================================================


def test_agent_skills_mapping_has_all_agents() -> None:
    """Test AGENT_SKILLS contains all 6 agent identifiers."""
    expected_agents = {"hunter", "analyst", "strategist", "scribe", "operator", "scout"}
    assert set(AGENT_SKILLS.keys()) == expected_agents


def test_agent_skills_hunter() -> None:
    """Test hunter agent has exact skill list."""
    assert AGENT_SKILLS["hunter"] == [
        "competitor-analysis",
        "lead-research",
        "company-profiling",
    ]


def test_agent_skills_analyst() -> None:
    """Test analyst agent has exact skill list."""
    assert AGENT_SKILLS["analyst"] == [
        "clinical-trial-analysis",
        "pubmed-research",
        "data-visualization",
    ]


def test_agent_skills_strategist() -> None:
    """Test strategist agent has exact skill list."""
    assert AGENT_SKILLS["strategist"] == [
        "market-analysis",
        "competitive-positioning",
        "pricing-strategy",
    ]


def test_agent_skills_scribe() -> None:
    """Test scribe agent has exact skill list."""
    assert AGENT_SKILLS["scribe"] == [
        "pdf",
        "docx",
        "pptx",
        "xlsx",
        "email-sequence",
    ]


def test_agent_skills_operator() -> None:
    """Test operator agent has exact skill list."""
    assert AGENT_SKILLS["operator"] == [
        "calendar-management",
        "crm-operations",
        "workflow-automation",
    ]


def test_agent_skills_scout() -> None:
    """Test scout agent has exact skill list."""
    assert AGENT_SKILLS["scout"] == [
        "regulatory-monitor",
        "news-aggregation",
        "signal-detection",
    ]


def test_agent_skills_values_are_lists() -> None:
    """Test that every value in AGENT_SKILLS is a non-empty list of strings."""
    for agent_id, skills in AGENT_SKILLS.items():
        assert isinstance(skills, list), f"{agent_id} skills should be a list"
        assert len(skills) > 0, f"{agent_id} should have at least one skill"
        for skill in skills:
            assert isinstance(skill, str), f"Skill '{skill}' for {agent_id} should be a string"


# ===========================================================================
# 3. SkillAwareAgent class tests
# ===========================================================================


def test_skill_aware_agent_extends_base_agent() -> None:
    """Test SkillAwareAgent is a subclass of BaseAgent."""
    assert issubclass(SkillAwareAgent, BaseAgent)


def test_skill_aware_agent_init_stores_agent_id() -> None:
    """Test that agent_id class attribute is accessible after init."""
    mock_llm = MagicMock()
    agent = _TestAgent(llm_client=mock_llm, user_id="user-1")
    assert agent.agent_id == "hunter"


def test_skill_aware_agent_init_without_skills() -> None:
    """Test initialization without skill orchestrator and index."""
    mock_llm = MagicMock()
    agent = _TestAgent(llm_client=mock_llm, user_id="user-1")
    assert agent.skill_orchestrator is None
    assert agent.skill_index is None
    assert agent.user_id == "user-1"
    assert agent.llm is mock_llm


def test_get_available_skills_returns_agent_skills() -> None:
    """Test _get_available_skills returns the correct list for the agent_id."""
    mock_llm = MagicMock()
    agent = _TestAgent(llm_client=mock_llm, user_id="user-1")
    skills = agent._get_available_skills()
    assert skills == AGENT_SKILLS["hunter"]


def test_get_available_skills_unknown_agent_returns_empty() -> None:
    """Test _get_available_skills returns [] for an unknown agent_id."""

    class UnknownAgent(SkillAwareAgent):
        agent_id = "unknown-agent"
        name = "Unknown"
        description = "Unknown agent"

        def _register_tools(self) -> dict[str, Any]:
            return {}

        async def execute(self, task: dict[str, Any]) -> AgentResult:
            return AgentResult(success=True, data={})

    mock_llm = MagicMock()
    agent = UnknownAgent(llm_client=mock_llm, user_id="user-1")
    assert agent._get_available_skills() == []


# ===========================================================================
# 4. _analyze_skill_needs tests
# ===========================================================================


@pytest.mark.asyncio
async def test_analyze_skill_needs_returns_skill_analysis() -> None:
    """Test _analyze_skill_needs returns a SkillAnalysis when LLM recommends skills."""
    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(
        return_value=json.dumps({
            "skills_needed": True,
            "recommended_skills": ["competitor-analysis"],
            "reasoning": "Competitor data needed",
        })
    )

    agent = _TestAgent(llm_client=mock_llm, user_id="user-1")
    result = await agent._analyze_skill_needs({"goal": "analyze competitor"})

    assert isinstance(result, SkillAnalysis)
    assert result.skills_needed is True
    assert result.recommended_skills == ["competitor-analysis"]
    assert result.reasoning == "Competitor data needed"


@pytest.mark.asyncio
async def test_analyze_skill_needs_no_skills_needed() -> None:
    """Test _analyze_skill_needs when LLM says no skills are needed."""
    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(
        return_value=json.dumps({
            "skills_needed": False,
            "recommended_skills": [],
            "reasoning": "Agent can handle this natively",
        })
    )

    agent = _TestAgent(llm_client=mock_llm, user_id="user-1")
    result = await agent._analyze_skill_needs({"goal": "simple lookup"})

    assert result.skills_needed is False
    assert result.recommended_skills == []


@pytest.mark.asyncio
async def test_analyze_skill_needs_filters_to_available_skills() -> None:
    """Test that _analyze_skill_needs filters out skills not in the agent's list."""
    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(
        return_value=json.dumps({
            "skills_needed": True,
            "recommended_skills": ["competitor-analysis", "unknown-skill", "pdf"],
            "reasoning": "Multiple skills suggested",
        })
    )

    agent = _TestAgent(llm_client=mock_llm, user_id="user-1")
    result = await agent._analyze_skill_needs({"goal": "complex task"})

    # Only "competitor-analysis" is in hunter's skill list
    assert result.recommended_skills == ["competitor-analysis"]
    assert result.skills_needed is True


@pytest.mark.asyncio
async def test_analyze_skill_needs_handles_llm_error() -> None:
    """Test _analyze_skill_needs returns safe fallback on LLM error."""
    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(side_effect=RuntimeError("API down"))

    agent = _TestAgent(llm_client=mock_llm, user_id="user-1")
    result = await agent._analyze_skill_needs({"goal": "anything"})

    assert result.skills_needed is False
    assert result.recommended_skills == []
    assert "Skill analysis error" in result.reasoning


@pytest.mark.asyncio
async def test_analyze_skill_needs_handles_malformed_json() -> None:
    """Test _analyze_skill_needs handles non-JSON LLM response gracefully."""
    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(return_value="Not valid JSON at all")

    agent = _TestAgent(llm_client=mock_llm, user_id="user-1")
    result = await agent._analyze_skill_needs({"goal": "test"})

    assert result.skills_needed is False
    assert result.recommended_skills == []
    assert "Failed to parse LLM response" in result.reasoning


# ===========================================================================
# 5. execute_with_skills tests
# ===========================================================================


@pytest.mark.asyncio
async def test_execute_with_skills_delegates_to_orchestrator() -> None:
    """Test execute_with_skills uses orchestrator when skills are recommended."""
    # Mock LLM to recommend skills
    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(
        return_value=json.dumps({
            "skills_needed": True,
            "recommended_skills": ["competitor-analysis"],
            "reasoning": "Need competitor data",
        })
    )

    # Mock skill index
    mock_index = MagicMock()
    mock_skill_entry = MagicMock()
    mock_skill_entry.id = "skill-uuid-1"
    mock_index.search = AsyncMock(return_value=[mock_skill_entry])

    # Mock orchestrator
    mock_orchestrator = MagicMock()

    mock_plan = MagicMock()
    mock_plan.plan_id = "plan-123"
    mock_plan.steps = [MagicMock()]
    mock_orchestrator.create_execution_plan = AsyncMock(return_value=mock_plan)

    mock_wm_entry = MagicMock()
    mock_wm_entry.step_number = 1
    mock_wm_entry.skill_id = "skill-uuid-1"
    mock_wm_entry.status = "completed"
    mock_wm_entry.summary = "Done"
    mock_wm_entry.artifacts = []
    mock_orchestrator.execute_plan = AsyncMock(return_value=[mock_wm_entry])

    agent = _TestAgent(
        llm_client=mock_llm,
        user_id="user-1",
        skill_orchestrator=mock_orchestrator,
        skill_index=mock_index,
    )

    result = await agent.execute_with_skills({"goal": "analyze competitor"})

    assert result.success is True
    assert result.data["skill_execution"] is True
    assert result.data["plan_id"] == "plan-123"
    assert len(result.data["steps"]) == 1
    assert result.data["steps"][0]["status"] == "completed"

    # Verify orchestrator was called
    mock_orchestrator.create_execution_plan.assert_awaited_once()
    mock_orchestrator.execute_plan.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_with_skills_falls_back_to_execute() -> None:
    """Test execute_with_skills falls back to native execute when no skills needed."""
    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(
        return_value=json.dumps({
            "skills_needed": False,
            "recommended_skills": [],
            "reasoning": "No skills required",
        })
    )

    agent = _TestAgent(llm_client=mock_llm, user_id="user-1")
    result = await agent.execute_with_skills({"goal": "simple task"})

    # Should use native execute which returns {"native": True}
    assert result.success is True
    assert result.data == {"native": True}


@pytest.mark.asyncio
async def test_execute_with_skills_no_orchestrator_falls_back() -> None:
    """Test execute_with_skills falls back when orchestrator is not set."""
    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(
        return_value=json.dumps({
            "skills_needed": True,
            "recommended_skills": ["competitor-analysis"],
            "reasoning": "Need skills but no orchestrator",
        })
    )

    # No orchestrator or index provided
    agent = _TestAgent(llm_client=mock_llm, user_id="user-1")
    result = await agent.execute_with_skills({"goal": "needs skills"})

    # Falls back to native execute
    assert result.success is True
    assert result.data == {"native": True}


@pytest.mark.asyncio
async def test_execute_with_skills_handles_orchestrator_error() -> None:
    """Test execute_with_skills handles orchestrator exceptions gracefully."""
    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(
        return_value=json.dumps({
            "skills_needed": True,
            "recommended_skills": ["competitor-analysis"],
            "reasoning": "Skills needed",
        })
    )

    mock_index = MagicMock()
    mock_index.search = AsyncMock(side_effect=RuntimeError("Index unavailable"))

    mock_orchestrator = MagicMock()

    agent = _TestAgent(
        llm_client=mock_llm,
        user_id="user-1",
        skill_orchestrator=mock_orchestrator,
        skill_index=mock_index,
    )

    result = await agent.execute_with_skills({"goal": "will fail"})

    assert result.success is False
    assert "Skill execution failed" in (result.error or "")


# --- Agent Integration Tests ---


def test_hunter_extends_skill_aware_agent() -> None:
    """Test HunterAgent extends SkillAwareAgent."""
    from src.agents.hunter import HunterAgent

    assert issubclass(HunterAgent, SkillAwareAgent)


def test_hunter_has_correct_agent_id() -> None:
    """Test HunterAgent has agent_id='hunter'."""
    from src.agents.hunter import HunterAgent

    assert HunterAgent.agent_id == "hunter"


def test_hunter_init_accepts_skill_params() -> None:
    """Test HunterAgent accepts skill_orchestrator and skill_index."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    mock_orchestrator = MagicMock()
    mock_index = MagicMock()

    agent = HunterAgent(
        llm_client=mock_llm,
        user_id="user-123",
        skill_orchestrator=mock_orchestrator,
        skill_index=mock_index,
    )

    assert agent.skill_orchestrator is mock_orchestrator
    assert agent.skill_index is mock_index
    assert agent._company_cache == {}


def test_hunter_init_works_without_skill_params() -> None:
    """Test HunterAgent still works without skill parameters."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    assert agent.skill_orchestrator is None
    assert agent.skill_index is None
    assert agent._company_cache == {}


def test_analyst_extends_skill_aware_agent() -> None:
    """Test AnalystAgent extends SkillAwareAgent."""
    from src.agents.analyst import AnalystAgent

    assert issubclass(AnalystAgent, SkillAwareAgent)
    assert AnalystAgent.agent_id == "analyst"


def test_analyst_init_accepts_skill_params() -> None:
    """Test AnalystAgent accepts and stores skill parameters."""
    from src.agents.analyst import AnalystAgent

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    assert agent.skill_orchestrator is None
    assert agent.skill_index is None


def test_strategist_extends_skill_aware_agent() -> None:
    """Test StrategistAgent extends SkillAwareAgent."""
    from src.agents.strategist import StrategistAgent

    assert issubclass(StrategistAgent, SkillAwareAgent)
    assert StrategistAgent.agent_id == "strategist"


def test_strategist_init_accepts_skill_params() -> None:
    """Test StrategistAgent accepts and stores skill parameters."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    assert agent.skill_orchestrator is None
    assert agent.skill_index is None


def test_scribe_extends_skill_aware_agent() -> None:
    """Test ScribeAgent extends SkillAwareAgent."""
    from src.agents.scribe import ScribeAgent

    assert issubclass(ScribeAgent, SkillAwareAgent)
    assert ScribeAgent.agent_id == "scribe"


def test_scribe_init_accepts_skill_params() -> None:
    """Test ScribeAgent accepts and stores skill parameters."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    assert agent.skill_orchestrator is None
    assert agent.skill_index is None


def test_operator_extends_skill_aware_agent() -> None:
    """Test OperatorAgent extends SkillAwareAgent."""
    from src.agents.operator import OperatorAgent

    assert issubclass(OperatorAgent, SkillAwareAgent)
    assert OperatorAgent.agent_id == "operator"


def test_operator_init_accepts_skill_params() -> None:
    """Test OperatorAgent accepts and stores skill parameters."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    assert agent.skill_orchestrator is None
    assert agent.skill_index is None


def test_scout_extends_skill_aware_agent() -> None:
    """Test ScoutAgent extends SkillAwareAgent."""
    from src.agents.scout import ScoutAgent

    assert issubclass(ScoutAgent, SkillAwareAgent)
    assert ScoutAgent.agent_id == "scout"


def test_scout_init_accepts_skill_params() -> None:
    """Test ScoutAgent accepts and stores skill parameters."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    assert agent.skill_orchestrator is None
    assert agent.skill_index is None
