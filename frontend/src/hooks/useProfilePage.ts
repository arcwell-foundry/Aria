import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationOptions,
  type UseQueryOptions,
} from "@tanstack/react-query";
import {
  getFullProfile,
  getProfileDocuments,
  updateUserDetails,
  updateCompanyDetails,
  updatePreferences,
  type FullProfile,
  type ProfileDocuments,
  type UpdateUserDetailsRequest,
  type UpdateCompanyDetailsRequest,
  type UpdatePreferencesRequest,
} from "@/api/profile";

// Query keys
export const profilePageKeys = {
  all: ["profilePage"] as const,
  detail: () => [...profilePageKeys.all, "detail"] as const,
  documents: () => [...profilePageKeys.all, "documents"] as const,
};

// Full profile query
export function useFullProfile(options?: UseQueryOptions<FullProfile>) {
  return useQuery({
    queryKey: profilePageKeys.detail(),
    queryFn: getFullProfile,
    ...options,
  });
}

// Documents query
export function useProfileDocuments(options?: UseQueryOptions<ProfileDocuments>) {
  return useQuery({
    queryKey: profilePageKeys.documents(),
    queryFn: getProfileDocuments,
    ...options,
  });
}

// Update user details mutation
export function useUpdateUserDetails(
  options?: UseMutationOptions<Record<string, unknown>, Error, UpdateUserDetailsRequest>,
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: UpdateUserDetailsRequest) => updateUserDetails(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: profilePageKeys.detail() });
    },
    ...options,
  });
}

// Update company details mutation
export function useUpdateCompanyDetails(
  options?: UseMutationOptions<Record<string, unknown>, Error, UpdateCompanyDetailsRequest>,
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: UpdateCompanyDetailsRequest) => updateCompanyDetails(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: profilePageKeys.detail() });
    },
    ...options,
  });
}

// Update preferences mutation
export function useUpdatePreferences(
  options?: UseMutationOptions<Record<string, unknown>, Error, UpdatePreferencesRequest>,
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: UpdatePreferencesRequest) => updatePreferences(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: profilePageKeys.detail() });
    },
    ...options,
  });
}
