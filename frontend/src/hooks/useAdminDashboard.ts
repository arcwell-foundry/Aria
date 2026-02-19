/** Admin Dashboard React Query Hooks.
 *
 * Provides typed hooks for fetching admin dashboard data.
 */

import { useQuery } from "@tanstack/react-query";
import type { UseQueryOptions } from "@tanstack/react-query";
import {
  getDashboardOverview,
  getActiveOODACycles,
  getAgentWaterfall,
  getTeamUsage,
  getTrustSummaries,
  getTrustEvolution,
  getVerificationStats,
  type DashboardOverview,
  type ActiveOODACycle,
  type AgentExecution,
  type TeamUsageResponse,
  type UserTrustSummary,
  type TrustEvolutionPoint,
  type VerificationStatsResponse,
} from "@/api/adminDashboard";

// ---------------------------------------------------------------------------
// Query Keys
// ---------------------------------------------------------------------------

export const adminDashboardKeys = {
  all: ["admin-dashboard"] as const,
  overview: () => [...adminDashboardKeys.all, "overview"] as const,
  oodaActive: () => [...adminDashboardKeys.all, "ooda-active"] as const,
  agentWaterfall: (hours: number) =>
    [...adminDashboardKeys.all, "agent-waterfall", hours] as const,
  teamUsage: (days: number, granularity: string) =>
    [...adminDashboardKeys.all, "team-usage", days, granularity] as const,
  trustSummaries: () => [...adminDashboardKeys.all, "trust-summaries"] as const,
  trustEvolution: (userId?: string, days?: number) =>
    [...adminDashboardKeys.all, "trust-evolution", userId, days] as const,
  verificationStats: (days?: number) =>
    [...adminDashboardKeys.all, "verification-stats", days] as const,
};

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function useDashboardOverview(
  options?: Omit<UseQueryOptions<DashboardOverview>, "queryKey" | "queryFn">,
) {
  return useQuery({
    queryKey: adminDashboardKeys.overview(),
    queryFn: getDashboardOverview,
    staleTime: 30 * 1000,
    ...options,
  });
}

export function useActiveOODACycles(
  options?: Omit<UseQueryOptions<ActiveOODACycle[]>, "queryKey" | "queryFn">,
) {
  return useQuery({
    queryKey: adminDashboardKeys.oodaActive(),
    queryFn: () => getActiveOODACycles(),
    refetchInterval: 5 * 1000,
    ...options,
  });
}

export function useAgentWaterfall(
  hours: number = 24,
  options?: Omit<UseQueryOptions<AgentExecution[]>, "queryKey" | "queryFn">,
) {
  return useQuery({
    queryKey: adminDashboardKeys.agentWaterfall(hours),
    queryFn: () => getAgentWaterfall(hours),
    staleTime: 30 * 1000,
    ...options,
  });
}

export function useTeamUsage(
  days: number = 30,
  granularity: string = "day",
  options?: Omit<UseQueryOptions<TeamUsageResponse>, "queryKey" | "queryFn">,
) {
  return useQuery({
    queryKey: adminDashboardKeys.teamUsage(days, granularity),
    queryFn: () => getTeamUsage(days, granularity),
    staleTime: 5 * 60 * 1000,
    ...options,
  });
}

export function useTrustSummaries(
  options?: Omit<UseQueryOptions<UserTrustSummary[]>, "queryKey" | "queryFn">,
) {
  return useQuery({
    queryKey: adminDashboardKeys.trustSummaries(),
    queryFn: getTrustSummaries,
    staleTime: 5 * 60 * 1000,
    ...options,
  });
}

export function useTrustEvolution(
  userId?: string,
  days: number = 30,
  options?: Omit<UseQueryOptions<TrustEvolutionPoint[]>, "queryKey" | "queryFn">,
) {
  return useQuery({
    queryKey: adminDashboardKeys.trustEvolution(userId, days),
    queryFn: () => getTrustEvolution(userId, days),
    staleTime: 5 * 60 * 1000,
    ...options,
  });
}

export function useVerificationStats(
  days: number = 30,
  options?: Omit<UseQueryOptions<VerificationStatsResponse>, "queryKey" | "queryFn">,
) {
  return useQuery({
    queryKey: adminDashboardKeys.verificationStats(days),
    queryFn: () => getVerificationStats(days),
    staleTime: 5 * 60 * 1000,
    ...options,
  });
}
