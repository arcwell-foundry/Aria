import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  generateBriefing,
  getBriefingByDate,
  getTodayBriefing,
  listBriefings,
} from "@/api/briefings";

// Query keys
export const briefingKeys = {
  all: ["briefings"] as const,
  today: () => [...briefingKeys.all, "today"] as const,
  lists: () => [...briefingKeys.all, "list"] as const,
  list: (limit: number) => [...briefingKeys.lists(), { limit }] as const,
  byDate: (date: string) => [...briefingKeys.all, "date", date] as const,
};

// Today's briefing query
export function useTodayBriefing() {
  return useQuery({
    queryKey: briefingKeys.today(),
    queryFn: () => getTodayBriefing(),
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
}

// List recent briefings query
export function useBriefingList(limit = 7) {
  return useQuery({
    queryKey: briefingKeys.list(limit),
    queryFn: () => listBriefings(limit),
  });
}

// Briefing by date query
export function useBriefingByDate(date: string) {
  return useQuery({
    queryKey: briefingKeys.byDate(date),
    queryFn: () => getBriefingByDate(date),
    enabled: !!date,
  });
}

// Regenerate briefing mutation
export function useRegenerateBriefing() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => getTodayBriefing(true),
    onSuccess: (data) => {
      queryClient.setQueryData(briefingKeys.today(), data);
      queryClient.invalidateQueries({ queryKey: briefingKeys.lists() });
    },
  });
}

// Generate briefing for specific date mutation
export function useGenerateBriefing() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (date?: string) => generateBriefing(date),
    onSuccess: (data, date) => {
      if (!date) {
        queryClient.setQueryData(briefingKeys.today(), data);
      }
      queryClient.invalidateQueries({ queryKey: briefingKeys.lists() });
    },
  });
}
