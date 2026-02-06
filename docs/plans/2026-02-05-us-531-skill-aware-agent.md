# US-531: Skill-Aware Agent Integration Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a `SkillAwareAgent` base class that integrates the skills system with all 6 ARIA agents, enabling agents to discover and execute skills as part of their OODA ACT phase.

**Architecture:** `SkillAwareAgent` extends `BaseAgent` with skill orchestration, skill analysis, and an `execute_with_skills()` method. Each agent declares which skills it can use via an `AGENT_SKILLS` mapping. LLM-based analysis determines whether skills should be invoked for a given task. All 6 agents are updated to extend `SkillAwareAgent` instead of `BaseAgent`.

**Tech Stack:** Python 3.11+ / Dataclasses / AsyncIO / LLMClient / SkillOrchestrator / SkillIndex

---

### Task 1: SkillAnalysis Dataclass and AGENT_SKILLS Mapping

**Files:**
- Create: `backend/src/agents/skill_aware_agent.py`
- Test: `backend/tests/test_skill_aware_agent.py`

**Step 1: Write the failing tests**

```python
# backend/tests/test_skill_aware_agent.py
"""Tests for SkillAwareAgent module."""

from src.agents.skill_aware_agent import AGENT_SKILLS, SkillAnalysis


def test_skill_analysis_dataclass_exists() -> None:
    """Test SkillAnalysis dataclass has required fields."""
    analysis = SkillAnalysis(
        skills_needed=True,
        recommended_skills=["pdf", "docx"],
        reasoning="Document generation needed",
    )

    assert analysis.skills_needed is True
    assert analysis.recommended_skills == ["pdf", "docx"]
    assert analysis.reasoning == "Document generation needed"


def test_skill_analysis_defaults() -> None:
    """Test SkillAnalysis works with minimal fields."""
    analysis = SkillAnalysis(
        skills_needed=False,
        recommended_skills=[],
        reasoning="No skills needed for this task",
    )

    assert analysis.skills_needed is False
    assert analysis.recommended_skills == []


def test_agent_skills_mapping_has_all_agents() -> None:
    """Test AGENT_SKILLS contains all 6 agents."""
    expected_agents = {"hunter", "analyst", "strategist", "scribe", "operator", "scout"}
    assert set(AGENT_SKILLS.keys()) == expected_agents


def test_agent_skills_hunter() -> None:
    """Test hunter agent has correct skills."""
    assert AGENT_SKILLS["hunter"] == [
        "competitor-analysis",
        "lead-research",
        "company-profiling",
    ]


def test_agent_skills_analyst() -> None:
    """Test analyst agent has correct skills."""
    assert AGENT_SKILLS["analyst"] == [
        "clinical-trial-analysis",
        "pubmed-research",
        "data-visualization",
    ]


def test_agent_skills_strategist() -> None:
    """Test strategist agent has correct skills."""
    assert AGENT_SKILLS["strategist"] == [
        "market-analysis",
        "competitive-positioning",
        "pricing-strategy",
    ]


def test_agent_skills_scribe() -> None:
    """Test scribe agent has correct skills."""
    assert AGENT_SKILLS["scribe"] == [
        "pdf",
        "docx",
        "pptx",
        "xlsx",
        "email-sequence",
    ]


def test_agent_skills_operator() -> None:
    """Test operator agent has correct skills."""
    assert AGENT_SKILLS["operator"] == [
        "calendar-management",
        "crm-operations",
        "workflow-automation",
    ]


def test_agent_skills_scout() -> None:
    """Test scout agent has correct skills."""
    assert AGENT_SKILLS["scout"] == [
        "regulatory-monitor",
        "news-aggregation",
        "signal-detection",
    ]


def test_agent_skills_values_are_lists() -> None:
    """Test all AGENT_SKILLS values are lists of strings."""
    for agent_id, skills in AGENT_SKILLS.items():
        assert isinstance(skills, list), f"{agent_id} skills is not a list"
        for skill in skills:
            assert isinstance(skill, str), f"{agent_id} has non-string skill: {skill}"
        assert len(skills) >= 3, f"{agent_id} has fewer than 3 skills"
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_aware_agent.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.agents.skill_aware_agent'`

**Step 3: Write minimal implementation**

```python
# backend/src/agents/skill_aware_agent.py
"""Skill-aware agent base class for ARIA.

Extends BaseAgent with skills.sh integration, enabling agents to
discover and execute skills as part of their OODA ACT phase.
"""

from dataclasses import dataclass


@dataclass
class SkillAnalysis:
    """Result of analyzing whether skills are needed for a task.

    Attributes:
        skills_needed: Whether any skills should be invoked.
        recommended_skills: List of skill paths to use.
        reasoning: LLM explanation of the decision.
    """

    skills_needed: bool
    recommended_skills: list[str]
    reasoning: str


# Maps agent_id to the skill paths that agent is authorized to use.
AGENT_SKILLS: dict[str, list[str]] = {
    "hunter": [
        "competitor-analysis",
        "lead-research",
        "company-profiling",
    ],
    "analyst": [
        "clinical-trial-analysis",
        "pubmed-research",
        "data-visualization",
    ],
    "strategist": [
        "market-analysis",
        "competitive-positioning",
        "pricing-strategy",
    ],
    "scribe": [
        "pdf",
        "docx",
        "pptx",
        "xlsx",
        "email-sequence",
    ],
    "operator": [
        "calendar-management",
        "crm-operations",
        "workflow-automation",
    ],
    "scout": [
        "regulatory-monitor",
        "news-aggregation",
        "signal-detection",
    ],
}
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_aware_agent.py -v`
Expected: All 10 tests PASS

**Step 5: Commit**

```bash
git add backend/src/agents/skill_aware_agent.py backend/tests/test_skill_aware_agent.py
git commit -m "feat(agents): add SkillAnalysis dataclass and AGENT_SKILLS mapping

Part of US-531: Integrate skills with ARIA agents."
```

---

### Task 2: SkillAwareAgent Class - Init and _get_available_skills

**Files:**
- Modify: `backend/src/agents/skill_aware_agent.py`
- Test: `backend/tests/test_skill_aware_agent.py`

**Step 1: Write the failing tests**

Append to `backend/tests/test_skill_aware_agent.py`:

```python
from unittest.mock import MagicMock

from src.agents.skill_aware_agent import AGENT_SKILLS, SkillAwareAgent, SkillAnalysis


def test_skill_aware_agent_extends_base_agent() -> None:
    """Test SkillAwareAgent is a subclass of BaseAgent."""
    from src.agents.base import BaseAgent

    assert issubclass(SkillAwareAgent, BaseAgent)


def test_skill_aware_agent_init_stores_agent_id() -> None:
    """Test SkillAwareAgent stores agent_id."""
    mock_llm = MagicMock()
    mock_orchestrator = MagicMock()
    mock_index = MagicMock()

    class TestAgent(SkillAwareAgent):
        name = "Test"
        description = "Test agent"
        agent_id = "hunter"

        def _register_tools(self):
            return {}

        async def execute(self, task):
            pass

    agent = TestAgent(
        llm_client=mock_llm,
        user_id="user-123",
        skill_orchestrator=mock_orchestrator,
        skill_index=mock_index,
    )

    assert agent.agent_id == "hunter"
    assert agent.skill_orchestrator is mock_orchestrator
    assert agent.skill_index is mock_index


def test_skill_aware_agent_init_without_skills() -> None:
    """Test SkillAwareAgent works when created without skill dependencies."""
    mock_llm = MagicMock()

    class TestAgent(SkillAwareAgent):
        name = "Test"
        description = "Test agent"
        agent_id = "hunter"

        def _register_tools(self):
            return {}

        async def execute(self, task):
            pass

    agent = TestAgent(llm_client=mock_llm, user_id="user-123")

    assert agent.skill_orchestrator is None
    assert agent.skill_index is None


def test_get_available_skills_returns_agent_skills() -> None:
    """Test _get_available_skills returns skills for the agent's ID."""
    mock_llm = MagicMock()

    class TestAgent(SkillAwareAgent):
        name = "Test"
        description = "Test agent"
        agent_id = "scribe"

        def _register_tools(self):
            return {}

        async def execute(self, task):
            pass

    agent = TestAgent(llm_client=mock_llm, user_id="user-123")
    skills = agent._get_available_skills()

    assert skills == AGENT_SKILLS["scribe"]


def test_get_available_skills_unknown_agent_returns_empty() -> None:
    """Test _get_available_skills returns empty list for unknown agent_id."""
    mock_llm = MagicMock()

    class TestAgent(SkillAwareAgent):
        name = "Test"
        description = "Test agent"
        agent_id = "unknown_agent"

        def _register_tools(self):
            return {}

        async def execute(self, task):
            pass

    agent = TestAgent(llm_client=mock_llm, user_id="user-123")
    skills = agent._get_available_skills()

    assert skills == []
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_aware_agent.py::test_skill_aware_agent_extends_base_agent -v`
Expected: FAIL with `ImportError: cannot import name 'SkillAwareAgent'`

**Step 3: Write implementation**

Update `backend/src/agents/skill_aware_agent.py` — add these imports and the class after `AGENT_SKILLS`:

```python
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.agents.base import BaseAgent

if TYPE_CHECKING:
    from src.core.llm import LLMClient
    from src.skills.index import SkillIndex
    from src.skills.orchestrator import SkillOrchestrator

logger = logging.getLogger(__name__)


# ... (SkillAnalysis and AGENT_SKILLS stay the same) ...


class SkillAwareAgent(BaseAgent):
    """Base class for agents that can discover and execute skills.

    Extends BaseAgent with:
    - A SkillOrchestrator for multi-skill execution
    - A SkillIndex for skill discovery
    - An agent_id that maps to AGENT_SKILLS for skill authorization
    - LLM-based skill need analysis
    - execute_with_skills() for skill-augmented task execution

    Subclasses must set the `agent_id` class attribute to one of the
    keys in AGENT_SKILLS.
    """

    agent_id: str

    def __init__(
        self,
        llm_client: "LLMClient",
        user_id: str,
        skill_orchestrator: "SkillOrchestrator | None" = None,
        skill_index: "SkillIndex | None" = None,
    ) -> None:
        """Initialize the skill-aware agent.

        Args:
            llm_client: LLM client for reasoning and generation.
            user_id: ID of the user this agent is working for.
            skill_orchestrator: Optional orchestrator for multi-skill execution.
            skill_index: Optional index for skill discovery.
        """
        self.skill_orchestrator = skill_orchestrator
        self.skill_index = skill_index
        super().__init__(llm_client=llm_client, user_id=user_id)

    def _get_available_skills(self) -> list[str]:
        """Get the list of skills this agent is authorized to use.

        Returns:
            List of skill path strings from AGENT_SKILLS, or empty list
            if the agent_id is not in the mapping.
        """
        return AGENT_SKILLS.get(self.agent_id, [])
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_aware_agent.py -v`
Expected: All 15 tests PASS

**Step 5: Commit**

```bash
git add backend/src/agents/skill_aware_agent.py backend/tests/test_skill_aware_agent.py
git commit -m "feat(agents): add SkillAwareAgent class with init and _get_available_skills

Part of US-531: Integrate skills with ARIA agents."
```

---

### Task 3: _analyze_skill_needs Method

**Files:**
- Modify: `backend/src/agents/skill_aware_agent.py`
- Test: `backend/tests/test_skill_aware_agent.py`

**Step 1: Write the failing tests**

Append to `backend/tests/test_skill_aware_agent.py`:

```python
import json

import pytest


@pytest.mark.asyncio
async def test_analyze_skill_needs_returns_skill_analysis() -> None:
    """Test _analyze_skill_needs returns a SkillAnalysis dataclass."""
    mock_llm = MagicMock()
    # Mock LLM to return JSON indicating skills are needed
    mock_llm.generate_response = MagicMock(
        return_value=json.dumps({
            "skills_needed": True,
            "recommended_skills": ["pdf"],
            "reasoning": "Task requires PDF generation",
        })
    )

    class TestAgent(SkillAwareAgent):
        name = "Test"
        description = "Test agent"
        agent_id = "scribe"

        def _register_tools(self):
            return {}

        async def execute(self, task):
            pass

    agent = TestAgent(llm_client=mock_llm, user_id="user-123")
    result = await agent._analyze_skill_needs({"goal": "generate a PDF report"})

    assert isinstance(result, SkillAnalysis)
    assert result.skills_needed is True
    assert "pdf" in result.recommended_skills
    assert len(result.reasoning) > 0


@pytest.mark.asyncio
async def test_analyze_skill_needs_no_skills_needed() -> None:
    """Test _analyze_skill_needs when LLM says no skills needed."""
    mock_llm = MagicMock()
    mock_llm.generate_response = MagicMock(
        return_value=json.dumps({
            "skills_needed": False,
            "recommended_skills": [],
            "reasoning": "Task can be handled by agent tools alone",
        })
    )

    class TestAgent(SkillAwareAgent):
        name = "Test"
        description = "Test agent"
        agent_id = "hunter"

        def _register_tools(self):
            return {}

        async def execute(self, task):
            pass

    agent = TestAgent(llm_client=mock_llm, user_id="user-123")
    result = await agent._analyze_skill_needs({"goal": "find leads"})

    assert result.skills_needed is False
    assert result.recommended_skills == []


@pytest.mark.asyncio
async def test_analyze_skill_needs_filters_to_available_skills() -> None:
    """Test _analyze_skill_needs only recommends skills the agent has access to."""
    mock_llm = MagicMock()
    # LLM recommends a skill the agent doesn't have
    mock_llm.generate_response = MagicMock(
        return_value=json.dumps({
            "skills_needed": True,
            "recommended_skills": ["pdf", "competitor-analysis"],
            "reasoning": "Multiple skills useful",
        })
    )

    class TestAgent(SkillAwareAgent):
        name = "Test"
        description = "Test agent"
        agent_id = "scribe"  # scribe doesn't have competitor-analysis

        def _register_tools(self):
            return {}

        async def execute(self, task):
            pass

    agent = TestAgent(llm_client=mock_llm, user_id="user-123")
    result = await agent._analyze_skill_needs({"goal": "create report"})

    # competitor-analysis should be filtered out since scribe doesn't have it
    assert "competitor-analysis" not in result.recommended_skills
    assert "pdf" in result.recommended_skills


@pytest.mark.asyncio
async def test_analyze_skill_needs_handles_llm_error() -> None:
    """Test _analyze_skill_needs returns no-skills-needed on LLM failure."""
    mock_llm = MagicMock()
    mock_llm.generate_response = MagicMock(side_effect=Exception("API error"))

    class TestAgent(SkillAwareAgent):
        name = "Test"
        description = "Test agent"
        agent_id = "hunter"

        def _register_tools(self):
            return {}

        async def execute(self, task):
            pass

    agent = TestAgent(llm_client=mock_llm, user_id="user-123")
    result = await agent._analyze_skill_needs({"goal": "find leads"})

    assert result.skills_needed is False
    assert result.recommended_skills == []
    assert "error" in result.reasoning.lower() or "failed" in result.reasoning.lower()


@pytest.mark.asyncio
async def test_analyze_skill_needs_handles_malformed_json() -> None:
    """Test _analyze_skill_needs handles malformed LLM response."""
    mock_llm = MagicMock()
    mock_llm.generate_response = MagicMock(return_value="not valid json at all")

    class TestAgent(SkillAwareAgent):
        name = "Test"
        description = "Test agent"
        agent_id = "hunter"

        def _register_tools(self):
            return {}

        async def execute(self, task):
            pass

    agent = TestAgent(llm_client=mock_llm, user_id="user-123")
    result = await agent._analyze_skill_needs({"goal": "find leads"})

    assert result.skills_needed is False
    assert result.recommended_skills == []
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_aware_agent.py::test_analyze_skill_needs_returns_skill_analysis -v`
Expected: FAIL with `AttributeError: 'TestAgent' object has no attribute '_analyze_skill_needs'`

**Step 3: Write implementation**

Add this method to `SkillAwareAgent` in `backend/src/agents/skill_aware_agent.py`:

```python
    async def _analyze_skill_needs(self, task: dict[str, Any]) -> SkillAnalysis:
        """Use LLM to determine if skills would help with a task.

        Sends the task description and available skills to the LLM,
        which returns a JSON response indicating whether skills are needed.

        Args:
            task: Task specification to analyze.

        Returns:
            SkillAnalysis with skills_needed, recommended_skills, reasoning.
            On error, returns SkillAnalysis with skills_needed=False.
        """
        available_skills = self._get_available_skills()

        if not available_skills:
            return SkillAnalysis(
                skills_needed=False,
                recommended_skills=[],
                reasoning="No skills available for this agent",
            )

        prompt = (
            "You are analyzing whether external skills should be used for a task.\n\n"
            f"Agent: {self.name} ({self.description})\n"
            f"Available skills: {', '.join(available_skills)}\n\n"
            f"Task: {json.dumps(task, default=str)}\n\n"
            "Respond with JSON only:\n"
            '{"skills_needed": bool, "recommended_skills": ["skill-name", ...], '
            '"reasoning": "explanation"}\n\n'
            "Only recommend skills from the available list. "
            "Set skills_needed to false if the agent's built-in tools suffice."
        )

        try:
            response = await self.llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=256,
                temperature=0.0,
            )

            parsed = json.loads(response)

            # Filter recommended skills to only those available
            recommended = [
                s for s in parsed.get("recommended_skills", [])
                if s in available_skills
            ]

            # If filtering removed all skills, mark as not needed
            skills_needed = parsed.get("skills_needed", False) and len(recommended) > 0

            return SkillAnalysis(
                skills_needed=skills_needed,
                recommended_skills=recommended,
                reasoning=parsed.get("reasoning", ""),
            )

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Failed to parse skill analysis response: {e}")
            return SkillAnalysis(
                skills_needed=False,
                recommended_skills=[],
                reasoning=f"Failed to parse LLM response: {e}",
            )
        except Exception as e:
            logger.error(f"Skill analysis failed: {e}")
            return SkillAnalysis(
                skills_needed=False,
                recommended_skills=[],
                reasoning=f"Skill analysis error: {e}",
            )
```

Also add `import json` to the top of the file.

**Step 4: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_aware_agent.py -v`
Expected: All 20 tests PASS

**Step 5: Commit**

```bash
git add backend/src/agents/skill_aware_agent.py backend/tests/test_skill_aware_agent.py
git commit -m "feat(agents): add _analyze_skill_needs LLM-based skill analysis

Part of US-531: Integrate skills with ARIA agents."
```

---

### Task 4: execute_with_skills Method

**Files:**
- Modify: `backend/src/agents/skill_aware_agent.py`
- Test: `backend/tests/test_skill_aware_agent.py`

**Step 1: Write the failing tests**

Append to `backend/tests/test_skill_aware_agent.py`:

```python
from unittest.mock import AsyncMock

from src.agents.base import AgentResult


@pytest.mark.asyncio
async def test_execute_with_skills_delegates_to_orchestrator() -> None:
    """Test execute_with_skills uses orchestrator when skills are needed."""
    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(
        return_value=json.dumps({
            "skills_needed": True,
            "recommended_skills": ["pdf"],
            "reasoning": "PDF generation needed",
        })
    )

    mock_orchestrator = MagicMock()
    mock_plan = MagicMock()
    mock_orchestrator.create_execution_plan = AsyncMock(return_value=mock_plan)
    mock_orchestrator.execute_plan = AsyncMock(return_value=[
        MagicMock(
            step_number=1,
            skill_id="skill-1",
            status="completed",
            summary="Generated PDF",
            artifacts=["report.pdf"],
            extracted_facts={},
            next_step_hints=[],
        ),
    ])

    mock_index = MagicMock()
    mock_index.search = AsyncMock(return_value=[
        MagicMock(id="skill-1", skill_path="pdf", skill_name="PDF Generator"),
    ])

    class TestAgent(SkillAwareAgent):
        name = "Test"
        description = "Test agent"
        agent_id = "scribe"

        def _register_tools(self):
            return {}

        async def execute(self, task):
            return AgentResult(success=True, data={"native": True})

    agent = TestAgent(
        llm_client=mock_llm,
        user_id="user-123",
        skill_orchestrator=mock_orchestrator,
        skill_index=mock_index,
    )

    result = await agent.execute_with_skills({"goal": "generate PDF"})

    assert isinstance(result, AgentResult)
    assert result.success is True
    # Orchestrator should have been called
    mock_orchestrator.create_execution_plan.assert_called_once()
    mock_orchestrator.execute_plan.assert_called_once()


@pytest.mark.asyncio
async def test_execute_with_skills_falls_back_to_execute() -> None:
    """Test execute_with_skills falls back to execute() when no skills needed."""
    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(
        return_value=json.dumps({
            "skills_needed": False,
            "recommended_skills": [],
            "reasoning": "No skills needed",
        })
    )

    class TestAgent(SkillAwareAgent):
        name = "Test"
        description = "Test agent"
        agent_id = "hunter"

        def _register_tools(self):
            return {}

        async def execute(self, task):
            return AgentResult(success=True, data={"native": True})

    agent = TestAgent(llm_client=mock_llm, user_id="user-123")
    result = await agent.execute_with_skills({"goal": "find leads"})

    assert isinstance(result, AgentResult)
    assert result.success is True
    assert result.data == {"native": True}


@pytest.mark.asyncio
async def test_execute_with_skills_no_orchestrator_falls_back() -> None:
    """Test execute_with_skills falls back to execute() when no orchestrator."""
    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(
        return_value=json.dumps({
            "skills_needed": True,
            "recommended_skills": ["pdf"],
            "reasoning": "PDF needed",
        })
    )

    class TestAgent(SkillAwareAgent):
        name = "Test"
        description = "Test agent"
        agent_id = "scribe"

        def _register_tools(self):
            return {}

        async def execute(self, task):
            return AgentResult(success=True, data={"fallback": True})

    # No orchestrator provided
    agent = TestAgent(llm_client=mock_llm, user_id="user-123")
    result = await agent.execute_with_skills({"goal": "generate PDF"})

    assert result.success is True
    assert result.data == {"fallback": True}


@pytest.mark.asyncio
async def test_execute_with_skills_handles_orchestrator_error() -> None:
    """Test execute_with_skills returns error result on orchestrator failure."""
    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(
        return_value=json.dumps({
            "skills_needed": True,
            "recommended_skills": ["pdf"],
            "reasoning": "PDF needed",
        })
    )

    mock_orchestrator = MagicMock()
    mock_orchestrator.create_execution_plan = AsyncMock(
        side_effect=Exception("Orchestrator exploded")
    )

    mock_index = MagicMock()
    mock_index.search = AsyncMock(return_value=[
        MagicMock(id="skill-1", skill_path="pdf"),
    ])

    class TestAgent(SkillAwareAgent):
        name = "Test"
        description = "Test agent"
        agent_id = "scribe"

        def _register_tools(self):
            return {}

        async def execute(self, task):
            return AgentResult(success=True, data={"native": True})

    agent = TestAgent(
        llm_client=mock_llm,
        user_id="user-123",
        skill_orchestrator=mock_orchestrator,
        skill_index=mock_index,
    )

    result = await agent.execute_with_skills({"goal": "generate PDF"})

    assert result.success is False
    assert "Orchestrator exploded" in (result.error or "")
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_aware_agent.py::test_execute_with_skills_delegates_to_orchestrator -v`
Expected: FAIL with `AttributeError: 'TestAgent' object has no attribute 'execute_with_skills'`

**Step 3: Write implementation**

Add this method to `SkillAwareAgent` in `backend/src/agents/skill_aware_agent.py`:

```python
    async def execute_with_skills(self, task: dict[str, Any]) -> AgentResult:
        """Execute a task, using skills if beneficial.

        This is the OODA ACT phase integration point. Analyzes whether
        skills would help, and if so, delegates to the SkillOrchestrator.
        Falls back to the agent's native execute() if skills aren't needed
        or aren't available.

        Args:
            task: Task specification with parameters.

        Returns:
            AgentResult with execution outcome.
        """
        # Step 1: Analyze if skills would help
        analysis = await self._analyze_skill_needs(task)

        if not analysis.skills_needed:
            logger.info(
                f"Agent {self.name}: no skills needed, using native execution",
                extra={"agent_id": self.agent_id, "reasoning": analysis.reasoning},
            )
            return await self.execute(task)

        # Step 2: Check if orchestrator is available
        if self.skill_orchestrator is None or self.skill_index is None:
            logger.warning(
                f"Agent {self.name}: skills recommended but no orchestrator available, "
                "falling back to native execution",
                extra={
                    "agent_id": self.agent_id,
                    "recommended_skills": analysis.recommended_skills,
                },
            )
            return await self.execute(task)

        # Step 3: Find skill metadata from index
        try:
            available_skill_entries = await self.skill_index.search(
                query=" ".join(analysis.recommended_skills),
            )

            # Build task description for orchestrator
            task_description = json.dumps(task, default=str)

            # Step 4: Create execution plan
            plan = await self.skill_orchestrator.create_execution_plan(
                task=task_description,
                available_skills=available_skill_entries,
            )

            logger.info(
                f"Agent {self.name}: executing skill plan with {len(plan.steps)} steps",
                extra={
                    "agent_id": self.agent_id,
                    "plan_id": plan.plan_id,
                    "step_count": len(plan.steps),
                },
            )

            # Step 5: Execute the plan
            working_memory = await self.skill_orchestrator.execute_plan(
                user_id=self.user_id,
                plan=plan,
            )

            # Step 6: Build result from working memory
            skill_outputs = []
            all_succeeded = True
            for entry in working_memory:
                skill_outputs.append({
                    "step": entry.step_number,
                    "skill_id": entry.skill_id,
                    "status": entry.status,
                    "summary": entry.summary,
                    "artifacts": entry.artifacts,
                })
                if entry.status != "completed":
                    all_succeeded = False

            return AgentResult(
                success=all_succeeded,
                data={
                    "skill_execution": True,
                    "plan_id": plan.plan_id,
                    "steps": skill_outputs,
                },
                error=None if all_succeeded else "One or more skill steps failed",
            )

        except Exception as e:
            logger.error(
                f"Agent {self.name}: skill execution failed: {e}",
                extra={"agent_id": self.agent_id, "error": str(e)},
            )
            return AgentResult(
                success=False,
                data=None,
                error=f"Skill execution failed: {e}",
            )
```

Also add `from src.agents.base import AgentResult, BaseAgent` at the top (update existing import).

**Step 4: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_aware_agent.py -v`
Expected: All 24 tests PASS

**Step 5: Commit**

```bash
git add backend/src/agents/skill_aware_agent.py backend/tests/test_skill_aware_agent.py
git commit -m "feat(agents): add execute_with_skills OODA ACT phase integration

Part of US-531: Integrate skills with ARIA agents."
```

---

### Task 5: Update HunterAgent to Extend SkillAwareAgent

**Files:**
- Modify: `backend/src/agents/hunter.py`
- Test: `backend/tests/test_skill_aware_agent.py` (add integration test)

**Step 1: Write the failing test**

Append to `backend/tests/test_skill_aware_agent.py`:

```python
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
    """Test HunterAgent still works without skill parameters (backward compat)."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    assert agent.skill_orchestrator is None
    assert agent.skill_index is None
    assert agent._company_cache == {}
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_aware_agent.py::test_hunter_extends_skill_aware_agent -v`
Expected: FAIL with `AssertionError: assert False` (HunterAgent extends BaseAgent, not SkillAwareAgent)

**Step 3: Modify HunterAgent**

In `backend/src/agents/hunter.py`, make these changes:

1. Change the import from `from src.agents.base import AgentResult, BaseAgent` to `from src.agents.base import AgentResult` and add `from src.agents.skill_aware_agent import SkillAwareAgent`

2. Change `class HunterAgent(BaseAgent):` to `class HunterAgent(SkillAwareAgent):`

3. Add `agent_id = "hunter"` as a class attribute (after `description`)

4. Update `__init__` signature to accept optional skill params:

```python
    def __init__(
        self,
        llm_client: "LLMClient",
        user_id: str,
        skill_orchestrator: "SkillOrchestrator | None" = None,
        skill_index: "SkillIndex | None" = None,
    ) -> None:
        """Initialize the Hunter agent.

        Args:
            llm_client: LLM client for reasoning and generation.
            user_id: ID of the user this agent is working for.
            skill_orchestrator: Optional orchestrator for multi-skill execution.
            skill_index: Optional index for skill discovery.
        """
        self._company_cache: dict[str, Any] = {}
        super().__init__(
            llm_client=llm_client,
            user_id=user_id,
            skill_orchestrator=skill_orchestrator,
            skill_index=skill_index,
        )
```

5. Add the TYPE_CHECKING imports for `SkillOrchestrator` and `SkillIndex`:

```python
if TYPE_CHECKING:
    from src.core.llm import LLMClient
    from src.skills.index import SkillIndex
    from src.skills.orchestrator import SkillOrchestrator
```

**Step 4: Run ALL tests to verify nothing broke**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_aware_agent.py backend/tests/test_hunter_agent.py -v`
Expected: All tests PASS (existing hunter tests still pass + new tests pass)

**Step 5: Commit**

```bash
git add backend/src/agents/hunter.py backend/tests/test_skill_aware_agent.py
git commit -m "feat(agents): update HunterAgent to extend SkillAwareAgent

Part of US-531: Integrate skills with ARIA agents."
```

---

### Task 6: Update AnalystAgent to Extend SkillAwareAgent

**Files:**
- Modify: `backend/src/agents/analyst.py`
- Test: `backend/tests/test_skill_aware_agent.py`

**Step 1: Write the failing test**

Append to `backend/tests/test_skill_aware_agent.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_aware_agent.py::test_analyst_extends_skill_aware_agent -v`
Expected: FAIL

**Step 3: Modify AnalystAgent**

In `backend/src/agents/analyst.py`:

1. Add import: `from src.agents.skill_aware_agent import SkillAwareAgent`
2. Remove `BaseAgent` from the import of `src.agents.base` (keep any other imports from base if used)
3. Change `class AnalystAgent(BaseAgent):` → `class AnalystAgent(SkillAwareAgent):`
4. Add class attribute: `agent_id = "analyst"`
5. Update `__init__` to accept and pass through `skill_orchestrator` and `skill_index`:

```python
    def __init__(
        self,
        llm_client: Any,
        user_id: str,
        skill_orchestrator: Any = None,
        skill_index: Any = None,
    ) -> None:
        self._research_cache: dict[str, Any] = {}
        self._http_client: httpx.AsyncClient | None = None
        super().__init__(
            llm_client=llm_client,
            user_id=user_id,
            skill_orchestrator=skill_orchestrator,
            skill_index=skill_index,
        )
```

**Step 4: Run ALL analyst tests**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_aware_agent.py backend/tests/test_analyst_agent.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add backend/src/agents/analyst.py backend/tests/test_skill_aware_agent.py
git commit -m "feat(agents): update AnalystAgent to extend SkillAwareAgent

Part of US-531: Integrate skills with ARIA agents."
```

---

### Task 7: Update StrategistAgent to Extend SkillAwareAgent

**Files:**
- Modify: `backend/src/agents/strategist.py`
- Test: `backend/tests/test_skill_aware_agent.py`

**Step 1: Write the failing test**

Append to `backend/tests/test_skill_aware_agent.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_aware_agent.py::test_strategist_extends_skill_aware_agent -v`
Expected: FAIL

**Step 3: Modify StrategistAgent**

In `backend/src/agents/strategist.py`:

1. Add import: `from src.agents.skill_aware_agent import SkillAwareAgent`
2. Change `from src.agents.base import AgentResult, BaseAgent` → `from src.agents.base import AgentResult`
3. Change `class StrategistAgent(BaseAgent):` → `class StrategistAgent(SkillAwareAgent):`
4. Add class attribute: `agent_id = "strategist"`
5. Update `__init__`:

```python
    def __init__(
        self,
        llm_client: "LLMClient",
        user_id: str,
        skill_orchestrator: "SkillOrchestrator | None" = None,
        skill_index: "SkillIndex | None" = None,
    ) -> None:
        super().__init__(
            llm_client=llm_client,
            user_id=user_id,
            skill_orchestrator=skill_orchestrator,
            skill_index=skill_index,
        )
```

6. Add TYPE_CHECKING imports for `SkillOrchestrator` and `SkillIndex`:

```python
if TYPE_CHECKING:
    from src.core.llm import LLMClient
    from src.skills.index import SkillIndex
    from src.skills.orchestrator import SkillOrchestrator
```

**Step 4: Run ALL strategist tests**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_aware_agent.py backend/tests/test_strategist_agent.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add backend/src/agents/strategist.py backend/tests/test_skill_aware_agent.py
git commit -m "feat(agents): update StrategistAgent to extend SkillAwareAgent

Part of US-531: Integrate skills with ARIA agents."
```

---

### Task 8: Update ScribeAgent to Extend SkillAwareAgent

**Files:**
- Modify: `backend/src/agents/scribe.py`
- Test: `backend/tests/test_skill_aware_agent.py`

**Step 1: Write the failing test**

Append to `backend/tests/test_skill_aware_agent.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_aware_agent.py::test_scribe_extends_skill_aware_agent -v`
Expected: FAIL

**Step 3: Modify ScribeAgent**

In `backend/src/agents/scribe.py`:

1. Add import: `from src.agents.skill_aware_agent import SkillAwareAgent`
2. Change `from src.agents.base import AgentResult, BaseAgent` → `from src.agents.base import AgentResult`
3. Change `class ScribeAgent(BaseAgent):` → `class ScribeAgent(SkillAwareAgent):`
4. Add class attribute: `agent_id = "scribe"`
5. Update `__init__`:

```python
    def __init__(
        self,
        llm_client: "LLMClient",
        user_id: str,
        skill_orchestrator: "SkillOrchestrator | None" = None,
        skill_index: "SkillIndex | None" = None,
    ) -> None:
        self._templates: dict[str, str] = self._get_builtin_templates()
        super().__init__(
            llm_client=llm_client,
            user_id=user_id,
            skill_orchestrator=skill_orchestrator,
            skill_index=skill_index,
        )
```

6. Add TYPE_CHECKING imports for `SkillOrchestrator` and `SkillIndex`.

**Step 4: Run ALL scribe tests**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_aware_agent.py backend/tests/test_scribe_agent.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add backend/src/agents/scribe.py backend/tests/test_skill_aware_agent.py
git commit -m "feat(agents): update ScribeAgent to extend SkillAwareAgent

Part of US-531: Integrate skills with ARIA agents."
```

---

### Task 9: Update OperatorAgent to Extend SkillAwareAgent

**Files:**
- Modify: `backend/src/agents/operator.py`
- Test: `backend/tests/test_skill_aware_agent.py`

**Step 1: Write the failing test**

Append to `backend/tests/test_skill_aware_agent.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_aware_agent.py::test_operator_extends_skill_aware_agent -v`
Expected: FAIL

**Step 3: Modify OperatorAgent**

In `backend/src/agents/operator.py`:

1. Add import: `from src.agents.skill_aware_agent import SkillAwareAgent`
2. Change `from src.agents.base import AgentResult, BaseAgent` → `from src.agents.base import AgentResult`
3. Change `class OperatorAgent(BaseAgent):` → `class OperatorAgent(SkillAwareAgent):`
4. Add class attribute: `agent_id = "operator"`
5. Update `__init__`:

```python
    def __init__(
        self,
        llm_client: "LLMClient",
        user_id: str,
        skill_orchestrator: "SkillOrchestrator | None" = None,
        skill_index: "SkillIndex | None" = None,
    ) -> None:
        self._integration_cache: dict[str, Any] = {}
        super().__init__(
            llm_client=llm_client,
            user_id=user_id,
            skill_orchestrator=skill_orchestrator,
            skill_index=skill_index,
        )
```

6. Add TYPE_CHECKING imports for `SkillOrchestrator` and `SkillIndex`.

**Step 4: Run ALL operator tests**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_aware_agent.py backend/tests/test_operator_agent.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add backend/src/agents/operator.py backend/tests/test_skill_aware_agent.py
git commit -m "feat(agents): update OperatorAgent to extend SkillAwareAgent

Part of US-531: Integrate skills with ARIA agents."
```

---

### Task 10: Update ScoutAgent to Extend SkillAwareAgent

**Files:**
- Modify: `backend/src/agents/scout.py`
- Test: `backend/tests/test_skill_aware_agent.py`

**Step 1: Write the failing test**

Append to `backend/tests/test_skill_aware_agent.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_aware_agent.py::test_scout_extends_skill_aware_agent -v`
Expected: FAIL

**Step 3: Modify ScoutAgent**

In `backend/src/agents/scout.py`:

1. Add import: `from src.agents.skill_aware_agent import SkillAwareAgent`
2. Change `from src.agents.base import AgentResult, BaseAgent` → `from src.agents.base import AgentResult`
3. Change `class ScoutAgent(BaseAgent):` → `class ScoutAgent(SkillAwareAgent):`
4. Add class attribute: `agent_id = "scout"`
5. Update `__init__`:

```python
    def __init__(
        self,
        llm_client: "LLMClient",
        user_id: str,
        skill_orchestrator: "SkillOrchestrator | None" = None,
        skill_index: "SkillIndex | None" = None,
    ) -> None:
        super().__init__(
            llm_client=llm_client,
            user_id=user_id,
            skill_orchestrator=skill_orchestrator,
            skill_index=skill_index,
        )
```

6. Add TYPE_CHECKING imports for `SkillOrchestrator` and `SkillIndex`.

**Step 4: Run ALL scout tests**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_aware_agent.py backend/tests/test_scout_agent.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add backend/src/agents/scout.py backend/tests/test_skill_aware_agent.py
git commit -m "feat(agents): update ScoutAgent to extend SkillAwareAgent

Part of US-531: Integrate skills with ARIA agents."
```

---

### Task 11: Update agents/__init__.py Exports

**Files:**
- Modify: `backend/src/agents/__init__.py`
- Test: `backend/tests/test_agents_module_exports.py`

**Step 1: Write the failing test**

Append to `backend/tests/test_agents_module_exports.py`:

```python
def test_skill_aware_agent_is_exported() -> None:
    """Test SkillAwareAgent is exported from agents module."""
    from src.agents import SkillAwareAgent

    assert SkillAwareAgent is not None


def test_skill_analysis_is_exported() -> None:
    """Test SkillAnalysis is exported from agents module."""
    from src.agents import SkillAnalysis

    assert SkillAnalysis is not None


def test_agent_skills_is_exported() -> None:
    """Test AGENT_SKILLS is exported from agents module."""
    from src.agents import AGENT_SKILLS

    assert AGENT_SKILLS is not None
    assert isinstance(AGENT_SKILLS, dict)


def test_all_includes_skill_aware_exports() -> None:
    """Test __all__ includes SkillAwareAgent, SkillAnalysis, AGENT_SKILLS."""
    from src.agents import __all__

    assert "SkillAwareAgent" in __all__
    assert "SkillAnalysis" in __all__
    assert "AGENT_SKILLS" in __all__
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_agents_module_exports.py::test_skill_aware_agent_is_exported -v`
Expected: FAIL with `ImportError: cannot import name 'SkillAwareAgent' from 'src.agents'`

**Step 3: Update exports**

In `backend/src/agents/__init__.py`, add the import and update `__all__`:

```python
"""ARIA specialized agents module.

This module provides the base agent class, all specialized agents,
the orchestrator for coordinating agent execution, and the
skill-aware agent base for skills.sh integration.
"""

from src.agents.analyst import AnalystAgent
from src.agents.base import AgentResult, AgentStatus, BaseAgent
from src.agents.hunter import HunterAgent
from src.agents.operator import OperatorAgent
from src.agents.orchestrator import (
    AgentOrchestrator,
    ExecutionMode,
    OrchestrationResult,
    ProgressUpdate,
)
from src.agents.scout import ScoutAgent
from src.agents.scribe import ScribeAgent
from src.agents.skill_aware_agent import AGENT_SKILLS, SkillAnalysis, SkillAwareAgent
from src.agents.strategist import StrategistAgent

__all__ = [
    "AGENT_SKILLS",
    "AgentOrchestrator",
    "AgentResult",
    "AgentStatus",
    "AnalystAgent",
    "BaseAgent",
    "ExecutionMode",
    "HunterAgent",
    "OperatorAgent",
    "OrchestrationResult",
    "ProgressUpdate",
    "ScoutAgent",
    "ScribeAgent",
    "SkillAnalysis",
    "SkillAwareAgent",
    "StrategistAgent",
]
```

**Step 4: Run ALL export tests and full agent test suite**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_agents_module_exports.py backend/tests/test_skill_aware_agent.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add backend/src/agents/__init__.py backend/tests/test_agents_module_exports.py
git commit -m "feat(agents): export SkillAwareAgent, SkillAnalysis, AGENT_SKILLS

Part of US-531: Integrate skills with ARIA agents."
```

---

### Task 12: Final Verification - Full Test Suite

**Step 1: Run the complete agent test suite**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_skill_aware_agent.py backend/tests/test_hunter_agent.py backend/tests/test_analyst_agent.py backend/tests/test_strategist_agent.py backend/tests/test_scribe_agent.py backend/tests/test_operator_agent.py backend/tests/test_scout_agent.py backend/tests/test_orchestrator.py backend/tests/test_agents_module_exports.py backend/tests/test_base_agent.py -v`
Expected: All tests PASS

**Step 2: Run type checking**

Run: `cd /Users/dhruv/aria && python -m mypy backend/src/agents/skill_aware_agent.py --strict --ignore-missing-imports`
Expected: No errors

**Step 3: Run linting**

Run: `cd /Users/dhruv/aria && python -m ruff check backend/src/agents/skill_aware_agent.py backend/src/agents/hunter.py backend/src/agents/analyst.py backend/src/agents/strategist.py backend/src/agents/scribe.py backend/src/agents/operator.py backend/src/agents/scout.py`
Expected: No errors

**Step 4: Fix any issues found, then commit**

If fixes are needed:
```bash
git add -A
git commit -m "fix(agents): address type/lint issues in skill-aware agent integration

Part of US-531: Integrate skills with ARIA agents."
```
