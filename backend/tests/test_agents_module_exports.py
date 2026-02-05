"""Tests for agents module exports."""


def test_scout_agent_is_exported() -> None:
    """Test ScoutAgent is exported from agents module."""
    from src.agents import ScoutAgent

    assert ScoutAgent is not None
    assert ScoutAgent.name == "Scout"


def test_all_agents_includes_scout() -> None:
    """Test __all__ includes ScoutAgent."""
    from src.agents import __all__

    assert "ScoutAgent" in __all__


def test_orchestrator_exports() -> None:
    """Test orchestrator types are exported from agents module."""
    from src.agents import (
        AgentOrchestrator,
        ExecutionMode,
        OrchestrationResult,
        ProgressUpdate,
    )

    assert AgentOrchestrator is not None
    assert ExecutionMode is not None
    assert OrchestrationResult is not None
    assert ProgressUpdate is not None


def test_skill_aware_agent_is_exported() -> None:
    """Test SkillAwareAgent is exported from agents module."""
    from src.agents import SkillAwareAgent

    assert SkillAwareAgent is not None


def test_skill_analysis_is_exported() -> None:
    """Test SkillAnalysis is exported from agents module."""
    from src.agents import SkillAnalysis

    assert SkillAnalysis is not None


def test_agent_skills_is_exported() -> None:
    """Test AGENT_SKILLS is exported from agents module."""
    from src.agents import AGENT_SKILLS

    assert AGENT_SKILLS is not None
    assert isinstance(AGENT_SKILLS, dict)


def test_all_includes_skill_aware_exports() -> None:
    """Test __all__ includes SkillAwareAgent, SkillAnalysis, AGENT_SKILLS."""
    from src.agents import __all__

    assert "SkillAwareAgent" in __all__
    assert "SkillAnalysis" in __all__
    assert "AGENT_SKILLS" in __all__
