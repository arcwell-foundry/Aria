"""Lead collaboration service for multi-user contributions.

This service enables team members to contribute to shared leads with
an owner approval workflow. Contributions are flagged for review and
can be merged or rejected by the lead owner.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from supabase import Client

logger = logging.getLogger(__name__)


# Internal enums for domain model
class ContributionStatus(str, Enum):
    PENDING = "pending"
    MERGED = "merged"
    REJECTED = "rejected"


class ContributionType(str, Enum):
    EVENT = "event"
    NOTE = "note"
    INSIGHT = "insight"


@dataclass
class Contribution:
    """A domain model representing a contribution to a lead.

    Attributes:
        id: Unique identifier for this contribution.
        lead_memory_id: ID of the lead memory this contribution belongs to.
        contributor_id: User ID of the contributor.
        contribution_type: Type of contribution (event, note, insight).
        contribution_id: ID of the event/note/insight being contributed.
        status: Review status (pending, merged, rejected).
        reviewed_by: User ID of the reviewer (if reviewed).
        reviewed_at: Timestamp of review (if reviewed).
        created_at: When this contribution was created.
    """

    id: str
    lead_memory_id: str
    contributor_id: str
    contribution_type: ContributionType
    contribution_id: str | None
    status: ContributionStatus
    reviewed_by: str | None
    reviewed_at: datetime | None
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Serialize contribution to a dictionary."""
        return {
            "id": self.id,
            "lead_memory_id": self.lead_memory_id,
            "contributor_id": self.contributor_id,
            "contribution_type": self.contribution_type.value,
            "contribution_id": self.contribution_id,
            "status": self.status.value,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Contribution:
        """Create a Contribution from a dictionary."""
        # Parse datetime fields
        reviewed_at = None
        if data.get("reviewed_at"):
            raw = data["reviewed_at"]
            reviewed_at = datetime.fromisoformat(raw) if isinstance(raw, str) else raw

        created_at_raw = data["created_at"]
        created_at = (
            datetime.fromisoformat(created_at_raw)
            if isinstance(created_at_raw, str)
            else created_at_raw
        )

        # Parse enums
        contribution_type_raw = data["contribution_type"]
        contribution_type = (
            ContributionType(contribution_type_raw)
            if isinstance(contribution_type_raw, str)
            else contribution_type_raw
        )

        status_raw = data["status"]
        status = ContributionStatus(status_raw) if isinstance(status_raw, str) else status_raw

        return cls(
            id=cast(str, data["id"]),
            lead_memory_id=cast(str, data["lead_memory_id"]),
            contributor_id=cast(str, data["contributor_id"]),
            contribution_type=contribution_type,
            contribution_id=cast(str | None, data.get("contribution_id")),
            status=status,
            reviewed_by=cast(str | None, data.get("reviewed_by")),
            reviewed_at=reviewed_at,
            created_at=created_at,
        )


@dataclass
class Contributor:
    """A domain model representing a contributor to a lead.

    Attributes:
        id: Unique identifier for this contributor relationship.
        lead_memory_id: ID of the lead memory this contributor belongs to.
        name: Full name of the contributor.
        email: Email address of the contributor.
        added_at: When this contributor was added.
        contribution_count: Number of contributions made by this contributor.
    """

    id: str
    lead_memory_id: str
    name: str
    email: str
    added_at: datetime
    contribution_count: int

    def to_dict(self) -> dict[str, Any]:
        """Serialize contributor to a dictionary."""
        return {
            "id": self.id,
            "lead_memory_id": self.lead_memory_id,
            "name": self.name,
            "email": self.email,
            "added_at": self.added_at.isoformat(),
            "contribution_count": self.contribution_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Contributor:
        """Create a Contributor from a dictionary."""
        added_at_raw = data["added_at"]
        added_at = (
            datetime.fromisoformat(added_at_raw) if isinstance(added_at_raw, str) else added_at_raw
        )

        return cls(
            id=cast(str, data["id"]),
            lead_memory_id=cast(str, data["lead_memory_id"]),
            name=cast(str, data["name"]),
            email=cast(str, data["email"]),
            added_at=added_at,
            contribution_count=cast(int, data["contribution_count"]),
        )


class LeadCollaborationService:
    """Service for managing lead collaboration operations."""

    def __init__(self, db_client: Client) -> None:
        """Initialize the collaboration service.

        Args:
            db_client: Supabase client for database operations.
        """
        self.db = db_client

    def _get_supabase_client(self) -> Client:
        """Get the Supabase client instance.

        Returns:
            The Supabase client.

        Raises:
            DatabaseError: If client retrieval fails.
        """
        from src.core.exceptions import DatabaseError
        from src.db.supabase import SupabaseClient

        try:
            return SupabaseClient.get_client()
        except Exception as e:
            raise DatabaseError(f"Failed to get Supabase client: {e}") from e

    async def add_contributor(
        self,
        user_id: str,
        lead_memory_id: str,
        contributor_id: str,
    ) -> str:
        """Add a contributor to a lead.

        Note: Contributors are implicitly added when they make their first
        contribution. This method exists for explicit addition and validation.

        Args:
            user_id: The user who owns the lead.
            lead_memory_id: The lead memory ID.
            contributor_id: User ID to add as contributor.

        Returns:
            The contributor_id that was added.

        Raises:
            DatabaseError: If operation fails.
        """
        from src.core.exceptions import DatabaseError

        try:
            client = self._get_supabase_client()

            # Check if contributor already has contributions to this lead
            response = (
                client.table("lead_memory_contributions")
                .select("*")
                .eq("lead_memory_id", lead_memory_id)
                .eq("contributor_id", contributor_id)
                .execute()
            )

            # Contributors are tracked via their contributions
            # No separate table - return the contributor_id
            logger.info(
                "Contributor added to lead",
                extra={
                    "user_id": user_id,
                    "lead_memory_id": lead_memory_id,
                    "contributor_id": contributor_id,
                    "existing_contributions": len(response.data or []),
                },
            )

            return contributor_id

        except DatabaseError:
            raise
        except Exception as e:
            logger.exception("Failed to add contributor")
            raise DatabaseError(f"Failed to add contributor: {e}") from e

    async def submit_contribution(
        self,
        user_id: str,
        lead_memory_id: str,
        contribution_type: ContributionType,
        contribution_id: str | None = None,
        content: str | None = None,  # noqa: ARG002
    ) -> str:
        """Submit a contribution to a lead for owner review.

        Args:
            user_id: The user submitting the contribution.
            lead_memory_id: The lead memory ID.
            contribution_type: Type of contribution (event, note, insight).
            contribution_id: Optional ID of existing event/note/insight.
            content: Optional content for note/insight contributions.

        Returns:
            The ID of the created contribution record.

        Raises:
            DatabaseError: If submission fails.
        """
        from src.core.exceptions import DatabaseError
        from src.models.notification import NotificationType
        from src.services.notification_service import NotificationService

        try:
            client = self._get_supabase_client()

            # Get lead owner to send notification
            lead_response = (
                client.table("lead_memories").select("user_id").eq("id", lead_memory_id).execute()
            )

            owner_id: str | None = None
            if lead_response.data and len(lead_response.data) > 0:
                lead_data = cast(dict[str, Any], lead_response.data[0])
                owner_id = cast(str | None, lead_data.get("user_id"))

            now = datetime.now(UTC)
            data = {
                "id": str(uuid.uuid4()),
                "lead_memory_id": lead_memory_id,
                "contributor_id": user_id,
                "contribution_type": contribution_type.value,
                "contribution_id": contribution_id,
                "status": ContributionStatus.PENDING.value,
                "reviewed_by": None,
                "reviewed_at": None,
                "created_at": now.isoformat(),
            }

            response = client.table("lead_memory_contributions").insert(data).execute()

            if not response.data or len(response.data) == 0:
                raise DatabaseError("Failed to insert contribution")

            first_record: dict[str, Any] = cast(dict[str, Any], response.data[0])
            new_contribution_id = cast(str, first_record.get("id"))

            if not new_contribution_id:
                raise DatabaseError("Failed to insert contribution")

            # Send notification to lead owner if different from contributor
            if owner_id and owner_id != user_id:
                # Generate type description for the notification message
                type_descriptions = {
                    ContributionType.EVENT: "event",
                    ContributionType.NOTE: "note",
                    ContributionType.INSIGHT: "insight",
                }
                type_desc = type_descriptions.get(contribution_type, "contribution")

                await NotificationService.create_notification(
                    user_id=owner_id,
                    type=NotificationType.TASK_DUE,
                    title="New contribution pending review",
                    message=f"A new {type_desc} contribution has been submitted for your review.",
                    link=f"/leads/{lead_memory_id}",
                    metadata={
                        "contribution_id": new_contribution_id,
                        "lead_memory_id": lead_memory_id,
                        "contribution_type": contribution_type.value,
                    },
                )

                logger.info(
                    "Notification sent to lead owner",
                    extra={
                        "owner_id": owner_id,
                        "contributor_id": user_id,
                        "contribution_id": new_contribution_id,
                    },
                )

            logger.info(
                "Contribution submitted",
                extra={
                    "contribution_id": new_contribution_id,
                    "user_id": user_id,
                    "lead_memory_id": lead_memory_id,
                    "contribution_type": contribution_type.value,
                    "owner_notified": owner_id and owner_id != user_id,
                },
            )

            return new_contribution_id

        except DatabaseError:
            raise
        except Exception as e:
            logger.exception("Failed to submit contribution")
            raise DatabaseError(f"Failed to submit contribution: {e}") from e

    async def get_pending_contributions(
        self,
        user_id: str,
        lead_memory_id: str,
    ) -> list[Contribution]:
        """Get pending contributions for a lead.

        Args:
            user_id: The user who owns the lead.
            lead_memory_id: The lead memory ID.

        Returns:
            List of pending Contribution instances, sorted by created_at descending.

        Raises:
            DatabaseError: If retrieval fails.
        """
        from src.core.exceptions import DatabaseError

        try:
            client = self._get_supabase_client()

            query = (
                client.table("lead_memory_contributions")
                .select("*")
                .eq("lead_memory_id", lead_memory_id)
                .eq("status", ContributionStatus.PENDING.value)
                .order("created_at", desc=True)
            )

            response = query.execute()

            contributions = []
            for item in response.data:
                contribution_dict = cast(dict[str, Any], item)
                contributions.append(Contribution.from_dict(contribution_dict))

            logger.info(
                "Retrieved pending contributions",
                extra={
                    "user_id": user_id,
                    "lead_memory_id": lead_memory_id,
                    "count": len(contributions),
                },
            )

            return contributions

        except Exception as e:
            logger.exception("Failed to get pending contributions")
            raise DatabaseError(f"Failed to get pending contributions: {e}") from e

    async def review_contribution(
        self,
        user_id: str,
        contribution_id: str,
        action: str,
    ) -> None:
        """Review a contribution (merge or reject).

        Args:
            user_id: The user reviewing the contribution (lead owner).
            contribution_id: The contribution ID to review.
            action: Action to take - "merge" or "reject".

        Raises:
            ValidationError: If action is invalid.
            DatabaseError: If review fails.
        """
        from src.core.exceptions import DatabaseError, ValidationError

        # Validate action
        if action not in ("merge", "reject"):
            raise ValidationError(
                f"Invalid action: {action}. Must be 'merge' or 'reject'.", field="action"
            )

        # Map action to status
        status = ContributionStatus.MERGED if action == "merge" else ContributionStatus.REJECTED

        try:
            client = self._get_supabase_client()

            now = datetime.now(UTC)
            update_data = {
                "status": status.value,
                "reviewed_by": user_id,
                "reviewed_at": now.isoformat(),
            }

            response = (
                client.table("lead_memory_contributions")
                .update(update_data)
                .eq("id", contribution_id)
                .execute()
            )

            if not response.data or len(response.data) == 0:
                raise DatabaseError(f"Contribution {contribution_id} not found")

            logger.info(
                "Contribution reviewed",
                extra={
                    "contribution_id": contribution_id,
                    "user_id": user_id,
                    "action": action,
                    "status": status.value,
                },
            )

        except ValidationError:
            raise
        except DatabaseError:
            raise
        except Exception as e:
            logger.exception("Failed to review contribution")
            raise DatabaseError(f"Failed to review contribution: {e}") from e

    async def get_contributors(
        self,
        user_id: str,
        lead_memory_id: str,
    ) -> list[Contributor]:
        """Get all contributors for a lead.

        Contributors are users who have submitted at least one contribution
        to the lead. Includes contribution counts.

        Args:
            user_id: The user who owns the lead.
            lead_memory_id: The lead memory ID.

        Returns:
            List of Contributor instances with contribution counts.

        Raises:
            DatabaseError: If retrieval fails.
        """
        from src.core.exceptions import DatabaseError

        try:
            client = self._get_supabase_client()

            # Get all contributions for this lead
            response = (
                client.table("lead_memory_contributions")
                .select("contributor_id, created_at")
                .eq("lead_memory_id", lead_memory_id)
                .execute()
            )

            # Aggregate unique contributors with counts and earliest added_at
            contributor_data: dict[str, dict[str, Any]] = {}
            for item in response.data:
                contrib = cast(dict[str, Any], item)
                contributor_id = cast(str, contrib["contributor_id"])
                created_at = contrib.get("created_at")

                # Skip contributions without created_at
                if not created_at:
                    continue

                if contributor_id not in contributor_data:
                    contributor_data[contributor_id] = {
                        "count": 0,
                        "added_at": created_at,
                    }
                else:
                    # Track the earliest (first) contribution timestamp
                    current = created_at
                    existing = contributor_data[contributor_id]["added_at"]
                    if (
                        isinstance(current, str)
                        and isinstance(existing, str)
                        and current < existing
                    ):
                        contributor_data[contributor_id]["added_at"] = current

                contributor_data[contributor_id]["count"] += 1

            # Get user profiles for names/emails
            contributors = []
            if contributor_data:
                user_ids = list(contributor_data.keys())
                users_response = (
                    client.table("user_profiles")
                    .select("id, full_name, email")
                    .in_("id", user_ids)
                    .execute()
                )

                user_map: dict[str, dict[str, str]] = {}
                for user in users_response.data:
                    user_dict = cast(dict[str, Any], user)
                    user_map[cast(str, user_dict["id"])] = {
                        "name": cast(str, user_dict.get("full_name", "")),
                        "email": cast(str, user_dict.get("email", "")),
                    }

                for contributor_id, data in contributor_data.items():
                    user_info = user_map.get(contributor_id, {"name": "", "email": ""})
                    added_at_raw = data["added_at"]

                    # Parse datetime (already validated to be non-None above)
                    added_at = (
                        datetime.fromisoformat(added_at_raw)
                        if isinstance(added_at_raw, str)
                        else added_at_raw
                    )

                    contributors.append(
                        Contributor(
                            id=contributor_id,
                            lead_memory_id=lead_memory_id,
                            name=user_info["name"],
                            email=user_info["email"],
                            added_at=added_at,
                            contribution_count=data["count"],
                        )
                    )

            # Sort contributors by added_at ascending (oldest first)
            contributors.sort(key=lambda c: c.added_at)

            logger.info(
                "Retrieved contributors",
                extra={
                    "user_id": user_id,
                    "lead_memory_id": lead_memory_id,
                    "count": len(contributors),
                },
            )

            return contributors

        except Exception as e:
            logger.exception("Failed to get contributors")
            raise DatabaseError(f"Failed to get contributors: {e}") from e
