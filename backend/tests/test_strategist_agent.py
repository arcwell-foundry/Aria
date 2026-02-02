"""Tests for StrategistAgent module."""

import pytest
from unittest.mock import MagicMock


def test_strategist_agent_has_name_and_description() -> None:
    """Test StrategistAgent has correct name and description class attributes."""
    from src.agents.strategist import StrategistAgent

    assert StrategistAgent.name == "Strategist"
    assert StrategistAgent.description == "Strategic planning and pursuit orchestration"


def test_strategist_agent_extends_base_agent() -> None:
    """Test StrategistAgent extends BaseAgent."""
    from src.agents.base import BaseAgent
    from src.agents.strategist import StrategistAgent

    assert issubclass(StrategistAgent, BaseAgent)


def test_strategist_agent_initializes_with_llm_and_user() -> None:
    """Test StrategistAgent initializes with llm_client, user_id."""
    from src.agents.base import AgentStatus
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    assert agent.llm == mock_llm
    assert agent.user_id == "user-123"
    assert agent.status == AgentStatus.IDLE


def test_strategist_agent_registers_three_tools() -> None:
    """Test StrategistAgent._register_tools returns dict with 3 tools."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    tools = agent.tools

    assert len(tools) == 3
    assert "analyze_account" in tools
    assert "generate_strategy" in tools
    assert "create_timeline" in tools


def test_validate_input_accepts_valid_task() -> None:
    """Test validate_input accepts properly formatted task."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    valid_task = {
        "goal": {
            "title": "Close deal with Acme Corp",
            "type": "close",
        },
        "resources": {
            "available_agents": ["Hunter", "Analyst"],
            "time_horizon_days": 90,
        },
    }

    assert agent.validate_input(valid_task) is True


def test_validate_input_requires_goal() -> None:
    """Test validate_input rejects task without goal."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    invalid_task = {
        "resources": {
            "available_agents": ["Hunter"],
            "time_horizon_days": 30,
        },
    }

    assert agent.validate_input(invalid_task) is False


def test_validate_input_requires_goal_title() -> None:
    """Test validate_input requires goal to have title."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    invalid_task = {
        "goal": {
            "type": "research",
        },
        "resources": {
            "available_agents": ["Analyst"],
            "time_horizon_days": 30,
        },
    }

    assert agent.validate_input(invalid_task) is False


def test_validate_input_requires_goal_type() -> None:
    """Test validate_input requires goal to have type."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    invalid_task = {
        "goal": {
            "title": "Some goal",
        },
        "resources": {
            "available_agents": ["Hunter"],
            "time_horizon_days": 30,
        },
    }

    assert agent.validate_input(invalid_task) is False


def test_validate_input_requires_resources() -> None:
    """Test validate_input rejects task without resources."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    invalid_task = {
        "goal": {
            "title": "Some goal",
            "type": "lead_gen",
        },
    }

    assert agent.validate_input(invalid_task) is False


def test_validate_input_requires_time_horizon() -> None:
    """Test validate_input requires time_horizon_days in resources."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    invalid_task = {
        "goal": {
            "title": "Some goal",
            "type": "outreach",
        },
        "resources": {
            "available_agents": ["Scribe"],
        },
    }

    assert agent.validate_input(invalid_task) is False


def test_validate_input_validates_goal_type() -> None:
    """Test validate_input validates goal type is one of allowed values."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    invalid_task = {
        "goal": {
            "title": "Some goal",
            "type": "invalid_type",
        },
        "resources": {
            "available_agents": ["Hunter"],
            "time_horizon_days": 30,
        },
    }

    assert agent.validate_input(invalid_task) is False


def test_validate_input_allows_optional_constraints() -> None:
    """Test validate_input allows optional constraints."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    task_with_constraints = {
        "goal": {
            "title": "Close deal with Acme Corp",
            "type": "close",
        },
        "resources": {
            "available_agents": ["Hunter", "Analyst"],
            "time_horizon_days": 90,
        },
        "constraints": {
            "deadline": "2026-06-01",
            "exclusions": ["Competitor Inc"],
        },
    }

    assert agent.validate_input(task_with_constraints) is True


# Task 3: _analyze_account tests


@pytest.mark.asyncio
async def test_analyze_account_returns_analysis_dict() -> None:
    """Test _analyze_account returns analysis dictionary."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    goal = {
        "title": "Close deal with Acme Corp",
        "type": "close",
        "target_company": "Acme Corp",
    }

    result = await agent._analyze_account(goal=goal)

    assert isinstance(result, dict)
    assert "opportunities" in result
    assert "challenges" in result
    assert "recommendation" in result


@pytest.mark.asyncio
async def test_analyze_account_considers_competitive_landscape() -> None:
    """Test _analyze_account considers competitive landscape."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    goal = {
        "title": "Close deal with Acme Corp",
        "type": "close",
        "target_company": "Acme Corp",
    }
    context = {
        "competitive_landscape": {
            "competitors": ["Competitor A", "Competitor B"],
            "our_strengths": ["Price", "Support"],
            "our_weaknesses": ["Brand recognition"],
        },
    }

    result = await agent._analyze_account(goal=goal, context=context)

    assert "competitive_analysis" in result
    assert isinstance(result["competitive_analysis"], dict)


@pytest.mark.asyncio
async def test_analyze_account_considers_stakeholder_map() -> None:
    """Test _analyze_account considers stakeholder map."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    goal = {
        "title": "Close deal with Acme Corp",
        "type": "close",
        "target_company": "Acme Corp",
    }
    context = {
        "stakeholder_map": {
            "decision_makers": [{"name": "John CEO", "role": "CEO"}],
            "influencers": [{"name": "Jane VP", "role": "VP Sales"}],
            "blockers": [],
        },
    }

    result = await agent._analyze_account(goal=goal, context=context)

    assert "stakeholder_analysis" in result


@pytest.mark.asyncio
async def test_analyze_account_identifies_key_actions() -> None:
    """Test _analyze_account identifies key actions."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    goal = {
        "title": "Research Acme Corp pipeline",
        "type": "research",
        "target_company": "Acme Corp",
    }

    result = await agent._analyze_account(goal=goal)

    assert "key_actions" in result
    assert isinstance(result["key_actions"], list)


# Task 4: _generate_strategy tests


@pytest.mark.asyncio
async def test_generate_strategy_returns_strategy_dict() -> None:
    """Test _generate_strategy returns strategy dictionary."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    goal = {
        "title": "Close deal with Acme Corp",
        "type": "close",
        "target_company": "Acme Corp",
    }
    analysis = {
        "opportunities": ["Strong product fit"],
        "challenges": ["Budget constraints"],
        "key_actions": ["Engage decision maker"],
    }
    resources = {
        "available_agents": ["Hunter", "Analyst", "Scribe"],
        "time_horizon_days": 90,
    }

    result = await agent._generate_strategy(
        goal=goal, analysis=analysis, resources=resources
    )

    assert isinstance(result, dict)
    assert "phases" in result
    assert "agent_tasks" in result
    assert "risks" in result
    assert "success_criteria" in result


@pytest.mark.asyncio
async def test_generate_strategy_creates_phases() -> None:
    """Test _generate_strategy creates multiple phases."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    goal = {"title": "Close deal", "type": "close"}
    analysis = {"opportunities": [], "challenges": [], "key_actions": []}
    resources = {"available_agents": ["Hunter"], "time_horizon_days": 90}

    result = await agent._generate_strategy(
        goal=goal, analysis=analysis, resources=resources
    )

    assert len(result["phases"]) >= 2
    for phase in result["phases"]:
        assert "phase_number" in phase
        assert "name" in phase
        assert "description" in phase
        assert "duration_days" in phase
        assert "objectives" in phase


@pytest.mark.asyncio
async def test_generate_strategy_creates_agent_tasks() -> None:
    """Test _generate_strategy creates tasks for available agents."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    goal = {"title": "Lead generation", "type": "lead_gen"}
    analysis = {"opportunities": [], "challenges": [], "key_actions": []}
    resources = {"available_agents": ["Hunter", "Analyst"], "time_horizon_days": 30}

    result = await agent._generate_strategy(
        goal=goal, analysis=analysis, resources=resources
    )

    assert len(result["agent_tasks"]) > 0
    for task in result["agent_tasks"]:
        assert "id" in task
        assert "agent" in task
        assert "task_type" in task
        assert "description" in task
        assert "phase" in task
        assert "priority" in task
        assert task["agent"] in resources["available_agents"]


@pytest.mark.asyncio
async def test_generate_strategy_identifies_risks() -> None:
    """Test _generate_strategy identifies risks."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    goal = {"title": "Close deal", "type": "close"}
    analysis = {
        "opportunities": [],
        "challenges": ["Budget constraints", "Long sales cycle"],
        "key_actions": [],
    }
    resources = {"available_agents": ["Scribe"], "time_horizon_days": 60}

    result = await agent._generate_strategy(
        goal=goal, analysis=analysis, resources=resources
    )

    assert len(result["risks"]) > 0
    for risk in result["risks"]:
        assert "description" in risk
        assert "likelihood" in risk
        assert "impact" in risk
        assert "mitigation" in risk


@pytest.mark.asyncio
async def test_generate_strategy_respects_constraints() -> None:
    """Test _generate_strategy respects provided constraints."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    goal = {"title": "Lead generation", "type": "lead_gen"}
    analysis = {"opportunities": [], "challenges": [], "key_actions": []}
    resources = {"available_agents": ["Hunter"], "time_horizon_days": 30}
    constraints = {
        "deadline": "2026-03-01",
        "exclusions": ["Competitor Inc"],
        "compliance_notes": ["GDPR compliance required"],
    }

    result = await agent._generate_strategy(
        goal=goal, analysis=analysis, resources=resources, constraints=constraints
    )

    assert "constraints_applied" in result
    assert result["constraints_applied"]["has_deadline"] is True


# Task 5: _create_timeline tests


@pytest.mark.asyncio
async def test_create_timeline_returns_timeline_dict() -> None:
    """Test _create_timeline returns timeline dictionary."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    strategy = {
        "phases": [
            {"phase_number": 1, "name": "Discovery", "duration_days": 10},
            {"phase_number": 2, "name": "Execution", "duration_days": 20},
        ],
        "agent_tasks": [
            {"id": "task-1", "agent": "Hunter", "phase": 1},
        ],
    }

    result = await agent._create_timeline(
        strategy=strategy, time_horizon_days=30
    )

    assert isinstance(result, dict)
    assert "milestones" in result
    assert "schedule" in result


@pytest.mark.asyncio
async def test_create_timeline_creates_milestones() -> None:
    """Test _create_timeline creates milestones for each phase."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    strategy = {
        "phases": [
            {"phase_number": 1, "name": "Discovery", "duration_days": 10, "objectives": ["Find leads"]},
            {"phase_number": 2, "name": "Engagement", "duration_days": 20, "objectives": ["Contact leads"]},
        ],
        "agent_tasks": [],
    }

    result = await agent._create_timeline(
        strategy=strategy, time_horizon_days=30
    )

    assert len(result["milestones"]) >= 2
    for milestone in result["milestones"]:
        assert "id" in milestone
        assert "name" in milestone
        assert "phase" in milestone
        assert "target_date" in milestone
        assert "success_criteria" in milestone


@pytest.mark.asyncio
async def test_create_timeline_respects_deadline() -> None:
    """Test _create_timeline respects hard deadline."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    strategy = {
        "phases": [
            {"phase_number": 1, "name": "Phase 1", "duration_days": 30},
            {"phase_number": 2, "name": "Phase 2", "duration_days": 30},
        ],
        "agent_tasks": [],
    }

    result = await agent._create_timeline(
        strategy=strategy,
        time_horizon_days=90,
        deadline="2026-03-01",
    )

    # All milestones should be on or before deadline
    for milestone in result["milestones"]:
        assert milestone["target_date"] <= "2026-03-01"


@pytest.mark.asyncio
async def test_create_timeline_schedules_tasks() -> None:
    """Test _create_timeline schedules agent tasks."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    strategy = {
        "phases": [
            {"phase_number": 1, "name": "Discovery", "duration_days": 15},
        ],
        "agent_tasks": [
            {"id": "task-1", "agent": "Hunter", "phase": 1, "priority": "high"},
            {"id": "task-2", "agent": "Analyst", "phase": 1, "priority": "medium"},
        ],
    }

    result = await agent._create_timeline(
        strategy=strategy, time_horizon_days=30
    )

    assert "task_schedule" in result
    assert len(result["task_schedule"]) == 2
    for task_entry in result["task_schedule"]:
        assert "task_id" in task_entry
        assert "start_date" in task_entry
        assert "end_date" in task_entry


@pytest.mark.asyncio
async def test_create_timeline_calculates_dates() -> None:
    """Test _create_timeline calculates actual dates."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    strategy = {
        "phases": [
            {"phase_number": 1, "name": "Phase 1", "duration_days": 7},
        ],
        "agent_tasks": [],
    }

    result = await agent._create_timeline(
        strategy=strategy, time_horizon_days=30
    )

    # Should have start_date and computed milestone dates
    assert "start_date" in result
    # Dates should be valid ISO format
    for milestone in result["milestones"]:
        # Simple check that target_date looks like ISO date
        assert len(milestone["target_date"]) == 10  # YYYY-MM-DD
        assert "-" in milestone["target_date"]
