"""Factory for CompanionOrchestrator.

Provides a single-call constructor that returns an orchestrator with
all subsystems lazy-initialized on first use.
"""

from src.companion.orchestrator import CompanionOrchestrator


def create_companion_orchestrator() -> CompanionOrchestrator:
    """Create a CompanionOrchestrator with default lazy-init subsystems."""
    return CompanionOrchestrator()
