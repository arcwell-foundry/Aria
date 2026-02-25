"""Shared Intelligence module for team-level knowledge sharing.

Enables team members to benefit from each other's insights about shared
accounts while maintaining proper privacy controls and attribution.

Key features:
- User opt-in required for sharing
- Anonymizable contributor attribution
- Confidence aggregation from multiple contributions
- Account-scoped fact storage
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, cast

from src.db.supabase import SupabaseClient
from src.memory.audit import MemoryOperation, MemoryType, log_memory_operation

if TYPE_CHECKING:
    from graphiti_core import Graphiti

logger = logging.getLogger(__name__)


class IntelligenceSource(Enum):
    """Source of shared intelligence."""

    GOAL_EXECUTION = "goal_execution"  # Extracted from agent goal execution
    MANUAL_ENTRY = "manual_entry"  # User manually added
    AGGREGATED = "aggregated"  # Aggregated from multiple contributions


@dataclass
class SharedFact:
    """A fact shared across team members about an account or contact."""

    id: str
    company_id: str
    subject: str
    predicate: str
    object: str
    confidence: float
    source_type: IntelligenceSource
    contribution_count: int
    contributed_by: str
    is_anonymized: bool
    related_account_name: str | None
    related_lead_id: str | None
    is_shareable: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
    graphiti_episode_name: str | None = None
    invalidated_at: datetime | None = None
    invalidation_reason: str | None = None

    def to_dict(self, viewer_id: str | None = None, include_contributor: bool = False) -> dict[str, Any]:
        """Serialize fact to dictionary with optional contributor info.

        Args:
            viewer_id: ID of user viewing the fact (for permission checks).
            include_contributor: Whether to include contributor attribution.

        Returns:
            Dictionary suitable for API responses.
        """
        result = {
            "id": self.id,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "confidence": self.confidence,
            "source_type": self.source_type.value,
            "contribution_count": self.contribution_count,
            "related_account_name": self.related_account_name,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
        }

        if include_contributor:
            # Include anonymized attribution unless viewer is admin or contributor
            result["contributed_by"] = self._get_contributor_display(viewer_id)

        return result

    def _get_contributor_display(self, viewer_id: str | None) -> str:
        """Get display name for contributor based on permissions.

        Args:
            viewer_id: ID of user viewing the fact.

        Returns:
            Contributor display name or "Team Member" if anonymized.
        """
        if not self.is_anonymized:
            # Not anonymized - show contributor
            return "contributor"

        if viewer_id and viewer_id == self.contributed_by:
            # Viewer is the contributor - they can see their own name
            return "you"

        # Anonymized - return generic
        return "Team Member"

    def to_fact_string(self) -> str:
        """Format as human-readable fact string.

        Returns:
            Fact in "subject predicate object" format.
        """
        return f"{self.subject} {self.predicate} {self.object}"


@dataclass
class UserOptInStatus:
    """User's team intelligence sharing preferences."""

    user_id: str
    company_id: str
    opted_in: bool
    opted_in_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "user_id": self.user_id,
            "company_id": self.company_id,
            "opted_in": self.opted_in,
            "opted_in_at": self.opted_in_at.isoformat() if self.opted_in_at else None,
        }


class SharedIntelligenceService:
    """Service for managing team-level shared intelligence.

    Provides methods for:
    - Opt-in management
    - Contributing facts from goal executions
    - Querying shared intelligence for context injection
    - Confidence aggregation from multiple contributions
    """

    def __init__(self) -> None:
        """Initialize service with database client."""
        self._db = SupabaseClient.get_client()

    # ── Opt-In Management ─────────────────────────────────────────────────────

    async def get_opt_in_status(self, user_id: str) -> UserOptInStatus | None:
        """Get user's team intelligence sharing preference.

        Args:
            user_id: The user to check.

        Returns:
            UserOptInStatus if user has a profile, None otherwise.
        """
        try:
            result = (
                self._db.table("user_profiles")
                .select("id, company_id, team_intelligence_opt_in, team_intelligence_opt_in_at")
                .eq("id", user_id)
                .maybe_single()
                .execute()
            )

            if not result or not result.data:
                return None

            data = result.data
            return UserOptInStatus(
                user_id=user_id,
                company_id=data.get("company_id") or "",
                opted_in=data.get("team_intelligence_opt_in", False),
                opted_in_at=(
                    datetime.fromisoformat(data["team_intelligence_opt_in_at"])
                    if data.get("team_intelligence_opt_in_at")
                    else None
                ),
            )

        except Exception as e:
            logger.warning(
                "Failed to get opt-in status",
                extra={"user_id": user_id, "error": str(e)},
            )
            return None

    async def set_opt_in(
        self,
        user_id: str,
        opted_in: bool,
    ) -> UserOptInStatus | None:
        """Set user's team intelligence sharing preference.

        Args:
            user_id: The user to update.
            opted_in: Whether to opt in to sharing.

        Returns:
            Updated UserOptInStatus if successful, None otherwise.
        """
        try:
            now = datetime.now(UTC).isoformat()

            result = (
                self._db.table("user_profiles")
                .update({
                    "team_intelligence_opt_in": opted_in,
                    "team_intelligence_opt_in_at": now,
                    "updated_at": now,
                })
                .eq("id", user_id)
                .select("id, company_id, team_intelligence_opt_in, team_intelligence_opt_in_at")
                .single()
                .execute()
            )

            if not result or not result.data:
                return None

            data = result.data
            logger.info(
                "Team intelligence opt-in updated",
                extra={"user_id": user_id, "opted_in": opted_in},
            )

            return UserOptInStatus(
                user_id=user_id,
                company_id=data.get("company_id") or "",
                opted_in=data.get("team_intelligence_opt_in", False),
                opted_in_at=(
                    datetime.fromisoformat(data["team_intelligence_opt_in_at"])
                    if data.get("team_intelligence_opt_in_at")
                    else None
                ),
            )

        except Exception as e:
            logger.warning(
                "Failed to set opt-in status",
                extra={"user_id": user_id, "error": str(e)},
            )
            return None

    async def is_user_opted_in(self, user_id: str) -> bool:
        """Check if user has opted into team intelligence sharing.

        Args:
            user_id: The user to check.

        Returns:
            True if user has opted in, False otherwise.
        """
        status = await self.get_opt_in_status(user_id)
        return status.opted_in if status else False

    # ── Fact Contribution ──────────────────────────────────────────────────────

    async def contribute_fact(
        self,
        user_id: str,
        company_id: str,
        subject: str,
        predicate: str,
        object: str,
        confidence: float = 0.7,
        related_account_name: str | None = None,
        related_lead_id: str | None = None,
        source_type: IntelligenceSource = IntelligenceSource.GOAL_EXECUTION,
        is_anonymized: bool = True,
    ) -> str | None:
        """Contribute a fact to the shared intelligence pool.

        If the same fact (same subject+predicate) already exists from another user,
        increments contribution_count and aggregates confidence.

        Args:
            user_id: The contributing user.
            company_id: The company to share within.
            subject: Entity the fact is about.
            predicate: Relationship type.
            object: Value or related entity.
            confidence: Initial confidence (0-1).
            related_account_name: Account this fact relates to.
            related_lead_id: Lead ID if applicable.
            source_type: Source of this fact.
            is_anonymized: Whether to anonymize contributor attribution.

        Returns:
            Fact ID if successful, None otherwise.
        """
        try:
            # Check if user has opted in
            if not await self.is_user_opted_in(user_id):
                logger.debug(
                    "User not opted in, skipping contribution",
                    extra={"user_id": user_id},
                )
                return None

            # Check if similar fact already exists
            existing = await self._find_existing_fact(
                company_id=company_id,
                subject=subject,
                predicate=predicate,
                object=object,
            )

            if existing:
                # Increment contribution count and aggregate confidence
                new_count = existing.contribution_count + 1
                # Confidence aggregation: weighted average with boost for multiple sources
                aggregated_confidence = min(
                    0.95,
                    (existing.confidence * existing.contribution_count + confidence)
                    / new_count
                    + (0.05 * (new_count - 1)),  # Boost for corroboration
                )

                self._db.table("shared_intelligence").update({
                    "contribution_count": new_count,
                    "confidence": aggregated_confidence,
                    "source_type": IntelligenceSource.AGGREGATED.value,
                    "updated_at": datetime.now(UTC).isoformat(),
                }).eq("id", existing.id).execute()

                logger.info(
                    "Aggregated shared intelligence fact",
                    extra={
                        "fact_id": existing.id,
                        "contribution_count": new_count,
                        "confidence": aggregated_confidence,
                    },
                )

                return existing.id

            # Create new fact
            fact_id = str(uuid.uuid4())

            result = (
                self._db.table("shared_intelligence")
                .insert({
                    "id": fact_id,
                    "company_id": company_id,
                    "subject": subject,
                    "predicate": predicate,
                    "object": object,
                    "confidence": confidence,
                    "source_type": source_type.value,
                    "contribution_count": 1,
                    "contributed_by": user_id,
                    "is_anonymized": is_anonymized,
                    "related_account_name": related_account_name,
                    "related_lead_id": related_lead_id,
                    "is_shareable": True,
                    "is_active": True,
                })
                .execute()
            )

            if result.data:
                logger.info(
                    "Contributed shared intelligence fact",
                    extra={
                        "fact_id": fact_id,
                        "user_id": user_id,
                        "subject": subject,
                        "predicate": predicate,
                    },
                )

                # Audit log
                await log_memory_operation(
                    user_id=user_id,
                    operation=MemoryOperation.CREATE,
                    memory_type=MemoryType.SEMANTIC,
                    memory_id=fact_id,
                    metadata={
                        "shared": True,
                        "company_id": company_id,
                        "subject": subject,
                    },
                    suppress_errors=True,
                )

                return fact_id

            return None

        except Exception as e:
            logger.warning(
                "Failed to contribute shared intelligence",
                extra={
                    "user_id": user_id,
                    "subject": subject,
                    "error": str(e),
                },
            )
            return None

    async def _find_existing_fact(
        self,
        company_id: str,
        subject: str,
        predicate: str,
        object: str,
    ) -> SharedFact | None:
        """Find an existing fact with matching content.

        Args:
            company_id: Company to search within.
            subject: Fact subject.
            predicate: Fact predicate.
            object: Fact object.

        Returns:
            SharedFact if found, None otherwise.
        """
        try:
            result = (
                self._db.table("shared_intelligence")
                .select("*")
                .eq("company_id", company_id)
                .eq("subject", subject)
                .eq("predicate", predicate)
                .eq("object", object)
                .eq("is_active", True)
                .maybe_single()
                .execute()
            )

            if result and result.data:
                return self._row_to_fact(result.data)

            return None

        except Exception:
            return None

    # ── Fact Consumption ───────────────────────────────────────────────────────

    async def get_facts_for_account(
        self,
        company_id: str,
        account_name: str,
        user_id: str | None = None,
        limit: int = 20,
    ) -> list[SharedFact]:
        """Get shared intelligence facts about a specific account.

        Args:
            company_id: Company to search within.
            account_name: Account name to filter by.
            user_id: Requesting user (for opt-in check).
            limit: Maximum facts to return.

        Returns:
            List of SharedFact instances.
        """
        if user_id and not await self.is_user_opted_in(user_id):
            return []

        try:
            result = (
                self._db.table("shared_intelligence")
                .select("*")
                .eq("company_id", company_id)
                .ilike("related_account_name", f"%{account_name}%")
                .eq("is_active", True)
                .order("confidence", desc=True)
                .limit(limit)
                .execute()
            )

            if result.data:
                return [self._row_to_fact(row) for row in result.data]

            return []

        except Exception as e:
            logger.warning(
                "Failed to get facts for account",
                extra={
                    "company_id": company_id,
                    "account_name": account_name,
                    "error": str(e),
                },
            )
            return []

    async def get_facts_for_lead(
        self,
        company_id: str,
        lead_id: str,
        user_id: str | None = None,
        limit: int = 20,
    ) -> list[SharedFact]:
        """Get shared intelligence facts about a specific lead.

        Args:
            company_id: Company to search within.
            lead_id: Lead ID to filter by.
            user_id: Requesting user (for opt-in check).
            limit: Maximum facts to return.

        Returns:
            List of SharedFact instances.
        """
        if user_id and not await self.is_user_opted_in(user_id):
            return []

        try:
            result = (
                self._db.table("shared_intelligence")
                .select("*")
                .eq("company_id", company_id)
                .eq("related_lead_id", lead_id)
                .eq("is_active", True)
                .order("confidence", desc=True)
                .limit(limit)
                .execute()
            )

            if result.data:
                return [self._row_to_fact(row) for row in result.data]

            return []

        except Exception as e:
            logger.warning(
                "Failed to get facts for lead",
                extra={
                    "company_id": company_id,
                    "lead_id": lead_id,
                    "error": str(e),
                },
            )
            return []

    async def get_all_company_facts(
        self,
        company_id: str,
        user_id: str | None = None,
        limit: int = 50,
    ) -> list[SharedFact]:
        """Get all shared intelligence for a company.

        Args:
            company_id: Company to get facts for.
            user_id: Requesting user (for opt-in check).
            limit: Maximum facts to return.

        Returns:
            List of SharedFact instances.
        """
        if user_id and not await self.is_user_opted_in(user_id):
            return []

        try:
            result = (
                self._db.table("shared_intelligence")
                .select("*")
                .eq("company_id", company_id)
                .eq("is_active", True)
                .order("contribution_count", desc=True)
                .order("confidence", desc=True)
                .limit(limit)
                .execute()
            )

            if result.data:
                return [self._row_to_fact(row) for row in result.data]

            return []

        except Exception as e:
            logger.warning(
                "Failed to get company facts",
                extra={"company_id": company_id, "error": str(e)},
            )
            return []

    async def search_facts(
        self,
        company_id: str,
        query: str,
        user_id: str | None = None,
        min_confidence: float = 0.5,
        limit: int = 20,
    ) -> list[SharedFact]:
        """Search shared intelligence by text query.

        Args:
            company_id: Company to search within.
            query: Search query text.
            user_id: Requesting user (for opt-in check).
            min_confidence: Minimum confidence threshold.
            limit: Maximum facts to return.

        Returns:
            List of matching SharedFact instances.
        """
        if user_id and not await self.is_user_opted_in(user_id):
            return []

        try:
            # Search in subject, predicate, object, and account name
            result = (
                self._db.table("shared_intelligence")
                .select("*")
                .eq("company_id", company_id)
                .eq("is_active", True)
                .gte("confidence", min_confidence)
                .or_(f"subject.ilike.%{query}%,predicate.ilike.%{query}%,object.ilike.%{query}%,related_account_name.ilike.%{query}%")
                .order("confidence", desc=True)
                .limit(limit)
                .execute()
            )

            if result.data:
                return [self._row_to_fact(row) for row in result.data]

            return []

        except Exception as e:
            logger.warning(
                "Failed to search shared intelligence",
                extra={
                    "company_id": company_id,
                    "query": query,
                    "error": str(e),
                },
            )
            return []

    async def get_formatted_team_context(
        self,
        company_id: str,
        account_name: str | None = None,
        lead_id: str | None = None,
        user_id: str | None = None,
        max_facts: int = 10,
    ) -> str:
        """Get formatted team intelligence context for LLM injection.

        This is the primary method for injecting shared intelligence
        into chat/system prompts.

        Args:
            company_id: Company to get facts for.
            account_name: Optional account name to filter by.
            lead_id: Optional lead ID to filter by.
            user_id: Requesting user (for opt-in check).
            max_facts: Maximum facts to include.

        Returns:
            Formatted string for LLM context, or empty string if none.
        """
        facts: list[SharedFact] = []

        # Get facts based on filters
        if account_name:
            facts = await self.get_facts_for_account(
                company_id=company_id,
                account_name=account_name,
                user_id=user_id,
                limit=max_facts,
            )
        elif lead_id:
            facts = await self.get_facts_for_lead(
                company_id=company_id,
                lead_id=lead_id,
                user_id=user_id,
                limit=max_facts,
            )
        else:
            facts = await self.get_all_company_facts(
                company_id=company_id,
                user_id=user_id,
                limit=max_facts,
            )

        if not facts:
            return ""

        # Format for LLM consumption
        lines = ["## Team Intelligence", ""]
        lines.append("The following insights have been gathered by your team about shared accounts:")
        lines.append("")

        for fact in facts:
            conf_str = f" ({fact.confidence:.0%} confidence)" if fact.confidence < 0.9 else ""
            contrib_str = ""
            if fact.contribution_count > 1:
                contrib_str = f" [corroborated by {fact.contribution_count} team members]"

            lines.append(f"- {fact.to_fact_string()}{conf_str}{contrib_str}")

        lines.append("")
        lines.append(
            "Reference these insights naturally when relevant. "
            "You can say \"Based on what the team has learned...\" when drawing on this context."
        )

        return "\n".join(lines)

    # ── Helper Methods ─────────────────────────────────────────────────────────

    def _row_to_fact(self, row: dict[str, Any]) -> SharedFact:
        """Convert database row to SharedFact instance.

        Args:
            row: Database row dictionary.

        Returns:
            SharedFact instance.
        """
        return SharedFact(
            id=row["id"],
            company_id=row["company_id"],
            subject=row["subject"],
            predicate=row["predicate"],
            object=row["object"],
            confidence=row["confidence"],
            source_type=IntelligenceSource(row["source_type"]),
            contribution_count=row["contribution_count"],
            contributed_by=row["contributed_by"],
            is_anonymized=row["is_anonymized"],
            related_account_name=row.get("related_account_name"),
            related_lead_id=row.get("related_lead_id"),
            is_shareable=row.get("is_shareable", True),
            is_active=row.get("is_active", True),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            graphiti_episode_name=row.get("graphiti_episode_name"),
            invalidated_at=(
                datetime.fromisoformat(row["invalidated_at"])
                if row.get("invalidated_at")
                else None
            ),
            invalidation_reason=row.get("invalidation_reason"),
        )


# Singleton instance
_shared_intelligence_service: SharedIntelligenceService | None = None


def get_shared_intelligence_service() -> SharedIntelligenceService:
    """Get or create the SharedIntelligenceService singleton.

    Returns:
        The singleton SharedIntelligenceService instance.
    """
    global _shared_intelligence_service  # noqa: PLW0603
    if _shared_intelligence_service is None:
        _shared_intelligence_service = SharedIntelligenceService()
    return _shared_intelligence_service
