"""ROI Analytics API Routes (US-943).

Provides endpoints for calculating and retrieving Return on Investment metrics
for ARIA, including time saved, intelligence delivered, actions taken, and
pipeline impact over configurable time periods.
"""

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from src.api.deps import CurrentUser
from src.core.exceptions import ARIAException
from src.models.roi import (
    PeriodValidation,
    ROIMetricsResponse,
    WeeklyTrendPoint,
)
from src.services.roi_service import ROIService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _get_service() -> ROIService:
    """Get ROIService instance.

    Returns:
        ROIService instance for calculating ROI metrics.
    """
    return ROIService()


# --- Route Handlers ---


@router.get("/roi", response_model=ROIMetricsResponse)
async def get_roi_metrics(
    current_user: CurrentUser,
    period: Annotated[
        str,
        Query(
            description="Time period for metrics: 7d, 30d, 90d, or all",
            examples=["30d"],
            pattern="^(7d|30d|90d|all)$",
        ),
    ] = "30d",
) -> ROIMetricsResponse:
    """Get comprehensive ROI metrics for the authenticated user.

    Calculates and returns time saved, intelligence delivered, actions taken,
    pipeline impact, and weekly trends for the specified time period.

    Args:
        current_user: The authenticated user.
        period: Time period identifier (7d, 30d, 90d, all). Defaults to "30d".

    Returns:
        Complete ROI metrics response with all metric categories.

    Raises:
        HTTPException: If metrics calculation fails.
    """
    try:
        # Validate period
        period_validation = PeriodValidation(period=str(period))

        # Get service and fetch metrics
        service = _get_service()
        metrics = await service.get_all_metrics(
            user_id=current_user.id,
            period=period_validation.period,
        )

        logger.info(
            "ROI metrics retrieved successfully",
            extra={
                "user_id": current_user.id,
                "period": period_validation.period,
            },
        )

        return ROIMetricsResponse(**metrics)

    except ValueError as e:
        logger.warning(
            "Invalid period parameter",
            extra={"user_id": current_user.id, "period": str(period), "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid period: {e}",
        ) from e
    except ARIAException as e:
        logger.exception(
            "ARIA error fetching ROI metrics",
            extra={"user_id": current_user.id, "period": str(period)},
        )
        raise HTTPException(
            status_code=e.status_code,
            detail={"message": e.message, "code": e.code},
        ) from e
    except Exception as e:
        logger.exception(
            "Unexpected error fetching ROI metrics",
            extra={"user_id": current_user.id, "period": str(period)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve ROI metrics",
        ) from e


@router.get("/roi/trend", response_model=list[WeeklyTrendPoint])
async def get_roi_trend(
    current_user: CurrentUser,
    period: Annotated[
        str,
        Query(
            description="Time period for trend data: 7d, 30d, 90d, or all",
            examples=["90d"],
            pattern="^(7d|30d|90d|all)$",
        ),
    ] = "90d",
) -> list[WeeklyTrendPoint]:
    """Get weekly time-saved trend for the authenticated user.

    Returns a list of weekly data points showing hours saved per week
    over the specified time period.

    Args:
        current_user: The authenticated user.
        period: Time period identifier (7d, 30d, 90d, all). Defaults to "90d".

    Returns:
        List of weekly trend points with week_start date and hours_saved.

    Raises:
        HTTPException: If trend calculation fails.
    """
    try:
        # Validate period
        period_validation = PeriodValidation(period=str(period))

        # Get service and calculate period start
        service = _get_service()
        from datetime import timedelta

        now = datetime.utcnow()
        if period_validation.period == "7d":
            period_start = now - timedelta(days=7)
        elif period_validation.period == "30d":
            period_start = now - timedelta(days=30)
        elif period_validation.period == "90d":
            period_start = now - timedelta(days=90)
        else:  # all
            period_start = datetime(2020, 1, 1)

        # Fetch trend data
        trend_data = await service.get_weekly_trend(
            user_id=current_user.id,
            period_start=period_start,
        )

        logger.info(
            "ROI trend retrieved successfully",
            extra={
                "user_id": current_user.id,
                "period": period_validation.period,
                "data_points": len(trend_data),
            },
        )

        return [WeeklyTrendPoint(**point) for point in trend_data]

    except ValueError as e:
        logger.warning(
            "Invalid period parameter for trend",
            extra={"user_id": current_user.id, "period": str(period), "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid period: {e}",
        ) from e
    except ARIAException as e:
        logger.exception(
            "ARIA error fetching ROI trend",
            extra={"user_id": current_user.id, "period": str(period)},
        )
        raise HTTPException(
            status_code=e.status_code,
            detail={"message": e.message, "code": e.code},
        ) from e
    except Exception as e:
        logger.exception(
            "Unexpected error fetching ROI trend",
            extra={"user_id": current_user.id, "period": str(period)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve ROI trend",
        ) from e
