import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationOptions,
  type UseQueryOptions,
} from "@tanstack/react-query";
import {
  getEmailPreferences,
  updateEmailPreferences,
  type EmailPreferences,
  type UpdateEmailPreferencesRequest,
} from "@/api/emailPreferences";

// Query keys
export const emailPreferencesKeys = {
  all: ["emailPreferences"] as const,
  detail: () => [...emailPreferencesKeys.all, "detail"] as const,
};

// Get email preferences query
export function useEmailPreferences(options?: UseQueryOptions<EmailPreferences>) {
  return useQuery({
    queryKey: emailPreferencesKeys.detail(),
    queryFn: getEmailPreferences,
    ...options,
  });
}

// Update email preferences mutation with optimistic updates
type MutationContext = {
  previousPreferences?: EmailPreferences;
};

export function useUpdateEmailPreferences(
  options?: UseMutationOptions<
    EmailPreferences,
    Error,
    UpdateEmailPreferencesRequest,
    MutationContext
  >
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: UpdateEmailPreferencesRequest) => updateEmailPreferences(data),
    onMutate: async (newData: UpdateEmailPreferencesRequest): Promise<MutationContext> => {
      // Cancel any outgoing refetches
      await queryClient.cancelQueries({ queryKey: emailPreferencesKeys.detail() });

      // Snapshot the previous value
      const previousPreferences = queryClient.getQueryData<EmailPreferences>(
        emailPreferencesKeys.detail()
      );

      // Optimistically update to the new value
      if (previousPreferences) {
        queryClient.setQueryData<EmailPreferences>(emailPreferencesKeys.detail(), {
          ...previousPreferences,
          ...newData,
        });
      }

      // Return a context object with the snapshotted value
      return { previousPreferences };
    },
    onError: (_err, _newData, context) => {
      // Rollback to the previous value on error
      if (context?.previousPreferences) {
        queryClient.setQueryData(
          emailPreferencesKeys.detail(),
          context.previousPreferences
        );
      }
    },
    onSettled: () => {
      // Always refetch after error or success
      queryClient.invalidateQueries({ queryKey: emailPreferencesKeys.detail() });
    },
    ...options,
  });
}
