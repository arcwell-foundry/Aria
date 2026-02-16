"""Companion personality and cognitive systems for ARIA.

This module provides:
- ARIA's consistent character with opinions, pushback capability, and personality traits
- Theory of Mind module for understanding user mental states
- Metacognition service for knowledge self-assessment and uncertainty acknowledgment
"""

from src.companion.metacognition import (
    KnowledgeAssessment,
    KnowledgeSource,
    MetacognitionService,
)
from src.companion.personality import (
    OpinionResult,
    PersonalityProfile,
    PersonalityService,
    TraitLevel,
)
from src.companion.self_improvement import (
    ImprovementArea,
    SelfImprovementLoop,
)
from src.companion.theory_of_mind import (
    ConfidenceLevel,
    MentalState,
    StatePattern,
    StressLevel,
    TheoryOfMindModule,
)

__all__ = [
    # Metacognition
    "KnowledgeAssessment",
    "KnowledgeSource",
    "MetacognitionService",
    # Personality
    "OpinionResult",
    "PersonalityProfile",
    "PersonalityService",
    "TraitLevel",
    # Self-Improvement
    "ImprovementArea",
    "SelfImprovementLoop",
    # Theory of Mind
    "ConfidenceLevel",
    "MentalState",
    "StatePattern",
    "StressLevel",
    "TheoryOfMindModule",
]
