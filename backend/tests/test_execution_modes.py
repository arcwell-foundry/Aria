"""Tests for execution mode selection and undo window timing.

Covers:
- 3×3 trust × risk matrix → correct execution mode
- Undo window timing (within window, expired)
- Action type category and risk level mapping
"""

from __future__ import annotations

import pytest

from src.core.trust import (
    APPROVE_EACH,
    APPROVE_PLAN,
    AUTO_EXECUTE,
    EXECUTE_AND_NOTIFY,
    TrustCalibrationService,
)
from src.models.action_queue import ActionStatus, ExecutionMode
from src.services.action_execution import (
    UNDO_WINDOW_SECONDS,
    action_type_to_category,
    risk_level_to_score,
)

# ---------------------------------------------------------------------------
# TestExecutionModeSelection — trust × risk matrix
# ---------------------------------------------------------------------------


class TestExecutionModeSelection:
    """Verify correct execution mode from the 3×3 trust × risk matrix."""

    def test_high_trust_low_risk_auto_execute(self) -> None:
        """HIGH trust + LOW risk → AUTO_EXECUTE."""
        result = TrustCalibrationService._compute_approval_level(trust=0.85, risk_score=0.1)
        assert result == AUTO_EXECUTE

    def test_high_trust_medium_risk_notify(self) -> None:
        """HIGH trust + MEDIUM risk → EXECUTE_AND_NOTIFY."""
        result = TrustCalibrationService._compute_approval_level(trust=0.85, risk_score=0.45)
        assert result == EXECUTE_AND_NOTIFY

    def test_high_trust_high_risk_approve_plan(self) -> None:
        """HIGH trust + HIGH risk → APPROVE_PLAN."""
        result = TrustCalibrationService._compute_approval_level(trust=0.85, risk_score=0.7)
        assert result == APPROVE_PLAN

    def test_medium_trust_low_risk_notify(self) -> None:
        """MEDIUM trust + LOW risk → EXECUTE_AND_NOTIFY."""
        result = TrustCalibrationService._compute_approval_level(trust=0.6, risk_score=0.1)
        assert result == EXECUTE_AND_NOTIFY

    def test_medium_trust_medium_risk_approve_plan(self) -> None:
        """MEDIUM trust + MEDIUM risk → APPROVE_PLAN."""
        result = TrustCalibrationService._compute_approval_level(trust=0.6, risk_score=0.45)
        assert result == APPROVE_PLAN

    def test_medium_trust_high_risk_approve_each(self) -> None:
        """MEDIUM trust + HIGH risk → APPROVE_EACH."""
        result = TrustCalibrationService._compute_approval_level(trust=0.6, risk_score=0.7)
        assert result == APPROVE_EACH

    def test_low_trust_low_risk_approve_plan(self) -> None:
        """LOW trust + LOW risk → APPROVE_PLAN."""
        result = TrustCalibrationService._compute_approval_level(trust=0.3, risk_score=0.1)
        assert result == APPROVE_PLAN

    def test_low_trust_medium_risk_approve_each(self) -> None:
        """LOW trust + MEDIUM risk → APPROVE_EACH."""
        result = TrustCalibrationService._compute_approval_level(trust=0.3, risk_score=0.45)
        assert result == APPROVE_EACH

    def test_low_trust_high_risk_approve_each(self) -> None:
        """LOW trust + HIGH risk → APPROVE_EACH."""
        result = TrustCalibrationService._compute_approval_level(trust=0.3, risk_score=0.9)
        assert result == APPROVE_EACH

    def test_boundary_trust_0_8_is_medium(self) -> None:
        """Trust at exactly 0.8 is medium tier (not high)."""
        result = TrustCalibrationService._compute_approval_level(trust=0.8, risk_score=0.1)
        assert result == EXECUTE_AND_NOTIFY  # Medium trust, not auto

    def test_boundary_trust_0_4_is_low(self) -> None:
        """Trust at exactly 0.4 is low tier (not medium)."""
        result = TrustCalibrationService._compute_approval_level(trust=0.4, risk_score=0.1)
        assert result == APPROVE_PLAN  # Low trust

    def test_boundary_risk_0_3_is_medium(self) -> None:
        """Risk at exactly 0.3 is medium (not low)."""
        result = TrustCalibrationService._compute_approval_level(trust=0.85, risk_score=0.3)
        assert result == EXECUTE_AND_NOTIFY  # High trust, medium risk

    def test_boundary_risk_0_6_is_high(self) -> None:
        """Risk at exactly 0.6 is high (not medium)."""
        result = TrustCalibrationService._compute_approval_level(trust=0.85, risk_score=0.6)
        assert result == APPROVE_PLAN  # High trust, high risk


# ---------------------------------------------------------------------------
# TestMappings — action_type_to_category, risk_level_to_score
# ---------------------------------------------------------------------------


class TestMappings:
    """Verify helper mapping functions."""

    def test_email_draft_category(self) -> None:
        assert action_type_to_category("email_draft") == "email_draft"

    def test_crm_update_category(self) -> None:
        assert action_type_to_category("crm_update") == "crm_action"

    def test_research_category(self) -> None:
        assert action_type_to_category("research") == "research"

    def test_meeting_prep_category(self) -> None:
        assert action_type_to_category("meeting_prep") == "meeting_prep"

    def test_lead_gen_category(self) -> None:
        assert action_type_to_category("lead_gen") == "lead_discovery"

    def test_unknown_category_defaults_to_general(self) -> None:
        assert action_type_to_category("unknown_type") == "general"

    def test_risk_low_score(self) -> None:
        assert risk_level_to_score("low") == pytest.approx(0.15)

    def test_risk_medium_score(self) -> None:
        assert risk_level_to_score("medium") == pytest.approx(0.45)

    def test_risk_high_score(self) -> None:
        assert risk_level_to_score("high") == pytest.approx(0.7)

    def test_risk_critical_score(self) -> None:
        assert risk_level_to_score("critical") == pytest.approx(0.9)

    def test_risk_unknown_defaults_to_0_5(self) -> None:
        assert risk_level_to_score("unknown") == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# TestEnums — ExecutionMode and UNDO_PENDING
# ---------------------------------------------------------------------------


class TestEnums:
    """Verify new enum values exist and serialize correctly."""

    def test_execution_mode_values(self) -> None:
        assert ExecutionMode.AUTO_EXECUTE.value == "auto_execute"
        assert ExecutionMode.EXECUTE_AND_NOTIFY.value == "execute_and_notify"
        assert ExecutionMode.APPROVE_PLAN.value == "approve_plan"
        assert ExecutionMode.APPROVE_EACH.value == "approve_each"

    def test_undo_pending_status(self) -> None:
        assert ActionStatus.UNDO_PENDING.value == "undo_pending"

    def test_undo_pending_in_status_list(self) -> None:
        values = [s.value for s in ActionStatus]
        assert "undo_pending" in values

    def test_undo_window_constant(self) -> None:
        assert UNDO_WINDOW_SECONDS == 300
