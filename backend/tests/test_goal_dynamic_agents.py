"""Tests for dynamic agent integration in GoalExecutionService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_deps():
    with patch("src.services.goal_execution.SupabaseClient") as mock_db_cls, \
         patch("src.services.goal_execution.LLMClient") as mock_llm_cls, \
         patch("src.services.goal_execution.ws_manager"):
        mock_db = MagicMock()
        mock_db_cls.get_client.return_value = mock_db
        mock_llm = MagicMock()
        mock_llm.generate_response = AsyncMock(return_value='{"result": "ok"}')
        mock_llm_cls.return_value = mock_llm
        yield mock_db, mock_llm


@pytest.fixture
def service(mock_deps):  # noqa: ARG001
    from src.services.goal_execution import GoalExecutionService
    return GoalExecutionService()


def test_register_dynamic_agent(service):
    """GoalExecutionService should accept dynamic agent registration."""
    from src.agents.dynamic_factory import DynamicAgentFactory, DynamicAgentSpec

    factory = DynamicAgentFactory()
    spec = DynamicAgentSpec(
        name="TestDynamicAgent",
        description="Test agent",
        goal_context="Testing",
        required_capabilities=["research"],
        task_description="Run test analysis",
        skill_access=[],
    )
    agent_cls = factory.create_agent_class(spec)
    service.register_dynamic_agent("test_dynamic", agent_cls)
    assert "test_dynamic" in service._dynamic_agents


def test_create_agent_instance_uses_dynamic(service, mock_deps):
    """_create_agent_instance should find dynamically registered agents."""
    from src.agents.dynamic_factory import DynamicAgentFactory, DynamicAgentSpec

    factory = DynamicAgentFactory()
    spec = DynamicAgentSpec(
        name="CustomAgent",
        description="Custom agent for testing",
        goal_context="Testing dynamic dispatch",
        required_capabilities=["analysis"],
        task_description="Analyze data",
        skill_access=[],
    )
    agent_cls = factory.create_agent_class(spec)
    service.register_dynamic_agent("custom_agent", agent_cls)

    # _create_agent_instance should now find this agent type
    _, mock_llm = mock_deps
    agent = service._create_agent_instance("custom_agent", "user-1")
    assert agent is not None
    assert agent.name == "CustomAgent"
