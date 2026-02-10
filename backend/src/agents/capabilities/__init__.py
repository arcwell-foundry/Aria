"""Agent capabilities module for ARIA.

Provides the BaseCapability abstract class that defines
how agents expose discrete, composable units of functionality.
"""

from src.agents.capabilities.base import BaseCapability, CapabilityResult
from src.agents.capabilities.crm_sync import CRMDeepSyncCapability

__all__ = [
    "BaseCapability",
    "CapabilityResult",
    "CRMDeepSyncCapability",
]
