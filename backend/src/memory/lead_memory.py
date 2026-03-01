"""Lead memory module for tracking sales pursuits.

Lead memory stores sales pursuit information with:
- Lifecycle stage progression (lead -> opportunity -> account)
- Status tracking (active, won, lost, dormant)
- Health score calculation (0-100)
- Trigger source tracking for lead creation
- Optional CRM integration fields

Leads are stored in Supabase for structured querying
and integration with the CRM sync system.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from src.core.exceptions import LeadMemoryError
from src.db.supabase import SupabaseClient
from src.memory.audit import MemoryOperation, MemoryType, log_memory_operation
from src.memory.health_score import HealthScoreCalculator, HealthScoreHistory
from src.memory.lead_memory_events import LeadEventService

logger = logging.getLogger(__name__)


class LifecycleStage(Enum):
    """Lifecycle stages for lead progression.

    Stages progress in order: lead -> opportunity -> account.
    History is preserved on transition.
    """

    LEAD = "lead"
    OPPORTUNITY = "opportunity"
    ACCOUNT = "account"


class LeadStatus(Enum):
    """Status of a lead within its lifecycle stage."""

    ACTIVE = "active"
    WON = "won"
    LOST = "lost"
    DORMANT = "dormant"


class TriggerType(Enum):
    """Source that triggered lead creation."""

    EMAIL_APPROVED = "email_approved"
    MANUAL = "manual"
    CRM_IMPORT = "crm_import"
    INBOUND = "inbound"


@dataclass
class LeadMemory:
    """A lead memory record representing a sales pursuit.

    Tracks the full lifecycle of a sales pursuit from initial
    lead through opportunity to closed account.
    """

    id: str
    user_id: str
    company_name: str
    lifecycle_stage: LifecycleStage
    status: LeadStatus
    health_score: int  # 0-100
    trigger: TriggerType
    first_touch_at: datetime
    last_activity_at: datetime
    created_at: datetime
    updated_at: datetime
    company_id: str | None = None
    crm_id: str | None = None
    crm_provider: str | None = None  # salesforce, hubspot
    expected_close_date: date | None = None
    expected_value: Decimal | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize lead to a dictionary.

        Returns:
            Dictionary representation suitable for JSON serialization.
        """
        return {
            "id": self.id,
            "user_id": self.user_id,
            "company_id": self.company_id,
            "company_name": self.company_name,
            "lifecycle_stage": self.lifecycle_stage.value,
            "status": self.status.value,
            "health_score": self.health_score,
            "trigger": self.trigger.value,
            "crm_id": self.crm_id,
            "crm_provider": self.crm_provider,
            "first_touch_at": self.first_touch_at.isoformat(),
            "last_activity_at": self.last_activity_at.isoformat(),
            "expected_close_date": self.expected_close_date.isoformat()
            if self.expected_close_date
            else None,
            "expected_value": str(self.expected_value) if self.expected_value else None,
            "tags": self.tags,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LeadMemory":
        """Create a LeadMemory instance from a dictionary.

        Args:
            data: Dictionary containing lead data.

        Returns:
            LeadMemory instance with restored state.
        """
        return cls(
            id=data["id"],
            user_id=data["user_id"],
            company_id=data.get("company_id"),
            company_name=data["company_name"],
            lifecycle_stage=LifecycleStage(data["lifecycle_stage"]),
            status=LeadStatus(data["status"]),
            health_score=data["health_score"],
            trigger=TriggerType(data["trigger"]) if data.get("trigger") else TriggerType.MANUAL,
            crm_id=data.get("crm_id"),
            crm_provider=data.get("crm_provider"),
            first_touch_at=datetime.fromisoformat(data["first_touch_at"])
            if isinstance(data["first_touch_at"], str)
            else data["first_touch_at"],
            last_activity_at=datetime.fromisoformat(data["last_activity_at"])
            if isinstance(data["last_activity_at"], str)
            else data["last_activity_at"],
            expected_close_date=date.fromisoformat(data["expected_close_date"])
            if data.get("expected_close_date")
            else None,
            expected_value=Decimal(data["expected_value"]) if data.get("expected_value") else None,
            tags=data.get("tags") or [],
            metadata=data.get("metadata") or {},
            created_at=datetime.fromisoformat(data["created_at"])
            if isinstance(data["created_at"], str)
            else data["created_at"],
            updated_at=datetime.fromisoformat(data["updated_at"])
            if isinstance(data["updated_at"], str)
            else data["updated_at"],
        )


class LeadMemoryService:
    """Service class for lead memory operations.

    Provides async interface for storing, retrieving, and managing
    lead memories. Uses Supabase as the underlying storage for
    structured querying and CRM integration.
    """

    # Class-level constant for valid stage transitions
    _STAGE_ORDER = [LifecycleStage.LEAD, LifecycleStage.OPPORTUNITY, LifecycleStage.ACCOUNT]

    def _get_supabase_client(self) -> Any:
        """Get the Supabase client instance.

        Returns:
            Initialized Supabase client.

        Raises:
            LeadMemoryError: If client initialization fails.
        """
        try:
            return SupabaseClient.get_client()
        except Exception as e:
            raise LeadMemoryError(f"Failed to get Supabase client: {e}") from e

    async def create(
        self,
        user_id: str,
        company_name: str,
        trigger: TriggerType,
        company_id: str | None = None,
        crm_id: str | None = None,
        crm_provider: str | None = None,
        expected_close_date: date | None = None,
        expected_value: Decimal | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LeadMemory:
        """Create a new lead in memory.

        Args:
            user_id: The user creating the lead.
            company_name: Name of the company/lead.
            trigger: Source that triggered lead creation.
            company_id: Optional company UUID reference.
            crm_id: Optional external CRM record ID.
            crm_provider: Optional CRM provider (salesforce, hubspot).
            expected_close_date: Optional expected close date.
            expected_value: Optional expected deal value.
            tags: Optional list of tags.
            metadata: Optional additional metadata.

        Returns:
            The created LeadMemory instance.

        Raises:
            LeadMemoryError: If creation fails.
        """
        try:
            lead_id = str(uuid.uuid4())
            now = datetime.now(UTC)

            # Create lead with defaults
            lead = LeadMemory(
                id=lead_id,
                user_id=user_id,
                company_id=company_id,
                company_name=company_name,
                lifecycle_stage=LifecycleStage.LEAD,
                status=LeadStatus.ACTIVE,
                health_score=50,  # Default health score
                trigger=trigger,
                crm_id=crm_id,
                crm_provider=crm_provider,
                first_touch_at=now,
                last_activity_at=now,
                expected_close_date=expected_close_date,
                expected_value=expected_value,
                tags=tags or [],
                metadata=metadata or {},
                created_at=now,
                updated_at=now,
            )

            # Prepare data for database
            data = {
                "id": lead.id,
                "user_id": lead.user_id,
                "company_id": lead.company_id,
                "company_name": lead.company_name,
                "lifecycle_stage": lead.lifecycle_stage.value,
                "status": lead.status.value,
                "health_score": lead.health_score,
                "crm_id": lead.crm_id,
                "crm_provider": lead.crm_provider,
                "first_touch_at": lead.first_touch_at.isoformat(),
                "last_activity_at": lead.last_activity_at.isoformat(),
                "expected_close_date": lead.expected_close_date.isoformat()
                if lead.expected_close_date
                else None,
                "expected_value": float(lead.expected_value) if lead.expected_value else None,
                "tags": lead.tags,
                "metadata": {
                    **lead.metadata,
                    "trigger": trigger.value,
                },
            }

            client = self._get_supabase_client()
            response = client.table("lead_memories").insert(data).execute()

            if not response.data or len(response.data) == 0:
                raise LeadMemoryError("Failed to insert lead")

            logger.info(
                "Created lead",
                extra={
                    "lead_id": lead_id,
                    "user_id": user_id,
                    "company_name": company_name,
                    "trigger": trigger.value,
                },
            )

            # Audit log the creation
            await log_memory_operation(
                user_id=user_id,
                operation=MemoryOperation.CREATE,
                memory_type=MemoryType.LEAD,
                memory_id=lead_id,
                metadata={"company_name": company_name, "trigger": trigger.value},
                suppress_errors=True,
            )

            # Auto-populate monitored entities for signal scanning
            try:
                from src.services.monitored_entity_service import MonitoredEntityService

                await MonitoredEntityService().ensure_entity(
                    user_id=user_id,
                    entity_type="company",
                    entity_name=company_name,
                )
            except Exception:
                logger.debug(
                    "Failed to ensure monitored entity for lead %s", company_name,
                    exc_info=True,
                )

            return lead

        except LeadMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to create lead")
            raise LeadMemoryError(f"Failed to create lead: {e}") from e

    async def get_by_id(self, user_id: str, lead_id: str) -> LeadMemory:
        """Retrieve a specific lead by ID.

        Args:
            user_id: The user who owns the lead.
            lead_id: The lead ID.

        Returns:
            The requested LeadMemory.

        Raises:
            LeadNotFoundError: If lead doesn't exist.
            LeadMemoryError: If retrieval fails.
        """
        from src.core.exceptions import LeadNotFoundError

        try:
            client = self._get_supabase_client()

            response = (
                client.table("lead_memories")
                .select("*")
                .eq("id", lead_id)
                .eq("user_id", user_id)
                .single()
                .execute()
            )

            if response.data is None:
                raise LeadNotFoundError(lead_id)

            # Extract trigger from metadata if present
            data = response.data
            if "trigger" not in data and data.get("metadata", {}).get("trigger"):
                data["trigger"] = data["metadata"]["trigger"]
            elif "trigger" not in data:
                data["trigger"] = "manual"

            return LeadMemory.from_dict(data)

        except LeadNotFoundError:
            raise
        except LeadMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to get lead", extra={"lead_id": lead_id})
            raise LeadMemoryError(f"Failed to get lead: {e}") from e

    async def update(
        self,
        user_id: str,
        lead_id: str,
        company_name: str | None = None,
        lifecycle_stage: LifecycleStage | None = None,
        status: LeadStatus | None = None,
        health_score: int | None = None,
        crm_id: str | None = None,
        crm_provider: str | None = None,
        expected_close_date: date | None = None,
        expected_value: Decimal | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Update an existing lead.

        Only provided fields will be updated. None values are ignored.

        Args:
            user_id: The user who owns the lead.
            lead_id: The lead ID to update.
            company_name: Optional new company name.
            lifecycle_stage: Optional new lifecycle stage.
            status: Optional new lead status.
            health_score: Optional new health score (0-100).
            crm_id: Optional CRM record ID.
            crm_provider: Optional CRM provider.
            expected_close_date: Optional expected close date.
            expected_value: Optional expected deal value.
            tags: Optional new tags list.
            metadata: Optional metadata to merge.

        Raises:
            LeadNotFoundError: If lead doesn't exist.
            LeadMemoryError: If update fails.
        """
        from src.core.exceptions import LeadNotFoundError

        try:
            client = self._get_supabase_client()
            now = datetime.now(UTC)

            # Build update data from provided fields
            data: dict[str, Any] = {
                "last_activity_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }

            if company_name is not None:
                data["company_name"] = company_name
            if lifecycle_stage is not None:
                data["lifecycle_stage"] = lifecycle_stage.value
            if status is not None:
                data["status"] = status.value
            if health_score is not None:
                data["health_score"] = health_score
            if crm_id is not None:
                data["crm_id"] = crm_id
            if crm_provider is not None:
                data["crm_provider"] = crm_provider
            if expected_close_date is not None:
                data["expected_close_date"] = expected_close_date.isoformat()
            if expected_value is not None:
                data["expected_value"] = float(expected_value)
            if tags is not None:
                data["tags"] = tags
            if metadata is not None:
                data["metadata"] = metadata

            response = (
                client.table("lead_memories")
                .update(data)
                .eq("id", lead_id)
                .eq("user_id", user_id)
                .execute()
            )

            if not response.data or len(response.data) == 0:
                raise LeadNotFoundError(lead_id)

            logger.info(
                "Updated lead",
                extra={
                    "lead_id": lead_id,
                    "user_id": user_id,
                    "updated_fields": list(data.keys()),
                },
            )

            # Audit log the update
            await log_memory_operation(
                user_id=user_id,
                operation=MemoryOperation.UPDATE,
                memory_type=MemoryType.LEAD,
                memory_id=lead_id,
                metadata={"updated_fields": list(data.keys())},
                suppress_errors=True,
            )

        except LeadNotFoundError:
            raise
        except LeadMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to update lead", extra={"lead_id": lead_id})
            raise LeadMemoryError(f"Failed to update lead: {e}") from e

    async def list_by_user(
        self,
        user_id: str,
        status: LeadStatus | None = None,
        lifecycle_stage: LifecycleStage | None = None,
        min_health_score: int | None = None,
        max_health_score: int | None = None,
        limit: int = 50,
    ) -> list[LeadMemory]:
        """List all leads for a user with optional filters.

        Args:
            user_id: The user to list leads for.
            status: Optional filter by lead status.
            lifecycle_stage: Optional filter by lifecycle stage.
            min_health_score: Optional minimum health score.
            max_health_score: Optional maximum health score.
            limit: Maximum number of leads to return.

        Returns:
            List of LeadMemory instances matching the filters.

        Raises:
            LeadMemoryError: If the query fails.
        """
        try:
            client = self._get_supabase_client()

            query = client.table("lead_memories").select("*").eq("user_id", user_id)

            if status is not None:
                query = query.eq("status", status.value)

            if lifecycle_stage is not None:
                query = query.eq("lifecycle_stage", lifecycle_stage.value)

            if min_health_score is not None:
                query = query.gte("health_score", min_health_score)

            if max_health_score is not None:
                query = query.lte("health_score", max_health_score)

            response = query.order("last_activity_at", desc=True).limit(limit).execute()

            if not response.data:
                return []

            leads = []
            for row in response.data:
                # Extract trigger from metadata if not present
                if "trigger" not in row and row.get("metadata", {}).get("trigger"):
                    row["trigger"] = row["metadata"]["trigger"]
                elif "trigger" not in row:
                    row["trigger"] = "manual"
                leads.append(LeadMemory.from_dict(row))

            logger.info(
                "Listed leads",
                extra={
                    "user_id": user_id,
                    "count": len(leads),
                    "filters": {
                        "status": status.value if status else None,
                        "lifecycle_stage": lifecycle_stage.value if lifecycle_stage else None,
                        "min_health_score": min_health_score,
                        "max_health_score": max_health_score,
                    },
                },
            )

            return leads

        except LeadMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to list leads")
            raise LeadMemoryError(f"Failed to list leads: {e}") from e

    async def transition_stage(
        self,
        user_id: str,
        lead_id: str,
        new_stage: LifecycleStage,
    ) -> None:
        """Transition a lead to a new lifecycle stage.

        Stages can only progress forward: lead -> opportunity -> account.
        History is preserved in metadata.

        Args:
            user_id: The user who owns the lead.
            lead_id: The lead ID to transition.
            new_stage: The target lifecycle stage.

        Raises:
            LeadNotFoundError: If lead doesn't exist.
            InvalidStageTransitionError: If transition is not allowed.
            LeadMemoryError: If transition fails.
        """
        from src.core.exceptions import InvalidStageTransitionError

        try:
            # Get current lead
            lead = await self.get_by_id(user_id, lead_id)

            # No-op if same stage
            if lead.lifecycle_stage == new_stage:
                logger.info(
                    "Stage transition is no-op (same stage)",
                    extra={"lead_id": lead_id, "stage": new_stage.value},
                )
                return

            # Validate forward-only progression
            current_index = self._STAGE_ORDER.index(lead.lifecycle_stage)
            target_index = self._STAGE_ORDER.index(new_stage)

            if target_index <= current_index:
                raise InvalidStageTransitionError(
                    current_stage=lead.lifecycle_stage.value,
                    target_stage=new_stage.value,
                )

            # Build stage history entry
            now = datetime.now(UTC)
            history_entry = {
                "from_stage": lead.lifecycle_stage.value,
                "to_stage": new_stage.value,
                "transitioned_at": now.isoformat(),
            }

            # Get existing history or create new
            existing_metadata = lead.metadata or {}
            stage_history = existing_metadata.get("stage_history", [])
            stage_history.append(history_entry)

            # Update metadata with preserved history
            updated_metadata = {
                **existing_metadata,
                "stage_history": stage_history,
            }

            # Perform update
            client = self._get_supabase_client()
            data = {
                "lifecycle_stage": new_stage.value,
                "metadata": updated_metadata,
                "last_activity_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }

            response = (
                client.table("lead_memories")
                .update(data)
                .eq("id", lead_id)
                .eq("user_id", user_id)
                .execute()
            )

            if not response.data or len(response.data) == 0:
                from src.core.exceptions import LeadNotFoundError

                raise LeadNotFoundError(lead_id)

            logger.info(
                "Transitioned lead stage",
                extra={
                    "lead_id": lead_id,
                    "user_id": user_id,
                    "from_stage": lead.lifecycle_stage.value,
                    "to_stage": new_stage.value,
                },
            )

            # Audit log the transition
            await log_memory_operation(
                user_id=user_id,
                operation=MemoryOperation.UPDATE,
                memory_type=MemoryType.LEAD,
                memory_id=lead_id,
                metadata={
                    "action": "stage_transition",
                    "from_stage": lead.lifecycle_stage.value,
                    "to_stage": new_stage.value,
                },
                suppress_errors=True,
            )

        except (InvalidStageTransitionError, LeadMemoryError):
            raise
        except Exception as e:
            logger.exception("Failed to transition stage", extra={"lead_id": lead_id})
            raise LeadMemoryError(f"Failed to transition stage: {e}") from e

    async def calculate_health_score(
        self,
        user_id: str,
        lead_id: str,
    ) -> int:
        """Calculate and update health score for a lead.

        Args:
            user_id: The user who owns the lead.
            lead_id: The lead ID to score.

        Returns:
            The calculated health score (0-100).

        Raises:
            LeadNotFoundError: If lead doesn't exist.
            LeadMemoryError: If calculation fails.
        """
        from src.core.exceptions import LeadNotFoundError

        try:
            # Get lead data
            lead = await self.get_by_id(user_id, lead_id)

            # Get events for scoring
            client = self._get_supabase_client()
            event_service = LeadEventService(db_client=client)
            events = await event_service.get_timeline(
                user_id=user_id,
                lead_memory_id=lead_id,
            )

            # Get insights (placeholder - will be implemented in US-515)
            insights = []

            # Get stakeholders (placeholder - will be implemented in US-515)
            stakeholders = []

            # Get stage history from metadata
            stage_history = lead.metadata.get("stage_history", [])

            # Calculate score
            calculator = HealthScoreCalculator()
            health_score = calculator.calculate(
                lead=lead,
                events=events,
                insights=insights,
                stakeholders=stakeholders,
                stage_history=stage_history,
            )

            # Update lead with new score
            await self.update(
                user_id=user_id,
                lead_id=lead_id,
                health_score=health_score,
            )

            # Store score history
            await self._store_score_history(
                user_id=user_id,
                lead_id=lead_id,
                score=health_score,
                calculator=calculator,
                lead=lead,
                events=events,
            )

            logger.info(
                "Calculated health score",
                extra={
                    "lead_id": lead_id,
                    "user_id": user_id,
                    "health_score": health_score,
                },
            )

            return health_score

        except LeadNotFoundError:
            raise
        except LeadMemoryError:
            raise
        except Exception as e:
            logger.exception("Failed to calculate health score")
            raise LeadMemoryError(f"Failed to calculate health score: {e}") from e

    async def _store_score_history(
        self,
        user_id: str,
        lead_id: str,
        score: int,
        calculator: HealthScoreCalculator,
        lead: object,
        events: list,
    ) -> None:
        """Store health score in history table.

        Args:
            user_id: The user who owns the lead.
            lead_id: The lead ID.
            score: The calculated health score.
            calculator: The calculator instance for component scores.
            lead: The lead object.
            events: List of events used for scoring.
        """
        try:
            client = self._get_supabase_client()

            # Calculate component scores for storage
            stage_history = lead.metadata.get("stage_history", [])
            stakeholders = []  # Placeholder

            component_scores = {
                "component_frequency": calculator._score_frequency(events),
                "component_response_time": calculator._score_response_time(events),
                "component_sentiment": calculator._score_sentiment([]),
                "component_breadth": calculator._score_breadth(stakeholders),
                "component_velocity": calculator._score_velocity(lead, stage_history),
            }

            data = {
                "lead_memory_id": lead_id,
                "user_id": user_id,
                "score": score,
                "calculated_at": datetime.now(UTC).isoformat(),
                **component_scores,
            }

            client.table("health_score_history").insert(data).execute()

        except Exception as e:
            # Don't fail the main operation if history storage fails
            logger.warning(
                "Failed to store health score history",
                extra={"lead_id": lead_id, "error": str(e)},
            )

    async def get_score_history(
        self,
        user_id: str,
        lead_id: str,
        limit: int = 100,
    ) -> list[HealthScoreHistory]:
        """Get health score history for a lead.

        Args:
            user_id: The user who owns the lead.
            lead_id: The lead ID.
            limit: Maximum number of history records.

        Returns:
            List of health score history records.

        Raises:
            LeadMemoryError: If retrieval fails.
        """
        try:
            client = self._get_supabase_client()

            response = (
                client.table("health_score_history")
                .select("score, calculated_at")
                .eq("lead_memory_id", lead_id)
                .eq("user_id", user_id)
                .order("calculated_at", desc=True)
                .limit(limit)
                .execute()
            )

            return [
                HealthScoreHistory(
                    score=row["score"],
                    calculated_at=datetime.fromisoformat(row["calculated_at"]),
                )
                for row in response.data
            ]

        except Exception as e:
            logger.exception("Failed to get score history")
            raise LeadMemoryError(f"Failed to get score history: {e}") from e

    async def check_for_health_alert(
        self,
        user_id: str,
        lead_id: str,
        new_score: int,
        alert_threshold: int = 20,
    ) -> bool:
        """Check if health score change should trigger alert.

        Args:
            user_id: The user who owns the lead.
            lead_id: The lead ID.
            new_score: The newly calculated health score.
            alert_threshold: Minimum drop to trigger alert.

        Returns:
            True if alert should be sent.

        Raises:
            LeadMemoryError: If check fails.
        """
        try:
            # Get score history
            history = await self.get_score_history(
                user_id=user_id,
                lead_id=lead_id,
                limit=1,
            )

            # Check if alert needed
            calculator = HealthScoreCalculator()
            should_alert = calculator._should_alert(
                current_score=new_score,
                history=history,
                threshold=alert_threshold,
            )

            if should_alert:
                logger.info(
                    "Health score alert triggered",
                    extra={
                        "lead_id": lead_id,
                        "user_id": user_id,
                        "new_score": new_score,
                        "previous_score": history[0].score if history else None,
                        "drop": history[0].score - new_score if history else 0,
                    },
                )

            return should_alert

        except Exception as e:
            logger.exception("Failed to check for health alert")
            raise LeadMemoryError(f"Failed to check for health alert: {e}") from e
