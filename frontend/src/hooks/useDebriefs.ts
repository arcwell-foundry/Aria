/**
 * React Query hooks for debrief operations.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  initiateDebrief,
  submitDebrief,
  getDebrief,
  getDebriefById,
  getDebriefsByMeeting,
  listDebriefs,
  getPendingDebriefs,
  updateDebrief,
} from "@/api/debriefs";
import type { DebriefSubmitRequest, UpdateDebriefRequest } from "@/types/debrief";

// =============================================================================
// Query Keys
// =============================================================================

/** Query keys factory for debrief queries */
export const debriefKeys = {
  all: ["debriefs"] as const,
  lists: () => [...debriefKeys.all, "list"] as const,
  list: (filters: DebriefListFilters) => [...debriefKeys.lists(), filters] as const,
  pending: () => [...debriefKeys.all, "pending"] as const,
  details: () => [...debriefKeys.all, "detail"] as const,
  detail: (id: string) => [...debriefKeys.details(), id] as const,
  byMeeting: (meetingId: string) => [...debriefKeys.all, "meeting", meetingId] as const,
};

// =============================================================================
// Filter Types
// =============================================================================

/** Filters for listing debriefs */
export interface DebriefListFilters {
  page?: number;
  page_size?: number;
  start_date?: string;
  end_date?: string;
  linked_lead_id?: string;
  search?: string;
}

/** @deprecated Use DebriefListFilters instead */
export type DebriefFilters = DebriefListFilters;

// =============================================================================
// Query Hooks
// =============================================================================

/**
 * Get a single debrief by meeting ID.
 */
export function useDebrief(meetingId: string) {
  return useQuery({
    queryKey: debriefKeys.byMeeting(meetingId),
    queryFn: () => getDebrief(meetingId),
    enabled: !!meetingId,
  });
}

/**
 * Get a single debrief by debrief ID.
 */
export function useDebriefById(debriefId: string) {
  return useQuery({
    queryKey: debriefKeys.detail(debriefId),
    queryFn: () => getDebriefById(debriefId),
    enabled: !!debriefId,
  });
}

/**
 * Get debriefs for a specific meeting.
 */
export function useDebriefsByMeeting(meetingId: string) {
  return useQuery({
    queryKey: debriefKeys.byMeeting(meetingId),
    queryFn: () => getDebriefsByMeeting(meetingId),
    enabled: !!meetingId,
  });
}

/**
 * List debriefs with optional filtering.
 */
export function useDebriefs(filters: DebriefListFilters = {}) {
  return useQuery({
    queryKey: debriefKeys.list(filters),
    queryFn: () => listDebriefs(filters),
  });
}

/**
 * Get pending debriefs (meetings without debriefs).
 */
export function usePendingDebriefs(limit?: number) {
  return useQuery({
    queryKey: debriefKeys.pending(),
    queryFn: () => getPendingDebriefs(limit),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

// =============================================================================
// Mutation Hooks
// =============================================================================

/**
 * Initiate a new debrief for a meeting.
 */
export function useInitiateDebrief() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      meetingId,
      calendarEventId,
    }: {
      meetingId: string;
      calendarEventId?: string;
    }) => initiateDebrief(meetingId, calendarEventId),
    onSuccess: () => {
      // Invalidate lists and pending to show new debrief
      queryClient.invalidateQueries({ queryKey: debriefKeys.lists() });
      queryClient.invalidateQueries({ queryKey: debriefKeys.pending() });
    },
  });
}

/**
 * Submit debrief notes (triggers AI extraction).
 */
export function useSubmitDebrief() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      debriefId,
      data,
    }: {
      debriefId: string;
      data: DebriefSubmitRequest;
    }) => submitDebrief(debriefId, data),
    onSuccess: (_, { debriefId }) => {
      // Invalidate the specific debrief and lists
      queryClient.invalidateQueries({ queryKey: debriefKeys.detail(debriefId) });
      queryClient.invalidateQueries({ queryKey: debriefKeys.lists() });
    },
  });
}

/**
 * Update a debrief (legacy, maps to useSubmitDebrief).
 * @deprecated Use useSubmitDebrief instead
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
      // Invalidate the specific debrief and lists
      queryClient.invalidateQueries({
        queryKey: debriefKeys.byMeeting(updatedDebrief.meeting_id),
      });
      queryClient.invalidateQueries({ queryKey: debriefKeys.lists() });
    },
  });
}
