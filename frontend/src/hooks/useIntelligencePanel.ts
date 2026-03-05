/**
 * useIntelligencePanel - Hook for fetching intelligence panel data
 *
 * Fetches on mount and refetches every 2 minutes so meetings
 * and signals stay current while the user is chatting.
 */

import { useQuery } from '@tanstack/react-query';
import { fetchIntelligencePanel } from '@/api/intelligencePanel';
import type { IntelligencePanelResponse } from '@/api/intelligencePanel';

export const intelligencePanelKeys = {
  all: ['intelligence-panel'] as const,
};

interface UseIntelligencePanelReturn {
  data: IntelligencePanelResponse | undefined;
  isLoading: boolean;
  refetch: () => void;
}

export function useIntelligencePanel(): UseIntelligencePanelReturn {
  const { data, isLoading, refetch } = useQuery({
    queryKey: intelligencePanelKeys.all,
    queryFn: fetchIntelligencePanel,
    staleTime: 1000 * 60 * 2, // 2 minutes
    refetchInterval: 1000 * 60 * 2, // Poll every 2 minutes
    refetchOnWindowFocus: true,
  });

  return {
    data,
    isLoading,
    refetch,
  };
}
