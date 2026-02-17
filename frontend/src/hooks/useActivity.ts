import { useQuery, useInfiniteQuery } from "@tanstack/react-query";
import {
  getActivityFeed,
  pollActivity,
  getActivityStats,
  getAgentStatus,
  getActivityDetail,
} from "@/api/activity";
import type { ActivityFilters } from "@/api/activity";

const PAGE_SIZE = 30;

export const activityKeys = {
  all: ["activity"] as const,
  feed: (filters?: Omit<ActivityFilters, "page" | "page_size">) =>
    [...activityKeys.all, "feed", filters ?? {}] as const,
  poll: (since: string) => [...activityKeys.all, "poll", since] as const,
  stats: (period: string) => [...activityKeys.all, "stats", period] as const,
  agents: () => [...activityKeys.all, "agents"] as const,
  detail: (id: string) => [...activityKeys.all, "detail", id] as const,
};

/** Infinite-scroll activity feed with server-side pagination. */
export function useActivityFeed(
  filters?: Omit<ActivityFilters, "page" | "page_size">
) {
  return useInfiniteQuery({
    queryKey: activityKeys.feed(filters),
    queryFn: ({ pageParam }) =>
      getActivityFeed({ ...filters, page: pageParam, page_size: PAGE_SIZE }),
    initialPageParam: 1,
    getNextPageParam: (lastPage) => {
      const loaded = lastPage.page * PAGE_SIZE;
      return loaded < lastPage.total ? lastPage.page + 1 : undefined;
    },
  });
}

/** Poll for new activity items since a given ISO timestamp. Polls every 10s. */
export function useActivityPoll(since: string | null) {
  return useQuery({
    queryKey: activityKeys.poll(since ?? ""),
    queryFn: () => pollActivity(since!),
    enabled: !!since,
    refetchInterval: 10_000,
  });
}

/** Activity summary stats for a given period. */
export function useActivityStats(period = "7d") {
  return useQuery({
    queryKey: activityKeys.stats(period),
    queryFn: () => getActivityStats(period),
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
