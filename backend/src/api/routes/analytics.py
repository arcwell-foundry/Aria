"""ROI Analytics API Routes (US-943).

Provides endpoints for calculating and retrieving Return on Investment metrics
for ARIA, including time saved, intelligence delivered, actions taken, and
pipeline impact over configurable time periods.
"""

import io
import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from src.api.deps import CurrentUser
from src.core.exceptions import ARIAException, sanitize_error
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
            detail=sanitize_error(e),
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
            detail=sanitize_error(e),
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


@router.get("/roi/export")
async def export_roi_report(
    current_user: CurrentUser,
    period: Annotated[
        str,
        Query(
            description="Time period for export: 7d, 30d, 90d, or all",
            examples=["30d"],
            pattern="^(7d|30d|90d|all)$",
        ),
    ] = "30d",
) -> StreamingResponse:
    """Export ROI metrics as a CSV report for the authenticated user.

    Generates a CSV file containing time saved, intelligence delivered,
    actions taken, pipeline impact, and weekly trend data for the
    specified period.

    Args:
        current_user: The authenticated user.
        period: Time period identifier (7d, 30d, 90d, all). Defaults to "30d".

    Returns:
        StreamingResponse with CSV content as a file download.

    Raises:
        HTTPException: If export generation fails.
    """
    try:
        # Validate period
        period_validation = PeriodValidation(period=str(period))
        validated_period = period_validation.period

        # Get service and fetch all metrics
        service = _get_service()
        metrics = await service.get_all_metrics(
            user_id=current_user.id,
            period=validated_period,
        )

        # Build CSV content
        output = io.StringIO()
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

        # Header
        output.write("ARIA ROI Report\n")
        output.write(f"Period: {validated_period}\n")
        output.write(f"Generated: {timestamp}\n")
        output.write("\n")

        # Time Saved section
        time_saved = metrics["time_saved"]
        breakdown = time_saved["breakdown"]
        output.write("Time Saved\n")
        output.write("Activity,Count,Hours Saved\n")
        output.write(
            f"Email Drafts,{breakdown['email_drafts']['count']},"
            f"{breakdown['email_drafts']['estimated_hours']}\n"
        )
        output.write(
            f"Meeting Prep,{breakdown['meeting_prep']['count']},"
            f"{breakdown['meeting_prep']['estimated_hours']}\n"
        )
        output.write(
            f"Research Reports,{breakdown['research_reports']['count']},"
            f"{breakdown['research_reports']['estimated_hours']}\n"
        )
        output.write(
            f"CRM Updates,{breakdown['crm_updates']['count']},"
            f"{breakdown['crm_updates']['estimated_hours']}\n"
        )
        output.write(f"Total,,{time_saved['hours']}\n")
        output.write("\n")

        # Intelligence Delivered section
        intelligence = metrics["intelligence_delivered"]
        output.write("Intelligence Delivered\n")
        output.write("Metric,Count\n")
        output.write(f"Facts Discovered,{intelligence['facts_discovered']}\n")
        output.write(f"Signals Detected,{intelligence['signals_detected']}\n")
        output.write(f"Knowledge Gaps Filled,{intelligence['gaps_filled']}\n")
        output.write(f"Briefings Generated,{intelligence['briefings_generated']}\n")
        output.write("\n")

        # Actions Taken section
        actions = metrics["actions_taken"]
        output.write("Actions Taken\n")
        output.write("Metric,Count\n")
        output.write(f"Total Actions,{actions['total']}\n")
        output.write(f"Auto-Approved,{actions['auto_approved']}\n")
        output.write(f"User-Approved,{actions['user_approved']}\n")
        output.write(f"Rejected,{actions['rejected']}\n")
        output.write("\n")

        # Pipeline Impact section
        pipeline = metrics["pipeline_impact"]
        output.write("Pipeline Impact\n")
        output.write("Metric,Count\n")
        output.write(f"Leads Discovered,{pipeline['leads_discovered']}\n")
        output.write(f"Meetings Prepared,{pipeline['meetings_prepped']}\n")
        output.write(f"Follow-ups Sent,{pipeline['follow_ups_sent']}\n")
        output.write("\n")

        # Weekly Trend section
        weekly_trend = metrics["weekly_trend"]
        output.write("Weekly Trend\n")
        output.write("Week Start,Hours Saved\n")
        for point in weekly_trend:
            output.write(f"{point['week_start']},{point['hours_saved']}\n")

        # Prepare streaming response
        csv_content = output.getvalue()
        output.close()

        filename = f"aria-roi-report-{validated_period}.csv"

        logger.info(
            "ROI report exported successfully",
            extra={
                "user_id": current_user.id,
                "period": validated_period,
                "filename": filename,
            },
        )

        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    except ValueError as e:
        logger.warning(
            "Invalid period parameter for export",
            extra={"user_id": current_user.id, "period": str(period), "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=sanitize_error(e),
        ) from e
    except ARIAException as e:
        logger.exception(
            "ARIA error exporting ROI report",
            extra={"user_id": current_user.id, "period": str(period)},
        )
        raise HTTPException(
            status_code=e.status_code,
            detail={"message": e.message, "code": e.code},
        ) from e
    except Exception as e:
        logger.exception(
            "Unexpected error exporting ROI report",
            extra={"user_id": current_user.id, "period": str(period)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export ROI report",
        ) from e
