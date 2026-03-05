"""Market signal detection service for ARIA.

This service handles:
- Creating and querying market signals
- Managing read/dismissed states
- Managing monitored entities
"""

import logging
from datetime import UTC, datetime
from typing import Any, cast

from src.core.text_cleaning import clean_signal_summary
from src.db.supabase import SupabaseClient
from src.models.signal import (
    MonitoredEntityCreate,
    SignalCreate,
    SignalType,
)
from src.services import notification_integration
from src.services.activity_service import ActivityService

logger = logging.getLogger(__name__)


class SignalService:
    """Service for market signal detection and management."""

    def __init__(self) -> None:
        """Initialize signal service with Supabase client."""
        self._db = SupabaseClient.get_client()
        self._activity_service = ActivityService()

    async def create_signal(self, user_id: str, data: SignalCreate) -> dict[str, Any]:
        """Create a new market signal.

        Args:
            user_id: The user's ID.
            data: Signal creation data.

        Returns:
            Created signal dict.
        """
        logger.info(
            "Creating market signal",
            extra={
                "user_id": user_id,
                "company_name": data.company_name,
                "signal_type": data.signal_type.value,
            },
        )

        # Clean the summary to remove web scraping markup
        cleaned_summary = clean_signal_summary(
            raw_text=data.summary or "",
            headline=data.headline,
            max_length=500,
        )

        result = (
            self._db.table("market_signals")
            .insert(
                {
                    "user_id": user_id,
                    "company_name": data.company_name,
                    "signal_type": data.signal_type.value,
                    "headline": data.headline,
                    "summary": cleaned_summary,
                    "source_url": data.source_url,
                    "source_name": data.source_name,
                    "relevance_score": data.relevance_score,
                    "linked_lead_id": data.linked_lead_id,
                    "metadata": data.metadata,
                }
            )
            .execute()
        )

        signal = cast(dict[str, Any], result.data[0])
        logger.info("Market signal created", extra={"signal_id": signal["id"]})

        # Log to activity feed
        try:
            await self._activity_service.record(
                user_id=user_id,
                agent="scout",
                activity_type="signal_detected",
                title=f"Signal detected: {data.headline}",
                description=data.summary or "",
                confidence=data.relevance_score or 0.5,
                related_entity_type="lead" if data.linked_lead_id else None,
                related_entity_id=data.linked_lead_id,
                metadata={
                    "signal_id": signal["id"],
                    "signal_type": data.signal_type.value,
                    "company_name": data.company_name,
                },
            )
        except Exception:
            logger.warning("Failed to log signal activity", extra={"signal_id": signal["id"]})

        # Notify user about the detected signal
        await notification_integration.notify_signal_detected(
            user_id=user_id,
            company_name=data.company_name,
            signal_type=data.signal_type.value,
            headline=data.headline,
            lead_id=data.linked_lead_id,
        )

        # Evaluate for proactive goal proposal (best-effort)
        try:
            from src.services.proactive_goal_proposer import ProactiveGoalProposer

            proposer = ProactiveGoalProposer()
            await proposer.evaluate_signal(
                user_id=user_id,
                signal_id=signal["id"],
                signal_type=data.signal_type.value,
                headline=data.headline,
                summary=data.summary,
                relevance_score=data.relevance_score or 0.0,
                company_name=data.company_name,
            )
        except Exception:
            logger.debug("Proactive goal proposal evaluation failed", exc_info=True)

        return signal

    async def get_signals(
        self,
        user_id: str,
        unread_only: bool = False,
        signal_type: SignalType | None = None,
        company_name: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get signals with optional filters.

        Args:
            user_id: The user's ID.
            unread_only: Only return unread signals.
            signal_type: Filter by signal type.
            company_name: Filter by company name (case-insensitive partial match).
            limit: Maximum number of signals to return.

        Returns:
            List of signal dicts with fields mapped for frontend compatibility.
        """
        query = self._db.table("market_signals").select("*").eq("user_id", user_id)

        if unread_only:
            query = query.is_("read_at", "null")
        if signal_type:
            query = query.eq("signal_type", signal_type.value)
        if company_name:
            query = query.ilike("company_name", f"%{company_name}%")

        result = query.order("detected_at", desc=True).limit(limit).execute()

        logger.info(
            "Retrieved market signals",
            extra={"user_id": user_id, "count": len(result.data)},
        )

        # Transform database fields to match frontend Signal interface:
        # - headline -> content (main display text)
        # - source_name -> source (origin of the signal)
        # - detected_at -> created_at (timestamp, formatted as ISO 8601)
        transformed = []
        for row in result.data:
            transformed_row = dict(row)
            # Map field names for frontend compatibility
            if "headline" in transformed_row:
                transformed_row["content"] = transformed_row.pop("headline")
            if "source_name" in transformed_row:
                transformed_row["source"] = transformed_row.pop("source_name")
            # Map detected_at to created_at and ensure ISO 8601 format
            if "detected_at" in transformed_row:
                detected_at = transformed_row.pop("detected_at")
                # Parse and reformat to proper ISO 8601
                try:
                    if isinstance(detected_at, str):
                        # Handle Postgres timestamp format: "2026-02-14 22:09:00.71081+00"
                        # Replace space with T for ISO 8601 compatibility
                        detected_at = detected_at.replace(" ", "T", 1)
                    transformed_row["created_at"] = detected_at
                except Exception:
                    transformed_row["created_at"] = detected_at
            transformed.append(transformed_row)

        return transformed

    async def mark_as_read(self, user_id: str, signal_id: str) -> dict[str, Any] | None:
        """Mark a signal as read.

        Args:
            user_id: The user's ID.
            signal_id: The signal ID to mark as read.

        Returns:
            Updated signal dict, or None if not found.
        """
        result = (
            self._db.table("market_signals")
            .update({"read_at": datetime.now(UTC).isoformat()})
            .eq("id", signal_id)
            .eq("user_id", user_id)
            .execute()
        )

        if result.data:
            logger.info("Signal marked as read", extra={"signal_id": signal_id})

        return cast(dict[str, Any] | None, result.data[0] if result.data else None)

    async def mark_all_read(self, user_id: str) -> int:
        """Mark all signals as read.

        Args:
            user_id: The user's ID.

        Returns:
            Number of signals marked as read.
        """
        result = (
            self._db.table("market_signals")
            .update({"read_at": datetime.now(UTC).isoformat()})
            .eq("user_id", user_id)
            .is_("read_at", "null")
            .execute()
        )

        count = len(result.data)
        logger.info("All signals marked as read", extra={"user_id": user_id, "count": count})

        return count

    async def dismiss_signal(self, user_id: str, signal_id: str) -> dict[str, Any] | None:
        """Dismiss a signal.

        Args:
            user_id: The user's ID.
            signal_id: The signal ID to dismiss.

        Returns:
            Updated signal dict, or None if not found.
        """
        result = (
            self._db.table("market_signals")
            .update({"dismissed_at": datetime.now(UTC).isoformat()})
            .eq("id", signal_id)
            .eq("user_id", user_id)
            .execute()
        )

        if result.data:
            logger.info("Signal dismissed", extra={"signal_id": signal_id})

        return cast(dict[str, Any] | None, result.data[0] if result.data else None)

    async def get_unread_count(self, user_id: str) -> int:
        """Get count of unread signals.

        Args:
            user_id: The user's ID.

        Returns:
            Number of unread signals.
        """
        result = (
            self._db.table("market_signals")
            .select("id", count="exact")  # type: ignore[arg-type]
            .eq("user_id", user_id)
            .is_("read_at", "null")
            .execute()
        )

        count = result.count or 0
        logger.debug("Unread signal count retrieved", extra={"user_id": user_id, "count": count})

        return count

    # Monitored Entities

    async def add_monitored_entity(
        self, user_id: str, data: MonitoredEntityCreate
    ) -> dict[str, Any]:
        """Add an entity to monitor.

        Args:
            user_id: The user's ID.
            data: Entity creation data.

        Returns:
            Created or updated entity dict.
        """
        logger.info(
            "Adding monitored entity",
            extra={
                "user_id": user_id,
                "entity_type": data.entity_type.value,
                "entity_name": data.entity_name,
            },
        )

        result = (
            self._db.table("monitored_entities")
            .upsert(
                {
                    "user_id": user_id,
                    "entity_type": data.entity_type.value,
                    "entity_name": data.entity_name,
                    "monitoring_config": data.monitoring_config,
                    "is_active": True,
                },
                on_conflict="user_id,entity_type,entity_name",
            )
            .execute()
        )

        entity = cast(dict[str, Any], result.data[0])
        logger.info("Monitored entity added", extra={"entity_id": entity["id"]})
        return entity

    async def get_monitored_entities(
        self, user_id: str, active_only: bool = True
    ) -> list[dict[str, Any]]:
        """Get monitored entities.

        Args:
            user_id: The user's ID.
            active_only: Only return active entities.

        Returns:
            List of entity dicts.
        """
        query = self._db.table("monitored_entities").select("*").eq("user_id", user_id)

        if active_only:
            query = query.eq("is_active", True)

        result = query.order("entity_name").execute()

        logger.info(
            "Retrieved monitored entities",
            extra={"user_id": user_id, "count": len(result.data)},
        )

        return cast(list[dict[str, Any]], result.data)

    async def remove_monitored_entity(self, user_id: str, entity_id: str) -> bool:
        """Remove a monitored entity.

        Args:
            user_id: The user's ID.
            entity_id: The entity ID to remove.

        Returns:
            True if successful.
        """
        self._db.table("monitored_entities").update({"is_active": False}).eq("id", entity_id).eq(
            "user_id", user_id
        ).execute()

        logger.info("Monitored entity removed", extra={"entity_id": entity_id})
        return True
