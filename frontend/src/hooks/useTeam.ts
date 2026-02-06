import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationOptions,
  type UseQueryOptions,
} from "@tanstack/react-query";
import {
  cancelInvite,
  changeMemberRole,
  deactivateMember,
  getCompany,
  getInvites,
  getTeam,
  inviteMember,
  reactivateMember,
  resendInvite,
  updateCompany,
  type ChangeRoleRequest,
  type Company,
  type InviteMemberRequest,
  type TeamInvite,
  type TeamMember,
  type UpdateCompanyRequest,
} from "@/api/admin";

// Query keys
export const teamKeys = {
  all: ["team"] as const,
  members: () => [...teamKeys.all, "members"] as const,
  invites: () => [...teamKeys.all, "invites"] as const,
  company: () => [...teamKeys.all, "company"] as const,
};

// Team Members Query
export function useTeamMembers(options?: UseQueryOptions<TeamMember[]>) {
  return useQuery({
    queryKey: teamKeys.members(),
    queryFn: getTeam,
    ...options,
  });
}

// Pending Invites Query
export function useTeamInvites(options?: UseQueryOptions<TeamInvite[]>) {
  return useQuery({
    queryKey: teamKeys.invites(),
    queryFn: getInvites,
    ...options,
  });
}

// Company Query
export function useTeamCompany(options?: UseQueryOptions<Company>) {
  return useQuery({
    queryKey: teamKeys.company(),
    queryFn: getCompany,
    ...options,
  });
}

// Invite Member Mutation
export function useInviteMember(
  options?: UseMutationOptions<TeamInvite, Error, InviteMemberRequest>
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: InviteMemberRequest) => inviteMember(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: teamKeys.invites() });
    },
    ...options,
  });
}

// Cancel Invite Mutation
export function useCancelInvite(
  options?: UseMutationOptions<{ message: string }, Error, string>
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (inviteId: string) => cancelInvite(inviteId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: teamKeys.invites() });
    },
    ...options,
  });
}

// Resend Invite Mutation
export function useResendInvite(
  options?: UseMutationOptions<TeamInvite, Error, string>
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (inviteId: string) => resendInvite(inviteId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: teamKeys.invites() });
    },
    ...options,
  });
}

// Change Role Mutation
export function useChangeMemberRole(
  options?: UseMutationOptions<TeamMember, Error, { userId: string; data: ChangeRoleRequest }>
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ userId, data }) => changeMemberRole(userId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: teamKeys.members() });
    },
    ...options,
  });
}

// Deactivate Member Mutation
export function useDeactivateMember(
  options?: UseMutationOptions<{ message: string }, Error, string>
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (userId: string) => deactivateMember(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: teamKeys.members() });
    },
    ...options,
  });
}

// Reactivate Member Mutation
export function useReactivateMember(
  options?: UseMutationOptions<{ message: string }, Error, string>
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (userId: string) => reactivateMember(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: teamKeys.members() });
    },
    ...options,
  });
}

// Update Company Mutation
export function useUpdateCompany(
  options?: UseMutationOptions<Company, Error, UpdateCompanyRequest>
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: UpdateCompanyRequest) => updateCompany(data),
    onSuccess: (data) => {
      queryClient.setQueryData(teamKeys.company(), data);
    },
    ...options,
  });
}
