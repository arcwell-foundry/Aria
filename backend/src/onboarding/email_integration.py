"""Email Integration service for onboarding (US-907).

Manages email OAuth connection and privacy configuration for
Gmail and Microsoft Outlook providers via Composio.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from src.db.supabase import SupabaseClient
from src.integrations.oauth import get_oauth_client

logger = logging.getLogger(__name__)


class PrivacyExclusion(BaseModel):
    """A privacy exclusion rule for email processing.

    Users can exclude specific senders, domains, or categories
    from email ingestion to protect personal communications.
    """

    type: str  # "sender", "domain", or "category"
    value: str  # email address, domain, or category name
    reason: str | None = None  # Optional reason for the exclusion


class EmailIntegrationConfig(BaseModel):
    """Configuration for email integration privacy controls.

    Users configure these settings BEFORE any ingestion starts,
    giving them full control over what ARIA learns from their email.
    """

    provider: str  # "google" or "microsoft"
    scopes: list[str] = Field(default_factory=list)  # OAuth scopes requested
    privacy_exclusions: list[PrivacyExclusion] = Field(default_factory=list)
    ingestion_scope_days: int = 365  # How many days of email history to ingest
    attachment_ingestion: bool = False  # Requires explicit opt-in


class EmailIntegrationService:
    """Manages email OAuth connection and privacy configuration.

    This service handles the US-907 requirements:
    - OAuth consent flow for Google Workspace and Microsoft 365
    - Privacy exclusion configuration before ingestion
    - Connection status checking
    - Readiness score updates
    - Episodic memory recording
    """

    # Categories that ARIA considers "personal" and should prompt exclusion
    PERSONAL_CATEGORIES = [
        "spouse/partner",
        "medical",
        "financial/banking",
        "legal/personal",
        "family",
    ]

    def __init__(self) -> None:
        """Initialize service with Supabase client."""
        self._db = SupabaseClient.get_client()

    async def initiate_oauth(self, user_id: str, provider: str) -> dict[str, Any]:
        """Start OAuth flow for email provider via Composio.

        Args:
            user_id: The authenticated user's ID.
            provider: Either "google" for Gmail or "microsoft" for Outlook.

        Returns:
            Dict with auth_url for frontend redirect and connection status:
            {"auth_url": str, "connection_id": str, "status": "pending"}
            or {"status": "error", "message": str} on failure.
        """
        try:
            oauth_client = get_oauth_client()

            # Map provider to Composio integration type
            integration_type = "GMAIL" if provider == "google" else "OUTLOOK"
            redirect_uri = (
                f"{self._get_base_url()}/onboarding"
            )

            # Generate OAuth URL via Composio SDK (returns real connection ID)
            auth_url, connection_id = await oauth_client.generate_auth_url_with_connection_id(
                user_id=user_id,
                integration_type=integration_type,
                redirect_uri=redirect_uri,
            )

            logger.info(
                "OAuth initiated for email integration",
                extra={"user_id": user_id, "provider": provider},
            )

            return {
                "auth_url": auth_url,
                "connection_id": connection_id,
                "status": "pending",
            }

        except ValueError as e:
            # Auth config not found — actionable error for the user
            logger.warning(
                "OAuth auth config missing",
                extra={"user_id": user_id, "provider": provider, "error": str(e)},
            )
            return {
                "auth_url": "",
                "status": "error",
                "message": str(e),
            }

        except Exception as e:
            logger.warning(
                "OAuth initiation failed",
                extra={"user_id": user_id, "provider": provider, "error": str(e)},
            )
            return {
                "auth_url": "",
                "status": "error",
                "message": str(e),
            }

    async def check_connection_status(self, user_id: str, provider: str) -> dict[str, Any]:
        """Check if email provider is connected for the user.

        First checks local database. If not found, queries Composio for
        active connections and auto-records them if found.

        Args:
            user_id: The authenticated user's ID.
            provider: Either "google" or "microsoft".

        Returns:
            Dict with connection status:
            {"connected": bool, "provider": str, "connected_at": str | None}
        """
        integration_type = "gmail" if provider == "google" else "outlook"

        # Check local database first
        result = (
            self._db.table("user_integrations")
            .select("*")
            .eq("user_id", user_id)
            .eq("integration_type", integration_type)
            .maybe_single()
            .execute()
        )

        if result and result.data:
            # Type ignore: Supabase returns Any but we know it's a dict at runtime
            data: dict[str, Any] = result.data  # type: ignore[assignment]
            # Check if status is actually "active", not just that a row exists
            is_active = data.get("status") == "active"
            return {
                "connected": is_active,
                "provider": provider,
                "connected_at": data.get("created_at") if is_active else None,
                "status": data.get("status"),
            }

        # Not in local DB — check Composio for active connections
        # This handles the case where OAuth completed but callback wasn't processed
        try:
            from src.integrations.oauth import get_oauth_client

            oauth_client = get_oauth_client()
            composio_type = "GMAIL" if provider == "google" else "OUTLOOK"

            # Query Composio for user's connected accounts
            import asyncio

            def _list_connections() -> Any:
                return oauth_client._client.client.connected_accounts.list(  # type: ignore[union-attr]

                )

            connections = await asyncio.to_thread(_list_connections)

            # Find matching connection
            for conn in connections.items:
                if (
                    hasattr(conn, "toolkit")
                    and hasattr(conn.toolkit, "slug")
                    and conn.toolkit.slug.lower() == composio_type.lower()
                    and str(conn.status).upper() == "ACTIVE"
                ):
                    # Found active connection — record it locally
                    connection_id = conn.id
                    logger.info(
                        "Auto-recording email connection from Composio",
                        extra={
                            "user_id": user_id,
                            "provider": provider,
                            "connection_id": connection_id,
                        },
                    )

                    self._db.table("user_integrations").upsert(
                        {
                            "user_id": user_id,
                            "integration_type": integration_type,
                            "provider": integration_type.upper(),
                            "status": "active",
                            "composio_connection_id": connection_id,
                        },
                        on_conflict="user_id,integration_type",
                    ).execute()

                    return {
                        "connected": True,
                        "provider": provider,
                        "connected_at": datetime.now(UTC).isoformat(),
                    }

        except Exception as e:
            logger.warning(
                "Failed to check Composio connections",
                extra={"user_id": user_id, "provider": provider, "error": str(e)},
            )

        return {"connected": False, "provider": provider}

    async def save_privacy_config(
        self,
        user_id: str,
        config: EmailIntegrationConfig,
    ) -> dict[str, Any]:
        """Save privacy exclusions and ingestion preferences.

        This method:
        1. Saves configuration to user_settings table
        2. Updates readiness scores (relationship_graph, digital_twin)
        3. Records event in episodic memory

        Args:
            user_id: The authenticated user's ID.
            config: The email integration configuration.

        Returns:
            Dict with save status: {"status": "saved", "exclusions": int}
        """
        # Save configuration to user_settings (merge into existing integrations JSONB)
        existing = (
            self._db.table("user_settings")
            .select("integrations")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        merged_integrations = (
            existing.data.get("integrations", {}) if existing and existing.data else {}
        )
        merged_integrations["email"] = {
            "provider": config.provider,
            "privacy_exclusions": [e.model_dump() for e in config.privacy_exclusions],
            "ingestion_scope_days": config.ingestion_scope_days,
            "attachment_ingestion": config.attachment_ingestion,
        }
        self._db.table("user_settings").upsert(
            {
                "user_id": user_id,
                "integrations": merged_integrations,
            },
            on_conflict="user_id",
        ).execute()

        # Update readiness scores
        try:
            from src.onboarding.orchestrator import OnboardingOrchestrator

            orch = OnboardingOrchestrator()
            await orch.update_readiness_scores(
                user_id,
                {
                    "relationship_graph": 15.0,  # Connection alone gives some readiness
                    "digital_twin": 15.0,  # Email will enrich the twin
                },
            )
        except Exception as e:
            logger.warning(
                "Readiness update failed",
                extra={"user_id": user_id, "error": str(e)},
            )

        # Record in episodic memory
        try:
            from src.memory.episodic import Episode, EpisodicMemory

            memory = EpisodicMemory()
            now = datetime.now(UTC)
            episode = Episode(
                id=str(uuid.uuid4()),
                user_id=user_id,
                event_type="onboarding_email_connected",
                content=f"Email integration configured for {config.provider}",
                participants=[],
                occurred_at=now,
                recorded_at=now,
                context={
                    "provider": config.provider,
                    "exclusions_count": len(config.privacy_exclusions),
                    "attachment_ingestion": config.attachment_ingestion,
                    "ingestion_scope_days": config.ingestion_scope_days,
                },
            )
            await memory.store_episode(episode)
        except Exception as e:
            logger.warning(
                "Episodic record failed",
                extra={"user_id": user_id, "error": str(e)},
            )

        # NOTE: Email bootstrap is now triggered from /integrations/record-connection
        # endpoint when the OAuth connection is successfully recorded.
        # This ensures bootstrap runs immediately after OAuth completes.

        logger.info(
            "Email privacy configuration saved",
            extra={
                "user_id": user_id,
                "provider": config.provider,
                "exclusions": len(config.privacy_exclusions),
            },
        )

        return {"status": "saved", "exclusions": len(config.privacy_exclusions)}

    def _get_base_url(self) -> str:
        """Get the base URL for OAuth redirects.

        In production, this comes from environment config.
        For local development, defaults to localhost.
        """
        from src.core.config import settings

        # Use first CORS origin as the redirect base
        origins = settings.cors_origins_list
        return origins[0] if origins else "http://localhost:5173"
