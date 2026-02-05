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


class TestHashComputation:
    """Tests for hash computation logic."""

    def test_compute_hash_creates_sha256(self) -> None:
        """Test _compute_hash creates a valid SHA256 hash."""
        from src.security.skill_audit import SkillAuditService

        service = SkillAuditService()
        entry_dict = {
            "skill_id": "test-skill",
            "user_id": "user-123",
            "success": True,
        }
        previous_hash = "prev-hash"

        result = service._compute_hash(entry_dict, previous_hash)

        # SHA256 hashes are 64 hex characters
        assert len(result) == 64
        # Should be valid hex
        assert all(c in "0123456789abcdef" for c in result)

    def test_compute_hash_is_deterministic(self) -> None:
        """Test same input produces same hash."""
        from src.security.skill_audit import SkillAuditService

        service = SkillAuditService()
        entry_dict = {
            "skill_id": "test-skill",
            "user_id": "user-123",
            "success": True,
        }
        previous_hash = "prev-hash"

        hash1 = service._compute_hash(entry_dict, previous_hash)
        hash2 = service._compute_hash(entry_dict, previous_hash)

        assert hash1 == hash2

    def test_compute_hash_different_input_different_hash(self) -> None:
        """Test different input produces different hash."""
        from src.security.skill_audit import SkillAuditService

        service = SkillAuditService()
        entry_dict1 = {"skill_id": "skill-a", "user_id": "user-123", "success": True}
        entry_dict2 = {"skill_id": "skill-b", "user_id": "user-123", "success": True}
        previous_hash = "prev-hash"

        hash1 = service._compute_hash(entry_dict1, previous_hash)
        hash2 = service._compute_hash(entry_dict2, previous_hash)

        assert hash1 != hash2

    def test_compute_hash_includes_previous_hash(self) -> None:
        """Test hash changes when previous_hash changes."""
        from src.security.skill_audit import SkillAuditService

        service = SkillAuditService()
        entry_dict = {"skill_id": "test-skill", "user_id": "user-123", "success": True}

        hash1 = service._compute_hash(entry_dict, "prev-hash-1")
        hash2 = service._compute_hash(entry_dict, "prev-hash-2")

        assert hash1 != hash2

    def test_compute_hash_handles_key_ordering(self) -> None:
        """Test semantically equivalent dicts with different key ordering produce same hash."""
        from src.security.skill_audit import SkillAuditService

        service = SkillAuditService()

        # Same data, different key ordering
        dict1 = {"skill_id": "test", "user_id": "123", "success": True}
        dict2 = {"user_id": "123", "skill_id": "test", "success": True}
        previous_hash = "prev-hash"

        hash1 = service._compute_hash(dict1, previous_hash)
        hash2 = service._compute_hash(dict2, previous_hash)

        assert hash1 == hash2

    def test_compute_hash_handles_boolean_and_none(self) -> None:
        """Test hash handles boolean and None values correctly."""
        from src.security.skill_audit import SkillAuditService

        service = SkillAuditService()

        data = {"active": True, "deleted": False, "metadata": None}
        result = service._compute_hash(data, "prev")

        # Should produce valid 64-char hash without error
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_compute_hash_handles_numeric_values(self) -> None:
        """Test hash handles integer and float values correctly."""
        from src.security.skill_audit import SkillAuditService

        service = SkillAuditService()

        data = {"count": 42, "ratio": 3.14, "tokens_used": 1000}
        result = service._compute_hash(data, "prev")

        assert len(result) == 64

    def test_compute_hash_handles_empty_dict(self) -> None:
        """Test hash handles empty dictionary correctly."""
        from src.security.skill_audit import SkillAuditService

        service = SkillAuditService()

        result = service._compute_hash({}, "prev-hash")

        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)
