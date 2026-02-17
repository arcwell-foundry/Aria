/**
 * React Query hook for fetching conversion scores for leads.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getConversionScore,
  type ScoreExplanation,
} from "@/api/leads";

// Query keys factory
export const conversionScoreKeys = {
  all: ["conversionScores"] as const,
  detail: (leadId: string) => [...conversionScoreKeys.all, leadId] as const,
};

/**
 * Get conversion score with explanation for a lead.
 */
export function useConversionScore(leadId: string, enabled = true) {
  return useQuery({
    queryKey: conversionScoreKeys.detail(leadId),
    queryFn: () => getConversionScore(leadId),
    enabled: !!leadId && enabled,
    staleTime: 1000 * 60 * 60, // 1 hour (scores cached on backend for 24h)
  });
}

/**
 * Refresh conversion score for a lead (force recalculation).
 */
export function useRefreshConversionScore() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (leadId: string) => getConversionScore(leadId, true),
    onSuccess: (data, leadId) => {
      // Update the cached score
      queryClient.setQueryData(conversionScoreKeys.detail(leadId), data);
      // Also invalidate leads list to update any cached conversion scores there
      queryClient.invalidateQueries({ queryKey: ["leads"] });
    },
  });
}

export type { ScoreExplanation };
