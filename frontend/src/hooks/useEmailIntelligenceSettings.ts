import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationOptions,
  type UseQueryOptions,
} from "@tanstack/react-query";
import {
  getEmailIntelligenceSettings,
  updateEmailIntelligenceSettings,
  type EmailIntelligenceSettings,
  type UpdateEmailIntelligenceSettingsRequest,
} from "@/api/emailIntelligenceSettings";

export const emailIntelligenceKeys = {
  all: ["emailIntelligenceSettings"] as const,
  detail: () => [...emailIntelligenceKeys.all, "detail"] as const,
};

export function useEmailIntelligenceSettings(
  options?: UseQueryOptions<EmailIntelligenceSettings>
) {
  return useQuery({
    queryKey: emailIntelligenceKeys.detail(),
    queryFn: getEmailIntelligenceSettings,
    ...options,
  });
}

type MutationContext = {
  previousSettings?: EmailIntelligenceSettings;
};

export function useUpdateEmailIntelligenceSettings(
  options?: UseMutationOptions<
    EmailIntelligenceSettings,
    Error,
    UpdateEmailIntelligenceSettingsRequest,
    MutationContext
  >
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: UpdateEmailIntelligenceSettingsRequest) =>
      updateEmailIntelligenceSettings(data),
    onMutate: async (
      newData: UpdateEmailIntelligenceSettingsRequest
    ): Promise<MutationContext> => {
      await queryClient.cancelQueries({
        queryKey: emailIntelligenceKeys.detail(),
      });

      const previousSettings =
        queryClient.getQueryData<EmailIntelligenceSettings>(
          emailIntelligenceKeys.detail()
        );

      if (previousSettings) {
        queryClient.setQueryData<EmailIntelligenceSettings>(
          emailIntelligenceKeys.detail(),
          { ...previousSettings, ...newData }
        );
      }

      return { previousSettings };
    },
    onError: (_err, _newData, context) => {
      if (context?.previousSettings) {
        queryClient.setQueryData(
          emailIntelligenceKeys.detail(),
          context.previousSettings
        );
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({
        queryKey: emailIntelligenceKeys.detail(),
      });
    },
    ...options,
  });
}
