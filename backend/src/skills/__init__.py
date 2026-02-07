"""Skills module for ARIA.

This module manages integration with skills.sh, providing:
- Skill discovery and indexing
- Search and retrieval
- Installation and lifecycle management
- Security-aware execution
- Multi-skill orchestration
- Autonomy and trust management
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
from src.skills.orchestrator import (
    ExecutionPlan,
    ExecutionStep,
    SkillOrchestrator,
    WorkingMemoryEntry,
)

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
    "ContextAllocation",
    "SummaryVerbosity",
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
    # Orchestrator
    "SkillOrchestrator",
    "ExecutionPlan",
    "ExecutionStep",
    "WorkingMemoryEntry",
]
