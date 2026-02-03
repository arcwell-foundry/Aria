import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  generateMeetingBrief,
  getMeetingBrief,
  getUpcomingMeetings,
  type GenerateBriefRequest,
} from "@/api/meetingBriefs";

// Query keys factory
export const meetingBriefKeys = {
  all: ["meetingBriefs"] as const,
  brief: (calendarEventId: string) => [...meetingBriefKeys.all, "brief", calendarEventId] as const,
  upcoming: (limit: number) => [...meetingBriefKeys.all, "upcoming", { limit }] as const,
};

// Get meeting brief by calendar event ID
export function useMeetingBrief(calendarEventId: string) {
  return useQuery({
    queryKey: meetingBriefKeys.brief(calendarEventId),
    queryFn: () => getMeetingBrief(calendarEventId),
    enabled: !!calendarEventId,
    staleTime: 1000 * 60 * 2, // 2 minutes
    // Poll while generating
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "generating" || status === "pending") {
        return 3000; // Poll every 3 seconds while generating
      }
      return false;
    },
  });
}

// Get upcoming meetings with brief status
export function useUpcomingMeetings(limit = 10) {
  return useQuery({
    queryKey: meetingBriefKeys.upcoming(limit),
    queryFn: () => getUpcomingMeetings(limit),
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
}

// Generate or regenerate a meeting brief
export function useGenerateMeetingBrief() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      calendarEventId,
      request,
    }: {
      calendarEventId: string;
      request: GenerateBriefRequest;
    }) => generateMeetingBrief(calendarEventId, request),
    onSuccess: (data, { calendarEventId }) => {
      // Update the brief cache
      queryClient.setQueryData(meetingBriefKeys.brief(calendarEventId), data);
      // Invalidate upcoming meetings to refresh status
      queryClient.invalidateQueries({ queryKey: meetingBriefKeys.all });
    },
  });
}
