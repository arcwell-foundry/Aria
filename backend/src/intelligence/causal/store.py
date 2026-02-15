"""Database store for causal chains.

This module provides persistence for causal chains, allowing them to be
stored, retrieved, and invalidated as needed.
"""

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from src.intelligence.causal.models import CausalChain

logger = logging.getLogger(__name__)


class CausalChainStore:
    """Store for persisting and retrieving causal chains.

    Provides CRUD operations for causal chains in the Supabase database.
    Supports user-scoped queries and chain invalidation.
    """

    def __init__(self, db_client: Any) -> None:
        """Initialize the causal chain store.

        Args:
            db_client: Supabase client instance
        """
        self._db = db_client

    async def save_chain(
        self,
        user_id: str,
        chain: CausalChain,
        source_context: str,
        source_id: str | None = None,
    ) -> UUID:
        """Save a causal chain to the database.

        Args:
            user_id: User ID who owns this chain
            chain: The causal chain to save
            source_context: Context where chain was discovered (e.g., "signal_analysis")
            source_id: Optional ID of the source that triggered this analysis

        Returns:
            UUID of the saved chain

        Raises:
            Exception: If database operation fails
        """
        try:
            # Convert hops to JSON-serializable format
            hops_data = [hop.model_dump() for hop in chain.hops]

            data = {
                "user_id": user_id,
                "trigger_event": chain.trigger_event,
                "hops": hops_data,
                "final_confidence": chain.final_confidence,
                "time_to_impact": chain.time_to_impact,
                "source_context": source_context,
                "source_id": source_id,
            }

            result = self._db.table("causal_chains").insert(data).execute()

            if result.data:
                chain_id = UUID(result.data[0]["id"])
                logger.debug(
                    "Saved causal chain",
                    extra={
                        "chain_id": str(chain_id),
                        "user_id": user_id,
                        "hops_count": len(chain.hops),
                    },
                )
                return chain_id

            raise Exception("Failed to save causal chain: no data returned")

        except Exception as e:
            logger.exception(f"Failed to save causal chain: {e}")
            raise

    async def get_chains(
        self,
        user_id: str,
        limit: int = 20,
        source_context: str | None = None,
    ) -> list[CausalChain]:
        """Get recent causal chains for a user.

        Args:
            user_id: User ID to get chains for
            limit: Maximum number of chains to return
            source_context: Optional filter by source context

        Returns:
            List of causal chains, most recent first
        """
        try:
            query = (
                self._db.table("causal_chains")
                .select("*")
                .eq("user_id", user_id)
                .is_("invalidated_at", "null")
                .order("created_at", desc=True)
                .limit(limit)
            )

            if source_context:
                query = query.eq("source_context", source_context)

            result = query.execute()

            chains = []
            for row in result.data or []:
                chain = self._row_to_chain(row)
                if chain:
                    chains.append(chain)

            return chains

        except Exception as e:
            logger.exception(f"Failed to get causal chains: {e}")
            return []

    async def get_chain(self, chain_id: UUID) -> CausalChain | None:
        """Get a specific causal chain by ID.

        Args:
            chain_id: UUID of the chain to retrieve

        Returns:
            The causal chain, or None if not found
        """
        try:
            result = (
                self._db.table("causal_chains")
                .select("*")
                .eq("id", str(chain_id))
                .single()
                .execute()
            )

            if result.data:
                return self._row_to_chain(result.data)

            return None

        except Exception as e:
            logger.warning(f"Failed to get causal chain {chain_id}: {e}")
            return None

    async def invalidate_chain(self, chain_id: UUID) -> bool:
        """Mark a causal chain as invalidated.

        Invalidated chains are kept for history but excluded from
        normal queries.

        Args:
            chain_id: UUID of the chain to invalidate

        Returns:
            True if successful, False otherwise
        """
        try:
            result = (
                self._db.table("causal_chains")
                .update({"invalidated_at": datetime.now(UTC).isoformat()})
                .eq("id", str(chain_id))
                .execute()
            )

            success = bool(result.data)
            if success:
                logger.debug(f"Invalidated causal chain {chain_id}")

            return success

        except Exception as e:
            logger.warning(f"Failed to invalidate causal chain {chain_id}: {e}")
            return False

    async def invalidate_chains_for_source(
        self,
        user_id: str,
        source_context: str,
        source_id: str,
    ) -> int:
        """Invalidate all chains for a specific source.

        Useful when new information makes previous chains obsolete.

        Args:
            user_id: User ID
            source_context: Context type (e.g., "signal_analysis")
            source_id: ID of the source

        Returns:
            Number of chains invalidated
        """
        try:
            result = (
                self._db.table("causal_chains")
                .update({"invalidated_at": datetime.now(UTC).isoformat()})
                .eq("user_id", user_id)
                .eq("source_context", source_context)
                .eq("source_id", source_id)
                .is_("invalidated_at", "null")
                .execute()
            )

            count = len(result.data) if result.data else 0
            if count > 0:
                logger.debug(
                    f"Invalidated {count} causal chains for source {source_context}/{source_id}"
                )

            return count

        except Exception as e:
            logger.warning(f"Failed to invalidate chains for source: {e}")
            return 0

    async def get_chains_by_entity(
        self,
        user_id: str,
        entity_name: str,
        limit: int = 10,
    ) -> list[CausalChain]:
        """Get chains that involve a specific entity.

        Searches both source and target entities across all hops.

        Args:
            user_id: User ID
            entity_name: Name of the entity to search for
            limit: Maximum chains to return

        Returns:
            List of chains involving the entity
        """
        try:
            # This requires a more complex query with JSONB
            # For now, fetch recent chains and filter in Python
            result = (
                self._db.table("causal_chains")
                .select("*")
                .eq("user_id", user_id)
                .is_("invalidated_at", "null")
                .order("created_at", desc=True)
                .limit(100)
                .execute()
            )

            matching_chains: list[CausalChain] = []
            entity_lower = entity_name.lower()

            for row in result.data or []:
                chain = self._row_to_chain(row)
                if not chain:
                    continue

                # Check if entity appears in any hop
                for hop in chain.hops:
                    if (
                        entity_lower in hop.source_entity.lower()
                        or entity_lower in hop.target_entity.lower()
                    ):
                        matching_chains.append(chain)
                        break

                if len(matching_chains) >= limit:
                    break

            return matching_chains

        except Exception as e:
            logger.warning(f"Failed to get chains by entity: {e}")
            return []

    def _row_to_chain(self, row: dict[str, Any]) -> CausalChain | None:
        """Convert a database row to a CausalChain model.

        Args:
            row: Database row dictionary

        Returns:
            CausalChain model, or None if conversion fails
        """
        try:
            from src.intelligence.causal.models import CausalHop

            hops_data = row.get("hops", [])
            hops = [CausalHop(**hop) for hop in hops_data]

            created_at_str = row.get("created_at")
            created_at = None
            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            source_id_str = row.get("source_id")
            source_id = UUID(source_id_str) if source_id_str else None

            return CausalChain(
                id=UUID(row["id"]),
                trigger_event=row["trigger_event"],
                hops=hops,
                final_confidence=row["final_confidence"],
                time_to_impact=row.get("time_to_impact"),
                source_context=row.get("source_context"),
                source_id=source_id,
                created_at=created_at,
            )

        except Exception as e:
            logger.warning(f"Failed to convert row to chain: {e}")
            return None
