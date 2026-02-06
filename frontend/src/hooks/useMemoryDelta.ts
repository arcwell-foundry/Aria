import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { correctMemory, getMemoryDelta } from "@/api/memory";
import type { CorrectionRequest } from "@/api/memory";

export const memoryDeltaKeys = {
  all: ["memoryDelta"] as const,
  delta: (since?: string, domain?: string) =>
    [...memoryDeltaKeys.all, { since, domain }] as const,
};

export function useMemoryDelta(since?: string, domain?: string) {
  return useQuery({
    queryKey: memoryDeltaKeys.delta(since, domain),
    queryFn: () => getMemoryDelta(since, domain),
    staleTime: 1000 * 60 * 2,
  });
}

export function useCorrectMemory() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (correction: CorrectionRequest) => correctMemory(correction),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: memoryDeltaKeys.all });
    },
  });
}
