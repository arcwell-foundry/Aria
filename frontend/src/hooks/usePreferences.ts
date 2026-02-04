import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getPreferences,
  updatePreferences,
  type UpdatePreferencesRequest,
  type UserPreferences,
} from "@/api/preferences";

// Query keys
export const preferenceKeys = {
  all: ["preferences"] as const,
  detail: () => [...preferenceKeys.all, "detail"] as const,
};

// Get preferences query
export function usePreferences() {
  return useQuery({
    queryKey: preferenceKeys.detail(),
    queryFn: () => getPreferences(),
  });
}

// Update preferences mutation with optimistic updates
export function useUpdatePreferences() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: UpdatePreferencesRequest) => updatePreferences(data),
    onMutate: async (newData) => {
      // Cancel any outgoing refetches
      await queryClient.cancelQueries({ queryKey: preferenceKeys.detail() });

      // Snapshot the previous value
      const previousPreferences = queryClient.getQueryData<UserPreferences>(
        preferenceKeys.detail()
      );

      // Optimistically update to the new value
      if (previousPreferences) {
        queryClient.setQueryData<UserPreferences>(preferenceKeys.detail(), {
          ...previousPreferences,
          ...newData,
          updated_at: new Date().toISOString(),
        });
      }

      // Return a context object with the snapshotted value
      return { previousPreferences };
    },
    onError: (_err, _newData, context) => {
      // Rollback to the previous value on error
      if (context?.previousPreferences) {
        queryClient.setQueryData(
          preferenceKeys.detail(),
          context.previousPreferences
        );
      }
    },
    onSettled: () => {
      // Always refetch after error or success
      queryClient.invalidateQueries({ queryKey: preferenceKeys.detail() });
    },
  });
}
