/** Analytics React Query Hooks.
 *
 * Provides typed hooks for fetching analytics data from the ARIA backend.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { UseQueryOptions } from "@tanstack/react-query";
import {
  comparePeriods,
  exportAnalytics,
  getActivityTrends,
  getAriaImpactSummary,
  getConversionFunnel,
  getOverviewMetrics,
  getResponseTimeMetrics,
  type ActivityTrends,
  type AnalyticsPeriod,
  type AriaImpactSummary,
  type ConversionFunnel,
  type OverviewMetrics,
  type PeriodComparison,
  type ResponseTimeMetrics,
  type TrendGranularity,
} from "@/api/analytics";

// ---------------------------------------------------------------------------
// Query Keys
// ---------------------------------------------------------------------------

export const analyticsKeys = {
  all: ["analytics"] as const,
  overview: (period: AnalyticsPeriod) =>
    [...analyticsKeys.all, "overview", period] as const,
  funnel: (period: AnalyticsPeriod) =>
    [...analyticsKeys.all, "funnel", period] as const,
  trends: (period: AnalyticsPeriod, granularity: TrendGranularity) =>
    [...analyticsKeys.all, "trends", period, granularity] as const,
  responseTimes: (period: AnalyticsPeriod) =>
    [...analyticsKeys.all, "responseTimes", period] as const,
  impact: (period: AnalyticsPeriod) =>
    [...analyticsKeys.all, "impact", period] as const,
  compare: (current: AnalyticsPeriod, previous: AnalyticsPeriod) =>
    [...analyticsKeys.all, "compare", current, previous] as const,
};

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

/** Fetch overview metrics (leads, meetings, emails, time saved) */
export function useOverviewMetrics(
  period: AnalyticsPeriod = "30d",
  options?: Omit<
    UseQueryOptions<OverviewMetrics>,
    "queryKey" | "queryFn"
  >,
) {
  return useQuery({
    queryKey: analyticsKeys.overview(period),
    queryFn: () => getOverviewMetrics(period),
    staleTime: 5 * 60 * 1000, // 5 minutes
    ...options,
  });
}

/** Fetch conversion funnel data */
export function useConversionFunnel(
  period: AnalyticsPeriod = "30d",
  options?: Omit<
    UseQueryOptions<ConversionFunnel>,
    "queryKey" | "queryFn"
  >,
) {
  return useQuery({
    queryKey: analyticsKeys.funnel(period),
    queryFn: () => getConversionFunnel(period),
    staleTime: 5 * 60 * 1000,
    ...options,
  });
}

/** Fetch activity trends */
export function useActivityTrends(
  period: AnalyticsPeriod = "30d",
  granularity: TrendGranularity = "day",
  options?: Omit<
    UseQueryOptions<ActivityTrends>,
    "queryKey" | "queryFn"
  >,
) {
  return useQuery({
    queryKey: analyticsKeys.trends(period, granularity),
    queryFn: () => getActivityTrends(period, granularity),
    staleTime: 5 * 60 * 1000,
    ...options,
  });
}

/** Fetch response time metrics */
export function useResponseTimeMetrics(
  period: AnalyticsPeriod = "30d",
  options?: Omit<
    UseQueryOptions<ResponseTimeMetrics>,
    "queryKey" | "queryFn"
  >,
) {
  return useQuery({
    queryKey: analyticsKeys.responseTimes(period),
    queryFn: () => getResponseTimeMetrics(period),
    staleTime: 5 * 60 * 1000,
    ...options,
  });
}

/** Fetch ARIA impact summary */
export function useAriaImpactSummary(
  period: AnalyticsPeriod = "30d",
  options?: Omit<
    UseQueryOptions<AriaImpactSummary>,
    "queryKey" | "queryFn"
  >,
) {
  return useQuery({
    queryKey: analyticsKeys.impact(period),
    queryFn: () => getAriaImpactSummary(period),
    staleTime: 5 * 60 * 1000,
    ...options,
  });
}

/** Compare metrics between two periods */
export function usePeriodComparison(
  currentPeriod: AnalyticsPeriod = "30d",
  previousPeriod: AnalyticsPeriod = "30d",
  options?: Omit<
    UseQueryOptions<PeriodComparison>,
    "queryKey" | "queryFn"
  >,
) {
  return useQuery({
    queryKey: analyticsKeys.compare(currentPeriod, previousPeriod),
    queryFn: () => comparePeriods(currentPeriod, previousPeriod),
    staleTime: 5 * 60 * 1000,
    ...options,
  });
}

/** Invalidate all analytics queries */
export function useInvalidateAnalytics() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: analyticsKeys.all });
  };
}

/** Export analytics data */
export function useExportAnalytics() {
  return useMutation({
    mutationFn: ({
      period,
      format,
    }: {
      period: AnalyticsPeriod;
      format: "csv" | "json";
    }) => exportAnalytics(period, format),
  });
}
