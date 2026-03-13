"""Apollo.io API routes for Settings UI.

Provides endpoints for managing Apollo configuration (BYOK vs LuminOne-provided mode)
and viewing credit consumption statistics.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from src.api.deps import CurrentUser
from src.core.config import settings
from src.integrations.apollo_client import ApolloClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/apollo", tags=["apollo"])


# Request/Response Models
class ApolloConfigResponse(BaseModel):
    """Response model for Apollo configuration."""

    is_configured: bool
    mode: str  # "byok", "luminone_provided", or "unconfigured"
    monthly_credit_limit: int
    credits_used: int
    credits_remaining: int
    billing_cycle_start: str | None = None
    billing_cycle_end: str | None = None
    has_byok_key: bool  # Whether a BYOK key is set (masked)


class ApolloConfigUpdateRequest(BaseModel):
    """Request model for updating Apollo configuration."""

    mode: str = Field(..., pattern="^(byok|luminone_provided)$")
    api_key: str | None = Field(None, max_length=200, description="Apollo API key for BYOK mode")
    monthly_credit_limit: int | None = Field(
        None, ge=0, le=100000, description="Credit limit for luminone_provided mode"
    )


class ApolloUsageResponse(BaseModel):
    """Response model for Apollo credit usage."""

    total_credits_used: int
    total_cost_cents: float
    billing_period_start: str | None
    billing_period_end: str | None
    breakdown: list[dict[str, Any]]
    recent_transactions: list[dict[str, Any]]


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str


def _get_company_id(user: CurrentUser) -> str | None:
    """Extract company_id from user profile.

    Args:
        user: The authenticated user

    Returns:
        Company UUID or None if not set
    """
    # Try to get company_id from user metadata or profile
    # This depends on how companies are linked to users
    try:
        from src.db.supabase import SupabaseClient

        db = SupabaseClient.get_client()
        result = (
            db.table("user_profiles")
            .select("company_id")
            .eq("id", user.id)
            .limit(1)
            .execute()
        )
        if result.data and result.data[0].get("company_id"):
            return result.data[0]["company_id"]
    except Exception as e:
        logger.warning("Failed to get company_id for user %s: %s", user.id, e)

    return None


@router.get("/config", response_model=ApolloConfigResponse)
async def get_apollo_config(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get Apollo configuration for the current user's company.

    Returns mode (byok/luminone_provided), credit limits, and usage stats.

    Args:
        current_user: The authenticated user

    Returns:
        Apollo configuration and usage summary
    """
    try:
        company_id = _get_company_id(current_user)
        client = ApolloClient()

        # Check if Apollo is configured at all
        if not settings.apollo_configured:
            return {
                "is_configured": False,
                "mode": "unconfigured",
                "monthly_credit_limit": 0,
                "credits_used": 0,
                "credits_remaining": 0,
                "billing_cycle_start": None,
                "billing_cycle_end": None,
                "has_byok_key": False,
            }

        # Get config from database if company exists
        if company_id:
            config = await client.get_config(company_id)
            usage = await client.get_usage_summary(company_id)

            # Map usage keys to expected response format
            credits_used = usage.get("used", 0)
            monthly_limit = config.get("monthly_credit_limit", 1000) if config else 1000

            return {
                "is_configured": True,
                "mode": config.get("mode", "luminone_provided") if config else "luminone_provided",
                "monthly_credit_limit": monthly_limit,
                "credits_used": credits_used,
                "credits_remaining": monthly_limit - credits_used,
                "billing_cycle_start": config.get("cycle_reset_date") if config else None,
                "billing_cycle_end": None,  # Calculated from cycle_reset_date + 1 month
                "has_byok_key": bool(config.get("encrypted_api_key")) if config else False,
            }

        # Default: LuminOne-provided mode with master key
        return {
            "is_configured": True,
            "mode": "luminone_provided",
            "monthly_credit_limit": 1000,
            "credits_used": 0,
            "credits_remaining": 1000,
            "billing_cycle_start": None,
            "billing_cycle_end": None,
            "has_byok_key": False,
        }

    except Exception as e:
        logger.exception("Error fetching Apollo config")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch Apollo configuration: {str(e)}",
        ) from e


@router.put("/config", response_model=MessageResponse)
async def update_apollo_config(
    request: ApolloConfigUpdateRequest,
    current_user: CurrentUser,
) -> dict[str, str]:
    """Update Apollo configuration.

    Allows switching between BYOK and LuminOne-provided modes,
    and setting BYOK API key or monthly credit limits.

    Args:
        request: Configuration update request
        current_user: The authenticated user

    Returns:
        Success message

    Raises:
        HTTPException: If update fails or validation errors
    """
    try:
        company_id = _get_company_id(current_user)
        if not company_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No company associated with user account",
            )

        client = ApolloClient()

        # Validate BYOK mode requires API key
        if request.mode == "byok" and not request.api_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="API key required for BYOK mode",
            )

        # Update configuration
        await client.update_config(
            company_id=company_id,
            mode=request.mode,
            api_key=request.api_key,
            monthly_credit_limit=request.monthly_credit_limit,
        )

        logger.info(
            "Apollo config updated for company %s: mode=%s",
            company_id,
            request.mode,
        )

        return {
            "message": f"Apollo configuration updated to {request.mode} mode"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating Apollo config")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update Apollo configuration: {str(e)}",
        ) from e


@router.get("/usage", response_model=ApolloUsageResponse)
async def get_apollo_usage(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get Apollo credit usage for the current billing cycle.

    Returns detailed breakdown by action type and recent transactions.

    Args:
        current_user: The authenticated user

    Returns:
        Credit usage statistics and transaction history
    """
    try:
        company_id = _get_company_id(current_user)
        if not company_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No company associated with user account",
            )

        client = ApolloClient()
        usage = await client.get_usage_summary(company_id)

        # Get recent transactions from credit log
        from src.db.supabase import SupabaseClient

        db = SupabaseClient.get_client()

        # Fetch recent credit log entries
        transactions_result = (
            db.table("apollo_credit_log")
            .select("*")
            .eq("company_id", company_id)
            .order("created_at", desc=True)
            .limit(50)
            .execute()
        )

        recent_transactions = []
        if transactions_result.data:
            for tx in transactions_result.data:
                recent_transactions.append({
                    "id": tx.get("id"),
                    "action": tx.get("action"),
                    "credits_consumed": tx.get("credits_consumed", 0),
                    "cost_cents": tx.get("cost_cents", 0),
                    "target_company": tx.get("target_company"),
                    "target_person": tx.get("target_person"),
                    "mode": tx.get("mode"),
                    "status": tx.get("status"),
                    "created_at": tx.get("created_at"),
                })

        return {
            "total_credits_used": usage.get("credits_used", 0),
            "total_cost_cents": usage.get("cost_cents", 0.0),
            "billing_period_start": usage.get("billing_period_start"),
            "billing_period_end": usage.get("billing_period_end"),
            "breakdown": usage.get("breakdown", []),
            "recent_transactions": recent_transactions,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error fetching Apollo usage")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch Apollo usage: {str(e)}",
        ) from e


@router.post("/reset-credits", response_model=MessageResponse)
async def reset_apollo_credits(
    current_user: CurrentUser,
) -> dict[str, str]:
    """Reset monthly credit counters for the current company.

    This is typically called by a scheduled job, but can be triggered
    manually for testing or billing adjustments.

    Args:
        current_user: The authenticated user

    Returns:
        Success message
    """
    try:
        company_id = _get_company_id(current_user)
        if not company_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No company associated with user account",
            )

        client = ApolloClient()
        await client.reset_monthly_credits(company_id)

        logger.info("Apollo credits reset for company %s", company_id)

        return {"message": "Monthly credits reset successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error resetting Apollo credits")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset credits: {str(e)}",
        ) from e


@router.get("/health")
async def apollo_health_check() -> dict[str, Any]:
    """Check Apollo API connectivity.

    Returns:
        Health status with API key configuration status
    """
    try:
        if not settings.apollo_configured:
            return {
                "status": "unconfigured",
                "message": "Apollo API key not configured",
            }

        # Try a lightweight API call to verify connectivity
        from src.agents.capabilities.enrichment_providers.apollo_provider import (
            ApolloEnrichmentProvider,
        )

        provider = ApolloEnrichmentProvider()
        is_healthy = await provider.health_check()

        if is_healthy:
            return {
                "status": "healthy",
                "message": "Apollo API is operational",
            }
        else:
            return {
                "status": "degraded",
                "message": "Apollo API key may be invalid or rate-limited",
            }

    except Exception as e:
        logger.exception("Apollo health check failed")
        return {
            "status": "error",
            "message": f"Health check failed: {str(e)}",
        }
