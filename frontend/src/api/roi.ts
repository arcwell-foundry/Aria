/** ROI Analytics API Client (US-943 Task 6).

 * TypeScript interfaces and API functions for fetching Return on Investment metrics
 * from the ARIA analytics endpoints. Mirrors the backend ROI Pydantic models.
 */

import { apiClient } from "./client";

// Type definitions matching backend Pydantic models
export type ROIPeriod = "7d" | "30d" | "90d" | "all";

/**
 * Detailed breakdown of time saved across activities.
 */
export interface TimeSavedBreakdown {
  /** Email drafts time savings: {count, estimated_hours} */
  email_drafts: {
    count: number;
    estimated_hours: number;
  };
  /** Meeting prep time savings: {count, estimated_hours} */
  meeting_prep: {
    count: number;
    estimated_hours: number;
  };
  /** Research reports time savings: {count, estimated_hours} */
  research_reports: {
    count: number;
    estimated_hours: number;
  };
  /** CRM updates time savings: {count, estimated_hours} */
  crm_updates: {
    count: number;
    estimated_hours: number;
  };
}

/**
 * Time saved metrics for ROI calculation.
 */
export interface TimeSavedMetrics {
  /** Total hours saved in the period */
  hours: number;
  /** Detailed breakdown of time savings by activity */
  breakdown: TimeSavedBreakdown;
}

/**
 * Intelligence delivered metrics showing ARIA's knowledge contributions.
 */
export interface IntelligenceDeliveredMetrics {
  /** Number of facts discovered and stored in semantic memory */
  facts_discovered: number;
  /** Number of market signals detected from communications */
  signals_detected: number;
  /** Number of knowledge gaps filled proactively */
  gaps_filled: number;
  /** Number of meeting briefings generated */
  briefings_generated: number;
}

/**
 * Actions taken metrics showing ARIA's autonomous and assisted actions.
 */
export interface ActionsTakenMetrics {
  /** Total actions taken by ARIA */
  total: number;
  /** Actions taken automatically without user review */
  auto_approved: number;
  /** Actions taken after user review and approval */
  user_approved: number;
  /** Actions suggested but rejected by user */
  rejected: number;
}

/**
 * Pipeline impact metrics showing ARIA's contribution to sales pipeline.
 */
export interface PipelineImpactMetrics {
  /** Number of new leads discovered by ARIA */
  leads_discovered: number;
  /** Number of meetings prepared with briefings */
  meetings_prepped: number;
  /** Number of follow-up actions completed */
  follow_ups_sent: number;
}

/**
 * A single data point in the weekly time-saved trend.
 */
export interface WeeklyTrendPoint {
  /** ISO date string for the start of the week (YYYY-MM-DD) */
  week_start: string;
  /** Total hours saved during this week */
  hours_saved: number;
}

/**
 * Complete ROI metrics response for the dashboard.
 */
export interface ROIMetricsResponse {
  /** Time saved metrics and breakdown */
  time_saved: TimeSavedMetrics;
  /** Intelligence discovery and delivery metrics */
  intelligence_delivered: IntelligenceDeliveredMetrics;
  /** Autonomous and assisted action metrics */
  actions_taken: ActionsTakenMetrics;
  /** Sales pipeline impact metrics */
  pipeline_impact: PipelineImpactMetrics;
  /** Weekly time-saved trend for the period */
  weekly_trend: WeeklyTrendPoint[];
  /** Time period covered by these metrics (7d, 30d, 90d, all) */
  period: ROIPeriod;
  /** ISO timestamp when metrics were calculated */
  calculated_at: string;
  /** Average hours saved per week in the period */
  time_saved_per_week: number | null;
  /** Rate of user-approved actions (auto + user) / total */
  action_approval_rate: number | null;
}

/**
 * Get ROI metrics for the specified time period
 * @param period - Time period: "7d", "30d", "90d", or "all"
 * @returns ROI metrics response with all metric categories
 */
export async function getROIMetrics(period: ROIPeriod = "30d"): Promise<ROIMetricsResponse> {
  const response = await apiClient.get<ROIMetricsResponse>("/analytics/roi", {
    params: { period },
  });
  return response.data;
}

/**
 * Get weekly time-saved trend for the specified time period
 * @param period - Time period: "7d", "30d", "90d", or "all"
 * @returns Array of weekly trend points with week_start and hours_saved
 */
export async function getROITrend(period: ROIPeriod = "90d"): Promise<WeeklyTrendPoint[]> {
  const response = await apiClient.get<WeeklyTrendPoint[]>("/analytics/roi/trend", {
    params: { period },
  });
  return response.data;
}
