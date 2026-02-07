import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationOptions,
  type UseQueryOptions,
} from "@tanstack/react-query";
import {
  getDataExport,
  deleteUserData,
  deleteDigitalTwin,
  getConsentStatus,
  updateConsent,
  getRetentionPolicies,
  type DeleteDataRequest,
  type DataExportResponse,
  type DeleteDataResponse,
  type DigitalTwinDeleteResponse,
  type ConsentStatusResponse,
  type UpdateConsentRequest,
  type UpdateConsentResponse,
  type RetentionPoliciesResponse,
} from "@/api/compliance";

// Query keys
export const complianceKeys = {
  all: ["compliance"] as const,
  dataExport: () => [...complianceKeys.all, "data-export"] as const,
  consent: () => [...complianceKeys.all, "consent"] as const,
  retention: () => [...complianceKeys.all, "retention"] as const,
};

// Data Export Query
export function useDataExport(options?: UseQueryOptions<DataExportResponse>) {
  return useQuery({
    queryKey: complianceKeys.dataExport(),
    queryFn: getDataExport,
    ...options,
  });
}

// Consent Status Query
export function useConsentStatus(options?: UseQueryOptions<ConsentStatusResponse>) {
  return useQuery({
    queryKey: complianceKeys.consent(),
    queryFn: getConsentStatus,
    ...options,
  });
}

// Retention Policies Query
export function useRetentionPolicies(options?: UseQueryOptions<RetentionPoliciesResponse>) {
  return useQuery({
    queryKey: complianceKeys.retention(),
    queryFn: getRetentionPolicies,
    ...options,
  });
}

// Delete User Data Mutation
export function useDeleteUserData(
  options?: UseMutationOptions<DeleteDataResponse, Error, DeleteDataRequest>
) {
  return useMutation({
    mutationFn: (data: DeleteDataRequest) => deleteUserData(data),
    ...options,
  });
}

// Delete Digital Twin Mutation
export function useDeleteDigitalTwin(
  options?: UseMutationOptions<DigitalTwinDeleteResponse, Error, void>
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => deleteDigitalTwin(),
    onSuccess: () => {
      // Invalidate consent to refresh any related data
      queryClient.invalidateQueries({ queryKey: complianceKeys.consent() });
    },
    ...options,
  });
}

// Update Consent Mutation
export function useUpdateConsent(
  options?: UseMutationOptions<UpdateConsentResponse, Error, UpdateConsentRequest>
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: UpdateConsentRequest) => updateConsent(data),
    onSuccess: () => {
      // Invalidate consent to refresh status
      queryClient.invalidateQueries({ queryKey: complianceKeys.consent() });
    },
    ...options,
  });
}

// Trigger Data Export Mutation (for manual refresh)
export function useRefreshDataExport(
  options?: UseMutationOptions<DataExportResponse, Error, void>
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => getDataExport(),
    onSuccess: (data) => {
      queryClient.setQueryData(complianceKeys.dataExport(), data);
    },
    ...options,
  });
}
