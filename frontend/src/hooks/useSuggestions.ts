/**
 * useSuggestions - Hook for context-aware suggestion chips
 *
 * Fetches suggestions on mount, refetches after streaming ends,
 * and polls every 5 minutes.
 */

import { useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchSuggestions } from '@/api/suggestions';
import type { SuggestionChip } from '@/api/suggestions';
import { useConversationStore } from '@/stores/conversationStore';

// Query keys
export const suggestionsKeys = {
  all: ['suggestions'] as const,
};

interface UseSuggestionsReturn {
  suggestions: SuggestionChip[];
  isLoading: boolean;
  refetch: () => void;
}

export function useSuggestions(): UseSuggestionsReturn {
  const isStreaming = useConversationStore((s) => s.isStreaming);
  const prevIsStreamingRef = useRef(isStreaming);

  // Fetch suggestions with React Query
  const { data, isLoading, refetch } = useQuery({
    queryKey: suggestionsKeys.all,
    queryFn: fetchSuggestions,
    staleTime: 1000 * 60 * 5, // 5 minutes
    refetchInterval: 1000 * 60 * 5, // Poll every 5 minutes
    refetchOnWindowFocus: true,
  });

  // Refetch when streaming transitions from true to false (ARIA response completed)
  useEffect(() => {
    const wasStreaming = prevIsStreamingRef.current;
    prevIsStreamingRef.current = isStreaming;

    // If streaming just ended, refetch suggestions
    if (wasStreaming && !isStreaming) {
      refetch();
    }
  }, [isStreaming, refetch]);

  return {
    suggestions: data?.suggestions ?? [],
    isLoading,
    refetch,
  };
}
