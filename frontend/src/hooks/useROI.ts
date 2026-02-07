import { useQuery, useQueryClient, type UseQueryOptions } from "@tanstack/react-query";
import {
  getROIMetrics,
  getROITrend,
  type ROIMetricsResponse,
  type ROIPeriod,
  type WeeklyTrendPoint,
} from "@/api/roi";

// Query keys
export const roiKeys = {
  all: ["roi"] as const,
  metrics: (period: ROIPeriod) => [...roiKeys.all, "metrics", period] as const,
  trend: (period: ROIPeriod) => [...roiKeys.all, "trend", period] as const,
};

/**
 * Hook to fetch ROI metrics for a specific time period
 * @param period - Time period: "7d", "30d", "90d", or "all" (default: "30d")
 * @param options - Additional React Query options
 * @returns Query result with ROI metrics data
 */
export function useROIMetrics(
  period: ROIPeriod = "30d",
  options?: Omit<UseQueryOptions<ROIMetricsResponse>, "queryKey" | "queryFn">
) {
  return useQuery({
    queryKey: roiKeys.metrics(period),
    queryFn: () => getROIMetrics(period),
    staleTime: 5 * 60 * 1000, // 5 minutes
    ...options,
  });
}

/**
 * Hook to fetch ROI weekly trend for a specific time period
 * @param period - Time period: "7d", "30d", "90d", or "all" (default: "90d")
 * @param options - Additional React Query options
 * @returns Query result with weekly trend data points
 */
export function useROITrend(
  period: ROIPeriod = "90d",
  options?: Omit<UseQueryOptions<WeeklyTrendPoint[]>, "queryKey" | "queryFn">
) {
  return useQuery({
    queryKey: roiKeys.trend(period),
    queryFn: () => getROITrend(period),
    staleTime: 10 * 60 * 1000, // 10 minutes
    ...options,
  });
}

/**
 * Hook to invalidate all ROI queries
 * Use this to trigger a refetch of all ROI data after mutations
 * @returns Function to invalidate all ROI queries
 */
export function useInvalidateROI() {
  const queryClient = useQueryClient();

  return () => {
    queryClient.invalidateQueries({ queryKey: roiKeys.all });
  };
}
