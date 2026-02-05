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

# Context budget constants (in tokens)
# These budgets ensure ARIA stays within practical token limits
# while maintaining effective skill coordination.

ORCHESTRATOR_BUDGET = 2000  # Total budget for orchestrator context
SKILL_INDEX_BUDGET = 600     # Budget for skill index summaries
WORKING_MEMORY_BUDGET = 800  # Budget for working memory entries
SUBAGENT_BUDGET = 6000       # Budget for individual skill subagent contexts


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
