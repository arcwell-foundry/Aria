"""Memory salience decay service.

Implements salience decay for memory prioritization:
- Recent memories have higher salience
- Frequently accessed memories decay slower
- All memories have a minimum salience (never truly forgotten)

Formula: salience = (base + access_boost) x 0.5^(days_since_access / half_life)
"""

import logging
import math
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from src.core.config import settings

if TYPE_CHECKING:
    from supabase import Client

logger = logging.getLogger(__name__)

# Type alias for memory types
MemoryType = Literal["episodic", "semantic", "lead"]


class SalienceService:
    """Service for calculating and managing memory salience.

    Salience represents how "prominent" a memory is based on recency
    and access frequency. Higher salience = more likely to be surfaced.
    """

    def __init__(
        self,
        db_client: "Client",
        half_life_days: float | None = None,
        access_boost: float | None = None,
        min_salience: float | None = None,
    ) -> None:
        """Initialize the salience service.

        Args:
            db_client: Supabase client for database operations.
            half_life_days: Days for salience to decay to 50%. Defaults to settings.
            access_boost: Boost per memory retrieval. Defaults to settings.
            min_salience: Minimum salience floor. Defaults to settings.
        """
        self.db = db_client
        self.half_life_days = (
            half_life_days if half_life_days is not None else settings.SALIENCE_HALF_LIFE_DAYS
        )
        self.access_boost = (
            access_boost if access_boost is not None else settings.SALIENCE_ACCESS_BOOST
        )
        self.min_salience = min_salience if min_salience is not None else settings.SALIENCE_MIN

    def calculate_decay(
        self,
        access_count: int,
        days_since_last_access: float,
    ) -> float:
        """Calculate current salience with exponential decay.

        Formula: salience = (1.0 + access_count * access_boost) x 0.5^(days / half_life)

        The base salience is always 1.0. Access boosts are additive to this base.
        Decay is exponential with the configured half-life.

        Args:
            access_count: Number of times the memory has been accessed.
            days_since_last_access: Days since the memory was last accessed.

        Returns:
            Current salience between min_salience and (1.0 + total_boost).
        """
        # Calculate base with access boost
        base_salience = 1.0 + (access_count * self.access_boost)

        # Calculate decay factor using half-life formula
        # decay_factor = 0.5^(days / half_life)
        if days_since_last_access <= 0:
            decay_factor = 1.0
        else:
            decay_factor = math.pow(0.5, days_since_last_access / self.half_life_days)

        # Apply decay to base
        current_salience = base_salience * decay_factor

        # Enforce minimum salience (memories never truly forgotten)
        return max(current_salience, self.min_salience)

    def calculate_decay_from_timestamp(
        self,
        access_count: int,
        last_accessed_at: datetime,
        as_of: datetime | None = None,
    ) -> float:
        """Calculate salience from a timestamp.

        Convenience method that calculates days from timestamps.

        Args:
            access_count: Number of times the memory has been accessed.
            last_accessed_at: When the memory was last accessed.
            as_of: Point in time to calculate for. Defaults to now.

        Returns:
            Current salience value.
        """
        check_time = as_of or datetime.now(UTC)
        days_since = (check_time - last_accessed_at).total_seconds() / 86400
        return self.calculate_decay(access_count, days_since)

    async def record_access(
        self,
        memory_id: str,
        memory_type: MemoryType,
        user_id: str,
        context: str | None = None,
    ) -> None:
        """Record memory access and update salience tracking.

        This should be called whenever a memory is retrieved/used.
        It logs the access and updates the salience tracking table.

        Args:
            memory_id: The Graphiti episode ID or other memory identifier.
            memory_type: Type of memory ('episodic', 'semantic', or 'lead').
            user_id: The user who accessed the memory.
            context: Optional context describing what triggered the access.
        """
        try:
            # 1. Log the access
            self._log_access(memory_id, memory_type, user_id, context)

            # 2. Update salience tracking
            self._update_salience_tracking(memory_id, memory_type, user_id)

        except Exception as e:
            # Log but don't fail - salience tracking is non-critical
            logger.warning(
                "Failed to record memory access",
                extra={
                    "memory_id": memory_id,
                    "memory_type": memory_type,
                    "user_id": user_id,
                    "error": str(e),
                },
            )

    def _log_access(
        self,
        memory_id: str,
        memory_type: MemoryType,
        user_id: str,
        context: str | None,
    ) -> None:
        """Insert a record into memory_access_log."""
        self.db.table("memory_access_log").insert(
            {
                "memory_id": memory_id,
                "memory_type": memory_type,
                "user_id": user_id,
                "access_context": context,
            }
        ).execute()

    def _update_salience_tracking(
        self,
        memory_id: str,
        memory_type: MemoryType,
        user_id: str,
    ) -> None:
        """Upsert the salience tracking table with updated access info."""
        # Determine which table to use
        if memory_type == "episodic":
            table_name = "episodic_memory_salience"
        else:
            # Both semantic and lead use semantic_fact_salience
            table_name = "semantic_fact_salience"

        now = datetime.now(UTC).isoformat()

        # Try to get existing record
        existing = (
            self.db.table(table_name)
            .select("id, access_count")
            .eq("user_id", user_id)
            .eq("graphiti_episode_id", memory_id)
            .single()
            .execute()
        )

        if existing.data:
            # Update existing record
            new_count = existing.data["access_count"] + 1
            new_salience = self.calculate_decay(access_count=new_count, days_since_last_access=0)

            self.db.table(table_name).update(
                {
                    "access_count": new_count,
                    "last_accessed_at": now,
                    "current_salience": new_salience,
                }
            ).eq("id", existing.data["id"]).execute()
        else:
            # Insert new record
            self.db.table(table_name).insert(
                {
                    "user_id": user_id,
                    "graphiti_episode_id": memory_id,
                    "current_salience": 1.0,
                    "last_accessed_at": now,
                    "access_count": 1,
                }
            ).execute()

    async def update_all_salience(self, user_id: str) -> int:
        """Batch update salience for all user memories.

        This is designed to be called by a background job (e.g., daily cron).
        It recalculates salience for all memories and updates those that have
        changed significantly (> 0.01 difference).

        Args:
            user_id: The user whose memories to update.

        Returns:
            Number of records that were updated.
        """
        updated_count = 0

        for table_name in ["episodic_memory_salience", "semantic_fact_salience"]:
            try:
                updated_count += self._update_table_salience(table_name, user_id)
            except Exception as e:
                logger.error(
                    f"Failed to update salience for {table_name}",
                    extra={"user_id": user_id, "error": str(e)},
                )

        return updated_count

    def _update_table_salience(self, table_name: str, user_id: str) -> int:
        """Update salience for all records in a specific table."""
        # Fetch all salience records for this user
        result = (
            self.db.table(table_name)
            .select("id, current_salience, access_count, last_accessed_at")
            .eq("user_id", user_id)
            .execute()
        )

        if not result.data:
            return 0

        updated = 0
        now = datetime.now(UTC)

        for record in result.data:
            # Parse the last_accessed_at timestamp
            last_accessed = datetime.fromisoformat(record["last_accessed_at"])
            days_since = (now - last_accessed).total_seconds() / 86400

            # Calculate new salience
            new_salience = self.calculate_decay(
                access_count=record["access_count"],
                days_since_last_access=days_since,
            )

            # Only update if salience changed significantly (> 0.01)
            if abs(new_salience - record["current_salience"]) > 0.01:
                self.db.table(table_name).update({"current_salience": new_salience}).eq(
                    "id", record["id"]
                ).execute()
                updated += 1

        return updated

    async def get_by_salience(
        self,
        user_id: str,
        memory_type: MemoryType,
        min_salience: float = 0.1,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get memory IDs filtered by salience threshold.

        Returns the Graphiti episode IDs of memories that meet the
        salience threshold, ordered by salience descending.

        Args:
            user_id: The user whose memories to query.
            memory_type: Type of memory ('episodic', 'semantic', or 'lead').
            min_salience: Minimum salience threshold (default 0.1).
            limit: Maximum number of results (default 10).

        Returns:
            List of salience records with graphiti_episode_id and salience info.
        """
        # Determine table name
        if memory_type == "episodic":
            table_name = "episodic_memory_salience"
        else:
            table_name = "semantic_fact_salience"

        result = (
            self.db.table(table_name)
            .select("graphiti_episode_id, current_salience, access_count")
            .eq("user_id", user_id)
            .gte("current_salience", min_salience)
            .order("current_salience", desc=True)
            .limit(limit)
            .execute()
        )

        return result.data or []
