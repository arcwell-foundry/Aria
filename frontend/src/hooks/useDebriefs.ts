/**
 * React Query hooks for debrief operations.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getDebrief,
  updateDebrief,
  listDebriefs,
  getPendingDebriefs,
  type UpdateDebriefRequest,
} from "@/api/debriefs";

// Filter type for list queries
export interface DebriefFilters {
  page?: number;
  pageSize?: number;
  startDate?: string;
  endDate?: string;
  search?: string;
}

// Query keys factory
export const debriefKeys = {
  all: ["debriefs"] as const,
  lists: () => [...debriefKeys.all, "list"] as const,
  list: (filters: DebriefFilters) => [...debriefKeys.lists(), filters] as const,
  pending: () => [...debriefKeys.all, "pending"] as const,
  details: () => [...debriefKeys.all, "detail"] as const,
  detail: (meetingId: string) => [...debriefKeys.details(), meetingId] as const,
};

/**
 * Get a debrief by meeting ID.
 */
export function useDebrief(meetingId: string) {
  return useQuery({
    queryKey: debriefKeys.detail(meetingId),
    queryFn: () => getDebrief(meetingId),
    enabled: !!meetingId,
  });
}

/**
 * Update a debrief mutation.
 */
export function useUpdateDebrief() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      debriefId,
      data,
    }: {
      debriefId: string;
      data: UpdateDebriefRequest;
    }) => updateDebrief(debriefId, data),
    onSuccess: (updatedDebrief) => {
      // Invalidate and refetch the debrief
      queryClient.invalidateQueries({
        queryKey: debriefKeys.detail(updatedDebrief.meeting_id),
      });
      // Also invalidate lists
      queryClient.invalidateQueries({ queryKey: debriefKeys.lists() });
    },
  });
}

/**
 * List debriefs with optional filtering.
 */
export function useDebriefs(filters: DebriefFilters = {}) {
  return useQuery({
    queryKey: debriefKeys.list(filters),
    queryFn: () =>
      listDebriefs(
        filters.page ?? 1,
        filters.pageSize ?? 20,
        filters.startDate,
        filters.endDate,
        filters.search
      ),
  });
}

/**
 * Get pending debriefs (meetings without debriefs).
 */
export function usePendingDebriefs() {
  return useQuery({
    queryKey: debriefKeys.pending(),
    queryFn: getPendingDebriefs,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}
