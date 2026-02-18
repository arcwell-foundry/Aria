import { useQuery } from "@tanstack/react-query";
import { getTraceTree, getRecentTraces } from "@/api/traces";

export const traceKeys = {
  all: ["traces"] as const,
  tree: (goalId: string) => [...traceKeys.all, "tree", goalId] as const,
  recent: (limit?: number) => [...traceKeys.all, "recent", { limit }] as const,
};

export function useTraceTree(goalId: string | null) {
  return useQuery({
    queryKey: traceKeys.tree(goalId ?? ""),
    queryFn: () => getTraceTree(goalId!),
    enabled: !!goalId,
  });
}

export function useRecentTraces(limit?: number) {
  return useQuery({
    queryKey: traceKeys.recent(limit),
    queryFn: () => getRecentTraces(limit),
  });
}
