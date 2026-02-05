"""Skill audit trail system for ARIA.

Provides immutable, hash-chained audit logging for all skill executions.
Any tampering with audit records breaks the cryptographic chain.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.core.exceptions import DatabaseError
from supabase import Client

logger = logging.getLogger(__name__)


@dataclass
class SkillAuditEntry:
    """Single audit entry for a skill execution.

    Each entry contains a hash of the previous entry, creating an immutable
    chain. Any modification to historical records breaks the chain.

    Attributes:
        user_id: User who triggered the skill execution.
        tenant_id: Optional tenant ID for multi-tenant scenarios.
        skill_id: Unique identifier for the skill.
        skill_path: File path or identifier for the skill.
        skill_trust_level: Trust level of the skill (core, verified, community, user).
        task_id: Optional task UUID this execution is part of.
        agent_id: Optional agent ID that triggered the skill.
        trigger_reason: Why this skill was invoked.
        data_classes_requested: Data classes the skill requested access to.
        data_classes_granted: Data classes actually granted to the skill.
        data_redacted: Whether sensitive data was redacted before passing to skill.
        tokens_used: List of token counts per model used.
        input_hash: SHA256 hash of input data for integrity verification.
        output_hash: SHA256 hash of output data (null if execution failed).
        execution_time_ms: Execution duration in milliseconds.
        success: Whether the skill execution succeeded.
        error: Error message if execution failed.
        sandbox_config: Sandbox settings applied during execution.
        security_flags: Any security concerns flagged during execution.
        previous_hash: Hash of the previous entry in the chain.
        entry_hash: SHA256 hash of this entry (includes previous_hash).
    """

    user_id: str
    skill_id: str
    skill_path: str
    skill_trust_level: str
    trigger_reason: str
    data_classes_requested: list[str]
    data_classes_granted: list[str]
    input_hash: str
    previous_hash: str
    entry_hash: str
    success: bool
    tenant_id: str | None = None
    task_id: str | None = None
    agent_id: str | None = None
    data_redacted: bool = False
    tokens_used: list[str] = field(default_factory=list)
    output_hash: str | None = None
    execution_time_ms: int | None = None
    error: str | None = None
    sandbox_config: dict[str, Any] | None = None
    security_flags: list[str] = field(default_factory=list)
