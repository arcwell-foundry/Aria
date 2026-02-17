/**
 * useBriefingStatus - Hook for video briefing status with REST + WebSocket
 *
 * Checks briefing status on mount and listens for WebSocket updates.
 * Handles viewed state to avoid re-prompting.
 */

import { useCallback, useEffect, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getBriefingStatus, markBriefingViewed, getTextBriefing } from '@/api/briefings';
import type { BriefingActionItem } from '@/api/briefings';
import { wsManager } from '@/core/WebSocketManager';

// Query keys
export const briefingStatusKeys = {
  status: ['briefing', 'status'] as const,
};

interface BriefingReadyPayload {
  briefing_id: string;
  duration: number;
  topics: string[];
}

interface UseBriefingStatusReturn {
  // State from REST
  ready: boolean;
  viewed: boolean;
  briefingId: string | null;
  duration: number;
  topics: string[];

  // Loading state
  isLoading: boolean;

  // Dismissed state (session-only, in-memory)
  dismissed: boolean;

  // Actions
  markViewed: () => Promise<{
    key_points: string[];
    action_items: BriefingActionItem[];
    completed_at: string;
  } | null>;
  dismiss: () => void;
  fetchTextBriefing: () => Promise<string>;

  // For showing summary after briefing ends
  summaryData: {
    key_points: string[];
    action_items: BriefingActionItem[];
    completed_at: string;
  } | null;
  clearSummaryData: () => void;
}

export function useBriefingStatus(): UseBriefingStatusReturn {
  const queryClient = useQueryClient();

  // Session-only dismissed state (not persisted)
  const [dismissed, setDismissed] = useState(false);

  // Summary data from markViewed (for BriefingSummaryCard)
  const [summaryData, setSummaryData] = useState<{
    key_points: string[];
    action_items: BriefingActionItem[];
    completed_at: string;
  } | null>(null);

  // Fetch briefing status via REST
  const { data, isLoading } = useQuery({
    queryKey: briefingStatusKeys.status,
    queryFn: getBriefingStatus,
    staleTime: 1000 * 60 * 5, // 5 minutes
    refetchOnWindowFocus: true,
  });

  // Mark viewed mutation
  const markViewedMutation = useMutation({
    mutationFn: async () => {
      if (!data?.briefing_id) return null;
      return markBriefingViewed(data.briefing_id);
    },
    onSuccess: (result) => {
      if (result) {
        setSummaryData(result);
      }
      // Invalidate to refresh viewed state
      queryClient.invalidateQueries({ queryKey: briefingStatusKeys.status });
    },
  });

  // Fetch text briefing
  const fetchTextBriefingMutation = useMutation({
    mutationFn: async () => {
      if (!data?.briefing_id) throw new Error('No briefing available');
      return getTextBriefing(data.briefing_id);
    },
  });

  // Listen for WebSocket briefing.ready event
  useEffect(() => {
    const handleBriefingReady = (payload: unknown) => {
      const event = payload as BriefingReadyPayload;
      // Update the query cache with new briefing data
      queryClient.setQueryData(briefingStatusKeys.status, {
        ready: true,
        viewed: false,
        briefing_id: event.briefing_id,
        duration: event.duration,
        topics: event.topics,
      });
      // Reset dismissed state for new briefing
      setDismissed(false);
    };

    wsManager.on('briefing.ready', handleBriefingReady);

    return () => {
      wsManager.off('briefing.ready', handleBriefingReady);
    };
  }, [queryClient]);

  // Mark briefing as viewed
  const markViewed = useCallback(async () => {
    return markViewedMutation.mutateAsync();
  }, [markViewedMutation]);

  // Dismiss the card (session-only)
  const dismiss = useCallback(() => {
    setDismissed(true);
  }, []);

  // Fetch text briefing
  const fetchTextBriefing = useCallback(async () => {
    return fetchTextBriefingMutation.mutateAsync();
  }, [fetchTextBriefingMutation]);

  // Clear summary data
  const clearSummaryData = useCallback(() => {
    setSummaryData(null);
  }, []);

  // Derive final state
  const ready = data?.ready ?? false;
  const viewed = data?.viewed ?? false;
  const briefingId = data?.briefing_id ?? null;
  const duration = data?.duration ?? 5;
  const topics = data?.topics ?? [];

  return {
    ready,
    viewed,
    briefingId,
    duration,
    topics,
    isLoading,
    dismissed,
    markViewed,
    dismiss,
    fetchTextBriefing,
    summaryData,
    clearSummaryData,
  };
}
