import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationOptions,
  type UseQueryOptions,
} from "@tanstack/react-query";
import {
  changePassword,
  deleteAccount,
  disable2FA,
  getProfile,
  listSessions,
  requestPasswordReset,
  revokeSession,
  setup2FA,
  updateProfile,
  verify2FA,
  type ChangePasswordRequest,
  type DeleteAccountRequest,
  type DisableTwoFactorRequest,
  type MessageResponse,
  type PasswordResetRequest,
  type SessionInfo,
  type TwoFactorSetupResponse,
  type UpdateProfileRequest,
  type UserProfile,
  type VerifyTwoFactorRequest,
} from "@/api/account";

// Query keys
export const accountKeys = {
  all: ["account"] as const,
  profile: () => [...accountKeys.all, "profile"] as const,
  sessions: () => [...accountKeys.all, "sessions"] as const,
};

// Profile Query
export function useProfile(options?: UseQueryOptions<UserProfile>) {
  return useQuery({
    queryKey: accountKeys.profile(),
    queryFn: getProfile,
    ...options,
  });
}

// Sessions Query
export function useSessions(options?: UseQueryOptions<SessionInfo[]>) {
  return useQuery({
    queryKey: accountKeys.sessions(),
    queryFn: listSessions,
    ...options,
  });
}

// Update Profile Mutation
export function useUpdateProfile(
  options?: UseMutationOptions<UserProfile, Error, UpdateProfileRequest>
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: UpdateProfileRequest) => updateProfile(data),
    onSuccess: (data) => {
      queryClient.setQueryData(accountKeys.profile(), data);
    },
    ...options,
  });
}

// Change Password Mutation
export function useChangePassword(
  options?: UseMutationOptions<MessageResponse, Error, ChangePasswordRequest>
) {
  return useMutation({
    mutationFn: (data: ChangePasswordRequest) => changePassword(data),
    ...options,
  });
}

// Request Password Reset Mutation
export function useRequestPasswordReset(
  options?: UseMutationOptions<{ message: string }, Error, PasswordResetRequest>
) {
  return useMutation({
    mutationFn: (data: PasswordResetRequest) => requestPasswordReset(data),
    ...options,
  });
}

// Setup 2FA Mutation
export function useSetup2FA(
  options?: UseMutationOptions<TwoFactorSetupResponse, Error, void>
) {
  return useMutation({
    mutationFn: () => setup2FA(),
    ...options,
  });
}

// Verify 2FA Mutation
export function useVerify2FA(
  options?: UseMutationOptions<UserProfile, Error, VerifyTwoFactorRequest>
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: VerifyTwoFactorRequest) => verify2FA(data),
    onSuccess: (data) => {
      queryClient.setQueryData(accountKeys.profile(), data);
    },
    ...options,
  });
}

// Disable 2FA Mutation
export function useDisable2FA(
  options?: UseMutationOptions<MessageResponse, Error, DisableTwoFactorRequest>
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: DisableTwoFactorRequest) => disable2FA(data),
    onSuccess: () => {
      // Invalidate profile to update 2FA status
      queryClient.invalidateQueries({ queryKey: accountKeys.profile() });
    },
    ...options,
  });
}

// Revoke Session Mutation
export function useRevokeSession(
  options?: UseMutationOptions<MessageResponse, Error, string>
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (sessionId: string) => revokeSession(sessionId),
    onSuccess: () => {
      // Invalidate sessions to refresh list
      queryClient.invalidateQueries({ queryKey: accountKeys.sessions() });
    },
    ...options,
  });
}

// Delete Account Mutation
export function useDeleteAccount(
  options?: UseMutationOptions<MessageResponse, Error, DeleteAccountRequest>
) {
  return useMutation({
    mutationFn: (data: DeleteAccountRequest) => deleteAccount(data),
    ...options,
  });
}
