"""Companion personality and theory of mind system for ARIA.

This module provides:
- ARIA's consistent character with opinions, pushback capability, and personality traits
- Theory of Mind module for understanding user mental states
"""

from src.companion.personality import (
    OpinionResult,
    PersonalityProfile,
    PersonalityService,
    TraitLevel,
)
from src.companion.theory_of_mind import (
    ConfidenceLevel,
    MentalState,
    StatePattern,
    StressLevel,
    TheoryOfMindModule,
)

__all__ = [
    # Personality
    "OpinionResult",
    "PersonalityProfile",
    "PersonalityService",
    "TraitLevel",
    # Theory of Mind
    "ConfidenceLevel",
    "MentalState",
    "StatePattern",
    "StressLevel",
    "TheoryOfMindModule",
]
