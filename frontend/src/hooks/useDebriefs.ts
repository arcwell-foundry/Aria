/**
 * React Query hooks for debrief operations.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getDebrief,
  updateDebrief,
  type UpdateDebriefRequest,
} from "@/api/debriefs";

// Query keys factory
export const debriefKeys = {
  all: ["debriefs"] as const,
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
    },
  });
}
