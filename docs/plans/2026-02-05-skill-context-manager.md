# Skill Context Manager Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create the skill context manager to control token budgets and build compact context for multi-skill orchestration.

**Architecture:** The context manager provides token budget enforcement and builds minimal context for orchestrator planning and individual skill execution. It estimates tokens, compacts content when needed, and manages verbosity levels for summaries.

**Tech Stack:** Python 3.11+, dataclasses, enum, pytest

---

## Task 1: Create the context manager module structure

**Files:**
- Create: `backend/src/skills/context_manager.py`

**Step 1: Write the module docstring and imports**

```python
"""Skill context manager for token budget control.

This module provides context building and token management for multi-skill orchestration:
- Token budget constants for orchestrator and subagent contexts
- Context allocation tracking
- Compact summary generation for handoffs
- Token estimation and compaction utilities

The context manager ensures ARIA stays within token limits while maintaining
effective skill coordination through minimal but sufficient context.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)
```

**Step 2: Run check to verify file creation**

Run: `ls -la backend/src/skills/context_manager.py`
Expected: File exists

**Step 3: Add context budget constants**

```python
# Context budget constants (in tokens)
# These budgets ensure ARIA stays within practical token limits
# while maintaining effective skill coordination.

ORCHESTRATOR_BUDGET = 2000  # Total budget for orchestrator context
SKILL_INDEX_BUDGET = 600     # Budget for skill index summaries
WORKING_MEMORY_BUDGET = 800  # Budget for working memory entries
SUBAGENT_BUDGET = 6000       # Budget for individual skill subagent contexts
```

**Step 4: Run mypy to verify constants**

Run: `cd backend && mypy src/skills/context_manager.py --strict`
Expected: No errors (constants are valid)

**Step 5: Commit**

```bash
git add backend/src/skills/context_manager.py
git commit -m "feat(skills): add context manager module structure with budget constants"
```

---

## Task 2: Create SummaryVerbosity enum

**Files:**
- Modify: `backend/src/skills/context_manager.py`

**Step 1: Write the failing test**

```python
def test_summary_verbosity_enum_has_three_levels() -> None:
    """Test SummaryVerbosity enum has MINIMAL, STANDARD, DETAILED."""
    from src.skills.context_manager import SummaryVerbosity

    assert SummaryVerbosity.MINIMAL.value == "minimal"
    assert SummaryVerbosity.STANDARD.value == "standard"
    assert SummaryVerbosity.DETAILED.value == "detailed"
    assert len(SummaryVerbosity) == 3


def test_summary_verbosity_minimal_has_token_target() -> None:
    """Test MINIMAL verbosity has 300 token target."""
    from src.skills.context_manager import SummaryVerbosity

    assert SummaryVerbosity.MINIMAL.token_target == 300


def test_summary_verbosity_standard_has_token_target() -> None:
    """Test STANDARD verbosity has 800 token target."""
    from src.skills.context_manager import SummaryVerbosity

    assert SummaryVerbosity.STANDARD.token_target == 800


def test_summary_verbosity_detailed_has_token_target() -> None:
    """Test DETAILED verbosity has 1500 token target."""
    from src.skills.context_manager import SummaryVerbosity

    assert SummaryVerbosity.DETAILED.token_target == 1500
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_context_manager.py::test_summary_verbosity_enum_has_three_levels -v`
Expected: FAIL with "SummaryVerbosity not defined"

**Step 3: Implement the SummaryVerbosity enum**

Add to `backend/src/skills/context_manager.py`:

```python
class SummaryVerbosity(Enum):
    """Verbosity level for context summaries.

    Each level has a target token count for generating summaries.
    The build_working_memory_entry method uses these targets.

    Attributes:
        token_target: Target token count for this verbosity level.
    """

    MINIMAL = "minimal"      # ~300 tokens - bare facts
    STANDARD = "standard"     # ~800 tokens - key details
    DETAILED = "detailed"     # ~1500 tokens - full context

    @property
    def token_target(self) -> int:
        """Get the target token count for this verbosity level."""
        targets = {
            SummaryVerbosity.MINIMAL: 300,
            SummaryVerbosity.STANDARD: 800,
            SummaryVerbosity.DETAILED: 1500,
        }
        return targets[self]
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_context_manager.py::test_summary_verbosity -v`
Expected: PASS all 4 tests

**Step 5: Run mypy for type checking**

Run: `cd backend && mypy src/skills/context_manager.py --strict`
Expected: PASS (no type errors)

**Step 6: Commit**

```bash
git add backend/src/skills/context_manager.py backend/tests/test_context_manager.py
git commit -m "feat(skills): add SummaryVerbosity enum with token targets"
```

---

## Task 3: Create ContextAllocation dataclass

**Files:**
- Modify: `backend/src/skills/context_manager.py`
- Test: `backend/tests/test_context_manager.py`

**Step 1: Write the failing test**

```python
def test_context_allocation_dataclass_initializes() -> None:
    """Test ContextAllocation initializes with all fields."""
    from src.skills.context_manager import ContextAllocation

    allocation = ContextAllocation(
        component="skill_index",
        allocated_tokens=600,
        used_tokens=450,
        content="# Skill summaries\n...",
    )

    assert allocation.component == "skill_index"
    assert allocation.allocated_tokens == 600
    assert allocation.used_tokens == 450
    assert allocation.content == "# Skill summaries\n..."


def test_context_allocation_has_remaining_tokens_property() -> None:
    """Test ContextAllocation.remaining_tokens returns correct value."""
    from src.skills.context_manager import ContextAllocation

    allocation = ContextAllocation(
        component="working_memory",
        allocated_tokens=800,
        used_tokens=350,
        content="Some content",
    )

    assert allocation.remaining_tokens == 450


def test_context_allocation_remaining_tokens_when_over() -> None:
    """Test remaining_tokens returns 0 when over budget."""
    from src.skills.context_manager import ContextAllocation

    allocation = ContextAllocation(
        component="over_budget",
        allocated_tokens=100,
        used_tokens=150,
        content="Too much content",
    )

    assert allocation.remaining_tokens == 0


def test_context_allocation_is_over_budget_property() -> None:
    """Test is_over_budget returns correct boolean."""
    from src.skills.context_manager import ContextAllocation

    under = ContextAllocation(
        component="under",
        allocated_tokens=100,
        used_tokens=50,
        content="OK",
    )

    over = ContextAllocation(
        component="over",
        allocated_tokens=100,
        used_tokens=150,
        content="Too much",
    )

    assert under.is_over_budget is False
    assert over.is_over_budget is True
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_context_manager.py::test_context_allocation -v`
Expected: FAIL with "ContextAllocation not defined"

**Step 3: Implement ContextAllocation dataclass**

Add to `backend/src/skills/context_manager.py`:

```python
@dataclass(frozen=True)
class ContextAllocation:
    """Tracks token allocation and usage for a context component.

    Used by SkillContextManager to track budget usage across components
    like skill_index, working_memory, execution_plan.

    Attributes:
        component: Name of the context component (e.g., "skill_index").
        allocated_tokens: Token budget allocated to this component.
        used_tokens: Actual tokens used by this component's content.
        content: The context string for this component.
    """

    component: str
    allocated_tokens: int
    used_tokens: int
    content: str

    @property
    def remaining_tokens(self) -> int:
        """Calculate remaining tokens in budget.

        Returns 0 if over budget (never negative).
        """
        remaining = self.allocated_tokens - self.used_tokens
        return max(0, remaining)

    @property
    def is_over_budget(self) -> bool:
        """Check if this component has exceeded its budget."""
        return self.used_tokens > self.allocated_tokens
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_context_manager.py::test_context_allocation -v`
Expected: PASS all 4 tests

**Step 5: Run mypy for type checking**

Run: `cd backend && mypy src/skills/context_manager.py --strict`
Expected: PASS (no type errors)

**Step 6: Commit**

```bash
git add backend/src/skills/context_manager.py backend/tests/test_context_manager.py
git commit -m "feat(skills): add ContextAllocation dataclass with budget tracking"
```

---

## Task 4: Create SkillContextManager class structure

**Files:**
- Modify: `backend/src/skills/context_manager.py`
- Test: `backend/tests/test_context_manager.py`

**Step 1: Write the failing test**

```python
def test_skill_context_manager_initializes() -> None:
    """Test SkillContextManager initializes with default budgets."""
    from src.skills.context_manager import SkillContextManager

    manager = SkillContextManager()

    assert manager.orchestrator_budget == 2000
    assert manager.skill_index_budget == 600
    assert manager.working_memory_budget == 800
    assert manager.subagent_budget == 6000


def test_skill_context_manager_accepts_custom_budgets() -> None:
    """Test SkillContextManager accepts custom budget values."""
    from src.skills.context_manager import SkillContextManager

    manager = SkillContextManager(
        orchestrator_budget=5000,
        skill_index_budget=1000,
        working_memory_budget=2000,
        subagent_budget=10000,
    )

    assert manager.orchestrator_budget == 5000
    assert manager.skill_index_budget == 1000
    assert manager.working_memory_budget == 2000
    assert manager.subagent_budget == 10000
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_context_manager.py::test_skill_context_manager_initializes -v`
Expected: FAIL with "SkillContextManager not defined"

**Step 3: Implement SkillContextManager class structure**

Add to `backend/src/skills/context_manager.py`:

```python
class SkillContextManager:
    """Manages context building and token budgets for skill orchestration.

    The context manager provides two key capabilities:
    1. Build compact orchestrator context (~2000 tokens) for planning
    2. Build isolated subagent context (~6000 tokens) per skill execution

    It also provides utilities for:
    - Estimating token counts from text
    - Compacting content to fit budgets
    - Building working memory entries with controlled verbosity
    """

    def __init__(
        self,
        *,
        orchestrator_budget: int = ORCHESTRATOR_BUDGET,
        skill_index_budget: int = SKILL_INDEX_BUDGET,
        working_memory_budget: int = WORKING_MEMORY_BUDGET,
        subagent_budget: int = SUBAGENT_BUDGET,
    ) -> None:
        """Initialize the context manager with budget limits.

        Args:
            orchestrator_budget: Total tokens for orchestrator planning context.
            skill_index_budget: Tokens for skill index summaries within orchestrator.
            working_memory_budget: Tokens for working memory entries within orchestrator.
            subagent_budget: Tokens for individual skill subagent contexts.
        """
        self.orchestrator_budget = orchestrator_budget
        self.skill_index_budget = skill_index_budget
        self.working_memory_budget = working_memory_budget
        self.subagent_budget = subagent_budget
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_context_manager.py::test_skill_context_manager_initializes -v`
Expected: PASS all 2 tests

**Step 5: Run mypy for type checking**

Run: `cd backend && mypy src/skills/context_manager.py --strict`
Expected: PASS (no type errors)

**Step 6: Commit**

```bash
git add backend/src/skills/context_manager.py backend/tests/test_context_manager.py
git commit -m "feat(skills): add SkillContextManager class with budget configuration"
```

---

## Task 5: Implement estimate_tokens method

**Files:**
- Modify: `backend/src/skills/context_manager.py`
- Test: `backend/tests/test_context_manager.py`

**Step 1: Write the failing test**

```python
def test_estimate_tokens_simple_text() -> None:
    """Test estimate_tokens approximates token count."""
    from src.skills.context_manager import SkillContextManager

    manager = SkillContextManager()

    # Simple approximation: 4 chars ≈ 1 token
    # "Hello world!" is 12 chars, ~3 tokens
    result = manager.estimate_tokens("Hello world!")
    assert result == 3


def test_estimate_tokens_empty_string() -> None:
    """Test estimate_tokens returns 0 for empty string."""
    from src.skills.context_manager import SkillContextManager

    manager = SkillContextManager()
    result = manager.estimate_tokens("")
    assert result == 0


def test_estimate_tokens_longer_text() -> None:
    """Test estimate_tokens scales with text length."""
    from src.skills.context_manager import SkillContextManager

    manager = SkillContextManager()

    # 100 chars ≈ 25 tokens
    text = "a" * 100
    result = manager.estimate_tokens(text)
    assert result == 25


def test_estimate_tokens_handles_unicode() -> None:
    """Test estimate_tokens handles unicode characters."""
    from src.skills.context_manager import SkillContextManager

    manager = SkillContextManager()

    # Unicode chars count the same
    text = "Hello 世界 🌍"
    result = manager.estimate_tokens(text)
    assert result > 0
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_context_manager.py::test_estimate_tokens -v`
Expected: FAIL with "estimate_tokens not defined"

**Step 3: Implement estimate_tokens method**

Add to `SkillContextManager` class:

```python
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count from text.

        Uses a simple heuristic: 4 characters ≈ 1 token.
        This is approximate but sufficient for budget management.
        For accurate counts, an actual tokenizer would be needed.

        Args:
            text: The text to estimate tokens for.

        Returns:
            Estimated token count (integer).
        """
        if not text:
            return 0
        return len(text) // 4
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_context_manager.py::test_estimate_tokens -v`
Expected: PASS all 4 tests

**Step 5: Run mypy for type checking**

Run: `cd backend && mypy src/skills/context_manager.py --strict`
Expected: PASS (no type errors)

**Step 6: Commit**

```bash
git add backend/src/skills/context_manager.py backend/tests/test_context_manager.py
git commit -m "feat(skills): add estimate_tokens method for token approximation"
```

---

## Task 6: Implement compact_if_needed method

**Files:**
- Modify: `backend/src/skills/context_manager.py`
- Test: `backend/tests/test_context_manager.py`

**Step 1: Write the failing test**

```python
def test_compact_if_needed_returns_original_when_under_budget() -> None:
    """Test compact_if_needed returns original text when under budget."""
    from src.skills.context_manager import SkillContextManager

    manager = SkillContextManager()
    short_text = "Hello world"  # ~3 tokens, well under 100

    result = manager.compact_if_needed(short_text, max_tokens=100)

    assert result == short_text


def test_compact_if_needed_truncates_when_over_budget() -> None:
    """Test compact_if_needed truncates when over budget."""
    from src.skills.context_manager import SkillContextManager

    manager = SkillContextManager()

    # 100 chars ≈ 25 tokens
    long_text = "a" * 100

    # Compact to ~10 tokens (40 chars)
    result = manager.compact_if_needed(long_text, max_tokens=10)

    # Should be truncated
    assert len(result) <= 50  # Allow some margin
    assert "..." in result  # Should indicate truncation


def test_compact_if_needed_handles_empty_string() -> None:
    """Test compact_if_needed handles empty string."""
    from src.skills.context_manager import SkillContextManager

    manager = SkillContextManager()
    result = manager.compact_if_needed("", max_tokens=100)

    assert result == ""


def test_compact_if_needed_indicates_truncation() -> None:
    """Test compact_if_needed adds truncation indicator."""
    from src.skills.context_manager import SkillContextManager

    manager = SkillContextManager()

    # Create text that will be truncated
    long_text = "This is a very long text that needs to be truncated because it exceeds the budget."

    result = manager.compact_if_needed(long_text, max_tokens=5)

    # Should end with truncation indicator
    assert result.endswith("...")
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_context_manager.py::test_compact_if_needed -v`
Expected: FAIL with "compact_if_needed not defined"

**Step 3: Implement compact_if_needed method**

Add to `SkillContextManager` class:

```python
    def compact_if_needed(self, context: str, max_tokens: int) -> str:
        """Compact context to fit within max_tokens budget.

        If the context is under budget, returns it unchanged.
        If over budget, truncates and adds "..." indicator.

        Note: This is a simple truncation. A production implementation
        might use LLM-based summarization for better results.

        Args:
            context: The context string to compact.
            max_tokens: Maximum tokens allowed.

        Returns:
            Compacted context string (within budget or with truncation).
        """
        if not context:
            return context

        estimated = self.estimate_tokens(context)

        if estimated <= max_tokens:
            return context

        # Need to compact - calculate target length
        # Reserve 3 chars for "..." indicator
        target_chars = (max_tokens * 4) - 3

        if target_chars <= 0:
            return "..."

        return context[:target_chars] + "..."
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_context_manager.py::test_compact_if_needed -v`
Expected: PASS all 4 tests

**Step 5: Run mypy for type checking**

Run: `cd backend && mypy src/skills/context_manager.py --strict`
Expected: PASS (no type errors)

**Step 6: Commit**

```bash
git add backend/src/skills/context_manager.py backend/tests/test_context_manager.py
git commit -m "feat(skills): add compact_if_needed method for context truncation"
```

---

## Task 7: Implement prepare_orchestrator_context method

**Files:**
- Modify: `backend/src/skills/context_manager.py`
- Test: `backend/tests/test_context_manager.py`

**Step 1: Write the failing test**

```python
def test_prepare_orchestrator_context_builds_compact_context() -> None:
    """Test prepare_orchestrator_context builds compact context."""
    from src.skills.context_manager import SkillContextManager

    manager = SkillContextManager()

    skill_index = {"skill1": "# PDF Parser\nExtracts text", "skill2": "# Email\nSend emails"}
    plan = {"step1": "Parse PDF", "step2": "Send email"}
    working_memory = {"result1": "Parsed content", "result2": "Email sent"}

    result = manager.prepare_orchestrator_context(skill_index, plan, working_memory)

    # Should contain all components
    assert "skill_index" in result.lower() or "skill" in result.lower()
    assert "plan" in result.lower() or "step" in result.lower()
    assert "memory" in result.lower() or "working" in result.lower()


def test_prepare_orchestrator_context_respects_budget() -> None:
    """Test prepare_orchestrator_context stays within budget."""
    from src.skills.context_manager import SkillContextManager

    manager = SkillContextManager(orchestrator_budget=100)

    # Create potentially large inputs
    skill_index = {"skill1": "x" * 500}  # ~125 tokens
    plan = {"step": "y" * 500}  # ~125 tokens
    working_memory = {"result": "z" * 500}  # ~125 tokens

    result = manager.prepare_orchestrator_context(skill_index, plan, working_memory)

    # Result should be compacted to fit budget
    estimated = manager.estimate_tokens(result)
    # Allow some margin for headers/formatting
    assert estimated <= 150  # Should be close to 100


def test_prepare_orchestrator_context_handles_empty_inputs() -> None:
    """Test prepare_orchestrator_context handles empty inputs."""
    from src.skills.context_manager import SkillContextManager

    manager = SkillContextManager()

    result = manager.prepare_orchestrator_context({}, {}, {})

    # Should return minimal context structure
    assert isinstance(result, str)
    assert len(result) >= 0


@pytest.mark.asyncio
async def test_prepare_orchestrator_context_with_summaries() -> None:
    """Test prepare_orchestrator_context uses skill summaries."""
    from src.skills.context_manager import SkillContextManager

    manager = SkillContextManager()

    # Mock skill summaries (compact strings)
    skill_index = {
        "skill-1": "PDF Parser [CORE] - Extracts text from PDFs",
        "skill-2": "Email Generator [Verified] - Creates email drafts",
    }
    plan = {"steps": ["Parse PDF", "Generate email"]}
    working_memory = {"last_result": "Successfully parsed document"}

    result = manager.prepare_orchestrator_context(skill_index, plan, working_memory)

    # Should contain skill names
    assert "PDF Parser" in result or "PDF" in result
    assert "Email" in result
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_context_manager.py::test_prepare_orchestrator_context -v`
Expected: FAIL with "prepare_orchestrator_context not defined"

**Step 3: Implement prepare_orchestrator_context method**

Add to `SkillContextManager` class:

```python
    def prepare_orchestrator_context(
        self,
        skill_index: dict[str, str],
        plan: dict[str, Any],
        working_memory: dict[str, str],
    ) -> str:
        """Build compact context for orchestrator planning.

        Combines skill index summaries, execution plan, and working memory
        into a compact context string within the orchestrator budget.

        The context is structured as:
        - Skill Index: Available skills with brief descriptions
        - Execution Plan: Current multi-step plan
        - Working Memory: Recent step results for handoffs

        Args:
            skill_index: Dict mapping skill_id to compact summary string.
            plan: Dict representing the execution plan (steps, dependencies).
            working_memory: Dict mapping step_id to result summary.

        Returns:
            Compact context string for orchestrator planning (~2000 tokens).
        """
        sections = []

        # Build skill index section
        if skill_index:
            skill_content = "\n".join(f"- {sid}: {summary}" for sid, summary in skill_index.items())
            skill_section = f"## Available Skills\n{skill_content}"
            skill_compacted = self.compact_if_needed(skill_section, self.skill_index_budget)
            sections.append(skill_compacted)

        # Build plan section
        if plan:
            plan_content = str(plan)
            plan_section = f"## Execution Plan\n{plan_content}"
            # Remaining budget after skills
            plan_budget = self.orchestrator_budget - self.skill_index_budget - self.working_memory_budget
            plan_compacted = self.compact_if_needed(plan_section, max(plan_budget, 200))
            sections.append(plan_compacted)

        # Build working memory section
        if working_memory:
            memory_content = "\n".join(f"- {step}: {result}" for step, result in working_memory.items())
            memory_section = f"## Working Memory\n{memory_content}"
            memory_compacted = self.compact_if_needed(memory_section, self.working_memory_budget)
            sections.append(memory_compacted)

        # Combine all sections
        full_context = "\n\n".join(sections)

        # Final compaction to ensure total budget
        return self.compact_if_needed(full_context, self.orchestrator_budget)
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_context_manager.py::test_prepare_orchestrator_context -v`
Expected: PASS all 4 tests

**Step 5: Run mypy for type checking**

Run: `cd backend && mypy src/skills/context_manager.py --strict`
Expected: PASS (no type errors)

**Step 6: Commit**

```bash
git add backend/src/skills/context_manager.py backend/tests/test_context_manager.py
git commit -m "feat(skills): add prepare_orchestrator_context method"
```

---

## Task 8: Implement prepare_subagent_context method

**Files:**
- Modify: `backend/src/skills/context_manager.py`
- Test: `backend/tests/test_context_manager.py`

**Step 1: Write the failing test**

```python
def test_prepare_subagent_context_builds_isolated_context() -> None:
    """Test prepare_subagent_context builds isolated skill context."""
    from src.skills.context_manager import SkillContextManager

    manager = SkillContextManager()

    task_briefing = "Parse the attached PDF document"
    skill_content = "# PDF Parser\n## How to use\nProvide file path..."
    input_data = {"file": "document.pdf", "pages": "all"}

    result = manager.prepare_subagent_context(task_briefing, skill_content, input_data)

    # Should contain all components
    assert "PDF" in result or "parse" in result.lower()
    assert "document.pdf" in result


def test_prepare_subagent_context_respects_budget() -> None:
    """Test prepare_subagent_context stays within subagent budget."""
    from src.skills.context_manager import SkillContextManager

    manager = SkillContextManager(subagent_budget=50)

    # Large content
    task_briefing = "x" * 500
    skill_content = "y" * 500
    input_data = {"data": "z" * 500}

    result = manager.prepare_subagent_context(task_briefing, skill_content, input_data)

    # Should be compacted
    estimated = manager.estimate_tokens(result)
    assert estimated <= 100  # Some margin over 50


def test_prepare_subagent_context_structures_components() -> None:
    """Test prepare_subagent_context structures components correctly."""
    from src.skills.context_manager import SkillContextManager

    manager = SkillContextManager()

    result = manager.prepare_subagent_context(
        task_briefing="Do the task",
        skill_content="# Skill\nInstructions here",
        input_data={"key": "value"},
    )

    # Should have clear sections
    assert "task" in result.lower() or "briefing" in result.lower()
    assert "skill" in result.lower() or "instruction" in result.lower()
    assert "input" in result.lower() or "data" in result.lower()


def test_prepare_subagent_context_handles_empty_data() -> None:
    """Test prepare_subagent_context handles empty input data."""
    from src.skills.context_manager import SkillContextManager

    manager = SkillContextManager()

    result = manager.prepare_subagent_context(
        task_briefing="Simple task",
        skill_content="# Skill\nDo this",
        input_data={},
    )

    # Should still return valid context
    assert isinstance(result, str)
    assert len(result) > 0
    assert "Simple task" in result
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_context_manager.py::test_prepare_subagent_context -v`
Expected: FAIL with "prepare_subagent_context not defined"

**Step 3: Implement prepare_subagent_context method**

Add to `SkillContextManager` class:

```python
    def prepare_subagent_context(
        self,
        task_briefing: str,
        skill_content: str,
        input_data: dict[str, Any],
    ) -> str:
        """Build isolated context for a single skill subagent.

        Each skill gets its own isolated context with:
        - Task briefing: What to do (~300 tokens)
        - Skill instructions: Full skill documentation (~2000 tokens)
        - Input data: Sanitized data for the skill (variable)

        The subagent context allows each skill to operate with full
        context about its task while keeping the orchestrator lean.

        Args:
            task_briefing: Description of what the skill should do.
            skill_content: Full skill content/documentation (markdown).
            input_data: Input data for the skill (dict will be stringified).

        Returns:
            Isolated context string for skill subagent (~6000 tokens).
        """
        sections = []

        # Task briefing section (~300 tokens)
        if task_briefing:
            briefing_section = f"## Task\n{task_briefing}"
            sections.append(briefing_section)

        # Skill instructions section (~2000 tokens for full skill doc)
        if skill_content:
            skill_section = f"## Skill Instructions\n{skill_content}"
            sections.append(skill_section)

        # Input data section (remaining budget)
        if input_data:
            data_str = str(input_data)
            data_section = f"## Input Data\n{data_str}"
            sections.append(data_section)

        # Combine and compact to subagent budget
        full_context = "\n\n".join(sections)
        return self.compact_if_needed(full_context, self.subagent_budget)
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_context_manager.py::test_prepare_subagent_context -v`
Expected: PASS all 4 tests

**Step 5: Run mypy for type checking**

Run: `cd backend && mypy src/skills/context_manager.py --strict`
Expected: PASS (no type errors)

**Step 6: Commit**

```bash
git add backend/src/skills/context_manager.py backend/tests/test_context_manager.py
git commit -m "feat(skills): add prepare_subagent_context method for isolated skill execution"
```

---

## Task 9: Implement build_working_memory_entry method

**Files:**
- Modify: `backend/src/skills/context_manager.py`
- Test: `backend/tests/test_context_manager.py`

**Step 1: Write the failing test**

```python
def test_build_working_memory_entry_minimal_verbosity() -> None:
    """Test build_working_memory_entry with MINIMAL verbosity."""
    from src.skills.context_manager import SkillContextManager, SummaryVerbosity

    manager = SkillContextManager()

    step_result = {
        "skill_id": "pdf-parser",
        "success": True,
        "result": {"text": "extracted content", "pages": 3},
    }

    result = manager.build_working_memory_entry(step_result, SummaryVerbosity.MINIMAL)

    # Minimal should be very brief
    assert len(result) <= 500  # ~125 tokens max
    assert "pdf-parser" in result.lower() or "pdf" in result.lower()
    assert "success" in result.lower() or "completed" in result.lower()


def test_build_working_memory_entry_standard_verbosity() -> None:
    """Test build_working_memory_entry with STANDARD verbosity."""
    from src.skills.context_manager import SkillContextManager, SummaryVerbosity

    manager = SkillContextManager()

    step_result = {
        "skill_id": "email-generator",
        "success": True,
        "result": {"email_id": "abc123", "recipient": "user@example.com"},
    }

    result = manager.build_working_memory_entry(step_result, SummaryVerbosity.STANDARD)

    # Standard should include more details
    assert "email" in result.lower()
    assert len(result) > 100  # Should have some substance


def test_build_working_memory_entry_detailed_verbosity() -> None:
    """Test build_working_memory_entry with DETAILED verbosity."""
    from src.skills.context_manager import SkillContextManager, SummaryVerbosity

    manager = SkillContextManager()

    step_result = {
        "skill_id": "clinical-trials-analyzer",
        "success": True,
        "result": {"trials": 5, "phase": "Phase 3", "compounds": ["DrugA", "DrugB"]},
        "metadata": {"execution_time_ms": 1500, "tokens_used": 450},
    }

    result = manager.build_working_memory_entry(step_result, SummaryVerbosity.DETAILED)

    # Detailed should include full context
    assert "clinical" in result.lower() or "trial" in result.lower()
    assert len(result) > 200  # Should be substantial


def test_build_working_memory_entry_handles_failure() -> None:
    """Test build_working_memory_entry handles failed steps."""
    from src.skills.context_manager import SkillContextManager, SummaryVerbosity

    manager = SkillContextManager()

    step_result = {
        "skill_id": "broken-skill",
        "success": False,
        "error": "Timeout after 30 seconds",
    }

    result = manager.build_working_memory_entry(step_result, SummaryVerbosity.STANDARD)

    # Should indicate failure
    assert "fail" in result.lower() or "error" in result.lower()
    assert "timeout" in result.lower() or "30" in result


def test_build_working_memory_entry_respects_token_target() -> None:
    """Test build_working_memory_entry respects verbosity token targets."""
    from src.skills.context_manager import SkillContextManager, SummaryVerbosity

    manager = SkillContextManager()

    # Create a large result
    large_result = {
        "skill_id": "large-output",
        "success": True,
        "result": {"data": "x" * 10000},  # Large output
    }

    # Minimal should be compacted
    minimal = manager.build_working_memory_entry(large_result, SummaryVerbosity.MINIMAL)
    minimal_tokens = manager.estimate_tokens(minimal)
    assert minimal_tokens <= 400  # Some margin over 300

    # Detailed should allow more
    detailed = manager.build_working_memory_entry(large_result, SummaryVerbosity.DETAILED)
    detailed_tokens = manager.estimate_tokens(detailed)
    assert detailed_tokens <= 1800  # Some margin over 1500
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_context_manager.py::test_build_working_memory_entry -v`
Expected: FAIL with "build_working_memory_entry not defined"

**Step 3: Implement build_working_memory_entry method**

Add to `SkillContextManager` class:

```python
    def build_working_memory_entry(
        self,
        step_result: dict[str, Any],
        verbosity: SummaryVerbosity,
    ) -> str:
        """Build a working memory entry from a skill execution result.

        Creates a summary of the step result for handoffs between skills.
        The verbosity level controls how much detail to include.

        Args:
            step_result: Dict with keys:
                - skill_id: ID of the executed skill
                - success: Whether execution succeeded
                - result: The skill output (if success)
                - error: Error message (if failure)
                - metadata: Optional execution metadata
            verbosity: SummaryVerbosity level for the entry.

        Returns:
            Compact summary string for working memory handoffs.
        """
        skill_id = step_result.get("skill_id", "unknown")
        success = step_result.get("success", False)
        result = step_result.get("result")
        error = step_result.get("error")
        metadata = step_result.get("metadata", {})

        # Build base summary
        parts = []

        # Status line
        status = "✓" if success else "✗"
        parts.append(f"{status} {skill_id}")

        # Success case
        if success and result:
            if verbosity == SummaryVerbosity.MINIMAL:
                # Just the type/type of result
                result_type = type(result).__name__
                parts.append(f"→ {result_type}")
            elif verbosity == SummaryVerbosity.STANDARD:
                # Key details
                if isinstance(result, dict):
                    details = ", ".join(f"{k}={v}" for k, v in list(result.items())[:3])
                    parts.append(f"→ {details}")
                else:
                    parts.append(f"→ {str(result)[:100]}")
            else:  # DETAILED
                # Full result
                parts.append(f"→ {result}")

        # Failure case
        elif not success and error:
            if verbosity == SummaryVerbosity.MINIMAL:
                parts.append(f"→ Failed")
            elif verbosity == SummaryVerbosity.STANDARD:
                parts.append(f"→ Error: {str(error)[:100]}")
            else:  # DETAILED
                parts.append(f"→ Error: {error}")

        # Metadata for detailed verbosity
        if verbosity == SummaryVerbosity.DETAILED and metadata:
            metadata_str = ", ".join(f"{k}={v}" for k, v in metadata.items())
            parts.append(f"({metadata_str})")

        # Combine and compact to target
        full_entry = " ".join(parts)
        return self.compact_if_needed(full_entry, verbosity.token_target)
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_context_manager.py::test_build_working_memory_entry -v`
Expected: PASS all 6 tests

**Step 5: Run mypy for type checking**

Run: `cd backend && mypy src/skills/context_manager.py --strict`
Expected: PASS (no type errors)

**Step 6: Commit**

```bash
git add backend/src/skills/context_manager.py backend/tests/test_context_manager.py
git commit -m "feat(skills): add build_working_memory_entry method with verbosity control"
```

---

## Task 10: Update skills module exports

**Files:**
- Modify: `backend/src/skills/__init__.py`
- Test: `backend/tests/test_context_manager.py`

**Step 1: Write the failing test**

```python
def test_skill_context_manager_exported_from_skills_module() -> None:
    """Test SkillContextManager is exported from skills module."""
    from src.skills import SkillContextManager

    assert SkillContextManager is not None


def test_summary_verbosity_exported_from_skills_module() -> None:
    """Test SummaryVerbosity is exported from skills module."""
    from src.skills import SummaryVerbosity

    assert SummaryVerbosity is not None


def test_context_allocation_exported_from_skills_module() -> None:
    """Test ContextAllocation is exported from skills module."""
    from src.skills import ContextAllocation

    assert ContextAllocation is not None


def test_context_budget_constants_exported() -> None:
    """Test context budget constants are exported."""
    from src.skills import (
        ORCHESTRATOR_BUDGET,
        SKILL_INDEX_BUDGET,
        SUBAGENT_BUDGET,
        WORKING_MEMORY_BUDGET,
    )

    assert ORCHESTRATOR_BUDGET == 2000
    assert SKILL_INDEX_BUDGET == 600
    assert WORKING_MEMORY_BUDGET == 800
    assert SUBAGENT_BUDGET == 6000
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_context_manager.py::test_skill_context_manager_exported -v`
Expected: FAIL with "cannot import name"

**Step 3: Update skills module exports**

Edit `backend/src/skills/__init__.py`:

```python
"""Skills module for ARIA.

This module manages integration with skills.sh, providing:
- Skill discovery and indexing
- Search and retrieval
- Installation and lifecycle management
- Security-aware execution
- Multi-skill orchestration
- Autonomy and trust management
- Context budget management
"""

from src.skills.autonomy import (
    SKILL_RISK_THRESHOLDS,
    SkillAutonomyService,
    SkillRiskLevel,
    TrustHistory,
)
from src.skills.context_manager import (
    ORCHESTRATOR_BUDGET,
    SKILL_INDEX_BUDGET,
    SUBAGENT_BUDGET,
    WORKING_MEMORY_BUDGET,
    ContextAllocation,
    SkillContextManager,
    SummaryVerbosity,
)
from src.skills.executor import SkillExecution, SkillExecutionError, SkillExecutor
from src.skills.index import (
    TIER_1_CORE_SKILLS,
    TIER_2_RELEVANT_TAG,
    TIER_3_DISCOVERY_ALL,
    SkillIndex,
    SkillIndexEntry,
)
from src.skills.installer import InstalledSkill, SkillInstaller, SkillNotFoundError

__all__ = [
    # Autonomy
    "SKILL_RISK_THRESHOLDS",
    "SkillAutonomyService",
    "SkillRiskLevel",
    "TrustHistory",
    # Context Manager
    "ORCHESTRATOR_BUDGET",
    "SKILL_INDEX_BUDGET",
    "WORKING_MEMORY_BUDGET",
    "SUBAGENT_BUDGET",
    "SkillContextManager",
    "SummaryVerbosity",
    "ContextAllocation",
    # Index
    "SkillIndex",
    "SkillIndexEntry",
    "TIER_1_CORE_SKILLS",
    "TIER_2_RELEVANT_TAG",
    "TIER_3_DISCOVERY_ALL",
    # Installer
    "SkillInstaller",
    "InstalledSkill",
    "SkillNotFoundError",
    # Executor
    "SkillExecutor",
    "SkillExecution",
    "SkillExecutionError",
]
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_context_manager.py::test_skill_context_manager_exported -v`
Expected: PASS all 4 tests

**Step 5: Run mypy for module exports**

Run: `cd backend && mypy src/skills/__init__.py --strict`
Expected: PASS (no type errors)

**Step 6: Commit**

```bash
git add backend/src/skills/__init__.py backend/tests/test_context_manager.py
git commit -m "feat(skills): export context manager from skills module"
```

---

## Task 11: Run full test suite and verify module completeness

**Files:**
- Test: `backend/tests/test_context_manager.py`

**Step 1: Run all context manager tests**

Run: `cd backend && pytest tests/test_context_manager.py -v`
Expected: PASS all tests

**Step 2: Run mypy on context_manager module**

Run: `cd backend && mypy src/skills/context_manager.py --strict`
Expected: PASS (no type errors)

**Step 3: Run ruff format check**

Run: `cd backend && ruff check src/skills/context_manager.py --fix`
Expected: No issues or issues auto-fixed

**Step 4: Run ruff format**

Run: `cd backend && ruff format src/skills/context_manager.py`
Expected: File formatted

**Step 5: Verify all module exports work**

Run: `cd backend && python -c "from src.skills import SkillContextManager, SummaryVerbosity, ContextAllocation, ORCHESTRATOR_BUDGET; print('All exports OK')"`
Expected: "All exports OK"

**Step 6: Run full skills test suite**

Run: `cd backend && pytest tests/test_skill*.py -v`
Expected: All PASS (including new context_manager tests)

**Step 7: Commit final changes**

```bash
git add backend/src/skills/context_manager.py backend/tests/test_context_manager.py backend/src/skills/__init__.py
git commit -m "feat(skills): complete skill context manager implementation"
```

---

## Implementation Notes

### Token Estimation
The `estimate_tokens` method uses a simple heuristic (4 chars ≈ 1 token). This is sufficient for budget management but not precise. For production, consider:
- Using actual tokenizer from tiktoken or similar
- Accounting for different tokenization of code vs natural language
- Adding buffer for safety margin

### Compaction Strategy
The `compact_if_needed` method currently does simple truncation. For better results:
- Consider LLM-based summarization for large content
- Implement sentence/paragraph-aware truncation
- Add "see full context" references when truncating

### Context Structure
The context manager assumes a specific structure:
- Orchestrator gets skill summaries + plan + working memory
- Subagents get task + skill content + input data

This design may evolve based on actual usage patterns.

---

## Verification Checklist

After implementation, verify:

- [ ] All tests pass: `pytest tests/test_context_manager.py -v`
- [ ] Type checking passes: `mypy src/skills/context_manager.py --strict`
- [ ] Formatting correct: `ruff format src/skills/context_manager.py`
- [ ] No lint issues: `ruff check src/skills/context_manager.py`
- [ ] Module exports work: `from src.skills import SkillContextManager`
- [ ] Constants are correct: `assert ORCHESTRATOR_BUDGET == 2000`
- [ ] Documentation is complete: Docstrings on all public methods
- [ ] Code follows project patterns: Dataclasses, frozen where appropriate, proper typing
