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
