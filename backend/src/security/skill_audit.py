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


class SkillAuditService:
    """Service for managing skill audit trail with hash chain integrity."""

    def __init__(self, supabase_client: Client | None = None) -> None:
        """Initialize the audit service.

        Args:
            supabase_client: Optional Supabase client. If None, uses default.
        """
        from src.db.supabase import SupabaseClient

        self._client = supabase_client or SupabaseClient.get_client()

    def _compute_hash(self, entry_data: dict[str, Any], previous_hash: str) -> str:
        """Compute SHA256 hash of entry data including previous hash.

        This creates the cryptographic link between entries in the chain.
        Uses sorted keys for deterministic JSON serialization.

        Args:
            entry_data: Dictionary of entry data to hash.
            previous_hash: Hash of the previous entry in the chain.

        Returns:
            64-character hex SHA256 hash.
        """
        # Create deterministic string representation
        # Sort keys for consistent ordering
        canonical = json.dumps(entry_data, sort_keys=True)
        # Include previous hash to chain entries together
        combined = f"{canonical}:{previous_hash}"
        # Return SHA256 as hex string
        return hashlib.sha256(combined.encode()).hexdigest()

    async def get_latest_hash(self, user_id: str) -> str:
        """Get the entry_hash of the most recent audit entry for a user.

        Args:
            user_id: The user's UUID.

        Returns:
            The entry_hash of the most recent entry, or zero hash if none exist.
        """
        try:
            response = await (
                self._client.table("skill_audit_log")
                .select("entry_hash")
                .eq("user_id", user_id)
                .order("timestamp", desc=True)
                .limit(1)
                .single()
                .execute()
            )

            if response.data and response.data.get("entry_hash"):
                return str(response.data["entry_hash"])

            # No entries: return zero hash for genesis block
            return "0" * 64

        except Exception as e:
            logger.warning(
                "Failed to fetch latest hash, using zero hash",
                extra={"user_id": user_id, "error": str(e), "error_type": type(e).__name__},
            )
            return "0" * 64

    async def log_execution(self, entry: SkillAuditEntry) -> None:
        """Log a skill execution to the audit trail.

        Args:
            entry: The audit entry to log.

        Raises:
            DatabaseError: If logging fails.
        """
        try:
            # Convert dataclass to dict for database insertion
            data = {
                "user_id": entry.user_id,
                "tenant_id": entry.tenant_id,
                "skill_id": entry.skill_id,
                "skill_path": entry.skill_path,
                "skill_trust_level": entry.skill_trust_level,
                "task_id": entry.task_id,
                "agent_id": entry.agent_id,
                "trigger_reason": entry.trigger_reason,
                "data_classes_requested": entry.data_classes_requested,
                "data_classes_granted": entry.data_classes_granted,
                "data_redacted": entry.data_redacted,
                "tokens_used": entry.tokens_used,
                "input_hash": entry.input_hash,
                "output_hash": entry.output_hash,
                "execution_time_ms": entry.execution_time_ms,
                "success": entry.success,
                "error": entry.error,
                "sandbox_config": entry.sandbox_config,
                "security_flags": entry.security_flags,
                "previous_hash": entry.previous_hash,
                "entry_hash": entry.entry_hash,
            }

            self._client.table("skill_audit_log").insert(data).execute()

            logger.info(
                "Skill execution logged",
                extra={
                    "user_id": entry.user_id,
                    "skill_id": entry.skill_id,
                    "success": entry.success,
                },
            )

        except Exception as e:
            logger.exception(
                "Failed to log skill execution",
                extra={"user_id": entry.user_id, "skill_id": entry.skill_id},
            )
            raise DatabaseError(f"Failed to log skill execution: {e}") from e

    async def verify_chain(self, user_id: str) -> bool:
        """Verify the integrity of a user's audit log hash chain.

        Checks that each entry's previous_hash matches the entry_hash of the
        immediately preceding entry. Any mismatch indicates tampering.

        Args:
            user_id: The user's UUID.

        Returns:
            True if chain is valid, False if tampering detected.
        """
        try:
            response = await (
                self._client.table("skill_audit_log")
                .select("*")
                .eq("user_id", user_id)
                .order("timestamp", desc=False)  # Oldest first
                .execute()
            )

            entries = response.data

            # Empty chain is valid
            if not entries:
                return True

            # Verify each link in the chain
            previous_hash = "0" * 64  # Genesis block has zero previous hash

            for entry in entries:
                # Check previous_hash matches
                if entry.get("previous_hash") != previous_hash:
                    logger.warning(
                        "Hash chain broken: previous_hash mismatch",
                        extra={
                            "user_id": user_id,
                            "entry_id": entry.get("id"),
                            "expected": previous_hash,
                            "actual": entry.get("previous_hash"),
                        },
                    )
                    return False

                # Recompute hash to verify entry wasn't modified
                entry_data = {
                    k: v
                    for k, v in entry.items()
                    if k not in ["id", "timestamp", "entry_hash", "previous_hash"]
                }
                computed_hash = self._compute_hash(entry_data, previous_hash)

                if entry.get("entry_hash") != computed_hash:
                    logger.warning(
                        "Hash chain broken: entry_hash mismatch",
                        extra={
                            "user_id": user_id,
                            "entry_id": entry.get("id"),
                            "expected": computed_hash,
                            "actual": entry.get("entry_hash"),
                        },
                    )
                    return False

                # Chain continues
                previous_hash = entry.get("entry_hash", "")

            return True

        except Exception as e:
            logger.exception("Failed to verify hash chain", extra={"user_id": user_id})
            return False
