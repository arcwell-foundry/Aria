import { useQuery } from "@tanstack/react-query";
import {
  getEnrichmentStatus,
  type EnrichmentStatus,
} from "@/api/onboarding";

export const enrichmentKeys = {
  all: ["enrichment"] as const,
  status: () => [...enrichmentKeys.all, "status"] as const,
};

export function useEnrichmentStatus(enabled: boolean = true) {
  const query = useQuery({
    queryKey: enrichmentKeys.status(),
    queryFn: getEnrichmentStatus,
    enabled,
    refetchInterval: (query) => {
      const data = query.state.data as EnrichmentStatus | undefined;
      // Poll every 5s while in progress, stop when complete
      if (data?.status === "complete") {
        return false;
      }
      return 5000;
    },
    staleTime: 2000,
  });

  return {
    ...query,
    status: query.data?.status ?? null,
    qualityScore: query.data?.quality_score ?? null,
    classification: query.data?.classification ?? null,
    enrichedAt: query.data?.enriched_at ?? null,
    isComplete: query.data?.status === "complete",
    isInProgress: query.data?.status === "in_progress",
  };
}
