"""Companion personality system for ARIA.

This module provides ARIA's consistent character with opinions,
pushback capability, and personality traits that adapt to user preferences.
"""

from src.companion.personality import (
    OpinionResult,
    PersonalityProfile,
    PersonalityService,
    TraitLevel,
)

__all__ = [
    "OpinionResult",
    "PersonalityProfile",
    "PersonalityService",
    "TraitLevel",
]
