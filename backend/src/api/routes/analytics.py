"""Analytics API Routes.

Provides endpoints for calculating and retrieving analytics metrics
for ARIA, including overview metrics, conversion funnel, activity trends,
response times, ARIA impact, and period comparisons.
"""

import io
import logging
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from src.api.deps import CurrentUser
from src.core.exceptions import ARIAException, sanitize_error
from src.models.analytics import (
    ActivityTrendsResponse,
    AriaImpactSummaryResponse,
    ConversionFunnelResponse,
    OverviewMetricsResponse,
    PeriodComparisonResponse,
    ResponseTimeMetricsResponse,
)
from src.models.roi import (
    PeriodValidation,
    ROIMetricsResponse,
    WeeklyTrendPoint,
)
from src.services.analytics_service import AnalyticsService
from src.services.roi_service import ROIService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _get_roi_service() -> ROIService:
    """Get ROIService instance.

    Returns:
        ROIService instance for calculating ROI metrics.
    """
    return ROIService()


def _get_analytics_service() -> AnalyticsService:
    """Get AnalyticsService instance.

    Returns:
        AnalyticsService instance for general analytics calculations.
    """
    return AnalyticsService()


def _parse_period_to_dates(
    period: str,
) -> tuple[datetime, datetime]:
    """Convert period string to start and end datetimes.

    Args:
        period: Period string like '7d', '30d', '90d', or 'all'.

    Returns:
        Tuple of (period_start, period_end) datetimes.
    """
    now = datetime.utcnow()
    if period == "7d":
        period_start = now - timedelta(days=7)
    elif period == "30d":
        period_start = now - timedelta(days=30)
    elif period == "90d":
        period_start = now - timedelta(days=90)
    else:  # all
        period_start = datetime(2020, 1, 1)
    return period_start, now


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
        service = _get_roi_service()
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
        service = _get_roi_service()
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
        service = _get_roi_service()
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


# --- General Analytics Routes ---


@router.get("/overview", response_model=OverviewMetricsResponse)
async def get_overview_metrics(
    current_user: CurrentUser,
    period: Annotated[
        str,
        Query(
            description="Time period for metrics: 7d, 30d, 90d, or all",
            examples=["30d"],
            pattern="^(7d|30d|90d|all)$",
        ),
    ] = "30d",
) -> OverviewMetricsResponse:
    """Get high-level overview metrics for the authenticated user.

    Returns counts for leads created, meetings booked, emails sent,
    debriefs completed, goals completed, average health score, and
    estimated time saved.

    Args:
        current_user: The authenticated user.
        period: Time period identifier (7d, 30d, 90d, all). Defaults to "30d".

    Returns:
        Overview metrics for the specified period.

    Raises:
        HTTPException: If metrics calculation fails.
    """
    try:
        period_start, period_end = _parse_period_to_dates(period)
        service = _get_analytics_service()

        metrics = await service.get_overview_metrics(
            user_id=current_user.id,
            period_start=period_start,
            period_end=period_end,
        )

        logger.info(
            "Overview metrics retrieved successfully",
            extra={"user_id": current_user.id, "period": period},
        )

        return OverviewMetricsResponse(**metrics)

    except ARIAException as e:
        logger.exception(
            "ARIA error fetching overview metrics",
            extra={"user_id": current_user.id, "period": str(period)},
        )
        raise HTTPException(
            status_code=e.status_code,
            detail={"message": e.message, "code": e.code},
        ) from e
    except Exception as e:
        logger.exception(
            "Unexpected error fetching overview metrics",
            extra={"user_id": current_user.id, "period": str(period)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve overview metrics",
        ) from e


@router.get("/funnel", response_model=ConversionFunnelResponse)
async def get_conversion_funnel(
    current_user: CurrentUser,
    period: Annotated[
        str,
        Query(
            description="Time period for funnel data: 7d, 30d, 90d, or all",
            examples=["30d"],
            pattern="^(7d|30d|90d|all)$",
        ),
    ] = "30d",
) -> ConversionFunnelResponse:
    """Get conversion funnel metrics for the authenticated user.

    Returns lead counts per lifecycle stage, stage-to-stage conversion rates,
    and average time spent in each stage.

    Args:
        current_user: The authenticated user.
        period: Time period identifier (7d, 30d, 90d, all). Defaults to "30d".

    Returns:
        Conversion funnel metrics for the specified period.

    Raises:
        HTTPException: If funnel calculation fails.
    """
    try:
        period_start, period_end = _parse_period_to_dates(period)
        service = _get_analytics_service()

        funnel = await service.get_conversion_funnel(
            user_id=current_user.id,
            period_start=period_start,
            period_end=period_end,
        )

        logger.info(
            "Conversion funnel retrieved successfully",
            extra={"user_id": current_user.id, "period": period},
        )

        return ConversionFunnelResponse(**funnel)

    except ARIAException as e:
        logger.exception(
            "ARIA error fetching conversion funnel",
            extra={"user_id": current_user.id, "period": str(period)},
        )
        raise HTTPException(
            status_code=e.status_code,
            detail={"message": e.message, "code": e.code},
        ) from e
    except Exception as e:
        logger.exception(
            "Unexpected error fetching conversion funnel",
            extra={"user_id": current_user.id, "period": str(period)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve conversion funnel",
        ) from e


@router.get("/trends", response_model=ActivityTrendsResponse)
async def get_activity_trends(
    current_user: CurrentUser,
    period: Annotated[
        str,
        Query(
            description="Time period for trends: 7d, 30d, 90d, or all",
            examples=["30d"],
            pattern="^(7d|30d|90d|all)$",
        ),
    ] = "30d",
    granularity: Annotated[
        str,
        Query(
            description="Time grouping: day, week, or month",
            examples=["day"],
            pattern="^(day|week|month)$",
        ),
    ] = "day",
) -> ActivityTrendsResponse:
    """Get activity trends as time series for the authenticated user.

    Returns time-bucketed counts for emails sent, meetings, ARIA actions,
    and leads created.

    Args:
        current_user: The authenticated user.
        period: Time period identifier (7d, 30d, 90d, all). Defaults to "30d".
        granularity: Time grouping (day, week, month). Defaults to "day".

    Returns:
        Activity trends time series for the specified period.

    Raises:
        HTTPException: If trends calculation fails.
    """
    try:
        period_start, period_end = _parse_period_to_dates(period)
        service = _get_analytics_service()

        trends = await service.get_activity_trends(
            user_id=current_user.id,
            period_start=period_start,
            period_end=period_end,
            granularity=granularity,
        )

        logger.info(
            "Activity trends retrieved successfully",
            extra={
                "user_id": current_user.id,
                "period": period,
                "granularity": granularity,
            },
        )

        return ActivityTrendsResponse(**trends)

    except ARIAException as e:
        logger.exception(
            "ARIA error fetching activity trends",
            extra={"user_id": current_user.id, "period": str(period)},
        )
        raise HTTPException(
            status_code=e.status_code,
            detail={"message": e.message, "code": e.code},
        ) from e
    except Exception as e:
        logger.exception(
            "Unexpected error fetching activity trends",
            extra={"user_id": current_user.id, "period": str(period)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve activity trends",
        ) from e


@router.get("/response-times", response_model=ResponseTimeMetricsResponse)
async def get_response_time_metrics(
    current_user: CurrentUser,
    period: Annotated[
        str,
        Query(
            description="Time period for response times: 7d, 30d, 90d, or all",
            examples=["30d"],
            pattern="^(7d|30d|90d|all)$",
        ),
    ] = "30d",
) -> ResponseTimeMetricsResponse:
    """Get email response time metrics for the authenticated user.

    Returns average response time, response time by lead, and daily trend.

    Args:
        current_user: The authenticated user.
        period: Time period identifier (7d, 30d, 90d, all). Defaults to "30d".

    Returns:
        Response time metrics for the specified period.

    Raises:
        HTTPException: If metrics calculation fails.
    """
    try:
        period_start, period_end = _parse_period_to_dates(period)
        service = _get_analytics_service()

        metrics = await service.get_response_time_metrics(
            user_id=current_user.id,
            period_start=period_start,
            period_end=period_end,
        )

        logger.info(
            "Response time metrics retrieved successfully",
            extra={"user_id": current_user.id, "period": period},
        )

        return ResponseTimeMetricsResponse(**metrics)

    except ARIAException as e:
        logger.exception(
            "ARIA error fetching response time metrics",
            extra={"user_id": current_user.id, "period": str(period)},
        )
        raise HTTPException(
            status_code=e.status_code,
            detail={"message": e.message, "code": e.code},
        ) from e
    except Exception as e:
        logger.exception(
            "Unexpected error fetching response time metrics",
            extra={"user_id": current_user.id, "period": str(period)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve response time metrics",
        ) from e


@router.get("/aria-impact", response_model=AriaImpactSummaryResponse)
async def get_aria_impact_summary(
    current_user: CurrentUser,
    period: Annotated[
        str,
        Query(
            description="Time period for impact summary: 7d, 30d, 90d, or all",
            examples=["30d"],
            pattern="^(7d|30d|90d|all)$",
        ),
    ] = "30d",
) -> AriaImpactSummaryResponse:
    """Get ARIA impact summary for the authenticated user.

    Returns total ARIA actions, breakdown by action type, estimated time saved,
    and pipeline impact metrics.

    Args:
        current_user: The authenticated user.
        period: Time period identifier (7d, 30d, 90d, all). Defaults to "30d".

    Returns:
        ARIA impact summary for the specified period.

    Raises:
        HTTPException: If impact calculation fails.
    """
    try:
        period_start, period_end = _parse_period_to_dates(period)
        service = _get_analytics_service()

        summary = await service.get_aria_impact_summary(
            user_id=current_user.id,
            period_start=period_start,
            period_end=period_end,
        )

        logger.info(
            "ARIA impact summary retrieved successfully",
            extra={"user_id": current_user.id, "period": period},
        )

        return AriaImpactSummaryResponse(**summary)

    except ARIAException as e:
        logger.exception(
            "ARIA error fetching impact summary",
            extra={"user_id": current_user.id, "period": str(period)},
        )
        raise HTTPException(
            status_code=e.status_code,
            detail={"message": e.message, "code": e.code},
        ) from e
    except Exception as e:
        logger.exception(
            "Unexpected error fetching impact summary",
            extra={"user_id": current_user.id, "period": str(period)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve ARIA impact summary",
        ) from e


@router.get("/compare", response_model=PeriodComparisonResponse)
async def compare_periods(
    current_user: CurrentUser,
    current: Annotated[
        str,
        Query(
            description="Current period: 7d, 30d, 90d, or all",
            examples=["30d"],
            pattern="^(7d|30d|90d|all)$",
        ),
    ] = "30d",
    previous: Annotated[
        str,
        Query(
            description="Previous period: 7d, 30d, 90d, or all",
            examples=["30d"],
            pattern="^(7d|30d|90d|all)$",
        ),
    ] = "30d",
) -> PeriodComparisonResponse:
    """Compare metrics between two time periods for the authenticated user.

    Returns metrics for both periods along with percentage deltas.

    Args:
        current_user: The authenticated user.
        current: Current period identifier. Defaults to "30d".
        previous: Previous period identifier. Defaults to "30d".

    Returns:
        Period comparison with current, previous, and delta percentages.

    Raises:
        HTTPException: If comparison calculation fails.
    """
    try:
        current_start, current_end = _parse_period_to_dates(current)

        # Calculate previous period by going back further
        previous_days = {
            "7d": 7,
            "30d": 30,
            "90d": 90,
            "all": 365 * 5,
        }.get(previous, 30)

        # Previous period ends where current period starts
        previous_end = current_start
        previous_start = current_start - timedelta(days=previous_days)

        service = _get_analytics_service()

        comparison = await service.compare_periods(
            user_id=current_user.id,
            current_start=current_start,
            current_end=current_end,
            previous_start=previous_start,
            previous_end=previous_end,
        )

        logger.info(
            "Period comparison retrieved successfully",
            extra={
                "user_id": current_user.id,
                "current_period": current,
                "previous_period": previous,
            },
        )

        return PeriodComparisonResponse(
            current=OverviewMetricsResponse(**comparison["current"]),
            previous=OverviewMetricsResponse(**comparison["previous"]),
            delta_pct=comparison["delta_pct"],
        )

    except ARIAException as e:
        logger.exception(
            "ARIA error comparing periods",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=e.status_code,
            detail={"message": e.message, "code": e.code},
        ) from e
    except Exception as e:
        logger.exception(
            "Unexpected error comparing periods",
            extra={"user_id": current_user.id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to compare periods",
        ) from e


@router.get("/export")
async def export_analytics(
    current_user: CurrentUser,
    period: Annotated[
        str,
        Query(
            description="Time period for export: 7d, 30d, 90d, or all",
            examples=["30d"],
            pattern="^(7d|30d|90d|all)$",
        ),
    ] = "30d",
    format: Annotated[  # noqa: A002
        str,
        Query(
            description="Export format: csv or json",
            examples=["csv"],
            pattern="^(csv|json)$",
        ),
    ] = "csv",
) -> StreamingResponse:
    """Export analytics data for the authenticated user.

    Generates a file containing all analytics metrics for the specified period.

    Args:
        current_user: The authenticated user.
        period: Time period identifier (7d, 30d, 90d, all). Defaults to "30d".
        format: Export format (csv or json). Defaults to "csv".

    Returns:
        StreamingResponse with exported file.

    Raises:
        HTTPException: If export generation fails.
    """
    try:
        period_start, period_end = _parse_period_to_dates(period)
        service = _get_analytics_service()

        # Fetch all analytics data
        overview = await service.get_overview_metrics(
            user_id=current_user.id,
            period_start=period_start,
            period_end=period_end,
        )
        funnel = await service.get_conversion_funnel(
            user_id=current_user.id,
            period_start=period_start,
            period_end=period_end,
        )
        trends = await service.get_activity_trends(
            user_id=current_user.id,
            period_start=period_start,
            period_end=period_end,
        )
        response_times = await service.get_response_time_metrics(
            user_id=current_user.id,
            period_start=period_start,
            period_end=period_end,
        )
        impact = await service.get_aria_impact_summary(
            user_id=current_user.id,
            period_start=period_start,
            period_end=period_end,
        )

        timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")

        if format == "json":
            import json

            data = {
                "period": period,
                "generated_at": timestamp,
                "overview": overview,
                "conversion_funnel": funnel,
                "activity_trends": trends,
                "response_times": response_times,
                "aria_impact": impact,
            }
            content = json.dumps(data, indent=2, default=str)
            filename = f"aria-analytics-{period}-{timestamp}.json"
            media_type = "application/json"
        else:
            # CSV format
            output = io.StringIO()
            output.write("ARIA Analytics Report\n")
            output.write(f"Period: {period}\n")
            output.write(f"Generated: {timestamp}\n\n")

            # Overview section
            output.write("OVERVIEW METRICS\n")
            output.write("Metric,Value\n")
            output.write(f"Leads Created,{overview['leads_created']}\n")
            output.write(f"Meetings Booked,{overview['meetings_booked']}\n")
            output.write(f"Emails Sent,{overview['emails_sent']}\n")
            output.write(f"Debriefs Completed,{overview['debriefs_completed']}\n")
            output.write(f"Goals Completed,{overview['goals_completed']}\n")
            output.write(f"Avg Health Score,{overview['avg_health_score'] or 'N/A'}\n")
            output.write(f"Time Saved (minutes),{overview['time_saved_minutes']}\n\n")

            # Funnel section
            output.write("CONVERSION FUNNEL\n")
            output.write("Stage,Count\n")
            for stage, count in funnel["stages"].items():
                output.write(f"{stage},{count}\n")
            output.write("\n")

            # Impact section
            output.write("ARIA IMPACT\n")
            output.write("Metric,Value\n")
            output.write(f"Total Actions,{impact['total_actions']}\n")
            output.write(f"Time Saved (minutes),{impact['estimated_time_saved_minutes']}\n")
            for action_type, count in impact["by_action_type"].items():
                output.write(f"{action_type},{count}\n")
            output.write("\n")

            content = output.getvalue()
            filename = f"aria-analytics-{period}-{timestamp}.csv"
            media_type = "text/csv"

        logger.info(
            "Analytics exported successfully",
            extra={
                "user_id": current_user.id,
                "period": period,
                "format": format,
                "filename": filename,
            },
        )

        return StreamingResponse(
            iter([content]),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except ARIAException as e:
        logger.exception(
            "ARIA error exporting analytics",
            extra={"user_id": current_user.id, "period": str(period)},
        )
        raise HTTPException(
            status_code=e.status_code,
            detail={"message": e.message, "code": e.code},
        ) from e
    except Exception as e:
        logger.exception(
            "Unexpected error exporting analytics",
            extra={"user_id": current_user.id, "period": str(period)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export analytics",
        ) from e
