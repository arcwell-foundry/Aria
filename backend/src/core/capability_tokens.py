"""Delegation Capability Tokens — scoped agent permissions.

Each agent dispatch receives a DelegationCapabilityToken that defines exactly
which actions the agent can perform, which are denied, and optional data-scope
restrictions.  Tokens are ephemeral (runtime only, no DB persistence) and
carry a time limit.

Enforcement in orchestrator.py / base.py is handled separately — this module
only handles minting and permission queries.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Wildcard helper
# ---------------------------------------------------------------------------


def _matches_any(action: str, patterns: list[str]) -> bool:
    """Check whether *action* matches any pattern in *patterns*.

    Supports exact matches and wildcard suffixes:
    - ``read_everything`` matches any action starting with ``read_``
    - ``write_anything`` matches any action starting with ``write_``
    - ``send_anything`` matches any action starting with ``send_``

    The prefix before ``_everything`` / ``_anything`` must be non-empty to
    prevent accidental universal matches (e.g. ``_everything`` won't match).
    """
    for pattern in patterns:
        if pattern == action:
            return True
        for suffix in ("_everything", "_anything"):
            if pattern.endswith(suffix):
                prefix = pattern[: -len(suffix)]
                if prefix and action.startswith(prefix + "_"):
                    return True
    return False


# ---------------------------------------------------------------------------
# Default agent permission profiles
# ---------------------------------------------------------------------------

AGENT_PROFILES: dict[str, dict[str, list[str]]] = {
    "hunter": {
        "allowed": ["read_exa", "read_apollo", "read_company_profiles"],
        "denied": ["send_email", "modify_crm", "delete_anything"],
    },
    "scout": {
        "allowed": ["read_exa", "read_news_apis", "read_fda", "read_uspto", "read_mcp_registries"],
        "denied": ["send_email", "modify_crm", "write_anything"],
    },
    "analyst": {
        "allowed": [
            "read_pubmed", "read_clinicaltrials", "read_chembl", "read_fda", "read_uspto",
            "read_memory", "evaluate_mcp_server",
        ],
        "denied": ["send_email", "modify_crm", "write_external"],
    },
    "strategist": {
        "allowed": ["read_memory", "read_lead_data", "read_competitor_data"],
        "denied": ["send_email", "modify_crm", "write_external"],
    },
    "scribe": {
        "allowed": ["read_memory", "read_digital_twin", "draft_email"],
        "denied": ["send_email", "modify_crm"],
    },
    "operator": {
        "allowed": ["read_crm", "write_crm", "read_calendar", "write_calendar", "send_email"],
        "denied": ["delete_crm_records", "modify_user_settings"],
    },
    "verifier": {
        "allowed": ["read_everything"],
        "denied": ["write_anything", "send_anything"],
    },
    "executor": {
        "allowed": ["browser_navigate"],
        "denied": ["enter_passwords", "modify_settings"],
    },
}


# ---------------------------------------------------------------------------
# Token dataclass
# ---------------------------------------------------------------------------


@dataclass
class DelegationCapabilityToken:
    """Scoped permission token issued to an agent for a single delegation."""

    token_id: str
    delegatee: str
    goal_id: str | None
    allowed_actions: list[str] = field(default_factory=list)
    denied_actions: list[str] = field(default_factory=list)
    data_scope: dict[str, Any] = field(default_factory=dict)
    time_limit_seconds: int = 300
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def is_valid(self) -> bool:
        """Return ``True`` if the token has not expired.

        A token is considered expired when the elapsed time since creation
        is **greater than or equal to** ``time_limit_seconds``.
        """
        elapsed = (datetime.now(UTC) - self.created_at).total_seconds()
        return elapsed < self.time_limit_seconds

    def can_perform(self, action: str) -> bool:
        """Check if *action* is permitted.

        Evaluation order:
        1. Deny list checked first — deny wins unconditionally.
        2. Allow list checked — action must match.
        3. Default: deny.
        """
        if _matches_any(action, self.denied_actions):
            return False
        return bool(_matches_any(action, self.allowed_actions))

    def within_scope(self, data_type: str, data_id: str) -> bool:
        """Check whether *data_id* is within the token's data scope.

        If ``data_scope`` does not contain *data_type*, access is unrestricted
        for that type.  If it does, *data_id* must be in the allowed list.
        """
        if data_type not in self.data_scope:
            return True
        return data_id in self.data_scope[data_type]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary (JSON-safe)."""
        return {
            "token_id": self.token_id,
            "delegatee": self.delegatee,
            "goal_id": self.goal_id,
            "allowed_actions": list(self.allowed_actions),
            "denied_actions": list(self.denied_actions),
            "data_scope": dict(self.data_scope),
            "time_limit_seconds": self.time_limit_seconds,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DelegationCapabilityToken:
        """Deserialize from a dictionary produced by ``to_dict()``."""
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        return cls(
            token_id=data["token_id"],
            delegatee=data["delegatee"],
            goal_id=data.get("goal_id"),
            allowed_actions=list(data.get("allowed_actions", [])),
            denied_actions=list(data.get("denied_actions", [])),
            data_scope=dict(data.get("data_scope", {})),
            time_limit_seconds=int(data.get("time_limit_seconds", 300)),
            created_at=created_at or datetime.now(UTC),
        )


# ---------------------------------------------------------------------------
# Minter
# ---------------------------------------------------------------------------


class DCTMinter:
    """Mints scoped capability tokens for agent delegations."""

    def mint(
        self,
        delegatee: str,
        goal_id: str | None = None,
        additional_scope: dict[str, Any] | None = None,
        time_limit: int = 300,
    ) -> DelegationCapabilityToken:
        """Create a new capability token for *delegatee*.

        Parameters
        ----------
        delegatee:
            Agent name (case-insensitive for profile lookup; original preserved
            in the token).
        goal_id:
            Optional goal identifier to link the token to.
        additional_scope:
            Optional dict with keys ``allowed_actions``, ``denied_actions``,
            and/or ``data_scope`` to merge into the profile defaults.
        time_limit:
            Token lifetime in seconds (default 300).

        Raises
        ------
        ValueError
            If *delegatee* does not map to a known agent profile.
        """
        # Normalize for profile lookup — first word, lowercased
        lookup_key = delegatee.strip().split()[0].lower()

        if lookup_key not in AGENT_PROFILES:
            known = ", ".join(sorted(AGENT_PROFILES))
            msg = f"Unknown agent '{delegatee}' (resolved to '{lookup_key}'). Known agents: {known}"
            raise ValueError(msg)

        profile = AGENT_PROFILES[lookup_key]

        # Copy lists to avoid mutating the constant
        allowed = list(profile["allowed"])
        denied = list(profile["denied"])
        data_scope: dict[str, Any] = {}

        if additional_scope:
            allowed.extend(additional_scope.get("allowed_actions", []))
            denied.extend(additional_scope.get("denied_actions", []))
            data_scope.update(additional_scope.get("data_scope", {}))

        token = DelegationCapabilityToken(
            token_id=str(uuid.uuid4()),
            delegatee=delegatee,
            goal_id=goal_id,
            allowed_actions=allowed,
            denied_actions=denied,
            data_scope=data_scope,
            time_limit_seconds=time_limit,
        )

        logger.info(
            "Minted DCT %s for agent '%s' (goal=%s, allowed=%d, denied=%d, ttl=%ds)",
            token.token_id,
            delegatee,
            goal_id,
            len(allowed),
            len(denied),
            time_limit,
        )

        return token
