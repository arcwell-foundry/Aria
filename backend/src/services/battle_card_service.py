"""Battle card service for competitive intelligence.

This service manages battle cards - competitive intelligence sheets
that help sales representatives handle competitive situations.
"""

import logging
from datetime import UTC, datetime
from typing import Any, cast

from pydantic import BaseModel, Field

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


class BattleCardCreate(BaseModel):
    """Request model for creating a battle card."""

    competitor_name: str = Field(..., min_length=1, description="Name of the competitor")
    competitor_domain: str | None = Field(None, description="Competitor's website domain")
    overview: str | None = Field(None, description="Brief overview of the competitor")
    strengths: list[str] = Field(default_factory=list, description="List of competitor strengths")
    weaknesses: list[str] = Field(default_factory=list, description="List of competitor weaknesses")
    pricing: dict[str, Any] = Field(
        default_factory=dict, description="Competitor pricing information"
    )
    differentiation: list[dict[str, Any]] = Field(
        default_factory=list, description="How we differentiate from this competitor"
    )
    objection_handlers: list[dict[str, Any]] = Field(
        default_factory=list, description="Common objections and responses"
    )


class BattleCardUpdate(BaseModel):
    """Request model for updating a battle card.

    All fields are optional - only provided fields will be updated.
    """

    overview: str | None = None
    strengths: list[str] | None = None
    weaknesses: list[str] | None = None
    pricing: dict[str, Any] | None = None
    differentiation: list[dict[str, Any]] | None = None
    objection_handlers: list[dict[str, Any]] | None = None


class BattleCardService:
    """Service for managing battle cards."""

    def __init__(self) -> None:
        """Initialize battle card service with Supabase client."""
        self._db = SupabaseClient.get_client()

    async def create_battle_card(
        self,
        company_id: str,
        data: BattleCardCreate,
    ) -> dict[str, Any]:
        """Create a new battle card.

        Args:
            company_id: The company ID to associate the battle card with.
            data: Battle card creation data.

        Returns:
            Created battle card with ID.
        """
        result = (
            self._db.table("battle_cards")
            .insert(
                {
                    "company_id": company_id,
                    "competitor_name": data.competitor_name,
                    "competitor_domain": data.competitor_domain,
                    "overview": data.overview,
                    "strengths": data.strengths,
                    "weaknesses": data.weaknesses,
                    "pricing": data.pricing,
                    "differentiation": data.differentiation,
                    "objection_handlers": data.objection_handlers,
                    "update_source": "manual",
                }
            )
            .execute()
        )

        card = cast(dict[str, Any], result.data[0])

        logger.info(
            "Created battle card",
            extra={
                "company_id": company_id,
                "competitor_name": data.competitor_name,
                "card_id": card.get("id"),
            },
        )

        return card

    async def get_battle_card(
        self,
        company_id: str,
        competitor_name: str,
    ) -> dict[str, Any] | None:
        """Get a specific battle card by company and competitor name.

        Args:
            company_id: The company ID.
            competitor_name: The competitor name.

        Returns:
            Battle card if found, None otherwise.
        """
        result = (
            self._db.table("battle_cards")
            .select("*")
            .eq("company_id", company_id)
            .eq("competitor_name", competitor_name)
            .single()
            .execute()
        )

        if result.data:
            return cast(dict[str, Any], result.data)
        return None

    async def get_battle_card_by_id(self, card_id: str) -> dict[str, Any] | None:
        """Get battle card by ID.

        Args:
            card_id: The battle card ID.

        Returns:
            Battle card if found, None otherwise.
        """
        result = self._db.table("battle_cards").select("*").eq("id", card_id).single().execute()

        if result.data:
            return cast(dict[str, Any], result.data)
        return None

    async def list_battle_cards(
        self,
        company_id: str,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        """List all battle cards for a company.

        Args:
            company_id: The company ID.
            search: Optional search term to filter by competitor name.

        Returns:
            List of battle cards ordered by competitor name.
        """
        query = self._db.table("battle_cards").select("*").eq("company_id", company_id)

        if search:
            query = query.ilike("competitor_name", f"%{search}%")

        result = query.order("competitor_name").execute()
        return cast(list[dict[str, Any]], result.data)

    async def update_battle_card(
        self,
        card_id: str,
        data: BattleCardUpdate,
        source: str = "manual",
    ) -> dict[str, Any]:
        """Update a battle card and track changes.

        Args:
            card_id: The battle card ID.
            data: Update data.
            source: Update source (manual or auto).

        Returns:
            Updated battle card.

        Raises:
            ValueError: If battle card not found.
        """
        # Get current state
        current = await self.get_battle_card_by_id(card_id)
        if not current:
            raise ValueError("Battle card not found")

        # Build update dict and track changes
        update_data: dict[str, Any] = {
            "last_updated": datetime.now(UTC).isoformat(),
            "update_source": source,
        }
        changes: list[dict[str, Any]] = []

        for field in [
            "overview",
            "strengths",
            "weaknesses",
            "pricing",
            "differentiation",
            "objection_handlers",
        ]:
            new_value = getattr(data, field, None)
            if new_value is not None and new_value != current.get(field):
                update_data[field] = new_value
                changes.append(
                    {
                        "battle_card_id": card_id,
                        "change_type": f"{field}_updated",
                        "field_name": field,
                        "old_value": current.get(field),
                        "new_value": new_value,
                    }
                )

        # Apply update
        result = self._db.table("battle_cards").update(update_data).eq("id", card_id).execute()

        # Record changes
        if changes:
            self._db.table("battle_card_changes").insert(changes).execute()

        logger.info(
            "Updated battle card",
            extra={
                "card_id": card_id,
                "fields_updated": len(update_data) - 2,  # Exclude last_updated and update_source
                "changes_recorded": len(changes),
                "source": source,
            },
        )

        return cast(dict[str, Any], result.data[0])

    async def delete_battle_card(self, card_id: str) -> bool:
        """Delete a battle card.

        Args:
            card_id: The battle card ID.

        Returns:
            True if deleted.
        """
        self._db.table("battle_cards").delete().eq("id", card_id).execute()

        logger.info("Deleted battle card", extra={"card_id": card_id})

        return True

    async def get_card_history(self, card_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Get change history for a battle card.

        Args:
            card_id: The battle card ID.
            limit: Maximum number of changes to return.

        Returns:
            List of change records ordered by most recent first.
        """
        result = (
            self._db.table("battle_card_changes")
            .select("*")
            .eq("battle_card_id", card_id)
            .order("detected_at", desc=True)
            .limit(limit)
            .execute()
        )

        return cast(list[dict[str, Any]], result.data)

    async def add_objection_handler(
        self,
        card_id: str,
        objection: str,
        response: str,
    ) -> dict[str, Any]:
        """Add an objection handler to a battle card.

        Args:
            card_id: The battle card ID.
            objection: The objection statement.
            response: The recommended response.

        Returns:
            Updated battle card.

        Raises:
            ValueError: If battle card not found.
        """
        current = await self.get_battle_card_by_id(card_id)
        if not current:
            raise ValueError("Battle card not found")

        handlers = list(current.get("objection_handlers", []))
        handlers.append({"objection": objection, "response": response})

        return await self.update_battle_card(card_id, BattleCardUpdate(objection_handlers=handlers))
