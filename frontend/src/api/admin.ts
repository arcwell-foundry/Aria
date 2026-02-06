import { apiClient } from "./client";

// Types
export interface TeamMember {
  id: string;
  full_name: string | null;
  email: string;
  role: "user" | "manager" | "admin";
  is_active: boolean;
  last_active: string | null;
  created_at: string | null;
}

export interface TeamInvite {
  id: string;
  email: string;
  role: "user" | "manager" | "admin";
  status: "pending" | "accepted" | "cancelled" | "expired";
  expires_at: string;
  created_at: string;
}

export interface InviteMemberRequest {
  email: string;
  role?: "user" | "manager" | "admin";
}

export interface ChangeRoleRequest {
  role: "user" | "manager" | "admin";
}

export interface Company {
  id: string;
  name: string;
  domain: string | null;
  created_at: string | null;
  settings: Record<string, unknown> | null;
}

export interface UpdateCompanyRequest {
  name?: string;
  settings?: Record<string, unknown>;
}

export interface MessageResponse {
  message: string;
}

// API functions
export async function getTeam(): Promise<TeamMember[]> {
  const response = await apiClient.get<TeamMember[]>("/admin/team");
  return response.data;
}

export async function inviteMember(data: InviteMemberRequest): Promise<TeamInvite> {
  const response = await apiClient.post<TeamInvite>("/admin/team/invite", data);
  return response.data;
}

export async function getInvites(): Promise<TeamInvite[]> {
  const response = await apiClient.get<TeamInvite[]>("/admin/team/invites");
  return response.data;
}

export async function cancelInvite(inviteId: string): Promise<MessageResponse> {
  const response = await apiClient.post<MessageResponse>(`/admin/team/invites/${inviteId}/cancel`);
  return response.data;
}

export async function resendInvite(inviteId: string): Promise<TeamInvite> {
  const response = await apiClient.post<TeamInvite>(`/admin/team/invites/${inviteId}/resend`);
  return response.data;
}

export async function changeMemberRole(userId: string, data: ChangeRoleRequest): Promise<TeamMember> {
  const response = await apiClient.patch<TeamMember>(`/admin/team/${userId}/role`, data);
  return response.data;
}

export async function deactivateMember(userId: string): Promise<MessageResponse> {
  const response = await apiClient.post<MessageResponse>(`/admin/team/${userId}/deactivate`);
  return response.data;
}

export async function reactivateMember(userId: string): Promise<MessageResponse> {
  const response = await apiClient.post<MessageResponse>(`/admin/team/${userId}/reactivate`);
  return response.data;
}

export async function getCompany(): Promise<Company> {
  const response = await apiClient.get<Company>("/admin/company");
  return response.data;
}

export async function updateCompany(data: UpdateCompanyRequest): Promise<Company> {
  const response = await apiClient.patch<Company>("/admin/company", data);
  return response.data;
}
