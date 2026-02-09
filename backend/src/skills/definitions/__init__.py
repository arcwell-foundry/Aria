"""Skill definitions module for ARIA.

Provides the BaseSkillDefinition class for loading YAML-based skill
definitions and executing them via the LLM client.
"""

from src.skills.definitions.base import BaseSkillDefinition, SkillDefinition

__all__ = [
    "BaseSkillDefinition",
    "SkillDefinition",
]
