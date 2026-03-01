"""ARIA Self-Provisioning: Capability Graph, Gap Detection, Resolution Engine.

This module contains the core services for ARIA's self-provisioning system:
- CapabilityGraphService: queries and resolves capability providers
- GapDetectionService: detects capability gaps during goal planning
- ResolutionEngine: generates ranked resolution strategies
- ProvisioningConversation: formats gaps as natural chat messages
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from src.models.capability import CapabilityGap, CapabilityProvider, ResolutionStrategy

logger = logging.getLogger(__name__)

# Map Composio app names to integration types in user_integrations table
_COMPOSIO_APP_TO_INTEGRATION_TYPE: dict[str, str] = {
    "OUTLOOK365": "email",
    "GMAIL": "email",
    "GOOGLE_CALENDAR": "calendar",
    "SALESFORCE": "crm",
    "HUBSPOT": "crm",
    "VEEVA_CRM": "crm",
    "SLACK": "messaging",
}


class CapabilityGraphService:
    """Manages the capability graph — what ARIA can do and at what quality."""

    def __init__(self, db_client: Any) -> None:
        self._db = db_client

    async def get_providers(self, capability_name: str) -> list[CapabilityProvider]:
        """Get all providers for a capability, sorted by quality descending."""
        try:
            result = (
                self._db.table("capability_graph")
                .select("*")
                .eq("capability_name", capability_name)
                .eq("is_active", True)
                .order("quality_score", desc=True)
                .execute()
            )
            return [CapabilityProvider(**r) for r in (result.data or [])]
        except Exception:
            logger.exception(
                "Failed to query capability_graph",
                extra={"capability_name": capability_name},
            )
            return []

    async def get_best_available(
        self, capability_name: str, user_id: str
    ) -> Optional[CapabilityProvider]:
        """Get the highest-quality available provider for a user.

        Availability rules:
        - native → always available
        - composio_oauth/api_key → user has active connection
        - composite → all required sub-capabilities are available
        - user_provided → always available (lowest quality)
        """
        try:
            providers = await self.get_providers(capability_name)
        except Exception:
            logger.exception(
                "Failed to get providers for capability",
                extra={"capability_name": capability_name},
            )
            return None

        for provider in providers:
            if provider.provider_type == "native":
                return provider

            elif provider.provider_type in ("composio_oauth", "composio_api_key"):
                connected = await self._check_user_connection(
                    user_id, provider.composio_app_name
                )
                if connected:
                    return provider

            elif provider.provider_type == "composite":
                all_available = True
                for req_cap in provider.required_capabilities or []:
                    sub = await self.get_best_available(req_cap, user_id)
                    if sub is None:
                        all_available = False
                        break
                if all_available:
                    return provider

            elif provider.provider_type == "user_provided":
                return provider

        return None

    async def _check_user_connection(
        self, user_id: str, composio_app: str | None
    ) -> bool:
        """Check if user has active Composio connection for this app.

        Uses active_integrations view (status = 'active' only).
        """
        if not composio_app:
            return False

        integration_type = _COMPOSIO_APP_TO_INTEGRATION_TYPE.get(composio_app)
        if not integration_type:
            return False

        try:
            result = (
                self._db.table("active_integrations")
                .select("id")
                .eq("user_id", user_id)
                .eq("integration_type", integration_type)
                .limit(1)
                .execute()
            )
            return len(result.data or []) > 0
        except Exception:
            logger.warning(
                "Failed to check user connection",
                extra={"user_id": user_id, "composio_app": composio_app},
            )
            return False
