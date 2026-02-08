import { useQuery } from "@tanstack/react-query";
import {
  getActivityFeed,
  getAgentStatus,
  getActivityDetail,
} from "@/api/activity";
import type { ActivityFilters } from "@/api/activity";

export const activityKeys = {
  all: ["activity"] as const,
  feed: (filters?: ActivityFilters) =>
    [...activityKeys.all, "feed", filters ?? {}] as const,
  agents: () => [...activityKeys.all, "agents"] as const,
  detail: (id: string) => [...activityKeys.all, "detail", id] as const,
};

export function useActivityFeed(filters?: ActivityFilters) {
  return useQuery({
    queryKey: activityKeys.feed(filters),
    queryFn: () => getActivityFeed(filters),
    refetchInterval: 15_000,
  });
}

export function useAgentStatus() {
  return useQuery({
    queryKey: activityKeys.agents(),
    queryFn: () => getAgentStatus(),
    refetchInterval: 10_000,
  });
}

export function useActivityDetail(activityId: string) {
  return useQuery({
    queryKey: activityKeys.detail(activityId),
    queryFn: () => getActivityDetail(activityId),
    enabled: !!activityId,
  });
}
