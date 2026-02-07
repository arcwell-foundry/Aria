/** ROI (Return on Investment) types for analytics dashboard (US-943). */

/** Detailed breakdown of time saved across activities */
export interface TimeSavedBreakdown {
  email_drafts: { count: number; estimated_hours: number };
  meeting_prep: { count: number; estimated_hours: number };
  research_reports: { count: number; estimated_hours: number };
  crm_updates: { count: number; estimated_hours: number };
}

/** Time saved metrics for ROI calculation */
export interface TimeSavedMetrics {
  hours: number;
  breakdown: TimeSavedBreakdown;
}

/** Intelligence delivered metrics showing ARIA's knowledge contributions */
export interface IntelligenceDeliveredMetrics {
  facts_discovered: number;
  signals_detected: number;
  gaps_filled: number;
  briefings_generated: number;
}

/** Actions taken metrics showing ARIA's autonomous and assisted actions */
export interface ActionsTakenMetrics {
  total: number;
  auto_approved: number;
  user_approved: number;
  rejected: number;
}

/** Pipeline impact metrics showing ARIA's contribution to sales pipeline */
export interface PipelineImpactMetrics {
  leads_discovered: number;
  meetings_prepped: number;
  follow_ups_sent: number;
}

/** A single data point in the weekly time-saved trend */
export interface WeeklyTrendPoint {
  week_start: string; // ISO date string (YYYY-MM-DD)
  hours_saved: number;
}

/** Valid time periods for ROI queries */
export type ROIPeriod = "7d" | "30d" | "90d" | "all";
