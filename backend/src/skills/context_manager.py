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

# Status indicators for working memory entries
STATUS_INDICATORS = {
    "completed": "✓",
    "failed": "✗",
    "in_progress": "⟳",
    "pending": "○",
}

# Context budget constants (in tokens)
# These budgets ensure ARIA stays within practical token limits
# while maintaining effective skill coordination.

ORCHESTRATOR_BUDGET = 2000  # Total budget for orchestrator context
SKILL_INDEX_BUDGET = 600  # Budget for skill index summaries
WORKING_MEMORY_BUDGET = 800  # Budget for working memory entries
SUBAGENT_BUDGET = 6000  # Budget for individual skill subagent contexts


class SummaryVerbosity(Enum):
    """Verbosity level for context summaries.

    Each level has a target token count for generating summaries.
    The build_working_memory_entry method uses these targets.

    Attributes:
        token_target: Target token count for this verbosity level.
    """

    MINIMAL = "minimal"  # ~300 tokens - bare facts
    STANDARD = "standard"  # ~800 tokens - key details
    DETAILED = "detailed"  # ~1500 tokens - full context

    @property
    def token_target(self) -> int:
        """Get the target token count for this verbosity level."""
        targets = {
            SummaryVerbosity.MINIMAL: 300,
            SummaryVerbosity.STANDARD: 800,
            SummaryVerbosity.DETAILED: 1500,
        }
        return targets[self]


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

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text using a simple heuristic.

        A rough approximation assuming ~4 characters per token on average.
        This is a simple heuristic and not perfectly accurate, but sufficient
        for budget management purposes.

        Args:
            text: The text to estimate tokens for.

        Returns:
            Estimated token count (integer).
        """
        return len(text) // 4

    def compact_if_needed(self, context: str, max_tokens: int) -> str:
        """Compact context to fit within max_tokens budget.

        If the context is already under the budget, returns it unchanged.
        If over budget, truncates the context and adds a "..." indicator.

        Args:
            context: The context string to potentially compact.
            max_tokens: Maximum token budget allowed.

        Returns:
            Original context if under budget, or truncated context with "..."
            suffix if over budget.
        """
        estimated = self.estimate_tokens(context)

        if estimated <= max_tokens:
            return context

        # Need to truncate - leave room for "..." suffix
        # Calculate target character count (leave 3 chars for "...")
        target_chars = (max_tokens * 4) - 3
        if target_chars < 0:
            target_chars = 0

        return context[:target_chars] + "..."

    def prepare_orchestrator_context(
        self,
        skill_index: str,
        plan: str,
        working_memory: str,
    ) -> str:
        """Build compact orchestrator context from skill index, plan, and working memory.

        Combines three sections into a unified orchestrator context:
        1. Available Skills (from skill index)
        2. Execution Plan (current plan)
        3. Working Memory (step summaries)

        Each section is compacted to fit its allocated budget before being combined.

        Args:
            skill_index: The skill index summaries to include.
            plan: The execution plan to include.
            working_memory: The working memory entries to include.

        Returns:
            A unified context string with all three sections, compacted to fit budgets.
        """
        # Compact each section to its allocated budget
        compacted_skill_index = self.compact_if_needed(
            skill_index,
            self.skill_index_budget,
        )
        compacted_plan = self.compact_if_needed(
            plan,
            self.orchestrator_budget - self.skill_index_budget - self.working_memory_budget,
        )
        compacted_working_memory = self.compact_if_needed(
            working_memory,
            self.working_memory_budget,
        )

        # Build the unified context with proper section headers
        sections = [
            "## Available Skills",
            compacted_skill_index,
            "",
            "## Execution Plan",
            compacted_plan,
            "",
            "## Working Memory",
            compacted_working_memory,
        ]

        return "\n".join(sections)

    def prepare_subagent_context(
        self,
        task_briefing: str,
        skill_content: str,
        input_data: str,
    ) -> str:
        """Build isolated subagent context for skill execution.

        Combines three sections into a unified subagent context:
        1. Task (what the skill should do)
        2. Skill Instructions (how to use the skill)
        3. Input Data (the data to process)

        The entire context is compacted to fit the subagent budget.

        Args:
            task_briefing: A brief description of what the skill should accomplish.
            skill_content: The skill's instructions and documentation.
            input_data: The input data for the skill to process.

        Returns:
            A unified context string with all three sections, compacted to fit budget.
        """
        # Build the unified context first
        sections = [
            "## Task",
            task_briefing,
            "",
            "## Skill Instructions",
            skill_content,
            "",
            "## Input Data",
            input_data,
        ]

        full_context = "\n".join(sections)

        # Compact the entire context to fit subagent budget
        return self.compact_if_needed(full_context, self.subagent_budget)

    def build_working_memory_entry(
        self,
        step_result: dict[str, Any],
        verbosity: SummaryVerbosity,
    ) -> str:
        """Build a working memory entry with controlled verbosity.

        Creates summaries of step results with status indicators and
        detail levels controlled by the verbosity parameter.

        Args:
            step_result: Dictionary containing step information with keys:
                - step: Name of the step
                - status: One of "completed", "failed", "in_progress", "pending"
                - result: Result description (optional)
                - error: Error message (optional, for failed steps)
                - details: Additional details (optional)
                - metadata: Additional metadata (optional)
            verbosity: How detailed the summary should be.

        Returns:
            A formatted working memory entry string.
        """
        step = step_result.get("step", "unknown_step")
        status = step_result.get("status", "pending")
        result = step_result.get("result", "")
        error = step_result.get("error", "")
        details = step_result.get("details", "")
        metadata = step_result.get("metadata", {})

        # Get status indicator
        indicator = STATUS_INDICATORS.get(status, "○")

        # Build base entry
        parts = [f"{indicator} {step}"]

        # Add content based on verbosity
        if status == "failed" and error:
            parts.append(f"Error: {error}")
        elif result:
            parts.append(result)

        # Add details for STANDARD and DETAILED
        if verbosity != SummaryVerbosity.MINIMAL and details:
            parts.append(details)

        # Add metadata for DETAILED
        if verbosity == SummaryVerbosity.DETAILED and metadata:
            metadata_str = ", ".join(f"{k}: {v}" for k, v in metadata.items())
            parts.append(f"({metadata_str})")

        entry = " - ".join(parts)

        # Compact to fit verbosity token target
        return self.compact_if_needed(entry, verbosity.token_target)
