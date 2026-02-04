"""Tests for health_score module exports."""

def test_health_score_calculator_export():
    """Test HealthScoreCalculator is exported from memory module."""
    from src.memory import HealthScoreCalculator
    assert HealthScoreCalculator is not None

def test_health_score_history_export():
    """Test HealthScoreHistory is exported from memory module."""
    from src.memory import HealthScoreHistory
    assert HealthScoreHistory is not None

def test_direct_health_score_import():
    """Test direct import from health_score module."""
    from src.memory.health_score import HealthScoreCalculator, HealthScoreHistory
    assert HealthScoreCalculator is not None
    assert HealthScoreHistory is not None