import { useQuery } from "@tanstack/react-query";
import {
  fetchUpcomingMeetings,
  type UpcomingMeetingWithContext,
} from "@/api/communications";

export const upcomingMeetingsKeys = {
  all: ["upcoming-meetings"] as const,
  list: (hoursAhead: number) =>
    [...upcomingMeetingsKeys.all, { hoursAhead }] as const,
};

/**
 * Fetch upcoming meetings enriched with email context.
 *
 * Cached for 5 minutes (staleTime) to avoid expensive calendar lookups
 * on every page view. Refetches on window focus.
 */
export function useUpcomingMeetings(hoursAhead: number = 24) {
  return useQuery<UpcomingMeetingWithContext[]>({
    queryKey: upcomingMeetingsKeys.list(hoursAhead),
    queryFn: () => fetchUpcomingMeetings(hoursAhead),
    staleTime: 1000 * 60 * 5, // 5 minutes
    refetchOnWindowFocus: true,
    // Never block page render — meetings are supplemental
    placeholderData: [],
  });
}
