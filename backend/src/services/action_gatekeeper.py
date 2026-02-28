"""ActionGatekeeper for ARIA draft pipeline risk-based approval.

Defines action policies with risk levels and auto-approve windows.
Used by AutonomousDraftEngine and draft approval endpoints to enforce
consistent gating on email actions.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ActionGatekeeper:
    """Gatekeeper that determines approval requirements for email actions.

    Policies map action types to risk levels and auto-approve windows.
    MEDIUM-risk actions auto-approve after a timeout; HIGH and CRITICAL
    actions require explicit user approval.
    """

    POLICIES: dict[str, dict[str, Any]] = {
        "email_draft_generated": {
            "risk": "MEDIUM",
            "approval": True,
            "auto_execute_after_minutes": 30,
        },
        "email_draft_save_to_client": {
            "risk": "HIGH",
            "approval": True,
            "auto_execute_after_minutes": None,
        },
        "email_send": {
            "risk": "CRITICAL",
            "approval": True,
            "auto_execute_after_minutes": None,
        },
    }

    async def check_action(self, action_type: str) -> dict[str, Any]:
        """Check the policy for a given action type.

        Args:
            action_type: The action being performed (e.g. "email_draft_generated").

        Returns:
            Policy dict with risk level, approval requirement, and
            optional auto_execute_after_minutes.
        """
        policy = self.POLICIES.get(
            action_type,
            {"risk": "HIGH", "approval": True, "auto_execute_after_minutes": None},
        )
        logger.debug(
            "ActionGatekeeper: action=%s policy=%s",
            action_type,
            policy,
        )
        return policy

    async def authorize_approval(self, action_type: str, user_id: str) -> bool:
        """Verify that a user is permitted to approve this action type.

        Currently all authenticated users can approve their own drafts.
        This hook exists so we can later add role-based or delegation checks.

        Args:
            action_type: The action being approved.
            user_id: The user requesting approval.

        Returns:
            True if the user is permitted to approve.
        """
        policy = await self.check_action(action_type)
        if not policy.get("approval"):
            logger.warning(
                "ActionGatekeeper: action %s does not require approval", action_type,
            )
            return True

        # All authenticated users can approve their own email actions
        return True


# Module-level singleton
_gatekeeper: ActionGatekeeper | None = None


def get_action_gatekeeper() -> ActionGatekeeper:
    """Return the module-level ActionGatekeeper singleton."""
    global _gatekeeper
    if _gatekeeper is None:
        _gatekeeper = ActionGatekeeper()
    return _gatekeeper
