"""Shared DCT enforcement middleware for MCP servers.

Every MCP tool call can optionally carry a ``_dct`` dict (serialized
DelegationCapabilityToken).  ``enforce_dct`` validates that the token
allows the requested action *before* the tool body runs.

Behaviour when ``_dct`` is None (no token provided):
    Fail-open — matches the existing orchestrator.py pattern where
    direct tool calls from tests or internal code skip DCT checks.
"""

from __future__ import annotations

import logging
from typing import Any

from src.core.capability_tokens import DelegationCapabilityToken

logger = logging.getLogger(__name__)


class DCTViolation(Exception):
    """Raised when a tool call is denied by DCT enforcement."""

    def __init__(self, tool_name: str, delegatee: str, action: str) -> None:
        self.tool_name = tool_name
        self.delegatee = delegatee
        self.action = action
        super().__init__(
            f"DCT violation: agent '{delegatee}' is not authorized "
            f"to perform '{action}' (tool={tool_name})"
        )


def enforce_dct(
    tool_name: str,
    dct_action: str,
    dct_dict: dict[str, Any] | None,
) -> None:
    """Validate that a DCT allows the requested action.

    Args:
        tool_name: Name of the MCP tool being called (for error messages).
        dct_action: The action string to check (e.g. ``"read_pubmed"``).
        dct_dict: Serialized DCT dict, or None to skip enforcement.

    Raises:
        DCTViolation: If the token denies the action or is expired.
    """
    if dct_dict is None:
        return  # Fail-open when no token provided

    dct = DelegationCapabilityToken.from_dict(dct_dict)

    if not dct.is_valid():
        logger.warning(
            "DCT expired for tool=%s delegatee=%s action=%s",
            tool_name,
            dct.delegatee,
            dct_action,
        )
        raise DCTViolation(tool_name, dct.delegatee, dct_action)

    if not dct.can_perform(dct_action):
        logger.warning(
            "DCT denied: tool=%s delegatee=%s action=%s allowed=%s denied=%s",
            tool_name,
            dct.delegatee,
            dct_action,
            dct.allowed_actions,
            dct.denied_actions,
        )
        raise DCTViolation(tool_name, dct.delegatee, dct_action)
