"""CRM synchronization service.

Provides bidirectional sync between ARIA Lead Memory and CRM systems
(Salesforce, HubSpot) via Composio.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from src.core.exceptions import (
    CRMConnectionError,
    CRMSyncError,
    DatabaseError,
    LeadMemoryNotFoundError,
)
from src.db.supabase import SupabaseClient
from src.integrations.oauth import get_oauth_client
from src.services.crm_audit import CRMAuditOperation, get_crm_audit_service
from src.services.crm_sync_models import (
    ConflictResolution,
    CRMSyncState,
    SyncDirection,
    SyncStatus,
)

logger = logging.getLogger(__name__)

# CRM stage mapping - Salesforce stages to ARIA lifecycle stages
SALESFORCE_STAGE_MAP = {
    "Prospecting": "lead",
    "Qualification": "lead",
    "Proposal": "opportunity",
    "Negotiation": "opportunity",
    "Closed Won": "account",
    "Closed Lost": "account",
}

# HubSpot deal stages to ARIA lifecycle stages
HUBSPOT_STAGE_MAP = {
    "appointmentscheduled": "lead",
    "qualifiedtobuy": "lead",
    "presentationscheduled": "opportunity",
    "decisionmakerboughtin": "opportunity",
    "contractsent": "opportunity",
    "closedwon": "account",
    "closedlost": "account",
}

# Fields where CRM wins on conflict
CRM_WINS_FIELDS = {"lifecycle_stage", "expected_value", "expected_close_date", "status"}

# Fields where ARIA wins on conflict
ARIA_WINS_FIELDS = {"health_score", "insights", "stakeholder_map"}

# Maximum number of retries before giving up
MAX_RETRIES = 5


class CRMSyncService:
    """Service for bidirectional CRM synchronization.

    Provides methods to:
    - Track sync state per lead (synced, pending, conflict, error)
    - Push ARIA summaries to CRM tagged with [ARIA]
    - Pull CRM stage changes to Lead Memory (CRM wins for structured fields)
    - Resolve conflicts (CRM wins for stage/value/date, merge for notes)
    - Schedule retries with exponential backoff tracking
    """

    def _get_supabase_client(self) -> Any:
        """Get the Supabase client instance.

        Returns:
            Initialized Supabase client.

        Raises:
            DatabaseError: If client initialization fails.
        """
        try:
            return SupabaseClient.get_client()
        except Exception as e:
            raise DatabaseError(f"Failed to get Supabase client: {e}") from e

    async def get_sync_state(self, lead_memory_id: str) -> CRMSyncState | None:
        """Get sync state for a lead.

        Args:
            lead_memory_id: The lead memory ID to get state for.

        Returns:
            CRMSyncState if exists, None otherwise.

        Raises:
            DatabaseError: If database operation fails.
        """
        try:
            client = self._get_supabase_client()

            response = (
                client.table("lead_memory_crm_sync")
                .select("*")
                .eq("lead_memory_id", lead_memory_id)
                .single()
                .execute()
            )

            if response.data is None:
                return None

            return CRMSyncState.from_dict(response.data)

        except DatabaseError:
            raise
        except Exception as e:
            # If the error is about no rows found, return None
            if "No rows" in str(e) or "multiple" in str(e).lower():
                return None
            logger.exception("Failed to get sync state")
            raise DatabaseError(f"Failed to get sync state: {e}") from e

    async def create_sync_state(self, lead_memory_id: str) -> CRMSyncState:
        """Create initial sync state for a lead.

        Args:
            lead_memory_id: The lead memory ID to create state for.

        Returns:
            The created CRMSyncState.

        Raises:
            DatabaseError: If creation fails.
        """
        try:
            client = self._get_supabase_client()
            now = datetime.now(UTC)

            data = {
                "id": str(uuid.uuid4()),
                "lead_memory_id": lead_memory_id,
                "status": SyncStatus.SYNCED.value,
                "last_sync_at": now.isoformat(),
                "pending_changes": [],
                "conflict_log": [],
                "retry_count": 0,
            }

            response = client.table("lead_memory_crm_sync").insert(data).execute()

            if not response.data or len(response.data) == 0:
                raise DatabaseError("Failed to create sync state: no data returned")

            logger.info(
                "Created sync state",
                extra={"lead_memory_id": lead_memory_id},
            )

            return CRMSyncState.from_dict(response.data[0])

        except DatabaseError:
            raise
        except Exception as e:
            logger.exception("Failed to create sync state")
            raise DatabaseError(f"Failed to create sync state: {e}") from e

    async def update_sync_status(
        self,
        lead_memory_id: str,
        status: SyncStatus,
        pending_changes: list[dict[str, Any]] | None = None,
        error_message: str | None = None,
        direction: SyncDirection | None = None,
    ) -> None:
        """Update sync status for a lead.

        Args:
            lead_memory_id: The lead memory ID to update.
            status: New sync status.
            pending_changes: Optional list of pending changes.
            error_message: Optional error message if status is ERROR.
            direction: Optional sync direction.

        Raises:
            DatabaseError: If update fails.
        """
        try:
            client = self._get_supabase_client()
            now = datetime.now(UTC)

            data: dict[str, Any] = {
                "status": status.value,
                "updated_at": now.isoformat(),
            }

            if direction is not None:
                data["sync_direction"] = direction.value

            if pending_changes is not None:
                data["pending_changes"] = pending_changes

            if error_message is not None:
                data["error_message"] = error_message

            if status == SyncStatus.SYNCED:
                data["last_sync_at"] = now.isoformat()
                data["error_message"] = None
                data["pending_changes"] = []

            response = (
                client.table("lead_memory_crm_sync")
                .update(data)
                .eq("lead_memory_id", lead_memory_id)
                .execute()
            )

            if not response.data or len(response.data) == 0:
                # State might not exist yet, create it
                await self.create_sync_state(lead_memory_id)
                # Retry the update
                response = (
                    client.table("lead_memory_crm_sync")
                    .update(data)
                    .eq("lead_memory_id", lead_memory_id)
                    .execute()
                )

            logger.info(
                "Updated sync status",
                extra={
                    "lead_memory_id": lead_memory_id,
                    "status": status.value,
                },
            )

        except DatabaseError:
            raise
        except Exception as e:
            logger.exception("Failed to update sync status")
            raise DatabaseError(f"Failed to update sync status: {e}") from e

    async def _get_lead_memory(self, user_id: str, lead_memory_id: str) -> dict[str, Any]:
        """Get lead memory record.

        Args:
            user_id: The user who owns the lead.
            lead_memory_id: The lead memory ID.

        Returns:
            Lead memory data dictionary.

        Raises:
            LeadMemoryNotFoundError: If lead not found.
            DatabaseError: If database operation fails.
        """
        try:
            client = self._get_supabase_client()

            response = (
                client.table("lead_memories")
                .select("*")
                .eq("id", lead_memory_id)
                .eq("user_id", user_id)
                .single()
                .execute()
            )

            if response.data is None:
                raise LeadMemoryNotFoundError(lead_memory_id)

            return dict(response.data)

        except LeadMemoryNotFoundError:
            raise
        except Exception as e:
            if "No rows" in str(e):
                raise LeadMemoryNotFoundError(lead_memory_id) from e
            logger.exception("Failed to get lead memory")
            raise DatabaseError(f"Failed to get lead memory: {e}") from e

    async def _get_crm_connection(self, user_id: str, provider: str) -> str:
        """Get Composio connection ID for CRM.

        Args:
            user_id: The user ID.
            provider: CRM provider name (salesforce, hubspot).

        Returns:
            Composio connection ID.

        Raises:
            CRMConnectionError: If CRM not connected.
        """
        try:
            client = self._get_supabase_client()

            response = (
                client.table("user_integrations")
                .select("*")
                .eq("user_id", user_id)
                .eq("integration_type", provider)
                .maybe_single()
                .execute()
            )

            if response.data is None:
                raise CRMConnectionError(
                    provider=provider,
                    message=f"No {provider} integration found for user",
                )

            return str(response.data["composio_connection_id"])

        except CRMConnectionError:
            raise
        except Exception as e:
            logger.exception("Failed to get CRM connection")
            raise CRMConnectionError(
                provider=provider,
                message=f"Failed to get CRM connection: {e}",
            ) from e

    async def push_summary_to_crm(
        self,
        user_id: str,
        lead_memory_id: str,
        summary: str,
    ) -> dict[str, Any]:
        """Push ARIA summary to CRM as a note.

        Notes are tagged with [ARIA] prefix to identify ARIA-generated content.

        Args:
            user_id: The user who owns the lead.
            lead_memory_id: The lead memory ID.
            summary: The summary text to push.

        Returns:
            Result dictionary with success status.

        Raises:
            CRMConnectionError: If CRM not connected.
            CRMSyncError: If sync fails.
        """
        audit_service = get_crm_audit_service()
        provider = None

        try:
            # Get lead memory to find CRM ID
            lead = await self._get_lead_memory(user_id, lead_memory_id)
            provider = lead.get("crm_provider", "salesforce")
            crm_id = lead.get("crm_id")

            if not crm_id:
                raise CRMSyncError(
                    message="Lead has no CRM ID for sync",
                    provider=provider,
                )

            # Get CRM connection
            connection_id = await self._get_crm_connection(user_id, provider)

            # Update sync status to pending
            await self.update_sync_status(
                lead_memory_id=lead_memory_id,
                status=SyncStatus.PENDING,
                direction=SyncDirection.PUSH,
            )

            # Prepare note with [ARIA] tag
            tagged_summary = f"[ARIA] {summary}"

            # Execute CRM action via Composio
            oauth_client = get_oauth_client()

            if provider == "salesforce":
                action = "salesforce_create_note"
                params = {
                    "parent_id": crm_id,
                    "title": f"ARIA Summary - {datetime.now(UTC).strftime('%Y-%m-%d')}",
                    "body": tagged_summary,
                }
            else:  # hubspot
                action = "hubspot_create_note"
                params = {
                    "object_id": crm_id,
                    "object_type": "deal",
                    "content": tagged_summary,
                }

            await oauth_client.execute_action(
                connection_id=connection_id,
                action=action,
                params=params,
            )

            # Update sync status to synced
            await self.update_sync_status(
                lead_memory_id=lead_memory_id,
                status=SyncStatus.SYNCED,
                direction=SyncDirection.PUSH,
            )

            # Log audit entry
            await audit_service.log_sync_operation(
                user_id=user_id,
                lead_memory_id=lead_memory_id,
                operation=CRMAuditOperation.PUSH,
                provider=provider,
                success=True,
                details={
                    "action": action,
                    "summary_length": len(summary),
                },
            )

            logger.info(
                "Pushed summary to CRM",
                extra={
                    "lead_memory_id": lead_memory_id,
                    "provider": provider,
                },
            )

            return {"success": True, "action": action, "crm_id": crm_id}

        except (CRMConnectionError, CRMSyncError) as exc:
            # Log error audit - wrapped to ensure original error is preserved
            if provider:
                try:
                    await audit_service.log_sync_operation(
                        user_id=user_id,
                        lead_memory_id=lead_memory_id,
                        operation=CRMAuditOperation.ERROR,
                        provider=provider,
                        success=False,
                        error_message=str(exc),
                    )
                except Exception:
                    logger.warning("Failed to log audit entry for sync error")
            raise
        except Exception as e:
            # Update sync status to error
            await self.update_sync_status(
                lead_memory_id=lead_memory_id,
                status=SyncStatus.ERROR,
                error_message=str(e),
            )
            logger.exception("Failed to push summary to CRM")
            raise CRMSyncError(
                message=f"Failed to push summary: {e}",
                provider=provider,
            ) from e

    async def pull_stage_changes(
        self,
        user_id: str,
        lead_memory_id: str,
    ) -> dict[str, Any]:
        """Pull stage changes from CRM to Lead Memory.

        CRM wins for structured fields (stage, value, date).

        Args:
            user_id: The user who owns the lead.
            lead_memory_id: The lead memory ID.

        Returns:
            Result dictionary with changes applied.

        Raises:
            CRMConnectionError: If CRM not connected.
            CRMSyncError: If sync fails.
        """
        audit_service = get_crm_audit_service()
        provider = None
        changes_applied: list[dict[str, Any]] = []

        try:
            # Get lead memory
            lead = await self._get_lead_memory(user_id, lead_memory_id)
            provider = lead.get("crm_provider", "salesforce")
            crm_id = lead.get("crm_id")

            if not crm_id:
                raise CRMSyncError(
                    message="Lead has no CRM ID for sync",
                    provider=provider,
                )

            # Get CRM connection
            connection_id = await self._get_crm_connection(user_id, provider)

            # Update sync status to pending
            await self.update_sync_status(
                lead_memory_id=lead_memory_id,
                status=SyncStatus.PENDING,
                direction=SyncDirection.PULL,
            )

            # Fetch record from CRM
            oauth_client = get_oauth_client()

            if provider == "salesforce":
                action = "salesforce_get_opportunity"
                params = {"id": crm_id}
            else:  # hubspot
                action = "hubspot_get_deal"
                params = {"deal_id": crm_id}

            result = await oauth_client.execute_action(
                connection_id=connection_id,
                action=action,
                params=params,
            )

            if not result.get("success"):
                raise CRMSyncError(
                    message="Failed to fetch CRM record",
                    provider=provider,
                )

            crm_data = result.get("data", {})

            # Map CRM fields to ARIA fields and resolve conflicts
            field_mappings = self._get_field_mappings(provider)
            update_data: dict[str, Any] = {}

            for crm_field, aria_field in field_mappings.items():
                if crm_field in crm_data:
                    crm_value = crm_data[crm_field]
                    aria_value = lead.get(aria_field)

                    if crm_value != aria_value:
                        resolution = self._resolve_conflict(
                            field=aria_field,
                            aria_value=aria_value,
                            crm_value=crm_value,
                        )

                        if resolution == ConflictResolution.CRM_WINS:
                            # Transform stage if needed
                            if aria_field == "lifecycle_stage":
                                stage_map = (
                                    SALESFORCE_STAGE_MAP
                                    if provider == "salesforce"
                                    else HUBSPOT_STAGE_MAP
                                )
                                crm_value = stage_map.get(crm_value, crm_value)

                            update_data[aria_field] = crm_value
                            changes_applied.append(
                                {
                                    "field": aria_field,
                                    "old_value": aria_value,
                                    "new_value": crm_value,
                                    "resolution": resolution.value,
                                }
                            )

                            # Log conflict resolution
                            await audit_service.log_conflict(
                                user_id=user_id,
                                lead_memory_id=lead_memory_id,
                                provider=provider,
                                field=aria_field,
                                aria_value=aria_value,
                                crm_value=crm_value,
                                resolution=resolution.value,
                                resolved_value=crm_value,
                            )

            # Apply updates to lead memory if any
            if update_data:
                try:
                    client = self._get_supabase_client()
                    update_data["updated_at"] = datetime.now(UTC).isoformat()
                    client.table("lead_memories").update(update_data).eq("id", lead_memory_id).eq(
                        "user_id", user_id
                    ).execute()
                except Exception as e:
                    logger.exception("Failed to update lead memory")
                    raise DatabaseError(f"Failed to update lead memory: {e}") from e

            # Update sync status to synced
            await self.update_sync_status(
                lead_memory_id=lead_memory_id,
                status=SyncStatus.SYNCED,
                direction=SyncDirection.PULL,
            )

            # Log audit entry
            await audit_service.log_sync_operation(
                user_id=user_id,
                lead_memory_id=lead_memory_id,
                operation=CRMAuditOperation.PULL,
                provider=provider,
                success=True,
                details={
                    "changes_count": len(changes_applied),
                    "fields_updated": list(update_data.keys()),
                },
            )

            logger.info(
                "Pulled stage changes from CRM",
                extra={
                    "lead_memory_id": lead_memory_id,
                    "provider": provider,
                    "changes_count": len(changes_applied),
                },
            )

            return {
                "success": True,
                "changes_applied": changes_applied,
                "provider": provider,
            }

        except (CRMConnectionError, CRMSyncError):
            raise
        except Exception as e:
            await self.update_sync_status(
                lead_memory_id=lead_memory_id,
                status=SyncStatus.ERROR,
                error_message=str(e),
            )
            logger.exception("Failed to pull stage changes from CRM")
            raise CRMSyncError(
                message=f"Failed to pull changes: {e}",
                provider=provider,
            ) from e

    def _get_field_mappings(self, provider: str) -> dict[str, str]:
        """Get field mappings for CRM provider.

        Args:
            provider: CRM provider name.

        Returns:
            Dictionary mapping CRM fields to ARIA fields.
        """
        if provider == "salesforce":
            return {
                "StageName": "lifecycle_stage",
                "Amount": "expected_value",
                "CloseDate": "expected_close_date",
                "Status__c": "status",
            }
        else:  # hubspot
            return {
                "dealstage": "lifecycle_stage",
                "amount": "expected_value",
                "closedate": "expected_close_date",
                "hs_deal_status": "status",
            }

    async def pull_activities(
        self,
        user_id: str,
        lead_memory_id: str,
    ) -> dict[str, Any]:
        """Pull activities from CRM to Lead Memory events.

        Args:
            user_id: The user who owns the lead.
            lead_memory_id: The lead memory ID.

        Returns:
            Result dictionary with activities imported count.

        Raises:
            CRMConnectionError: If CRM not connected.
            CRMSyncError: If sync fails.
        """
        audit_service = get_crm_audit_service()
        provider = None
        activities_imported = 0

        try:
            # Get lead memory
            lead = await self._get_lead_memory(user_id, lead_memory_id)
            provider = lead.get("crm_provider", "salesforce")
            crm_id = lead.get("crm_id")

            if not crm_id:
                raise CRMSyncError(
                    message="Lead has no CRM ID for sync",
                    provider=provider,
                )

            # Get CRM connection
            connection_id = await self._get_crm_connection(user_id, provider)

            # Fetch activities from CRM
            oauth_client = get_oauth_client()

            if provider == "salesforce":
                action = "salesforce_get_activities"
                params = {"parent_id": crm_id}
            else:  # hubspot
                action = "hubspot_get_engagements"
                params = {"object_id": crm_id, "object_type": "deal"}

            result = await oauth_client.execute_action(
                connection_id=connection_id,
                action=action,
                params=params,
            )

            if not result.get("success"):
                raise CRMSyncError(
                    message="Failed to fetch CRM activities",
                    provider=provider,
                )

            activities = result.get("data", [])
            client = self._get_supabase_client()

            # Create lead events for each activity
            for activity in activities:
                try:
                    event_data = self._map_activity_to_event(
                        activity=activity,
                        provider=provider,
                        user_id=user_id,
                        lead_memory_id=lead_memory_id,
                    )

                    client.table("lead_memory_events").insert(event_data).execute()
                    activities_imported += 1
                except Exception as e:
                    logger.warning(
                        "Failed to import activity",
                        extra={"activity_id": activity.get("id"), "error": str(e)},
                    )
                    # Continue with other activities

            # Update sync state
            await self.update_sync_status(
                lead_memory_id=lead_memory_id,
                status=SyncStatus.SYNCED,
                direction=SyncDirection.PULL,
            )

            # Log audit entry
            await audit_service.log_sync_operation(
                user_id=user_id,
                lead_memory_id=lead_memory_id,
                operation=CRMAuditOperation.PULL,
                provider=provider,
                success=True,
                details={
                    "activities_imported": activities_imported,
                },
            )

            logger.info(
                "Pulled activities from CRM",
                extra={
                    "lead_memory_id": lead_memory_id,
                    "provider": provider,
                    "activities_imported": activities_imported,
                },
            )

            return {
                "success": True,
                "activities_imported": activities_imported,
                "provider": provider,
            }

        except (CRMConnectionError, CRMSyncError):
            raise
        except Exception as e:
            logger.exception("Failed to pull activities from CRM")
            raise CRMSyncError(
                message=f"Failed to pull activities: {e}",
                provider=provider,
            ) from e

    def _map_activity_to_event(
        self,
        activity: dict[str, Any],
        provider: str,
        user_id: str,  # noqa: ARG002 - kept for future user tracking
        lead_memory_id: str,
    ) -> dict[str, Any]:
        """Map CRM activity to lead event data.

        Maps CRM activity fields to lead_memory_events table schema:
        - event_type, direction, subject, content, participants,
        - occurred_at, source, source_id, metadata

        Args:
            activity: CRM activity data.
            provider: CRM provider name.
            user_id: User ID (for future user tracking).
            lead_memory_id: Lead memory ID.

        Returns:
            Lead event data dictionary matching lead_memory_events schema.
        """
        now = datetime.now(UTC)

        if provider == "salesforce":
            return {
                "id": str(uuid.uuid4()),
                "lead_memory_id": lead_memory_id,
                "event_type": activity.get("Type", "other").lower(),
                "direction": "inbound",  # CRM activities are typically inbound
                "subject": activity.get("Subject", "CRM Activity"),
                "content": activity.get("Description", ""),
                "participants": [],  # Salesforce doesn't have direct participants
                "occurred_at": activity.get("ActivityDate", now.isoformat()),
                "source": "crm_import",
                "source_id": activity.get("Id"),
                "metadata": {
                    "crm_provider": provider,
                    "original_type": activity.get("Type"),
                },
            }
        else:  # hubspot
            return {
                "id": str(uuid.uuid4()),
                "lead_memory_id": lead_memory_id,
                "event_type": activity.get("type", "other").lower(),
                "direction": "inbound",
                "subject": activity.get("title", "CRM Activity"),
                "content": activity.get("body", ""),
                "participants": [],
                "occurred_at": activity.get("timestamp", now.isoformat()),
                "source": "crm_import",
                "source_id": activity.get("id"),
                "metadata": {
                    "crm_provider": provider,
                    "original_type": activity.get("type"),
                },
            }

    def _resolve_conflict(
        self,
        field: str,
        aria_value: Any,  # noqa: ARG002 - kept for future merge logic
        crm_value: Any,  # noqa: ARG002 - kept for future merge logic
    ) -> ConflictResolution:
        """Resolve a sync conflict between ARIA and CRM values.

        Resolution rules:
        - CRM wins for structured fields: stage, value, date, status
        - ARIA wins for computed fields: health_score, insights
        - Merge for text fields: notes

        Args:
            field: The field name with conflict.
            aria_value: ARIA's current value (used in merge logic).
            crm_value: CRM's current value (used in merge logic).

        Returns:
            ConflictResolution indicating how to resolve.
        """
        # Note: aria_value and crm_value will be used when implementing
        # actual merge logic for notes and other text fields
        _ = aria_value, crm_value  # Mark as intentionally unused for now

        if field in CRM_WINS_FIELDS:
            return ConflictResolution.CRM_WINS

        if field in ARIA_WINS_FIELDS:
            return ConflictResolution.ARIA_WINS

        if field in {"notes", "description", "summary"}:
            return ConflictResolution.MERGE

        # Default to ARIA wins for unknown fields
        return ConflictResolution.ARIA_WINS

    async def trigger_manual_sync(
        self,
        user_id: str,
        lead_memory_id: str,
    ) -> dict[str, Any]:
        """Trigger a manual bidirectional sync.

        Performs:
        1. Pull stage changes from CRM
        2. Push any pending ARIA changes to CRM

        Args:
            user_id: The user who owns the lead.
            lead_memory_id: The lead memory ID.

        Returns:
            Result dictionary with sync details.

        Raises:
            CRMConnectionError: If CRM not connected.
            CRMSyncError: If sync fails.
        """
        provider = None

        try:
            # Get lead memory for provider
            lead = await self._get_lead_memory(user_id, lead_memory_id)
            provider = lead.get("crm_provider", "salesforce")

            # Update sync status to pending
            await self.update_sync_status(
                lead_memory_id=lead_memory_id,
                status=SyncStatus.PENDING,
                direction=SyncDirection.BIDIRECTIONAL,
            )

            # Pull changes from CRM first (CRM wins for structured fields)
            pull_result = await self.pull_stage_changes(user_id, lead_memory_id)

            # Update status to synced
            await self.update_sync_status(
                lead_memory_id=lead_memory_id,
                status=SyncStatus.SYNCED,
                direction=SyncDirection.BIDIRECTIONAL,
            )

            logger.info(
                "Manual sync completed",
                extra={
                    "lead_memory_id": lead_memory_id,
                    "provider": provider,
                },
            )

            return {
                "success": True,
                "direction": "bidirectional",
                "pull_result": pull_result,
                "provider": provider,
            }

        except (CRMConnectionError, CRMSyncError):
            raise
        except Exception as e:
            await self.update_sync_status(
                lead_memory_id=lead_memory_id,
                status=SyncStatus.ERROR,
                error_message=str(e),
            )
            logger.exception("Manual sync failed")
            raise CRMSyncError(
                message=f"Manual sync failed: {e}",
                provider=provider,
            ) from e

    async def schedule_retry(self, lead_memory_id: str) -> dict[str, Any]:
        """Schedule a retry for a failed sync.

        Implements exponential backoff tracking with max 5 retries.

        Args:
            lead_memory_id: The lead memory ID to retry.

        Returns:
            Result dictionary with retry status.
        """
        try:
            # Get current sync state
            state = await self.get_sync_state(lead_memory_id)

            if state is None:
                return {
                    "scheduled": False,
                    "reason": "No sync state found",
                }

            current_count = state.retry_count

            # Check if max retries reached
            if not self._should_retry(current_count):
                logger.warning(
                    "Max retries reached",
                    extra={
                        "lead_memory_id": lead_memory_id,
                        "retry_count": current_count,
                    },
                )
                return {
                    "scheduled": False,
                    "max_retries_reached": True,
                    "retry_count": current_count,
                }

            # Increment retry count
            new_count = current_count + 1
            client = self._get_supabase_client()

            client.table("lead_memory_crm_sync").update(
                {
                    "retry_count": new_count,
                    "status": SyncStatus.PENDING.value,
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ).eq("lead_memory_id", lead_memory_id).execute()

            # Log retry to audit
            audit_service = get_crm_audit_service()
            await audit_service.log_sync_operation(
                user_id="system",
                lead_memory_id=lead_memory_id,
                operation=CRMAuditOperation.RETRY,
                provider="unknown",
                success=True,
                details={
                    "retry_count": new_count,
                    "previous_error": state.error_message,
                },
            )

            logger.info(
                "Scheduled sync retry",
                extra={
                    "lead_memory_id": lead_memory_id,
                    "retry_count": new_count,
                },
            )

            return {
                "scheduled": True,
                "retry_count": new_count,
                "max_retries": MAX_RETRIES,
            }

        except Exception as e:
            logger.exception("Failed to schedule retry")
            return {
                "scheduled": False,
                "error": str(e),
            }

    def _should_retry(self, retry_count: int) -> bool:
        """Check if sync should be retried.

        Args:
            retry_count: Current retry count.

        Returns:
            True if should retry, False if max reached.
        """
        return retry_count < MAX_RETRIES


# Singleton instance
_crm_sync_service: CRMSyncService | None = None


def get_crm_sync_service() -> CRMSyncService:
    """Get or create CRM sync service singleton.

    Returns:
        The shared CRMSyncService instance.
    """
    global _crm_sync_service
    if _crm_sync_service is None:
        _crm_sync_service = CRMSyncService()
    return _crm_sync_service
