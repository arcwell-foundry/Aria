"""Tests for skill_audit module."""

import pytest
from dataclasses import dataclass


def test_skill_audit_entry_dataclass_exists() -> None:
    """Test SkillAuditEntry dataclass can be imported."""
    from src.security.skill_audit import SkillAuditEntry

    assert SkillAuditEntry is not None


def test_skill_audit_entry_has_required_fields() -> None:
    """Test SkillAuditEntry has all required fields."""
    from src.security.skill_audit import SkillAuditEntry

    entry = SkillAuditEntry(
        user_id="user-123",
        skill_id="skill-456",
        skill_path="/skills/pdf",
        skill_trust_level="core",
        trigger_reason="user_request",
        data_classes_requested=["public", "internal"],
        data_classes_granted=["public", "internal"],
        input_hash="abc123",
        previous_hash="def456",
        entry_hash="computed_hash",
        success=True,
    )

    assert entry.user_id == "user-123"
    assert entry.skill_id == "skill-456"
    assert entry.skill_path == "/skills/pdf"
    assert entry.skill_trust_level == "core"
    assert entry.trigger_reason == "user_request"
    assert entry.data_classes_requested == ["public", "internal"]
    assert entry.data_classes_granted == ["public", "internal"]
    assert entry.input_hash == "abc123"
    assert entry.previous_hash == "def456"
    assert entry.entry_hash == "computed_hash"
    assert entry.success is True


def test_skill_audit_entry_optional_fields_default() -> None:
    """Test SkillAuditEntry optional fields have sensible defaults."""
    from src.security.skill_audit import SkillAuditEntry

    entry = SkillAuditEntry(
        user_id="user-123",
        skill_id="skill-456",
        skill_path="/skills/pdf",
        skill_trust_level="core",
        trigger_reason="user_request",
        data_classes_requested=["public"],
        data_classes_granted=["public"],
        input_hash="abc123",
        previous_hash="def456",
        entry_hash="computed_hash",
        success=True,
    )

    assert entry.tenant_id is None
    assert entry.task_id is None
    assert entry.agent_id is None
    assert entry.data_redacted is False
    assert entry.tokens_used == []
    assert entry.output_hash is None
    assert entry.execution_time_ms is None
    assert entry.error is None
    assert entry.sandbox_config is None
    assert entry.security_flags == []
