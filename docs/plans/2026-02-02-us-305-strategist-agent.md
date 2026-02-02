# US-305: Strategist Agent Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the Strategist agent for planning and synthesis, enabling ARIA to create effective pursuit strategies with phases, milestones, and sub-tasks for other agents.

**Architecture:** The StrategistAgent extends BaseAgent and implements strategic planning through three main tools: analyze_account (evaluate account context and opportunities), generate_strategy (create phased pursuit plan), and create_timeline (build milestone-based schedule). The execute method orchestrates these tools to produce comprehensive strategy documents. The agent considers competitive landscape, stakeholder mapping, and timing constraints when generating strategies.

**Tech Stack:** Python 3.11+, async/await patterns, Pydantic-style data models, unittest.mock for testing

---

## Acceptance Criteria Checklist

From PHASE_3_AGENTS.md US-305:
- [ ] `src/agents/strategist.py` extends BaseAgent
- [ ] Tools: analyze_account, generate_strategy, create_timeline
- [ ] Accepts: goal details, available resources, constraints
- [ ] Returns: actionable strategy with phases and milestones
- [ ] Considers: competitive landscape, stakeholder map, timing
- [ ] Generates sub-tasks for other agents
- [ ] Unit tests for strategy generation

---

## Data Models Reference

### StrategyInput (Task Schema)

```python
{
    "goal": {
        "title": str,              # e.g., "Close deal with Acme Corp"
        "type": str,               # lead_gen, research, outreach, close
        "description": str | None,
        "target_company": str | None,
        "target_value": float | None,
    },
    "resources": {
        "available_agents": list[str],  # ["Hunter", "Analyst", "Scribe"]
        "budget": float | None,
        "time_horizon_days": int,       # e.g., 90
    },
    "constraints": {
        "deadline": str | None,         # ISO date
        "exclusions": list[str],        # Companies/contacts to avoid
        "compliance_notes": list[str],  # Regulatory considerations
    },
    "context": {
        "competitive_landscape": dict | None,
        "stakeholder_map": dict | None,
        "previous_interactions": list[dict] | None,
    }
}
```

### Strategy (Output)

```python
{
    "goal_id": str,
    "title": str,
    "summary": str,                     # Executive summary
    "phases": list[Phase],
    "milestones": list[Milestone],
    "agent_tasks": list[AgentTask],     # Sub-tasks for other agents
    "risks": list[Risk],
    "success_criteria": list[str],
    "created_at": str,                  # ISO timestamp
}
```

### Phase

```python
{
    "phase_number": int,
    "name": str,                        # e.g., "Discovery", "Engagement", "Proposal"
    "description": str,
    "duration_days": int,
    "objectives": list[str],
    "dependencies": list[int] | None,   # Phase numbers this depends on
}
```

### Milestone

```python
{
    "id": str,
    "name": str,
    "phase": int,
    "target_date": str | None,          # ISO date
    "success_criteria": str,
    "owner": str | None,                # Agent name
}
```

### AgentTask

```python
{
    "id": str,
    "agent": str,                       # "Hunter", "Analyst", "Scribe", etc.
    "task_type": str,
    "description": str,
    "phase": int,
    "priority": str,                    # "high", "medium", "low"
    "inputs": dict,                     # Task-specific parameters
    "depends_on": list[str] | None,     # Task IDs this depends on
}
```

### Risk

```python
{
    "description": str,
    "likelihood": str,                  # "high", "medium", "low"
    "impact": str,                      # "high", "medium", "low"
    "mitigation": str,
}
```

---

### Task 1: Create Strategist Agent Skeleton

**Files:**
- Create: `backend/src/agents/strategist.py`
- Create: `backend/tests/test_strategist_agent.py`

**Step 1: Write failing tests for StrategistAgent initialization**

Create `backend/tests/test_strategist_agent.py`:

```python
"""Tests for StrategistAgent module."""

from unittest.mock import MagicMock

import pytest


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
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_strategist_agent.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'src.agents.strategist'"

**Step 3: Write minimal implementation**

Create `backend/src/agents/strategist.py`:

```python
"""StrategistAgent module for ARIA.

Provides strategic planning and pursuit orchestration capabilities,
creating actionable strategies with phases, milestones, and agent tasks.
"""

import logging
from typing import TYPE_CHECKING, Any

from src.agents.base import AgentResult, BaseAgent

if TYPE_CHECKING:
    from src.core.llm import LLMClient

logger = logging.getLogger(__name__)


class StrategistAgent(BaseAgent):
    """Strategic planning agent for pursuit orchestration.

    The Strategist agent analyzes account context, generates pursuit
    strategies, and creates timelines with milestones and agent tasks.
    """

    name = "Strategist"
    description = "Strategic planning and pursuit orchestration"

    def __init__(self, llm_client: "LLMClient", user_id: str) -> None:
        """Initialize the Strategist agent.

        Args:
            llm_client: LLM client for reasoning and generation.
            user_id: ID of the user this agent is working for.
        """
        super().__init__(llm_client=llm_client, user_id=user_id)

    def _register_tools(self) -> dict[str, Any]:
        """Register Strategist agent's planning tools.

        Returns:
            Dictionary mapping tool names to callable functions.
        """
        return {
            "analyze_account": self._analyze_account,
            "generate_strategy": self._generate_strategy,
            "create_timeline": self._create_timeline,
        }

    async def execute(self, task: dict[str, Any]) -> AgentResult:
        """Execute the strategist agent's primary task.

        Args:
            task: Task specification with parameters.

        Returns:
            AgentResult with success status and output data.
        """
        return AgentResult(success=True, data={})

    async def _analyze_account(
        self,
        goal: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Analyze account context and opportunities.

        Args:
            goal: Goal details including target company.
            context: Optional context with competitive landscape, stakeholders.

        Returns:
            Account analysis with opportunities and challenges.
        """
        return {}

    async def _generate_strategy(
        self,
        goal: dict[str, Any],
        analysis: dict[str, Any],
        resources: dict[str, Any],
        constraints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate pursuit strategy with phases.

        Args:
            goal: Goal details.
            analysis: Account analysis results.
            resources: Available resources and agents.
            constraints: Optional constraints like deadlines.

        Returns:
            Strategy with phases, milestones, and agent tasks.
        """
        return {}

    async def _create_timeline(
        self,
        strategy: dict[str, Any],
        time_horizon_days: int,
        deadline: str | None = None,
    ) -> dict[str, Any]:
        """Create timeline with milestones.

        Args:
            strategy: Generated strategy.
            time_horizon_days: Time horizon in days.
            deadline: Optional hard deadline.

        Returns:
            Timeline with scheduled milestones.
        """
        return {}
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_strategist_agent.py -v`

Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add backend/src/agents/strategist.py backend/tests/test_strategist_agent.py
git commit -m "feat(agents): add StrategistAgent skeleton with tool registration"
```

---

### Task 2: Implement validate_input for Strategy Task Schema

**Files:**
- Modify: `backend/src/agents/strategist.py`
- Modify: `backend/tests/test_strategist_agent.py`

**Step 1: Write failing tests for input validation**

Add to `backend/tests/test_strategist_agent.py`:

```python
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
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_strategist_agent.py::test_validate_input_accepts_valid_task tests/test_strategist_agent.py::test_validate_input_requires_goal -v`

Expected: FAIL - default validate_input returns True for everything

**Step 3: Write minimal implementation**

Add to `StrategistAgent` class in `backend/src/agents/strategist.py`:

```python
    # Valid goal types
    VALID_GOAL_TYPES = {"lead_gen", "research", "outreach", "close", "retention"}

    def validate_input(self, task: dict[str, Any]) -> bool:
        """Validate strategy task input before execution.

        Args:
            task: Task specification to validate.

        Returns:
            True if valid, False otherwise.
        """
        # Required: goal
        if "goal" not in task:
            return False

        goal = task["goal"]
        if not isinstance(goal, dict):
            return False

        # Goal must have title and type
        if "title" not in goal or not goal["title"]:
            return False

        if "type" not in goal:
            return False

        # Validate goal type
        if goal["type"] not in self.VALID_GOAL_TYPES:
            return False

        # Required: resources
        if "resources" not in task:
            return False

        resources = task["resources"]
        if not isinstance(resources, dict):
            return False

        # Resources must have time_horizon_days
        if "time_horizon_days" not in resources:
            return False

        time_horizon = resources["time_horizon_days"]
        if not isinstance(time_horizon, int) or time_horizon <= 0:
            return False

        return True
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_strategist_agent.py -v`

Expected: PASS (12 tests)

**Step 5: Commit**

```bash
git add backend/src/agents/strategist.py backend/tests/test_strategist_agent.py
git commit -m "feat(agents): add input validation to StrategistAgent"
```

---

### Task 3: Implement analyze_account Tool

**Files:**
- Modify: `backend/src/agents/strategist.py`
- Modify: `backend/tests/test_strategist_agent.py`

**Step 1: Write failing tests for analyze_account**

Add to `backend/tests/test_strategist_agent.py`:

```python
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
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_strategist_agent.py::test_analyze_account_returns_analysis_dict -v`

Expected: FAIL - current implementation returns empty dict

**Step 3: Write minimal implementation**

Replace `_analyze_account` in `backend/src/agents/strategist.py`:

```python
    async def _analyze_account(
        self,
        goal: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Analyze account context and opportunities.

        Evaluates the goal, target company, competitive landscape,
        and stakeholder map to identify opportunities and challenges.

        Args:
            goal: Goal details including target company.
            context: Optional context with competitive landscape, stakeholders.

        Returns:
            Account analysis with opportunities, challenges, and recommendations.
        """
        context = context or {}
        target_company = goal.get("target_company", "Unknown")
        goal_type = goal.get("type", "general")

        logger.info(
            f"Analyzing account for goal: {goal.get('title')}",
            extra={"target_company": target_company, "goal_type": goal_type},
        )

        analysis: dict[str, Any] = {
            "target_company": target_company,
            "goal_type": goal_type,
            "opportunities": [],
            "challenges": [],
            "key_actions": [],
            "recommendation": "",
        }

        # Analyze competitive landscape if provided
        competitive_landscape = context.get("competitive_landscape")
        if competitive_landscape:
            analysis["competitive_analysis"] = self._analyze_competitive(
                competitive_landscape
            )
            # Add opportunities from strengths
            for strength in competitive_landscape.get("our_strengths", []):
                analysis["opportunities"].append(f"Leverage strength: {strength}")
            # Add challenges from weaknesses
            for weakness in competitive_landscape.get("our_weaknesses", []):
                analysis["challenges"].append(f"Address weakness: {weakness}")

        # Analyze stakeholder map if provided
        stakeholder_map = context.get("stakeholder_map")
        if stakeholder_map:
            analysis["stakeholder_analysis"] = self._analyze_stakeholders(
                stakeholder_map
            )
            # Add key actions based on stakeholders
            for dm in stakeholder_map.get("decision_makers", []):
                analysis["key_actions"].append(
                    f"Engage decision maker: {dm.get('name', 'Unknown')}"
                )

        # Generate default opportunities and challenges based on goal type
        if goal_type == "lead_gen":
            analysis["opportunities"].append("Identify new prospects matching ICP")
            analysis["key_actions"].append("Run Hunter agent for lead discovery")
        elif goal_type == "research":
            analysis["opportunities"].append("Gather competitive intelligence")
            analysis["key_actions"].append("Run Analyst agent for research")
        elif goal_type == "outreach":
            analysis["opportunities"].append("Personalize outreach based on research")
            analysis["key_actions"].append("Run Scribe agent for communication drafts")
        elif goal_type == "close":
            analysis["opportunities"].append("Accelerate deal timeline")
            analysis["challenges"].append("Navigate procurement process")
            analysis["key_actions"].append("Prepare proposal and ROI documentation")

        # Generate recommendation
        analysis["recommendation"] = self._generate_recommendation(
            goal_type, analysis["opportunities"], analysis["challenges"]
        )

        return analysis

    def _analyze_competitive(
        self,
        landscape: dict[str, Any],
    ) -> dict[str, Any]:
        """Analyze competitive landscape.

        Args:
            landscape: Competitive landscape data.

        Returns:
            Competitive analysis summary.
        """
        competitors = landscape.get("competitors", [])
        strengths = landscape.get("our_strengths", [])
        weaknesses = landscape.get("our_weaknesses", [])

        return {
            "competitor_count": len(competitors),
            "competitors": competitors,
            "strength_count": len(strengths),
            "weakness_count": len(weaknesses),
            "competitive_position": (
                "strong" if len(strengths) > len(weaknesses) else "needs_improvement"
            ),
        }

    def _analyze_stakeholders(
        self,
        stakeholder_map: dict[str, Any],
    ) -> dict[str, Any]:
        """Analyze stakeholder map.

        Args:
            stakeholder_map: Stakeholder information.

        Returns:
            Stakeholder analysis summary.
        """
        decision_makers = stakeholder_map.get("decision_makers", [])
        influencers = stakeholder_map.get("influencers", [])
        blockers = stakeholder_map.get("blockers", [])

        return {
            "decision_maker_count": len(decision_makers),
            "influencer_count": len(influencers),
            "blocker_count": len(blockers),
            "engagement_priority": decision_makers + influencers,
            "risk_level": "high" if blockers else "low",
        }

    def _generate_recommendation(
        self,
        goal_type: str,
        opportunities: list[str],
        challenges: list[str],
    ) -> str:
        """Generate strategic recommendation.

        Args:
            goal_type: Type of goal.
            opportunities: Identified opportunities.
            challenges: Identified challenges.

        Returns:
            Strategic recommendation text.
        """
        if not opportunities and not challenges:
            return f"Proceed with standard {goal_type} approach."

        if len(opportunities) > len(challenges):
            return (
                f"Favorable conditions for {goal_type}. "
                f"Capitalize on {len(opportunities)} identified opportunities."
            )
        else:
            return (
                f"Address {len(challenges)} challenges before proceeding with {goal_type}. "
                "Consider risk mitigation strategies."
            )
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_strategist_agent.py -v`

Expected: PASS (16 tests)

**Step 5: Commit**

```bash
git add backend/src/agents/strategist.py backend/tests/test_strategist_agent.py
git commit -m "feat(agents): implement analyze_account tool with competitive and stakeholder analysis"
```

---

### Task 4: Implement generate_strategy Tool

**Files:**
- Modify: `backend/src/agents/strategist.py`
- Modify: `backend/tests/test_strategist_agent.py`

**Step 1: Write failing tests for generate_strategy**

Add to `backend/tests/test_strategist_agent.py`:

```python
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

    # Strategy should acknowledge constraints
    assert "constraints_applied" in result
    assert result["constraints_applied"]["has_deadline"] is True
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_strategist_agent.py::test_generate_strategy_returns_strategy_dict -v`

Expected: FAIL - current implementation returns empty dict

**Step 3: Write minimal implementation**

Replace `_generate_strategy` in `backend/src/agents/strategist.py`:

```python
    async def _generate_strategy(
        self,
        goal: dict[str, Any],
        analysis: dict[str, Any],
        resources: dict[str, Any],
        constraints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate pursuit strategy with phases.

        Creates a comprehensive strategy including phases, agent tasks,
        risks, and success criteria based on goal analysis.

        Args:
            goal: Goal details.
            analysis: Account analysis results.
            resources: Available resources and agents.
            constraints: Optional constraints like deadlines.

        Returns:
            Strategy with phases, milestones, and agent tasks.
        """
        import uuid

        constraints = constraints or {}
        goal_type = goal.get("type", "general")
        time_horizon = resources.get("time_horizon_days", 90)
        available_agents = resources.get("available_agents", [])

        logger.info(
            f"Generating strategy for: {goal.get('title')}",
            extra={
                "goal_type": goal_type,
                "time_horizon": time_horizon,
                "agent_count": len(available_agents),
            },
        )

        # Generate phases based on goal type
        phases = self._generate_phases(goal_type, time_horizon)

        # Generate agent tasks based on available agents and phases
        agent_tasks = self._generate_agent_tasks(
            goal_type, available_agents, phases, analysis
        )

        # Identify risks from challenges
        risks = self._generate_risks(analysis.get("challenges", []), constraints)

        # Generate success criteria
        success_criteria = self._generate_success_criteria(goal_type, goal)

        strategy: dict[str, Any] = {
            "goal_title": goal.get("title"),
            "goal_type": goal_type,
            "summary": self._generate_summary(goal, phases, agent_tasks),
            "phases": phases,
            "agent_tasks": agent_tasks,
            "risks": risks,
            "success_criteria": success_criteria,
            "constraints_applied": {
                "has_deadline": "deadline" in constraints,
                "exclusion_count": len(constraints.get("exclusions", [])),
                "compliance_notes": constraints.get("compliance_notes", []),
            },
        }

        return strategy

    def _generate_phases(
        self,
        goal_type: str,
        time_horizon: int,
    ) -> list[dict[str, Any]]:
        """Generate phases based on goal type.

        Args:
            goal_type: Type of goal.
            time_horizon: Time horizon in days.

        Returns:
            List of phase definitions.
        """
        # Standard phase templates by goal type
        phase_templates: dict[str, list[dict[str, Any]]] = {
            "lead_gen": [
                {
                    "name": "Discovery",
                    "description": "Identify and qualify potential leads",
                    "objectives": ["Define ICP criteria", "Search for prospects"],
                    "duration_pct": 0.3,
                },
                {
                    "name": "Enrichment",
                    "description": "Enrich lead data and prioritize",
                    "objectives": ["Gather company data", "Score leads"],
                    "duration_pct": 0.4,
                },
                {
                    "name": "Handoff",
                    "description": "Prepare leads for outreach",
                    "objectives": ["Create lead profiles", "Assign to pipeline"],
                    "duration_pct": 0.3,
                },
            ],
            "research": [
                {
                    "name": "Scoping",
                    "description": "Define research questions and sources",
                    "objectives": ["Clarify research goals", "Identify data sources"],
                    "duration_pct": 0.2,
                },
                {
                    "name": "Investigation",
                    "description": "Conduct research and gather data",
                    "objectives": ["Query scientific databases", "Analyze findings"],
                    "duration_pct": 0.5,
                },
                {
                    "name": "Synthesis",
                    "description": "Compile and present findings",
                    "objectives": ["Create research report", "Generate insights"],
                    "duration_pct": 0.3,
                },
            ],
            "outreach": [
                {
                    "name": "Preparation",
                    "description": "Research recipients and prepare messaging",
                    "objectives": ["Research contacts", "Craft messaging"],
                    "duration_pct": 0.3,
                },
                {
                    "name": "Execution",
                    "description": "Send communications and track responses",
                    "objectives": ["Send outreach", "Monitor engagement"],
                    "duration_pct": 0.5,
                },
                {
                    "name": "Follow-up",
                    "description": "Follow up and nurture responses",
                    "objectives": ["Send follow-ups", "Schedule meetings"],
                    "duration_pct": 0.2,
                },
            ],
            "close": [
                {
                    "name": "Discovery",
                    "description": "Understand needs and decision process",
                    "objectives": ["Map stakeholders", "Identify requirements"],
                    "duration_pct": 0.2,
                },
                {
                    "name": "Proposal",
                    "description": "Prepare and present proposal",
                    "objectives": ["Create proposal", "Present solution"],
                    "duration_pct": 0.3,
                },
                {
                    "name": "Negotiation",
                    "description": "Negotiate terms and address concerns",
                    "objectives": ["Handle objections", "Finalize terms"],
                    "duration_pct": 0.3,
                },
                {
                    "name": "Closing",
                    "description": "Complete deal and handoff",
                    "objectives": ["Sign contract", "Begin onboarding"],
                    "duration_pct": 0.2,
                },
            ],
        }

        templates = phase_templates.get(
            goal_type,
            [
                {
                    "name": "Planning",
                    "description": "Plan the approach",
                    "objectives": ["Define approach"],
                    "duration_pct": 0.3,
                },
                {
                    "name": "Execution",
                    "description": "Execute the plan",
                    "objectives": ["Complete tasks"],
                    "duration_pct": 0.7,
                },
            ],
        )

        phases = []
        for i, template in enumerate(templates, start=1):
            duration_days = int(time_horizon * template["duration_pct"])
            phases.append(
                {
                    "phase_number": i,
                    "name": template["name"],
                    "description": template["description"],
                    "duration_days": max(1, duration_days),
                    "objectives": template["objectives"],
                    "dependencies": [i - 1] if i > 1 else None,
                }
            )

        return phases

    def _generate_agent_tasks(
        self,
        goal_type: str,
        available_agents: list[str],
        phases: list[dict[str, Any]],
        analysis: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Generate tasks for available agents.

        Args:
            goal_type: Type of goal.
            available_agents: List of available agent names.
            phases: Generated phases.
            analysis: Account analysis.

        Returns:
            List of agent task definitions.
        """
        import uuid

        tasks: list[dict[str, Any]] = []
        task_counter = 0

        # Map agents to typical tasks
        agent_task_map: dict[str, list[dict[str, Any]]] = {
            "Hunter": [
                {
                    "task_type": "lead_discovery",
                    "description": "Search for companies matching ICP",
                    "priority": "high",
                    "phase": 1,
                },
                {
                    "task_type": "lead_enrichment",
                    "description": "Enrich company and contact data",
                    "priority": "medium",
                    "phase": 2,
                },
            ],
            "Analyst": [
                {
                    "task_type": "research",
                    "description": "Research target company and market",
                    "priority": "high",
                    "phase": 1,
                },
                {
                    "task_type": "competitive_analysis",
                    "description": "Analyze competitive landscape",
                    "priority": "medium",
                    "phase": 1,
                },
            ],
            "Scribe": [
                {
                    "task_type": "draft_outreach",
                    "description": "Draft personalized outreach messages",
                    "priority": "high",
                    "phase": 2,
                },
                {
                    "task_type": "draft_proposal",
                    "description": "Draft proposal document",
                    "priority": "high",
                    "phase": 2,
                },
            ],
            "Operator": [
                {
                    "task_type": "schedule_meetings",
                    "description": "Schedule meetings with stakeholders",
                    "priority": "medium",
                    "phase": 2,
                },
                {
                    "task_type": "crm_update",
                    "description": "Update CRM with progress",
                    "priority": "low",
                    "phase": 3,
                },
            ],
            "Scout": [
                {
                    "task_type": "monitor_signals",
                    "description": "Monitor news and signals about target",
                    "priority": "medium",
                    "phase": 1,
                },
            ],
        }

        for agent in available_agents:
            agent_tasks = agent_task_map.get(agent, [])
            for task_template in agent_tasks:
                task_counter += 1
                # Only include tasks for phases that exist
                if task_template["phase"] <= len(phases):
                    tasks.append(
                        {
                            "id": f"task-{task_counter}",
                            "agent": agent,
                            "task_type": task_template["task_type"],
                            "description": task_template["description"],
                            "phase": task_template["phase"],
                            "priority": task_template["priority"],
                            "inputs": {},
                            "depends_on": None,
                        }
                    )

        return tasks

    def _generate_risks(
        self,
        challenges: list[str],
        constraints: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Generate risk assessments.

        Args:
            challenges: Identified challenges.
            constraints: Applied constraints.

        Returns:
            List of risk definitions.
        """
        risks: list[dict[str, Any]] = []

        # Convert challenges to risks
        for challenge in challenges:
            risks.append(
                {
                    "description": challenge,
                    "likelihood": "medium",
                    "impact": "medium",
                    "mitigation": f"Address early: {challenge}",
                }
            )

        # Add constraint-based risks
        if constraints.get("deadline"):
            risks.append(
                {
                    "description": "Tight deadline may compress activities",
                    "likelihood": "high",
                    "impact": "medium",
                    "mitigation": "Prioritize critical path activities",
                }
            )

        # Add default risks if none identified
        if not risks:
            risks.append(
                {
                    "description": "Unforeseen obstacles may delay progress",
                    "likelihood": "low",
                    "impact": "medium",
                    "mitigation": "Build buffer time into schedule",
                }
            )

        return risks

    def _generate_success_criteria(
        self,
        goal_type: str,
        goal: dict[str, Any],
    ) -> list[str]:
        """Generate success criteria for the strategy.

        Args:
            goal_type: Type of goal.
            goal: Goal details.

        Returns:
            List of success criteria.
        """
        criteria_templates: dict[str, list[str]] = {
            "lead_gen": [
                "Identified qualified leads matching ICP",
                "Leads enriched with contact information",
                "Leads prioritized by fit score",
            ],
            "research": [
                "Research questions answered comprehensively",
                "Findings documented with citations",
                "Actionable insights generated",
            ],
            "outreach": [
                "Outreach messages sent to targets",
                "Response rate above threshold",
                "Meetings scheduled with interested parties",
            ],
            "close": [
                "Proposal presented to decision makers",
                "Objections addressed satisfactorily",
                "Contract signed or clear next steps defined",
            ],
        }

        return criteria_templates.get(
            goal_type,
            [
                "Goal objectives achieved",
                "Deliverables completed on time",
                "Stakeholders satisfied with outcome",
            ],
        )

    def _generate_summary(
        self,
        goal: dict[str, Any],
        phases: list[dict[str, Any]],
        agent_tasks: list[dict[str, Any]],
    ) -> str:
        """Generate executive summary.

        Args:
            goal: Goal details.
            phases: Generated phases.
            agent_tasks: Generated agent tasks.

        Returns:
            Executive summary text.
        """
        total_duration = sum(p["duration_days"] for p in phases)
        agent_count = len(set(t["agent"] for t in agent_tasks))

        return (
            f"Strategy for '{goal.get('title')}' spanning {total_duration} days "
            f"across {len(phases)} phases, utilizing {agent_count} agents "
            f"to execute {len(agent_tasks)} tasks."
        )
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_strategist_agent.py -v`

Expected: PASS (21 tests)

**Step 5: Commit**

```bash
git add backend/src/agents/strategist.py backend/tests/test_strategist_agent.py
git commit -m "feat(agents): implement generate_strategy tool with phases and agent tasks"
```

---

### Task 5: Implement create_timeline Tool

**Files:**
- Modify: `backend/src/agents/strategist.py`
- Modify: `backend/tests/test_strategist_agent.py`

**Step 1: Write failing tests for create_timeline**

Add to `backend/tests/test_strategist_agent.py`:

```python
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
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_strategist_agent.py::test_create_timeline_returns_timeline_dict -v`

Expected: FAIL - current implementation returns empty dict

**Step 3: Write minimal implementation**

Replace `_create_timeline` in `backend/src/agents/strategist.py` and add required imports:

Add to imports at top of file:
```python
from datetime import datetime, timedelta
```

Replace method:
```python
    async def _create_timeline(
        self,
        strategy: dict[str, Any],
        time_horizon_days: int,
        deadline: str | None = None,
    ) -> dict[str, Any]:
        """Create timeline with milestones.

        Schedules phases and tasks with actual dates, respecting
        any hard deadline constraints.

        Args:
            strategy: Generated strategy with phases and tasks.
            time_horizon_days: Time horizon in days.
            deadline: Optional hard deadline (ISO date string).

        Returns:
            Timeline with scheduled milestones and task schedule.
        """
        start_date = datetime.utcnow().date()
        phases = strategy.get("phases", [])
        agent_tasks = strategy.get("agent_tasks", [])

        logger.info(
            f"Creating timeline starting {start_date}",
            extra={
                "time_horizon": time_horizon_days,
                "phase_count": len(phases),
                "deadline": deadline,
            },
        )

        # Parse deadline if provided
        end_date: datetime | None = None
        if deadline:
            try:
                end_date = datetime.fromisoformat(deadline)
                # Adjust time horizon if deadline is earlier
                days_to_deadline = (end_date.date() - start_date).days
                if days_to_deadline < time_horizon_days:
                    time_horizon_days = days_to_deadline
            except ValueError:
                logger.warning(f"Invalid deadline format: {deadline}")

        # Calculate phase dates
        phase_schedule: list[dict[str, Any]] = []
        current_date = start_date
        total_phase_days = sum(p.get("duration_days", 0) for p in phases)

        # Scale phases if they exceed time horizon
        scale_factor = 1.0
        if total_phase_days > time_horizon_days:
            scale_factor = time_horizon_days / total_phase_days

        for phase in phases:
            phase_duration = int(phase.get("duration_days", 7) * scale_factor)
            phase_duration = max(1, phase_duration)  # Minimum 1 day

            phase_end = current_date + timedelta(days=phase_duration)

            phase_schedule.append(
                {
                    "phase_number": phase.get("phase_number"),
                    "name": phase.get("name"),
                    "start_date": current_date.isoformat(),
                    "end_date": phase_end.isoformat(),
                    "duration_days": phase_duration,
                }
            )

            current_date = phase_end

        # Create milestones (one per phase completion)
        milestones: list[dict[str, Any]] = []
        for i, scheduled_phase in enumerate(phase_schedule):
            phase_info = phases[i] if i < len(phases) else {}
            objectives = phase_info.get("objectives", [])

            milestones.append(
                {
                    "id": f"milestone-{i + 1}",
                    "name": f"{scheduled_phase['name']} Complete",
                    "phase": scheduled_phase["phase_number"],
                    "target_date": scheduled_phase["end_date"],
                    "success_criteria": (
                        objectives[0] if objectives else f"Phase {i + 1} objectives met"
                    ),
                    "owner": None,
                }
            )

        # Schedule agent tasks within their phases
        task_schedule: list[dict[str, Any]] = []
        for task in agent_tasks:
            task_phase = task.get("phase", 1)

            # Find the phase schedule
            phase_sched = next(
                (p for p in phase_schedule if p["phase_number"] == task_phase),
                phase_schedule[0] if phase_schedule else None,
            )

            if phase_sched:
                # High priority tasks start at phase start
                # Medium/low priority tasks start at phase midpoint
                phase_start = datetime.fromisoformat(phase_sched["start_date"])
                phase_end = datetime.fromisoformat(phase_sched["end_date"])
                phase_mid = phase_start + (phase_end - phase_start) / 2

                priority = task.get("priority", "medium")
                if priority == "high":
                    task_start = phase_start
                else:
                    task_start = phase_mid

                task_schedule.append(
                    {
                        "task_id": task.get("id"),
                        "agent": task.get("agent"),
                        "start_date": task_start.date().isoformat(),
                        "end_date": phase_end.date().isoformat(),
                        "priority": priority,
                    }
                )

        # Ensure all milestone dates respect deadline
        if deadline:
            for milestone in milestones:
                if milestone["target_date"] > deadline:
                    milestone["target_date"] = deadline

        timeline: dict[str, Any] = {
            "start_date": start_date.isoformat(),
            "end_date": current_date.isoformat(),
            "time_horizon_days": time_horizon_days,
            "deadline": deadline,
            "schedule": phase_schedule,
            "milestones": milestones,
            "task_schedule": task_schedule,
        }

        return timeline
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_strategist_agent.py -v`

Expected: PASS (26 tests)

**Step 5: Commit**

```bash
git add backend/src/agents/strategist.py backend/tests/test_strategist_agent.py
git commit -m "feat(agents): implement create_timeline tool with milestone scheduling"
```

---

### Task 6: Implement execute Method (Full Orchestration)

**Files:**
- Modify: `backend/src/agents/strategist.py`
- Modify: `backend/tests/test_strategist_agent.py`

**Step 1: Write failing tests for execute**

Add to `backend/tests/test_strategist_agent.py`:

```python
@pytest.mark.asyncio
async def test_execute_returns_agent_result() -> None:
    """Test execute returns AgentResult with strategy data."""
    from src.agents.base import AgentResult
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "goal": {
            "title": "Close deal with Acme Corp",
            "type": "close",
            "target_company": "Acme Corp",
        },
        "resources": {
            "available_agents": ["Hunter", "Analyst", "Scribe"],
            "time_horizon_days": 90,
        },
    }

    result = await agent.execute(task)

    assert isinstance(result, AgentResult)
    assert result.success is True
    assert isinstance(result.data, dict)


@pytest.mark.asyncio
async def test_execute_returns_complete_strategy() -> None:
    """Test execute returns complete strategy with all components."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "goal": {
            "title": "Lead generation campaign",
            "type": "lead_gen",
        },
        "resources": {
            "available_agents": ["Hunter"],
            "time_horizon_days": 30,
        },
    }

    result = await agent.execute(task)
    data = result.data

    # Should have analysis
    assert "analysis" in data

    # Should have strategy
    assert "strategy" in data
    assert "phases" in data["strategy"]
    assert "agent_tasks" in data["strategy"]
    assert "risks" in data["strategy"]
    assert "success_criteria" in data["strategy"]

    # Should have timeline
    assert "timeline" in data
    assert "milestones" in data["timeline"]
    assert "schedule" in data["timeline"]


@pytest.mark.asyncio
async def test_execute_uses_context_for_analysis() -> None:
    """Test execute uses provided context for analysis."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "goal": {
            "title": "Close deal",
            "type": "close",
            "target_company": "Acme Corp",
        },
        "resources": {
            "available_agents": ["Hunter", "Scribe"],
            "time_horizon_days": 60,
        },
        "context": {
            "competitive_landscape": {
                "competitors": ["Competitor A"],
                "our_strengths": ["Price"],
            },
            "stakeholder_map": {
                "decision_makers": [{"name": "CEO John", "role": "CEO"}],
            },
        },
    }

    result = await agent.execute(task)
    analysis = result.data["analysis"]

    # Should include competitive analysis
    assert "competitive_analysis" in analysis

    # Should include stakeholder analysis
    assert "stakeholder_analysis" in analysis


@pytest.mark.asyncio
async def test_execute_respects_constraints() -> None:
    """Test execute respects provided constraints."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "goal": {
            "title": "Quick outreach",
            "type": "outreach",
        },
        "resources": {
            "available_agents": ["Scribe"],
            "time_horizon_days": 30,
        },
        "constraints": {
            "deadline": "2026-02-15",
        },
    }

    result = await agent.execute(task)
    timeline = result.data["timeline"]

    # Timeline should respect deadline
    assert timeline.get("deadline") == "2026-02-15"


@pytest.mark.asyncio
async def test_execute_includes_metadata() -> None:
    """Test execute includes metadata in result."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "goal": {
            "title": "Research project",
            "type": "research",
        },
        "resources": {
            "available_agents": ["Analyst"],
            "time_horizon_days": 14,
        },
    }

    result = await agent.execute(task)

    # Should have metadata
    assert "created_at" in result.data
    assert "goal_id" in result.data
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_strategist_agent.py::test_execute_returns_agent_result -v`

Expected: FAIL - current execute returns empty data

**Step 3: Write minimal implementation**

Add uuid import and replace `execute` method in `backend/src/agents/strategist.py`:

Add to imports:
```python
import uuid
```

Replace execute method:
```python
    async def execute(self, task: dict[str, Any]) -> AgentResult:
        """Execute the strategist agent's primary task.

        Orchestrates the full strategic planning workflow:
        1. Analyze account context
        2. Generate strategy with phases and tasks
        3. Create timeline with milestones

        Args:
            task: Task specification with:
                - goal: Goal details (title, type, target_company)
                - resources: Available resources (agents, time_horizon)
                - constraints: Optional constraints (deadline, exclusions)
                - context: Optional context (competitive, stakeholders)

        Returns:
            AgentResult with complete strategy document.
        """
        goal = task["goal"]
        resources = task["resources"]
        constraints = task.get("constraints", {})
        context = task.get("context", {})
        time_horizon = resources.get("time_horizon_days", 90)

        logger.info(
            f"Starting strategy generation for: {goal.get('title')}",
            extra={
                "goal_type": goal.get("type"),
                "time_horizon": time_horizon,
                "has_context": bool(context),
            },
        )

        try:
            # Step 1: Analyze account
            analysis = await self._analyze_account(goal=goal, context=context)

            # Step 2: Generate strategy
            strategy = await self._generate_strategy(
                goal=goal,
                analysis=analysis,
                resources=resources,
                constraints=constraints,
            )

            # Step 3: Create timeline
            timeline = await self._create_timeline(
                strategy=strategy,
                time_horizon_days=time_horizon,
                deadline=constraints.get("deadline"),
            )

            # Compile complete result
            result_data: dict[str, Any] = {
                "goal_id": str(uuid.uuid4()),
                "goal": goal,
                "analysis": analysis,
                "strategy": strategy,
                "timeline": timeline,
                "created_at": datetime.utcnow().isoformat(),
            }

            logger.info(
                f"Strategy generation complete for: {goal.get('title')}",
                extra={
                    "phase_count": len(strategy.get("phases", [])),
                    "task_count": len(strategy.get("agent_tasks", [])),
                    "milestone_count": len(timeline.get("milestones", [])),
                },
            )

            return AgentResult(
                success=True,
                data=result_data,
            )

        except Exception as e:
            logger.error(
                f"Strategy generation failed: {e}",
                extra={"goal_title": goal.get("title"), "error": str(e)},
            )
            return AgentResult(
                success=False,
                data={},
                error=str(e),
            )
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_strategist_agent.py -v`

Expected: PASS (31 tests)

**Step 5: Commit**

```bash
git add backend/src/agents/strategist.py backend/tests/test_strategist_agent.py
git commit -m "feat(agents): implement execute method with full strategy orchestration"
```

---

### Task 7: Add format_output for Strategy Formatting

**Files:**
- Modify: `backend/src/agents/strategist.py`
- Modify: `backend/tests/test_strategist_agent.py`

**Step 1: Write failing tests for format_output**

Add to `backend/tests/test_strategist_agent.py`:

```python
def test_format_output_adds_summary_stats() -> None:
    """Test format_output adds summary statistics."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    data = {
        "goal": {"title": "Test Goal", "type": "lead_gen"},
        "strategy": {
            "phases": [{"phase_number": 1}, {"phase_number": 2}],
            "agent_tasks": [{"id": "t1"}, {"id": "t2"}, {"id": "t3"}],
            "risks": [{"description": "Risk 1"}],
        },
        "timeline": {
            "milestones": [{"id": "m1"}, {"id": "m2"}],
            "time_horizon_days": 30,
        },
    }

    formatted = agent.format_output(data)

    assert "summary_stats" in formatted
    assert formatted["summary_stats"]["phase_count"] == 2
    assert formatted["summary_stats"]["task_count"] == 3
    assert formatted["summary_stats"]["milestone_count"] == 2
    assert formatted["summary_stats"]["risk_count"] == 1


def test_format_output_preserves_original_data() -> None:
    """Test format_output preserves all original data."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    data = {
        "goal": {"title": "Test", "type": "research"},
        "strategy": {"phases": []},
        "timeline": {"milestones": []},
        "analysis": {"opportunities": []},
    }

    formatted = agent.format_output(data)

    assert formatted["goal"] == data["goal"]
    assert formatted["strategy"] == data["strategy"]
    assert formatted["timeline"] == data["timeline"]
    assert formatted["analysis"] == data["analysis"]
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_strategist_agent.py::test_format_output_adds_summary_stats -v`

Expected: FAIL - default format_output returns unchanged data

**Step 3: Write minimal implementation**

Add to `StrategistAgent` class in `backend/src/agents/strategist.py`:

```python
    def format_output(self, data: Any) -> Any:
        """Format output data with summary statistics.

        Args:
            data: Raw strategy output data.

        Returns:
            Formatted strategy with summary statistics.
        """
        if not isinstance(data, dict):
            return data

        strategy = data.get("strategy", {})
        timeline = data.get("timeline", {})

        summary_stats = {
            "phase_count": len(strategy.get("phases", [])),
            "task_count": len(strategy.get("agent_tasks", [])),
            "milestone_count": len(timeline.get("milestones", [])),
            "risk_count": len(strategy.get("risks", [])),
            "time_horizon_days": timeline.get("time_horizon_days", 0),
        }

        data["summary_stats"] = summary_stats

        return data
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_strategist_agent.py -v`

Expected: PASS (33 tests)

**Step 5: Commit**

```bash
git add backend/src/agents/strategist.py backend/tests/test_strategist_agent.py
git commit -m "feat(agents): add format_output with summary statistics"
```

---

### Task 8: Add Integration Test for Full Strategist Workflow

**Files:**
- Modify: `backend/tests/test_strategist_agent.py`

**Step 1: Write integration test**

Add to `backend/tests/test_strategist_agent.py`:

```python
@pytest.mark.asyncio
async def test_full_strategist_workflow() -> None:
    """Integration test demonstrating complete Strategist agent workflow."""
    from src.agents.base import AgentStatus
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    # Verify initial state
    assert agent.is_idle
    assert agent.total_tokens_used == 0

    # Define a comprehensive task
    task = {
        "goal": {
            "title": "Close enterprise deal with BioTech Corp",
            "type": "close",
            "target_company": "BioTech Corp",
            "target_value": 500000,
        },
        "resources": {
            "available_agents": ["Hunter", "Analyst", "Scribe", "Operator"],
            "budget": 10000,
            "time_horizon_days": 90,
        },
        "constraints": {
            "deadline": "2026-05-01",
            "exclusions": ["Competitor Inc"],
            "compliance_notes": ["SOC2 required"],
        },
        "context": {
            "competitive_landscape": {
                "competitors": ["Competitor A", "Competitor B"],
                "our_strengths": ["Technical depth", "Customer support"],
                "our_weaknesses": ["Brand awareness"],
            },
            "stakeholder_map": {
                "decision_makers": [
                    {"name": "CEO John", "role": "CEO"},
                    {"name": "CFO Sarah", "role": "CFO"},
                ],
                "influencers": [
                    {"name": "VP Tech Mike", "role": "VP Engineering"},
                ],
                "blockers": [],
            },
        },
    }

    # Run the agent
    result = await agent.run(task)

    # Verify execution result
    assert result.success is True
    assert result.execution_time_ms >= 0

    data = result.data

    # Verify analysis
    assert "analysis" in data
    assert "competitive_analysis" in data["analysis"]
    assert "stakeholder_analysis" in data["analysis"]
    assert len(data["analysis"]["opportunities"]) > 0

    # Verify strategy
    assert "strategy" in data
    strategy = data["strategy"]
    assert len(strategy["phases"]) >= 3  # Close type has 4 phases
    assert len(strategy["agent_tasks"]) > 0
    assert len(strategy["risks"]) > 0
    assert len(strategy["success_criteria"]) > 0

    # Verify all tasks use available agents
    for task_item in strategy["agent_tasks"]:
        assert task_item["agent"] in task["resources"]["available_agents"]

    # Verify timeline
    assert "timeline" in data
    timeline = data["timeline"]
    assert timeline["deadline"] == "2026-05-01"
    assert len(timeline["milestones"]) > 0
    assert len(timeline["schedule"]) > 0

    # Verify all milestone dates respect deadline
    for milestone in timeline["milestones"]:
        assert milestone["target_date"] <= "2026-05-01"

    # Verify summary stats
    assert "summary_stats" in data
    assert data["summary_stats"]["phase_count"] == len(strategy["phases"])

    # Verify agent state
    assert agent.is_complete

    # Verify metadata
    assert "goal_id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_strategist_agent_handles_validation_failure() -> None:
    """Test Strategist agent handles invalid input gracefully."""
    from src.agents.base import AgentStatus
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    # Invalid task - missing goal
    invalid_task = {
        "resources": {
            "available_agents": ["Hunter"],
            "time_horizon_days": 30,
        },
    }

    result = await agent.run(invalid_task)

    # Should fail validation
    assert result.success is False
    assert "validation" in (result.error or "").lower()
    assert agent.is_failed


@pytest.mark.asyncio
async def test_strategist_minimal_task() -> None:
    """Test Strategist handles minimal valid task."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    # Minimal valid task
    task = {
        "goal": {
            "title": "Simple research",
            "type": "research",
        },
        "resources": {
            "available_agents": [],
            "time_horizon_days": 7,
        },
    }

    result = await agent.run(task)

    # Should still succeed
    assert result.success is True
    assert "strategy" in result.data
    assert "timeline" in result.data
```

**Step 2: Run integration tests**

Run: `cd backend && pytest tests/test_strategist_agent.py::test_full_strategist_workflow tests/test_strategist_agent.py::test_strategist_agent_handles_validation_failure tests/test_strategist_agent.py::test_strategist_minimal_task -v`

Expected: PASS

**Step 3: Run full test suite**

Run: `cd backend && pytest tests/test_strategist_agent.py -v`

Expected: PASS (36 tests)

**Step 4: Commit**

```bash
git add backend/tests/test_strategist_agent.py
git commit -m "test(agents): add integration tests for Strategist agent workflow"
```

---

### Task 9: Update Module Exports

**Files:**
- Modify: `backend/src/agents/__init__.py`

**Step 1: Write failing test for export**

Add to `backend/tests/test_strategist_agent.py`:

```python
def test_strategist_agent_exported_from_module() -> None:
    """Test StrategistAgent is exported from agents module."""
    from src.agents import StrategistAgent

    assert StrategistAgent.name == "Strategist"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_strategist_agent.py::test_strategist_agent_exported_from_module -v`

Expected: FAIL with "ImportError: cannot import name 'StrategistAgent'"

**Step 3: Update exports**

Update `backend/src/agents/__init__.py`:

```python
"""ARIA specialized agents module.

This module provides the base agent class and all specialized agents
for ARIA's task execution system.
"""

from src.agents.analyst import AnalystAgent
from src.agents.base import AgentResult, AgentStatus, BaseAgent
from src.agents.hunter import HunterAgent
from src.agents.strategist import StrategistAgent

__all__ = [
    "AgentResult",
    "AgentStatus",
    "AnalystAgent",
    "BaseAgent",
    "HunterAgent",
    "StrategistAgent",
]
```

**Step 4: Verify exports work**

Run: `cd backend && python -c "from src.agents import StrategistAgent; print(StrategistAgent.name)"`

Expected output: "Strategist"

**Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/test_strategist_agent.py -v`

Expected: PASS (37 tests)

**Step 6: Commit**

```bash
git add backend/src/agents/__init__.py backend/tests/test_strategist_agent.py
git commit -m "feat(agents): export StrategistAgent from agents module"
```

---

### Task 10: Run Quality Gates and Fix Issues

**Files:**
- Verify: All quality gates pass

**Step 1: Run type checking**

Run: `cd backend && mypy src/agents/strategist.py --strict`

If mypy reports issues, fix them. Common fixes:
- Add `from __future__ import annotations` if needed
- Fix any missing type annotations
- Ensure return types are explicit

**Step 2: Run linting**

Run: `cd backend && ruff check src/agents/strategist.py`

If ruff reports issues:
- Fix import ordering
- Fix line length issues
- Fix any linting violations

**Step 3: Run formatting**

Run: `cd backend && ruff format src/agents/strategist.py`

**Step 4: Run all Strategist tests**

Run: `cd backend && pytest tests/test_strategist_agent.py -v`

Expected: PASS (37 tests)

**Step 5: Run full backend test suite**

Run: `cd backend && pytest tests/ -v --tb=short`

Expected: All tests pass

**Step 6: Fix any issues and commit**

If any issues were found and fixed:

```bash
git add backend/src/agents/strategist.py backend/tests/test_strategist_agent.py
git commit -m "style(agents): fix quality gate issues in Strategist agent"
```

---

## Summary

This plan implements US-305: Strategist Agent with the following components:

1. **StrategistAgent class** - Extends BaseAgent with strategic planning capabilities
2. **Input validation** - Ensures task has goal (title, type) and resources (time_horizon_days)
3. **Three core tools**:
   - `analyze_account`: Evaluate competitive landscape, stakeholder map, opportunities/challenges
   - `generate_strategy`: Create phases, agent tasks, risks, and success criteria
   - `create_timeline`: Schedule milestones and tasks with actual dates
4. **Full orchestration** via `execute()` - Runs complete strategy workflow
5. **Comprehensive tests** - 37 tests covering all functionality
6. **Quality gates** - mypy strict, ruff linting, and formatting

The agent creates actionable strategies with:
- **Phases**: Discovery, Proposal, Negotiation, Closing (varies by goal type)
- **Agent Tasks**: Mapped to available agents with priorities
- **Milestones**: Scheduled with target dates respecting deadlines
- **Risks**: Derived from challenges and constraints
- **Success Criteria**: Goal-type specific measurable outcomes

All code follows the project's patterns:
- Async-first with proper type hints
- Logging instead of print
- Comprehensive docstrings
- TDD approach with tests before implementation
- YAGNI - only what's needed for the US
- DRY - template-based phase/task generation
