/** Analytics API Client.
 *
 * TypeScript interfaces and API functions for fetching analytics metrics
 * from the ARIA analytics endpoints. Covers overview, funnel, trends,
 * response times, ARIA impact, and period comparisons.
 */

import { apiClient } from "./client";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type AnalyticsPeriod = "7d" | "30d" | "90d" | "all";
export type TrendGranularity = "day" | "week" | "month";

/** High-level overview metrics */
export interface OverviewMetrics {
  leads_created: number;
  meetings_booked: number;
  emails_sent: number;
  debriefs_completed: number;
  goals_completed: number;
  avg_health_score: number | null;
  time_saved_minutes: number;
}

/** Conversion funnel stage data */
export interface ConversionFunnel {
  stages: Record<string, number>;
  conversion_rates: Record<string, number | null>;
  avg_days_in_stage: Record<string, number | null>;
}

/** Activity trends time series */
export interface ActivityTrends {
  granularity: TrendGranularity;
  series: {
    emails_sent: Record<string, number>;
    meetings: Record<string, number>;
    aria_actions: Record<string, number>;
    leads_created: Record<string, number>;
  };
}

/** Response time metrics */
export interface ResponseTimeMetrics {
  avg_response_minutes: number | null;
  by_lead: Record<string, number>;
  trend: Array<{ date: string; avg_response_minutes: number }>;
}

/** ARIA impact summary */
export interface AriaImpactSummary {
  total_actions: number;
  by_action_type: Record<string, number>;
  estimated_time_saved_minutes: number;
  pipeline_impact: Record<string, { count: number; estimated_value: number }>;
}

/** Period comparison with deltas */
export interface PeriodComparison {
  current: OverviewMetrics;
  previous: OverviewMetrics;
  delta_pct: Record<string, number | null>;
}

// ---------------------------------------------------------------------------
// API Functions
// ---------------------------------------------------------------------------

/** Get high-level overview metrics */
export async function getOverviewMetrics(
  period: AnalyticsPeriod = "30d",
): Promise<OverviewMetrics> {
  const response = await apiClient.get<OverviewMetrics>("/analytics/overview", {
    params: { period },
  });
  return response.data;
}

/** Get conversion funnel metrics */
export async function getConversionFunnel(
  period: AnalyticsPeriod = "30d",
): Promise<ConversionFunnel> {
  const response = await apiClient.get<ConversionFunnel>("/analytics/funnel", {
    params: { period },
  });
  return response.data;
}

/** Get activity trends */
export async function getActivityTrends(
  period: AnalyticsPeriod = "30d",
  granularity: TrendGranularity = "day",
): Promise<ActivityTrends> {
  const response = await apiClient.get<ActivityTrends>("/analytics/trends", {
    params: { period, granularity },
  });
  return response.data;
}

/** Get response time metrics */
export async function getResponseTimeMetrics(
  period: AnalyticsPeriod = "30d",
): Promise<ResponseTimeMetrics> {
  const response = await apiClient.get<ResponseTimeMetrics>(
    "/analytics/response-times",
    {
      params: { period },
    },
  );
  return response.data;
}

/** Get ARIA impact summary */
export async function getAriaImpactSummary(
  period: AnalyticsPeriod = "30d",
): Promise<AriaImpactSummary> {
  const response = await apiClient.get<AriaImpactSummary>(
    "/analytics/aria-impact",
    {
      params: { period },
    },
  );
  return response.data;
}

/** Compare metrics between two periods */
export async function comparePeriods(
  currentPeriod: AnalyticsPeriod = "30d",
  previousPeriod: AnalyticsPeriod = "30d",
): Promise<PeriodComparison> {
  const response = await apiClient.get<PeriodComparison>("/analytics/compare", {
    params: { current: currentPeriod, previous: previousPeriod },
  });
  return response.data;
}

/** Export analytics data as CSV or JSON */
export async function exportAnalytics(
  period: AnalyticsPeriod = "30d",
  format: "csv" | "json" = "csv",
): Promise<void> {
  const response = await apiClient.get("/analytics/export", {
    params: { period, format },
    responseType: "blob",
  });

  const blob = new Blob([response.data], {
    type: format === "csv" ? "text/csv" : "application/json",
  });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.setAttribute(
    "download",
    `aria-analytics-${period}.${format}`,
  );
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
}
