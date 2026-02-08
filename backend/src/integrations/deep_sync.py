"""Deep sync service for bi-directional CRM and calendar synchronization.

This module implements the core sync service that pulls data from external
systems (CRM, Calendar) into ARIA's memory systems and pushes ARIA insights
back to external systems.

Key features:
- CRM Pull: Import opportunities, contacts, and activities from Salesforce/HubSpot
- Calendar Pull: Import calendar events and create pre-meeting research tasks
- Memory Integration: Store CRM data in Lead Memory, Semantic Memory, and Episodic Memory
- Sync State Tracking: Track sync status and schedule recurring syncs
- Error Handling: Graceful error handling with detailed logging

Note: Imports are done lazily to avoid circular import issues.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

# Use TYPE_CHECKING to avoid circular imports during type checking
if TYPE_CHECKING:
    from src.integrations.deep_sync_domain import (
        CalendarEvent,
        CRMEntity,
        PushQueueItem,
        SyncConfig,
        SyncResult,
        SyncStatus,
    )
    from src.integrations.domain import IntegrationType

logger = logging.getLogger(__name__)


class DeepSyncService:
    """Service for deep sync between ARIA and external integrations.

    Handles pulling data from CRM and Calendar systems into ARIA's memory
    systems, and pushing ARIA insights back to external systems.
    """

    def __init__(self, config: "SyncConfig | None" = None) -> None:
        """Initialize the deep sync service.

        Args:
            config: Optional sync configuration. Uses defaults if not provided.
        """
        # Lazy imports to avoid circular dependency
        from src.db.supabase import SupabaseClient
        from src.integrations.deep_sync_domain import SyncConfig
        from src.integrations.oauth import get_oauth_client
        from src.memory.lead_memory import LeadMemoryService

        self.config = config or SyncConfig()
        self.supabase = SupabaseClient
        self.integration_service = get_oauth_client()
        self.lead_memory_service = LeadMemoryService()

    async def sync_crm_to_aria(
        self,
        user_id: str,
        integration_type: "IntegrationType",
    ) -> "SyncResult":
        """Sync CRM data to ARIA memory systems.

        Main entry point for CRM pull sync. Fetches opportunities, contacts,
        and activities from the CRM and stores them in ARIA's memory systems.

        Args:
            user_id: The user's ID.
            integration_type: The integration type (SALESFORCE or HUBSPOT).

        Returns:
            SyncResult with metrics and status.

        Raises:
            CRMSyncError: If sync validation or execution fails.
        """
        from src.core.exceptions import CRMSyncError
        from src.integrations.deep_sync_domain import (
            SyncDirection,
            SyncResult,
            SyncStatus,
        )
        from src.integrations.domain import IntegrationType

        started_at = datetime.now(UTC)

        # Validate integration type
        if integration_type not in (IntegrationType.SALESFORCE, IntegrationType.HUBSPOT):
            raise CRMSyncError(
                message=f"Unsupported integration type for CRM sync: {integration_type.value}",
                provider=integration_type.value,
            )

        # Get integration connection
        client = self.supabase.get_client()
        integration_response = (
            client.table("user_integrations")
            .select("*")
            .eq("user_id", user_id)
            .eq("integration_type", integration_type.value)
            .maybe_single()
            .execute()
        )

        if not integration_response.data:
            raise CRMSyncError(
                message=f"No active {integration_type.value} integration found for user",
                provider=integration_type.value,
            )

        integration = integration_response.data
        connection_id = integration.get("composio_connection_id")

        if not connection_id:
            raise CRMSyncError(
                message=f"No connection ID found for {integration_type.value} integration",
                provider=integration_type.value,
            )

        # Initialize sync result
        total_processed = 0
        total_succeeded = 0
        total_failed = 0
        all_memory_entries = []
        all_errors: dict[str, Any] = {}

        try:
            # Pull opportunities
            logger.info(
                "Pulling opportunities from CRM",
                extra={"user_id": user_id, "integration_type": integration_type.value},
            )
            opp_result = await self._pull_opportunities(
                user_id=user_id,
                integration_type=integration_type,
                connection_id=connection_id,
            )
            total_processed += opp_result["processed"]
            total_succeeded += opp_result["succeeded"]
            total_failed += opp_result["failed"]
            all_memory_entries.extend(opp_result["memory_entries"])
            all_errors["opportunities"] = opp_result["errors"]

            # Pull contacts
            logger.info(
                "Pulling contacts from CRM",
                extra={"user_id": user_id, "integration_type": integration_type.value},
            )
            contact_result = await self._pull_contacts(
                user_id=user_id,
                integration_type=integration_type,
                connection_id=connection_id,
            )
            total_processed += contact_result["processed"]
            total_succeeded += contact_result["succeeded"]
            total_failed += contact_result["failed"]
            all_memory_entries.extend(contact_result["memory_entries"])
            all_errors["contacts"] = contact_result["errors"]

            # Pull activities
            logger.info(
                "Pulling activities from CRM",
                extra={"user_id": user_id, "integration_type": integration_type.value},
            )
            activity_result = await self._pull_activities(
                user_id=user_id,
                integration_type=integration_type,
                connection_id=connection_id,
            )
            total_processed += activity_result["processed"]
            total_succeeded += activity_result["succeeded"]
            total_failed += activity_result["failed"]
            all_memory_entries.extend(activity_result["memory_entries"])
            all_errors["activities"] = activity_result["errors"]

            # Determine sync status
            if total_failed == 0:
                sync_status = SyncStatus.SUCCESS
            elif total_succeeded > 0:
                sync_status = SyncStatus.PARTIAL
            else:
                sync_status = SyncStatus.FAILED

            # Update sync state
            next_sync_at = datetime.now(UTC) + timedelta(minutes=self.config.sync_interval_minutes)
            await self._update_sync_state(
                user_id=user_id,
                integration_type=integration_type,
                status=sync_status,
                next_sync_at=next_sync_at,
                error_message=None
                if sync_status == SyncStatus.SUCCESS
                else "Partial sync completed",
            )

            # Log sync operation
            await self._log_sync(
                user_id=user_id,
                integration_type=integration_type,
                sync_type="pull",
                status=sync_status,
                records_processed=total_processed,
                records_succeeded=total_succeeded,
                records_failed=total_failed,
                error_details=all_errors if sync_status != SyncStatus.SUCCESS else None,
            )

            completed_at = datetime.now(UTC)

            logger.info(
                "CRM sync completed",
                extra={
                    "user_id": user_id,
                    "integration_type": integration_type.value,
                    "processed": total_processed,
                    "succeeded": total_succeeded,
                    "failed": total_failed,
                    "status": sync_status.value,
                },
            )

            return SyncResult(
                direction=SyncDirection.PULL,
                integration_type=integration_type,
                status=sync_status,
                records_processed=total_processed,
                records_succeeded=total_succeeded,
                records_failed=total_failed,
                started_at=started_at,
                completed_at=completed_at,
                error_details=all_errors if sync_status != SyncStatus.SUCCESS else None,
                memory_entries_created=len(all_memory_entries),
            )

        except Exception as e:
            from src.core.exceptions import CRMSyncError

            logger.exception(
                "CRM sync failed",
                extra={"user_id": user_id, "integration_type": integration_type.value},
            )
            await self._update_sync_state(
                user_id=user_id,
                integration_type=integration_type,
                status=SyncStatus.FAILED,
                next_sync_at=None,
                error_message=str(e),
            )
            await self._log_sync(
                user_id=user_id,
                integration_type=integration_type,
                sync_type="pull",
                status=SyncStatus.FAILED,
                records_processed=total_processed,
                records_succeeded=total_succeeded,
                records_failed=total_failed,
                error_details={"error": str(e)},
            )
            raise CRMSyncError(
                message=f"CRM sync failed: {e}",
                provider=integration_type.value,
            ) from e

    async def _pull_opportunities(
        self,
        user_id: str,
        integration_type: "IntegrationType",
        connection_id: str,
    ) -> dict[str, Any]:
        """Pull opportunities from CRM.

        Fetches opportunities from Salesforce or HubSpot and creates
        Lead Memory entries for each one.

        Args:
            user_id: The user's ID.
            integration_type: The CRM integration type.
            connection_id: The Composio connection ID.

        Returns:
            Dictionary with processed, succeeded, failed counts and details.
        """
        from src.integrations.domain import IntegrationType

        processed = 0
        succeeded = 0
        failed = 0
        memory_entries: list[str] = []
        errors: list[dict[str, Any]] = []

        try:
            # Determine the action name based on integration type
            if integration_type == IntegrationType.SALESFORCE:
                action = "salesforce_get_opportunities"
            else:  # HUBSPOT
                action = "hubspot_get_deals"

            # Execute Composio action
            result = await self.integration_service.execute_action(
                connection_id=connection_id,
                action=action,
                params={},
            )

            # Extract opportunities from response
            opportunities = result.get("data", [])
            if not isinstance(opportunities, list):
                opportunities = []

            for opp_data in opportunities:
                processed += 1
                try:
                    # Create CRM entity
                    entity = self._map_opportunity_to_crm_entity(
                        data=opp_data,
                        integration_type=integration_type,
                    )

                    # Create lead memory from CRM entity
                    lead_id = await self._create_lead_memory_from_crm(
                        user_id=user_id,
                        entity=entity,
                    )

                    if lead_id:
                        succeeded += 1
                        memory_entries.append(lead_id)
                    else:
                        failed += 1
                        errors.append(
                            {
                                "entity_id": entity.external_id,
                                "error": "Failed to create lead memory",
                            }
                        )

                except Exception as e:
                    failed += 1
                    logger.warning(
                        "Failed to process opportunity",
                        extra={"opportunity": opp_data, "error": str(e)},
                    )
                    errors.append(
                        {
                            "opportunity": opp_data.get("Id") or opp_data.get("id"),
                            "error": str(e),
                        }
                    )

        except Exception as e:
            logger.exception("Failed to pull opportunities")
            errors.append({"error": f"Failed to fetch opportunities: {e}"})

        return {
            "processed": processed,
            "succeeded": succeeded,
            "failed": failed,
            "memory_entries": memory_entries,
            "errors": errors,
        }

    def _map_opportunity_to_crm_entity(
        self,
        data: dict[str, Any],
        integration_type: "IntegrationType",
    ) -> "CRMEntity":
        """Map opportunity data from CRM to CRMEntity.

        Args:
            data: Raw opportunity data from CRM.
            integration_type: The CRM integration type.

        Returns:
            CRMEntity representation of the opportunity.
        """
        from src.integrations.deep_sync_domain import CRMEntity
        from src.integrations.domain import IntegrationType

        if integration_type == IntegrationType.SALESFORCE:
            external_id = data.get("Id") or data.get("id", "")
            name = data.get("Name") or data.get("name", "")
        else:  # HUBSPOT
            external_id = data.get("dealId") or data.get("id", "")
            name = data.get("dealname") or data.get("properties", {}).get("dealname", "")

        return CRMEntity(
            entity_type="opportunity",
            external_id=external_id,
            name=name,
            data=data,
            confidence=0.85,  # CRM data confidence per source hierarchy
        )

    async def _create_lead_memory_from_crm(
        self,
        user_id: str,
        entity: "CRMEntity",
    ) -> str | None:
        """Create Lead Memory entry from CRM opportunity.

        Maps CRM fields to ARIA's Lead Memory model and creates
        a new lead entry.

        Args:
            user_id: The user's ID.
            entity: The CRM entity representing an opportunity.

        Returns:
            The created lead ID, or None if creation failed.
        """
        from datetime import date

        from src.core.exceptions import LeadMemoryError
        from src.memory.lead_memory import TriggerType

        try:
            data = entity.data
            company_name = ""
            stage = ""
            value = None
            close_date = None

            # Map Salesforce fields
            if "Account" in data or "account" in data:
                account = data.get("Account") or data.get("account", {})
                if isinstance(account, dict):
                    company_name = account.get("Name") or account.get("name", "")
                else:
                    company_name = str(account) if account else ""

            stage = data.get("StageName") or data.get("stageName") or data.get("stage", "")

            amount = data.get("Amount") or data.get("amount")
            if amount:
                try:
                    value = Decimal(str(amount))
                except (ValueError, TypeError):
                    value = None

            close_date_str = data.get("CloseDate") or data.get("closeDate")
            if close_date_str:
                try:
                    if isinstance(close_date_str, str):
                        close_date = date.fromisoformat(
                            close_date_str.replace("Z", "").split("T")[0]
                        )
                    elif isinstance(close_date_str, date):
                        close_date = close_date_str
                except (ValueError, TypeError):
                    close_date = None

            # Determine CRM provider from entity type or data
            crm_provider = "salesforce" if "Id" in data or "StageName" in data else "hubspot"

            # Create lead memory
            lead = await self.lead_memory_service.create(
                user_id=user_id,
                company_name=company_name or entity.name,
                trigger=TriggerType.CRM_IMPORT,
                crm_id=entity.external_id,
                crm_provider=crm_provider,
                expected_close_date=close_date,
                expected_value=value,
                metadata={
                    "crm_stage": stage,
                    "crm_raw_data": data,
                },
            )

            logger.info(
                "Created lead memory from CRM opportunity",
                extra={
                    "user_id": user_id,
                    "lead_id": lead.id,
                    "crm_id": entity.external_id,
                },
            )

            return lead.id

        except (LeadMemoryError, Exception) as e:
            logger.warning(
                "Failed to create lead memory from CRM entity",
                extra={"user_id": user_id, "entity_id": entity.external_id, "error": str(e)},
            )
            return None

    async def _pull_contacts(
        self,
        user_id: str,
        integration_type: "IntegrationType",
        connection_id: str,
    ) -> dict[str, Any]:
        """Pull contacts from CRM.

        Fetches contacts from Salesforce or HubSpot and stores
        them as semantic memory facts.

        Args:
            user_id: The user's ID.
            integration_type: The CRM integration type.
            connection_id: The Composio connection ID.

        Returns:
            Dictionary with processed, succeeded, failed counts and details.
        """
        from src.integrations.domain import IntegrationType

        processed = 0
        succeeded = 0
        failed = 0
        memory_entries: list[str] = []
        errors: list[dict[str, Any]] = []

        try:
            # Determine the action name based on integration type
            if integration_type == IntegrationType.SALESFORCE:
                action = "salesforce_get_contacts"
            else:  # HUBSPOT
                action = "hubspot_get_contacts"

            # Execute Composio action
            result = await self.integration_service.execute_action(
                connection_id=connection_id,
                action=action,
                params={},
            )

            # Extract contacts from response
            contacts = result.get("data", [])
            if not isinstance(contacts, list):
                contacts = []

            for contact_data in contacts:
                processed += 1
                try:
                    # Store contact in semantic memory
                    memory_id = await self._store_contact_in_semantic_memory(
                        user_id=user_id,
                        entity=self._map_contact_to_crm_entity(
                            data=contact_data,
                            integration_type=integration_type,
                        ),
                    )

                    if memory_id:
                        succeeded += 1
                        memory_entries.append(memory_id)
                    else:
                        failed += 1
                        errors.append(
                            {
                                "contact_id": contact_data.get("Id") or contact_data.get("id"),
                                "error": "Failed to store contact in semantic memory",
                            }
                        )

                except Exception as e:
                    failed += 1
                    logger.warning(
                        "Failed to process contact",
                        extra={"contact": contact_data, "error": str(e)},
                    )
                    errors.append(
                        {
                            "contact_id": contact_data.get("Id") or contact_data.get("id"),
                            "error": str(e),
                        }
                    )

        except Exception as e:
            logger.exception("Failed to pull contacts")
            errors.append({"error": f"Failed to fetch contacts: {e}"})

        return {
            "processed": processed,
            "succeeded": succeeded,
            "failed": failed,
            "memory_entries": memory_entries,
            "errors": errors,
        }

    def _map_contact_to_crm_entity(
        self,
        data: dict[str, Any],
        integration_type: "IntegrationType",
    ) -> "CRMEntity":
        """Map contact data from CRM to CRMEntity.

        Args:
            data: Raw contact data from CRM.
            integration_type: The CRM integration type.

        Returns:
            CRMEntity representation of the contact.
        """
        from src.integrations.deep_sync_domain import CRMEntity
        from src.integrations.domain import IntegrationType

        if integration_type == IntegrationType.SALESFORCE:
            external_id = data.get("Id") or data.get("id", "")
            name = data.get("Name") or data.get("name", "")
        else:  # HUBSPOT
            external_id = data.get("contactId") or data.get("id", "")
            props = data.get("properties", {})
            name = props.get("firstname", "") + " " + props.get("lastname", "")
            name = name.strip()

        return CRMEntity(
            entity_type="contact",
            external_id=external_id,
            name=name,
            data=data,
            confidence=0.85,
        )

    async def _store_contact_in_semantic_memory(
        self,
        user_id: str,
        entity: "CRMEntity",
    ) -> str | None:
        """Store CRM contact as semantic memory fact.

        Creates a semantic memory entry for the contact with confidence 0.85
        and source "crm".

        Args:
            user_id: The user's ID.
            entity: The CRM entity representing a contact.

        Returns:
            The created memory ID, or None if storage failed.
        """
        try:
            data = entity.data
            name = ""
            title = ""
            company = ""
            email = ""

            # Map Salesforce fields
            if "FirstName" in data or "LastName" in data:
                first = data.get("FirstName", "")
                last = data.get("LastName", "")
                name = f"{first} {last}".strip()
                title = data.get("Title", "")
                account = data.get("Account", {})
                if isinstance(account, dict):
                    company = account.get("Name", "")
                email = data.get("Email", "")
            else:  # HubSpot
                props = data.get("properties", {})
                name = entity.name
                title = props.get("jobtitle", "")
                company = props.get("company", "")
                email = props.get("email", "")

            # Format semantic memory content
            content_parts = [f"Contact: {name}"]
            if title:
                content_parts.append(f"({title})")
            if company:
                content_parts.append(f"at {company}")
            if email:
                content_parts.append(f"- Email: {email}")

            content = " ".join(content_parts)

            # Insert into semantic memory
            client = self.supabase.get_client()
            memory_id = str(uuid.uuid4())
            now = datetime.now(UTC)

            response = (
                client.table("memory_semantic")
                .insert(
                    {
                        "id": memory_id,
                        "user_id": user_id,
                        "fact": content,
                        "confidence": 0.85,
                        "source": "crm",
                        "created_at": now.isoformat(),
                        "metadata": {
                            "crm_entity_id": entity.external_id,
                            "crm_entity_type": "contact",
                            "raw_data": data,
                        },
                    }
                )
                .execute()
            )

            if response.data:
                logger.info(
                    "Stored contact in semantic memory",
                    extra={"user_id": user_id, "memory_id": memory_id, "contact": name},
                )
                return memory_id

            return None

        except Exception as e:
            logger.warning(
                "Failed to store contact in semantic memory",
                extra={"user_id": user_id, "entity_id": entity.external_id, "error": str(e)},
            )
            return None

    async def _pull_activities(
        self,
        user_id: str,
        integration_type: "IntegrationType",
        connection_id: str,
    ) -> dict[str, Any]:
        """Pull activities from CRM.

        Fetches recent activities from Salesforce or HubSpot and stores
        them as episodic memories.

        Args:
            user_id: The user's ID.
            integration_type: The CRM integration type.
            connection_id: The Composio connection ID.

        Returns:
            Dictionary with processed, succeeded, failed counts and details.
        """
        from src.integrations.domain import IntegrationType

        processed = 0
        succeeded = 0
        failed = 0
        memory_entries: list[str] = []
        errors: list[dict[str, Any]] = []

        try:
            # Determine the action name based on integration type
            if integration_type == IntegrationType.SALESFORCE:
                action = "salesforce_get_activities"
            else:  # HUBSPOT
                action = "hubspot_get_engagements"

            # Execute Composio action with limit
            result = await self.integration_service.execute_action(
                connection_id=connection_id,
                action=action,
                params={"limit": 100},
            )

            # Extract activities from response
            activities = result.get("data", [])
            if not isinstance(activities, list):
                activities = []

            for activity_data in activities[:100]:  # Limit to 100 most recent
                processed += 1
                try:
                    # Store activity as episodic memory
                    memory_id = await self._store_activity_as_episodic_memory(
                        user_id=user_id,
                        entity=self._map_activity_to_crm_entity(
                            data=activity_data,
                            integration_type=integration_type,
                        ),
                    )

                    if memory_id:
                        succeeded += 1
                        memory_entries.append(memory_id)
                    else:
                        failed += 1
                        errors.append(
                            {
                                "activity_id": activity_data.get("Id") or activity_data.get("id"),
                                "error": "Failed to store activity as episodic memory",
                            }
                        )

                except Exception as e:
                    failed += 1
                    logger.warning(
                        "Failed to process activity",
                        extra={"activity": activity_data, "error": str(e)},
                    )
                    errors.append(
                        {
                            "activity_id": activity_data.get("Id") or activity_data.get("id"),
                            "error": str(e),
                        }
                    )

        except Exception as e:
            logger.exception("Failed to pull activities")
            errors.append({"error": f"Failed to fetch activities: {e}"})

        return {
            "processed": processed,
            "succeeded": succeeded,
            "failed": failed,
            "memory_entries": memory_entries,
            "errors": errors,
        }

    def _map_activity_to_crm_entity(
        self,
        data: dict[str, Any],
        integration_type: "IntegrationType",
    ) -> "CRMEntity":
        """Map activity data from CRM to CRMEntity.

        Args:
            data: Raw activity data from CRM.
            integration_type: The CRM integration type.

        Returns:
            CRMEntity representation of the activity.
        """
        from src.integrations.deep_sync_domain import CRMEntity
        from src.integrations.domain import IntegrationType

        if integration_type == IntegrationType.SALESFORCE:
            external_id = data.get("Id") or data.get("id", "")
            name = data.get("Subject") or data.get("subject", "")
        else:  # HUBSPOT
            external_id = data.get("engagementId") or data.get("id", "")
            props = data.get("properties", {})
            name = props.get("hs_payload", {}).get("type", "")

        return CRMEntity(
            entity_type="activity",
            external_id=external_id,
            name=name,
            data=data,
            confidence=0.85,
        )

    async def _store_activity_as_episodic_memory(
        self,
        user_id: str,
        entity: "CRMEntity",
    ) -> str | None:
        """Store CRM activity as episodic memory.

        Creates an episodic memory entry for the activity with
        parsed timestamp from the CRM data.

        Args:
            user_id: The user's ID.
            entity: The CRM entity representing an activity.

        Returns:
            The created memory ID, or None if storage failed.
        """
        from datetime import date

        try:
            data = entity.data
            subject = ""
            account = ""
            description = ""
            occurred_at = datetime.now(UTC)

            # Map Salesforce fields
            if "Subject" in data or "subject" in data:
                subject = data.get("Subject") or data.get("subject", "")
                account_obj = data.get("Account") or data.get("account", {})
                if isinstance(account_obj, dict):
                    account = account_obj.get("Name", "")
                description = data.get("Description") or data.get("description", "")

                activity_date = data.get("ActivityDate") or data.get("activityDate")
                if activity_date:
                    try:
                        if isinstance(activity_date, str):
                            parsed_date = date.fromisoformat(activity_date.replace("Z", ""))
                            occurred_at = datetime.combine(
                                parsed_date, datetime.min.time()
                            ).replace(tzinfo=UTC)
                    except (ValueError, TypeError):
                        pass
            else:  # HubSpot
                props = data.get("properties", {})
                subject = entity.name or "CRM Activity"
                account = props.get("hs_object_source", {}).get("title", "")
                description = props.get("hs_body_preview", "")

                timestamp = props.get("hs_timestamp")
                if timestamp:
                    from contextlib import suppress

                    with suppress(ValueError, TypeError):
                        occurred_at = datetime.fromtimestamp(int(timestamp) / 1000, tz=UTC)

            # Format episodic memory content
            content = f"CRM Activity: {subject}"
            if account:
                content += f" with {account}"
            if description:
                content += f" - {description[:200]}"  # Limit description length

            # Insert into episodic memories
            client = self.supabase.get_client()
            memory_id = str(uuid.uuid4())
            now = datetime.now(UTC)

            response = (
                client.table("episodic_memories")
                .insert(
                    {
                        "id": memory_id,
                        "user_id": user_id,
                        "content": content,
                        "occurred_at": occurred_at.isoformat(),
                        "created_at": now.isoformat(),
                        "metadata": {
                            "crm_entity_id": entity.external_id,
                            "crm_entity_type": "activity",
                            "raw_data": data,
                        },
                    }
                )
                .execute()
            )

            if response.data:
                logger.info(
                    "Stored activity as episodic memory",
                    extra={"user_id": user_id, "memory_id": memory_id, "subject": subject},
                )
                return memory_id

            return None

        except Exception as e:
            logger.warning(
                "Failed to store activity as episodic memory",
                extra={"user_id": user_id, "entity_id": entity.external_id, "error": str(e)},
            )
            return None

    async def _update_sync_state(
        self,
        user_id: str,
        integration_type: "IntegrationType",
        status: "SyncStatus",
        next_sync_at: datetime | None,
        error_message: str | None = None,
    ) -> None:
        """Update sync state in database.

        Upserts into integration_sync_state table with current
        sync status and next scheduled sync time.

        Args:
            user_id: The user's ID.
            integration_type: The integration type.
            status: The sync status.
            next_sync_at: When the next sync should run.
            error_message: Optional error message if sync failed.
        """
        try:
            client = self.supabase.get_client()
            now = datetime.now(UTC)

            # Check if state exists
            existing = (
                client.table("integration_sync_state")
                .select("*")
                .eq("user_id", user_id)
                .eq("integration_type", integration_type.value)
                .maybe_single()
                .execute()
            )

            data = {
                "user_id": user_id,
                "integration_type": integration_type.value,
                "last_sync_at": now.isoformat(),
                "last_sync_status": status.value,
                "last_sync_error": error_message,
                "next_sync_at": next_sync_at.isoformat() if next_sync_at else None,
                "updated_at": now.isoformat(),
            }

            if existing.data:
                # Update existing
                client.table("integration_sync_state").update(data).eq("user_id", user_id).eq(
                    "integration_type", integration_type.value
                ).execute()
            else:
                # Insert new
                data["id"] = str(uuid.uuid4())
                data["created_at"] = now.isoformat()
                client.table("integration_sync_state").insert(data).execute()

            logger.info(
                "Updated sync state",
                extra={
                    "user_id": user_id,
                    "integration_type": integration_type.value,
                    "status": status.value,
                },
            )

        except Exception as e:
            logger.warning(
                "Failed to update sync state",
                extra={
                    "user_id": user_id,
                    "integration_type": integration_type.value,
                    "error": str(e),
                },
            )

    async def _log_sync(
        self,
        user_id: str,
        integration_type: "IntegrationType",
        sync_type: str,
        status: "SyncStatus",
        records_processed: int,
        records_succeeded: int,
        records_failed: int,
        error_details: dict[str, Any] | None = None,
    ) -> None:
        """Log sync operation to database.

        Inserts a record into integration_sync_log table for
        audit and troubleshooting.

        Args:
            user_id: The user's ID.
            integration_type: The integration type.
            sync_type: Type of sync ('pull' or 'push').
            status: The sync status.
            records_processed: Number of records processed.
            records_succeeded: Number of successful records.
            records_failed: Number of failed records.
            error_details: Optional error details.
        """
        try:
            client = self.supabase.get_client()
            now = datetime.now(UTC)

            log_entry = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "integration_type": integration_type.value,
                "sync_type": sync_type,
                "status": status.value,
                "records_processed": records_processed,
                "records_succeeded": records_succeeded,
                "records_failed": records_failed,
                "error_details": error_details,
                "completed_at": now.isoformat(),
                "created_at": now.isoformat(),
            }

            client.table("integration_sync_log").insert(log_entry).execute()

            logger.info(
                "Logged sync operation",
                extra={
                    "user_id": user_id,
                    "integration_type": integration_type.value,
                    "sync_type": sync_type,
                    "status": status.value,
                },
            )

        except Exception as e:
            # Don't fail the sync if logging fails
            logger.warning(
                "Failed to log sync operation",
                extra={
                    "user_id": user_id,
                    "integration_type": integration_type.value,
                    "error": str(e),
                },
            )

    async def sync_calendar(
        self,
        user_id: str,
        integration_type: "IntegrationType",
    ) -> "SyncResult":
        """Sync calendar events to ARIA memory systems.

        Main entry point for calendar pull sync. Fetches events from
        Google Calendar or Outlook and creates prospective memory
        entries for external meetings (pre-meeting research tasks).

        Args:
            user_id: The user's ID.
            integration_type: The integration type (GOOGLE_CALENDAR or OUTLOOK).

        Returns:
            SyncResult with metrics and status.

        Raises:
            CRMSyncError: If sync validation or execution fails.
        """
        from src.core.exceptions import CRMSyncError
        from src.integrations.deep_sync_domain import (
            SyncDirection,
            SyncResult,
            SyncStatus,
        )
        from src.integrations.domain import IntegrationType

        started_at = datetime.now(UTC)

        # Validate integration type
        if integration_type not in (IntegrationType.GOOGLE_CALENDAR, IntegrationType.OUTLOOK):
            raise CRMSyncError(
                message=f"Unsupported integration type for calendar sync: {integration_type.value}",
                provider=integration_type.value,
            )

        # Get integration connection
        client = self.supabase.get_client()
        integration_response = (
            client.table("user_integrations")
            .select("*")
            .eq("user_id", user_id)
            .eq("integration_type", integration_type.value)
            .maybe_single()
            .execute()
        )

        if not integration_response.data:
            raise CRMSyncError(
                message=f"No active {integration_type.value} integration found for user",
                provider=integration_type.value,
            )

        integration = integration_response.data
        connection_id = integration.get("composio_connection_id")

        if not connection_id:
            raise CRMSyncError(
                message=f"No connection ID found for {integration_type.value} integration",
                provider=integration_type.value,
            )

        # Initialize sync result
        total_processed = 0
        total_succeeded = 0
        total_failed = 0
        all_errors: dict[str, Any] = {}

        try:
            # Pull calendar events
            logger.info(
                "Pulling calendar events",
                extra={"user_id": user_id, "integration_type": integration_type.value},
            )
            event_result = await self._pull_calendar_events(
                user_id=user_id,
                integration_type=integration_type,
                connection_id=connection_id,
            )
            total_processed += event_result["processed"]
            total_succeeded += event_result["succeeded"]
            total_failed += event_result["failed"]
            all_errors["events"] = event_result["errors"]

            # Determine sync status
            if total_failed == 0:
                sync_status = SyncStatus.SUCCESS
            elif total_succeeded > 0:
                sync_status = SyncStatus.PARTIAL
            else:
                sync_status = SyncStatus.FAILED

            # Update sync state
            next_sync_at = datetime.now(UTC) + timedelta(minutes=self.config.sync_interval_minutes)
            await self._update_sync_state(
                user_id=user_id,
                integration_type=integration_type,
                status=sync_status,
                next_sync_at=next_sync_at,
                error_message=None
                if sync_status == SyncStatus.SUCCESS
                else "Partial sync completed",
            )

            # Log sync operation
            await self._log_sync(
                user_id=user_id,
                integration_type=integration_type,
                sync_type="pull",
                status=sync_status,
                records_processed=total_processed,
                records_succeeded=total_succeeded,
                records_failed=total_failed,
                error_details=all_errors if sync_status != SyncStatus.SUCCESS else None,
            )

            completed_at = datetime.now(UTC)

            logger.info(
                "Calendar sync completed",
                extra={
                    "user_id": user_id,
                    "integration_type": integration_type.value,
                    "processed": total_processed,
                    "succeeded": total_succeeded,
                    "failed": total_failed,
                    "status": sync_status.value,
                },
            )

            return SyncResult(
                direction=SyncDirection.PULL,
                integration_type=integration_type,
                status=sync_status,
                records_processed=total_processed,
                records_succeeded=total_succeeded,
                records_failed=total_failed,
                started_at=started_at,
                completed_at=completed_at,
                error_details=all_errors if sync_status != SyncStatus.SUCCESS else None,
                memory_entries_created=event_result.get("research_tasks", 0),
            )

        except Exception as e:
            from src.core.exceptions import CRMSyncError

            logger.exception(
                "Calendar sync failed",
                extra={"user_id": user_id, "integration_type": integration_type.value},
            )
            await self._update_sync_state(
                user_id=user_id,
                integration_type=integration_type,
                status=SyncStatus.FAILED,
                next_sync_at=None,
                error_message=str(e),
            )
            await self._log_sync(
                user_id=user_id,
                integration_type=integration_type,
                sync_type="pull",
                status=SyncStatus.FAILED,
                records_processed=total_processed,
                records_succeeded=total_succeeded,
                records_failed=total_failed,
                error_details={"error": str(e)},
            )
            raise CRMSyncError(
                message=f"Calendar sync failed: {e}",
                provider=integration_type.value,
            ) from e

    async def _pull_calendar_events(
        self,
        user_id: str,
        integration_type: "IntegrationType",
        connection_id: str,
    ) -> dict[str, Any]:
        """Pull calendar events from external provider.

        Fetches events for the next 7 days and creates prospective memory
        entries for external meetings (pre-meeting research tasks).

        Args:
            user_id: The user's ID.
            integration_type: The calendar integration type.
            connection_id: The Composio connection ID.

        Returns:
            Dictionary with processed, succeeded, failed counts and details.
        """
        from src.integrations.domain import IntegrationType

        processed = 0
        succeeded = 0
        failed = 0
        research_tasks_created = 0
        errors: list[dict[str, Any]] = []

        try:
            # Calculate time range: now to 7 days from now
            now = datetime.now(UTC)
            time_max = now + timedelta(days=7)

            # Format time strings for API
            time_min_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            time_max_str = time_max.strftime("%Y-%m-%dT%H:%M:%SZ")

            # Determine the action and params based on integration type
            if integration_type == IntegrationType.GOOGLE_CALENDAR:
                action = "list_events"
                params = {
                    "timeMin": time_min_str,
                    "timeMax": time_max_str,
                }
            else:  # OUTLOOK
                action = "list_calendar_events"
                params = {
                    "startDateTime": time_min_str,
                    "endDateTime": time_max_str,
                }

            # Execute Composio action
            result = await self.integration_service.execute_action(
                connection_id=connection_id,
                action=action,
                params=params,
            )

            # Extract events from response
            events = result.get("data", [])
            if not isinstance(events, list):
                events = []

            for event_data in events:
                processed += 1
                try:
                    # Parse calendar event
                    event = self._parse_calendar_event(
                        event_data=event_data,
                        integration_type=integration_type,
                    )

                    # Create research task for external meetings
                    if event.is_external:
                        task_id = await self._create_meeting_research_task(
                            user_id=user_id,
                            event=event,
                        )
                        if task_id:
                            research_tasks_created += 1
                        else:
                            failed += 1
                            errors.append(
                                {
                                    "event_id": event.external_id,
                                    "error": "Failed to create research task",
                                }
                            )

                    succeeded += 1

                except Exception as e:
                    failed += 1
                    logger.warning(
                        "Failed to process calendar event",
                        extra={"event": event_data, "error": str(e)},
                    )
                    errors.append(
                        {
                            "event_id": event_data.get("id") or event_data.get("Id"),
                            "error": str(e),
                        }
                    )

        except Exception as e:
            logger.exception("Failed to pull calendar events")
            errors.append({"error": f"Failed to fetch events: {e}"})

        return {
            "processed": processed,
            "succeeded": succeeded,
            "failed": failed,
            "research_tasks": research_tasks_created,
            "errors": errors,
        }

    def _parse_calendar_event(
        self,
        event_data: dict[str, Any],
        integration_type: "IntegrationType",
    ) -> "CalendarEvent":
        """Parse calendar event data from external provider.

        Parses event data from Google Calendar or Outlook format into
        a CalendarEvent domain model.

        Args:
            event_data: Raw event data from calendar provider.
            integration_type: The calendar integration type.

        Returns:
            CalendarEvent representation of the event.
        """
        from src.integrations.deep_sync_domain import CalendarEvent
        from src.integrations.domain import IntegrationType

        if integration_type == IntegrationType.GOOGLE_CALENDAR:
            external_id = event_data.get("id", "")
            title = event_data.get("summary", "No Title")

            # Parse start/end times
            start_obj = event_data.get("start", {})
            end_obj = event_data.get("end", {})

            start_str = start_obj.get("dateTime") or start_obj.get("date", "")
            end_str = end_obj.get("dateTime") or end_obj.get("date", "")

            # Parse datetime strings, handling Z suffix
            start_time = self._parse_datetime_string(start_str)
            end_time = self._parse_datetime_string(end_str)

            # Extract attendees
            attendees_data = event_data.get("attendees", [])
            attendees = []
            for attendee in attendees_data:
                email = attendee.get("email", "")
                if email:
                    attendees.append(email)

            description = event_data.get("description")
            location = event_data.get("location")

        else:  # OUTLOOK
            external_id = event_data.get("id", "")
            title = event_data.get("subject", "No Title")

            # Parse start/end times
            start_str = event_data.get("start", {}).get("dateTime", "")
            end_str = event_data.get("end", {}).get("dateTime", "")

            start_time = self._parse_datetime_string(start_str)
            end_time = self._parse_datetime_string(end_str)

            # Extract attendees
            attendees_data = event_data.get("attendees", [])
            attendees = []
            for attendee in attendees_data:
                email_data = attendee.get("emailAddress", {})
                email = email_data.get("address", "") if email_data else ""
                if email:
                    attendees.append(email)

            description = event_data.get("bodyPreview")
            location = (
                event_data.get("location", {}).get("displayName")
                if event_data.get("location")
                else None
            )

        # Detect if event is external (has non-company attendees)
        # For now, use simplified @company.com check
        is_external = (
            any(not attendee.endswith("@company.com") for attendee in attendees)
            if attendees
            else False
        )

        return CalendarEvent(
            external_id=external_id,
            title=title,
            start_time=start_time,
            end_time=end_time,
            attendees=attendees,
            description=description,
            location=location,
            is_external=is_external,
            data=event_data,
        )

    def _parse_datetime_string(self, datetime_str: str) -> datetime:
        """Parse datetime string from calendar API.

        Handles ISO format strings with optional Z suffix.

        Args:
            datetime_str: The datetime string to parse.

        Returns:
            Parsed datetime with UTC timezone.
        """
        try:
            # Remove Z suffix if present and parse
            clean_str = datetime_str.replace("Z", "").replace("+00:00", "")
            parsed = datetime.fromisoformat(clean_str)
            # Ensure UTC timezone
            parsed = parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
            return parsed
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse datetime string: {datetime_str}, error: {e}")
            return datetime.now(UTC)

    async def _create_meeting_research_task(
        self,
        user_id: str,
        event: "CalendarEvent",
    ) -> str | None:
        """Create a prospective memory task for meeting research.

        Creates a pre-meeting research task triggered 24 hours before
        the external meeting.

        Args:
            user_id: The user's ID.
            event: The calendar event to create a task for.

        Returns:
            The created task ID, or None if creation failed.
        """
        from src.memory.prospective import (
            ProspectiveMemory,
            ProspectiveTask,
            TaskPriority,
            TriggerType,
        )

        try:
            # Format time for display
            time_str = event.start_time.strftime("%Y-%m-%d %H:%M")
            attendees_str = ", ".join(event.attendees[:5])  # Limit to 5 attendees
            if len(event.attendees) > 5:
                attendees_str += f" and {len(event.attendees) - 5} others"

            # Create task content
            task = f"Prepare meeting brief for: {event.title}"
            description = (
                f"Prepare meeting brief for: {event.title}\n"
                f"When: {time_str}\n"
                f"Attendees: {attendees_str}"
            )
            if event.description:
                description += f"\n\nDescription: {event.description[:200]}"
            if event.location:
                description += f"\n\nLocation: {event.location}"

            # Calculate trigger time (24 hours before meeting)
            trigger_at = event.start_time - timedelta(hours=24)

            # Determine priority (medium for external, low for internal)
            priority = TaskPriority.MEDIUM if event.is_external else TaskPriority.LOW

            # Create prospective task
            prospective_task = ProspectiveTask(
                id=str(uuid.uuid4()),
                user_id=user_id,
                task=task,
                description=description,
                trigger_type=TriggerType.TIME,
                trigger_config={"due_at": trigger_at.isoformat()},
                status="pending",  # type: ignore
                priority=priority,  # type: ignore
                related_goal_id=None,
                related_lead_id=None,
                completed_at=None,
                created_at=datetime.now(UTC),
            )

            # Store task
            prospective_memory = ProspectiveMemory()
            task_id = await prospective_memory.create_task(prospective_task)

            logger.info(
                "Created meeting research task",
                extra={
                    "user_id": user_id,
                    "task_id": task_id,
                    "event_id": event.external_id,
                    "event_title": event.title,
                    "trigger_at": trigger_at.isoformat(),
                },
            )

            return task_id

        except Exception as e:
            logger.warning(
                "Failed to create meeting research task",
                extra={"user_id": user_id, "event_id": event.external_id, "error": str(e)},
            )
            return None

    async def queue_push_item(self, item: "PushQueueItem") -> str:
        """Queue a push item for user approval.

        Creates a new push queue item in the database with expiration
        of 7 days. The item will require user approval before being
        pushed to the external system (per US-937 action queue).

        Args:
            item: The PushQueueItem to queue.

        Returns:
            The queue_id of the created item.

        Raises:
            Exception: If database insertion fails.
        """
        from src.integrations.deep_sync_domain import PushPriority

        try:
            client = self.supabase.get_client()
            now = datetime.now(UTC)
            expires_at = now + timedelta(days=7)

            # Calculate priority_int
            priority_mapping = {
                PushPriority.CRITICAL: 4,
                PushPriority.HIGH: 3,
                PushPriority.MEDIUM: 2,
                PushPriority.LOW: 1,
            }
            priority_int = priority_mapping.get(item.priority, 2)

            queue_id = str(uuid.uuid4())

            queue_data = {
                "id": queue_id,
                "user_id": item.user_id,
                "integration_type": item.integration_type.value,
                "action_type": item.action_type.value,
                "priority": item.priority.value,
                "priority_int": priority_int,
                "payload": item.payload,
                "status": item.status.value,
                "created_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
            }

            response = client.table("integration_push_queue").insert(queue_data).execute()

            if response.data:
                logger.info(
                    "Queued push item for user approval",
                    extra={
                        "queue_id": queue_id,
                        "user_id": item.user_id,
                        "integration_type": item.integration_type.value,
                        "action_type": item.action_type.value,
                        "priority": item.priority.value,
                    },
                )
                return queue_id

            raise Exception("Failed to insert push queue item")

        except Exception as e:
            logger.error(
                "Failed to queue push item",
                extra={
                    "user_id": item.user_id,
                    "integration_type": item.integration_type.value,
                    "action_type": item.action_type.value,
                    "error": str(e),
                },
            )
            raise

    async def process_approved_push_items(
        self,
        user_id: str,
        integration_type: "IntegrationType",
    ) -> "SyncResult":
        """Process approved push items from the queue.

        Fetches all approved items from the push queue and executes them
        in order of priority (highest first). Marks each item as completed
        or failed after execution.

        Args:
            user_id: The user's ID.
            integration_type: The integration type.

        Returns:
            SyncResult with metrics about the push sync.

        Raises:
            Exception: If fetching items or logging fails.
        """
        from src.integrations.deep_sync_domain import (
            SyncDirection,
            SyncResult,
            SyncStatus,
        )

        started_at = datetime.now(UTC)

        # Get integration connection
        client = self.supabase.get_client()
        integration_response = (
            client.table("user_integrations")
            .select("*")
            .eq("user_id", user_id)
            .eq("integration_type", integration_type.value)
            .maybe_single()
            .execute()
        )

        if not integration_response.data:
            raise Exception(f"No active {integration_type.value} integration found for user")

        integration = integration_response.data
        connection_id = integration.get("composio_connection_id")

        if not connection_id:
            raise Exception(f"No connection ID found for {integration_type.value} integration")

        # Fetch approved items ordered by priority
        items_response = (
            client.table("integration_push_queue")
            .select("*")
            .eq("user_id", user_id)
            .eq("integration_type", integration_type.value)
            .eq("status", "approved")
            .order("priority_int", desc=True)
            .execute()
        )

        items = items_response.data or []

        total_processed = len(items)
        total_succeeded = 0
        total_failed = 0
        all_errors: dict[str, Any] = {}

        for item in items:
            try:
                # Execute the push item
                await self._execute_push_item(
                    integration_type=integration_type,
                    connection_id=connection_id,
                    item=item,
                )

                # Mark as completed
                client.table("integration_push_queue").update(
                    {
                        "status": "completed",
                        "processed_at": datetime.now(UTC).isoformat(),
                    }
                ).eq("id", item["id"]).execute()

                total_succeeded += 1

            except Exception as e:
                total_failed += 1
                error_msg = str(e)
                all_errors[item["id"]] = error_msg

                # Mark as failed
                client.table("integration_push_queue").update(
                    {
                        "status": "failed",
                        "error_message": error_msg,
                        "processed_at": datetime.now(UTC).isoformat(),
                    }
                ).eq("id", item["id"]).execute()

                logger.warning(
                    "Push item failed",
                    extra={
                        "queue_id": item["id"],
                        "user_id": user_id,
                        "error": error_msg,
                    },
                )

        # Determine sync status
        if total_failed == 0:
            sync_status = SyncStatus.SUCCESS
        elif total_succeeded > 0:
            sync_status = SyncStatus.PARTIAL
        else:
            sync_status = SyncStatus.FAILED

        # Log push sync operation
        await self._log_sync(
            user_id=user_id,
            integration_type=integration_type,
            sync_type="push",
            status=sync_status,
            records_processed=total_processed,
            records_succeeded=total_succeeded,
            records_failed=total_failed,
            error_details=all_errors if sync_status != SyncStatus.SUCCESS else None,
        )

        completed_at = datetime.now(UTC)

        logger.info(
            "Push sync completed",
            extra={
                "user_id": user_id,
                "integration_type": integration_type.value,
                "processed": total_processed,
                "succeeded": total_succeeded,
                "failed": total_failed,
                "status": sync_status.value,
            },
        )

        return SyncResult(
            direction=SyncDirection.PUSH,
            integration_type=integration_type,
            status=sync_status,
            records_processed=total_processed,
            records_succeeded=total_succeeded,
            records_failed=total_failed,
            started_at=started_at,
            completed_at=completed_at,
            error_details=all_errors if sync_status != SyncStatus.SUCCESS else None,
            push_queue_items=total_processed,
        )

    async def _execute_push_item(
        self,
        integration_type: "IntegrationType",
        connection_id: str,
        item: dict[str, Any],
    ) -> None:
        """Execute a single push item against the external system.

        Routes to the appropriate Composio action based on the
        action_type and integration_type.

        Args:
            integration_type: The integration type.
            connection_id: The Composio connection ID.
            item: The push queue item from database.

        Raises:
            Exception: If execution fails.
        """
        action_type = item.get("action_type")
        payload = item.get("payload", {})

        # Execute based on action_type
        if action_type == "create_note":
            await self._execute_create_note(
                integration_type=integration_type,
                connection_id=connection_id,
                payload=payload,
            )
        elif action_type == "update_field":
            await self._execute_update_field(
                integration_type=integration_type,
                connection_id=connection_id,
                payload=payload,
            )
        elif action_type == "create_event":
            await self._execute_create_event(
                integration_type=integration_type,
                connection_id=connection_id,
                payload=payload,
            )
        else:
            raise Exception(f"Unknown action_type: {action_type}")

    async def _execute_create_note(
        self,
        integration_type: "IntegrationType",
        connection_id: str,
        payload: dict[str, Any],
    ) -> None:
        """Execute create_note action for CRM.

        Creates an activity note in Salesforce or HubSpot.

        Args:
            integration_type: The CRM integration type.
            connection_id: The Composio connection ID.
            payload: Contains parentId, title, body.

        Raises:
            Exception: If execution fails.
        """
        from src.integrations.domain import IntegrationType

        if integration_type == IntegrationType.SALESFORCE:
            action = "salesforce_create_note"
            params = {
                "parentId": payload.get("parentId"),
                "title": payload.get("title"),
                "body": payload.get("body"),
            }
        else:  # HUBSPOT
            action = "hubspot_create_engagement"
            params = {
                "associatedObjectId": payload.get("parentId"),
                "type": "NOTE",
                "body": payload.get("body"),
            }

        result = await self.integration_service.execute_action(
            connection_id=connection_id,
            action=action,
            params=params,
        )

        if not result.get("data"):
            raise Exception(f"Failed to create note: {result}")

    async def _execute_update_field(
        self,
        integration_type: "IntegrationType",
        connection_id: str,
        payload: dict[str, Any],
    ) -> None:
        """Execute update_field action for CRM.

        Updates a custom field (e.g., lead score) in Salesforce or HubSpot.

        Args:
            integration_type: The CRM integration type.
            connection_id: The Composio connection ID.
            payload: Contains entityId, field_name, field_value.

        Raises:
            Exception: If execution fails.
        """
        from src.integrations.domain import IntegrationType

        if integration_type == IntegrationType.SALESFORCE:
            action = "salesforce_update_opportunity"
            params = {
                "opportunityId": payload.get("entityId"),
                "aria_Lead_Score__c": payload.get("field_value"),
            }
        else:  # HUBSPOT
            action = "hubspot_update_deal"
            params = {
                "dealId": payload.get("entityId"),
                "aria_lead_score": payload.get("field_value"),
            }

        result = await self.integration_service.execute_action(
            connection_id=connection_id,
            action=action,
            params=params,
        )

        if not result.get("data"):
            raise Exception(f"Failed to update field: {result}")

    async def _execute_create_event(
        self,
        integration_type: "IntegrationType",
        connection_id: str,
        payload: dict[str, Any],
    ) -> None:
        """Execute create_event action for calendar.

        Creates a calendar event in Google Calendar or Outlook.

        Args:
            integration_type: The calendar integration type.
            connection_id: The Composio connection ID.
            payload: Contains summary, description, start, end, attendees.

        Raises:
            Exception: If execution fails.
        """
        from src.integrations.domain import IntegrationType

        if integration_type == IntegrationType.GOOGLE_CALENDAR:
            action = "create_event"
            params = {
                "summary": payload.get("summary"),
                "description": payload.get("description"),
                "start": payload.get("start"),
                "end": payload.get("end"),
                "attendees": payload.get("attendees", []),
            }
        else:  # OUTLOOK
            action = "create_calendar_event"
            params = {
                "subject": payload.get("summary"),
                "bodyPreview": payload.get("description"),
                "start": payload.get("start"),
                "end": payload.get("end"),
                "attendees": payload.get("attendees", []),
            }

        result = await self.integration_service.execute_action(
            connection_id=connection_id,
            action=action,
            params=params,
        )

        if not result.get("data"):
            raise Exception(f"Failed to create event: {result}")


# Singleton instance
_deep_sync_service: "DeepSyncService | None" = None


def get_deep_sync_service() -> DeepSyncService:
    """Get the singleton DeepSyncService instance.

    Returns:
        The shared DeepSyncService instance.
    """
    global _deep_sync_service
    if _deep_sync_service is None:
        _deep_sync_service = DeepSyncService()
    return _deep_sync_service
