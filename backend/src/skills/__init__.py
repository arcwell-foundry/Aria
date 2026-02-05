"""Skills module for ARIA.

This module manages integration with skills.sh, providing:
- Skill discovery and indexing
- Search and retrieval
- Installation and lifecycle management
- Security-aware execution
- Multi-skill orchestration
"""

from src.skills.index import (
    TIER_1_CORE_SKILLS,
    TIER_2_RELEVANT_TAG,
    TIER_3_DISCOVERY_ALL,
    SkillIndex,
    SkillIndexEntry,
)
from src.skills.installer import InstalledSkill, SkillInstaller, SkillNotFoundError

__all__ = [
    "SkillIndex",
    "SkillIndexEntry",
    "TIER_1_CORE_SKILLS",
    "TIER_2_RELEVANT_TAG",
    "TIER_3_DISCOVERY_ALL",
    "SkillInstaller",
    "InstalledSkill",
    "SkillNotFoundError",
]
