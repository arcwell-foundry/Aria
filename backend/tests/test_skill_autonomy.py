"""Tests for skill autonomy and trust system."""

from enum import Enum

import pytest

from src.skills.autonomy import SKILL_RISK_THRESHOLDS, SkillRiskLevel


class TestSkillRiskLevel:
    """Tests for SkillRiskLevel enum."""

    def test_risk_level_enum_values(self) -> None:
        """Test SkillRiskLevel has all required risk levels."""
        assert SkillRiskLevel.LOW.value == "low"
        assert SkillRiskLevel.MEDIUM.value == "medium"
        assert SkillRiskLevel.HIGH.value == "high"
        assert SkillRiskLevel.CRITICAL.value == "critical"

    def test_risk_levels_are_ordered(self) -> None:
        """Test risk levels can be compared by severity."""
        levels = list(SkillRiskLevel)
        assert levels == [
            SkillRiskLevel.LOW,
            SkillRiskLevel.MEDIUM,
            SkillRiskLevel.HIGH,
            SkillRiskLevel.CRITICAL,
        ]


class TestSkillRiskThresholds:
    """Tests for SKILL_RISK_THRESHOLDS configuration."""

    def test_thresholds_defined_for_all_risk_levels(self) -> None:
        """Test thresholds exist for all risk levels."""
        assert SkillRiskLevel.LOW in SKILL_RISK_THRESHOLDS
        assert SkillRiskLevel.MEDIUM in SKILL_RISK_THRESHOLDS
        assert SkillRiskLevel.HIGH in SKILL_RISK_THRESHOLDS
        assert SkillRiskLevel.CRITICAL in SKILL_RISK_THRESHOLDS

    def test_low_threshold_requires_3_successes(self) -> None:
        """Test LOW risk requires 3 successful executions."""
        assert SKILL_RISK_THRESHOLDS[SkillRiskLevel.LOW]["auto_approve_after"] == 3

    def test_medium_threshold_requires_10_successes(self) -> None:
        """Test MEDIUM risk requires 10 successful executions."""
        assert SKILL_RISK_THRESHOLDS[SkillRiskLevel.MEDIUM]["auto_approve_after"] == 10

    def test_high_threshold_never_auto_approves(self) -> None:
        """Test HIGH risk never auto-approves (session trust only)."""
        assert SKILL_RISK_THRESHOLDS[SkillRiskLevel.HIGH]["auto_approve_after"] is None

    def test_critical_threshold_never_auto_approves(self) -> None:
        """Test CRITICAL risk never auto-approves (always ask)."""
        assert SKILL_RISK_THRESHOLDS[SkillRiskLevel.CRITICAL]["auto_approve_after"] is None

    def test_threshold_values_are_positive_or_none(self) -> None:
        """Test all auto_approve_after values are positive integers or None."""
        for threshold in SKILL_RISK_THRESHOLDS.values():
            value = threshold["auto_approve_after"]
            assert value is None or (isinstance(value, int) and value > 0)
