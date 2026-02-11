"""Tests for DynamicAgentFactory."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.dynamic_factory import DynamicAgentFactory, DynamicAgentSpec
from src.agents.skill_aware_agent import SkillAwareAgent


@pytest.fixture
def factory():
    return DynamicAgentFactory()


@pytest.fixture
def sample_spec():
    return DynamicAgentSpec(
        name="BoardPrepAgent",
        description="Prepares board meeting materials and executive summaries",
        goal_context="Q1 board meeting preparation for Lonza partnership",
        required_capabilities=["research", "document_generation"],
        task_description="Compile competitive analysis for board deck",
        skill_access=["market-analysis", "competitive-positioning"],
    )


def test_spec_creation(sample_spec):
    assert sample_spec.name == "BoardPrepAgent"
    assert len(sample_spec.required_capabilities) == 2
    assert len(sample_spec.skill_access) == 2


def test_create_agent_class(factory, sample_spec):
    """Factory creates a class that extends SkillAwareAgent."""
    agent_cls = factory.create_agent_class(sample_spec)
    assert issubclass(agent_cls, SkillAwareAgent)
    assert agent_cls.name == "BoardPrepAgent"
    assert agent_cls.description == sample_spec.description
    assert agent_cls.agent_id == "dynamic_BoardPrepAgent"


def test_created_class_has_correct_skills(factory, sample_spec):
    """Dynamic agent class should have skill access configured."""
    factory.create_agent_class(sample_spec)
    from src.agents.skill_aware_agent import AGENT_SKILLS
    assert "dynamic_BoardPrepAgent" in AGENT_SKILLS
    assert AGENT_SKILLS["dynamic_BoardPrepAgent"] == ["market-analysis", "competitive-positioning"]


def test_create_agent_instance(factory, sample_spec):
    """Factory can create an instance from a spec."""
    mock_llm = MagicMock()
    agent = factory.create_agent(
        spec=sample_spec,
        llm_client=mock_llm,
        user_id="user-1",
    )
    assert isinstance(agent, SkillAwareAgent)
    assert agent.name == "BoardPrepAgent"
    assert agent.user_id == "user-1"


@pytest.mark.asyncio
async def test_agent_execute_uses_llm(factory, sample_spec):
    """Dynamic agent's execute() should call LLM with the generated system prompt."""
    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(return_value='{"result": "analysis complete"}')

    agent = factory.create_agent(
        spec=sample_spec,
        llm_client=mock_llm,
        user_id="user-1",
    )
    result = await agent.execute({"task": "compile analysis"})
    assert result.success
    assert result.data is not None
    mock_llm.generate_response.assert_called_once()


def test_build_system_prompt(factory, sample_spec):
    """System prompt should include agent name, description, and goal context."""
    prompt = factory._build_system_prompt(sample_spec)
    assert "BoardPrepAgent" in prompt
    assert "board meeting materials" in prompt
    assert "Q1 board meeting" in prompt


def test_multiple_agents_independent(factory):
    """Creating multiple dynamic agents should not interfere with each other."""
    spec_a = DynamicAgentSpec(
        name="AgentA",
        description="Agent A",
        goal_context="Context A",
        required_capabilities=["research"],
        task_description="Task A",
        skill_access=["market-analysis"],
    )
    spec_b = DynamicAgentSpec(
        name="AgentB",
        description="Agent B",
        goal_context="Context B",
        required_capabilities=["writing"],
        task_description="Task B",
        skill_access=["email-sequence"],
    )

    cls_a = factory.create_agent_class(spec_a)
    cls_b = factory.create_agent_class(spec_b)

    assert cls_a.name == "AgentA"
    assert cls_b.name == "AgentB"
    assert cls_a is not cls_b
