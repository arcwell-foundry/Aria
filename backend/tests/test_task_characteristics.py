"""Tests for TaskCharacteristics risk scoring."""


def test_risk_score_formula_weighted_correctly() -> None:
    """Verify risk_score uses the documented weighted formula."""
    from src.core.task_characteristics import TaskCharacteristics

    tc = TaskCharacteristics(
        complexity=0.6,
        criticality=0.8,
        uncertainty=0.4,
        reversibility=0.2,
        verifiability=0.5,
        subjectivity=0.3,
        contextuality=0.7,
    )
    expected = (
        0.8 * 0.3       # criticality
        + (1 - 0.2) * 0.25  # 1-reversibility
        + 0.4 * 0.2     # uncertainty
        + 0.6 * 0.15    # complexity
        + 0.7 * 0.1     # contextuality
    )
    assert abs(tc.risk_score - expected) < 1e-9


def test_risk_score_bounds() -> None:
    """All zeros gives 0.25 (from 1 - reversibility=0 term)."""
    from src.core.task_characteristics import TaskCharacteristics

    tc_zeros = TaskCharacteristics(
        complexity=0.0,
        criticality=0.0,
        uncertainty=0.0,
        reversibility=0.0,
        verifiability=0.0,
        subjectivity=0.0,
        contextuality=0.0,
    )
    # Only (1-0)*0.25 = 0.25 contributes
    assert abs(tc_zeros.risk_score - 0.25) < 1e-9

    tc_ones = TaskCharacteristics(
        complexity=1.0,
        criticality=1.0,
        uncertainty=1.0,
        reversibility=1.0,
        verifiability=1.0,
        subjectivity=1.0,
        contextuality=1.0,
    )
    # 1*0.3 + 0*0.25 + 1*0.2 + 1*0.15 + 1*0.1 = 0.75
    assert abs(tc_ones.risk_score - 0.75) < 1e-9


def test_thinking_effort_routine_below_04() -> None:
    """Risk score <= 0.4 maps to routine."""
    from src.core.task_characteristics import TaskCharacteristics

    tc = TaskCharacteristics.default_for_action("research")
    assert tc.risk_score <= 0.4
    assert tc.thinking_effort == "routine"


def test_thinking_effort_complex_04_to_07() -> None:
    """Risk score between 0.4 and 0.7 maps to complex."""
    from src.core.task_characteristics import TaskCharacteristics

    tc = TaskCharacteristics(
        complexity=0.6,
        criticality=0.6,
        uncertainty=0.5,
        reversibility=0.3,
        verifiability=0.5,
        subjectivity=0.5,
        contextuality=0.5,
    )
    assert 0.4 < tc.risk_score <= 0.7
    assert tc.thinking_effort == "complex"


def test_thinking_effort_critical_above_07() -> None:
    """Risk score > 0.7 maps to critical."""
    from src.core.task_characteristics import TaskCharacteristics

    tc = TaskCharacteristics(
        complexity=0.9,
        criticality=1.0,
        uncertainty=0.9,
        reversibility=0.0,
        verifiability=0.1,
        subjectivity=0.9,
        contextuality=0.9,
    )
    assert tc.risk_score > 0.7
    assert tc.thinking_effort == "critical"


def test_approval_level_thresholds() -> None:
    """All four approval levels are reachable."""
    from src.core.task_characteristics import TaskCharacteristics

    # AUTO_EXECUTE: risk < 0.2
    tc_low = TaskCharacteristics(
        complexity=0.0, criticality=0.0, uncertainty=0.0,
        reversibility=1.0, verifiability=1.0, subjectivity=0.0, contextuality=0.0,
    )
    assert tc_low.risk_score < 0.2
    assert tc_low.approval_level == "AUTO_EXECUTE"

    # EXECUTE_AND_NOTIFY: 0.2 <= risk <= 0.5
    tc_med = TaskCharacteristics.default_for_action("research")
    assert 0.2 <= tc_med.risk_score <= 0.5
    assert tc_med.approval_level == "EXECUTE_AND_NOTIFY"

    # APPROVE_PLAN: 0.5 < risk <= 0.75
    tc_high = TaskCharacteristics.default_for_action("communicate")
    assert 0.5 < tc_high.risk_score <= 0.75
    assert tc_high.approval_level == "APPROVE_PLAN"

    # APPROVE_EACH: risk > 0.75
    tc_crit = TaskCharacteristics(
        complexity=1.0, criticality=1.0, uncertainty=1.0,
        reversibility=0.0, verifiability=0.0, subjectivity=1.0, contextuality=1.0,
    )
    assert tc_crit.risk_score > 0.75
    assert tc_crit.approval_level == "APPROVE_EACH"


def test_risk_level_maps_to_enum_values() -> None:
    """risk_level returns strings matching RiskLevel enum."""
    from src.core.task_characteristics import TaskCharacteristics

    assert TaskCharacteristics(
        complexity=0.0, criticality=0.0, uncertainty=0.0,
        reversibility=1.0, verifiability=1.0, subjectivity=0.0, contextuality=0.0,
    ).risk_level == "low"

    assert TaskCharacteristics.default_for_action("research").risk_level == "medium"

    assert TaskCharacteristics.default_for_action("communicate").risk_level == "high"

    assert TaskCharacteristics(
        complexity=1.0, criticality=1.0, uncertainty=1.0,
        reversibility=0.0, verifiability=0.0, subjectivity=1.0, contextuality=1.0,
    ).risk_level == "critical"


def test_to_dict_includes_computed_properties() -> None:
    """to_dict() includes risk_score, thinking_effort, approval_level, risk_level."""
    from src.core.task_characteristics import TaskCharacteristics

    tc = TaskCharacteristics.default_for_action("plan")
    d = tc.to_dict()

    assert "risk_score" in d
    assert "thinking_effort" in d
    assert "approval_level" in d
    assert "risk_level" in d
    assert d["complexity"] == tc.complexity
    assert isinstance(d["risk_score"], float)


def test_from_dict_roundtrip() -> None:
    """from_dict(to_dict()) preserves dimension values."""
    from src.core.task_characteristics import TaskCharacteristics

    original = TaskCharacteristics(
        complexity=0.1, criticality=0.2, uncertainty=0.3,
        reversibility=0.4, verifiability=0.5, subjectivity=0.6, contextuality=0.7,
    )
    restored = TaskCharacteristics.from_dict(original.to_dict())

    assert abs(restored.complexity - original.complexity) < 1e-9
    assert abs(restored.criticality - original.criticality) < 1e-9
    assert abs(restored.uncertainty - original.uncertainty) < 1e-9
    assert abs(restored.reversibility - original.reversibility) < 1e-9
    assert abs(restored.risk_score - original.risk_score) < 1e-9


def test_default_for_action_research() -> None:
    """Research defaults: high reversibility, low criticality."""
    from src.core.task_characteristics import TaskCharacteristics

    tc = TaskCharacteristics.default_for_action("research")
    assert tc.reversibility == 1.0
    assert tc.criticality == 0.2


def test_default_for_action_communicate() -> None:
    """Communicate defaults: low reversibility, high criticality."""
    from src.core.task_characteristics import TaskCharacteristics

    tc = TaskCharacteristics.default_for_action("communicate")
    assert tc.reversibility == 0.1
    assert tc.criticality == 0.7


def test_default_for_action_unknown() -> None:
    """Unknown action returns neutral 0.5 defaults."""
    from src.core.task_characteristics import TaskCharacteristics

    tc = TaskCharacteristics.default_for_action("nonexistent_action")
    assert tc.complexity == 0.5
    assert tc.criticality == 0.5
    assert tc.reversibility == 0.5
