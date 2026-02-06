import { apiClient } from "./client";

// Types
export interface UserProfile {
  id: string;
  full_name: string | null;
  avatar_url: string | null;
  company_id: string | null;
  role: string;
  is_2fa_enabled: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface UpdateProfileRequest {
  full_name?: string;
  avatar_url?: string;
}

export interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
}

export interface PasswordResetRequest {
  email: string;
}

export interface TwoFactorSetupResponse {
  secret: string;
  qr_code_uri: string;
  provisioning_uri: string;
}

export interface VerifyTwoFactorRequest {
  code: string;
  secret: string;
}

export interface DisableTwoFactorRequest {
  password: string;
}

export interface SessionInfo {
  id: string;
  device: string;
  ip_address: string;
  user_agent: string;
  last_active: string | null;
  is_current: boolean;
}

export interface DeleteAccountRequest {
  confirmation: string;
  password: string;
}

export interface MessageResponse {
  message: string;
}

export interface PasswordResetResponse {
  message: string;
}

// API functions
export async function getProfile(): Promise<UserProfile> {
  const response = await apiClient.get<UserProfile>("/account/profile");
  return response.data;
}

export async function updateProfile(data: UpdateProfileRequest): Promise<UserProfile> {
  const response = await apiClient.patch<UserProfile>("/account/profile", data);
  return response.data;
}

export async function changePassword(data: ChangePasswordRequest): Promise<MessageResponse> {
  const response = await apiClient.post<MessageResponse>("/account/password/change", data);
  return response.data;
}

export async function requestPasswordReset(
  data: PasswordResetRequest
): Promise<PasswordResetResponse> {
  const response = await apiClient.post<PasswordResetResponse>(
    "/account/password/reset-request",
    data
  );
  return response.data;
}

export async function setup2FA(): Promise<TwoFactorSetupResponse> {
  const response = await apiClient.post<TwoFactorSetupResponse>("/account/2fa/setup");
  return response.data;
}

export async function verify2FA(data: VerifyTwoFactorRequest): Promise<UserProfile> {
  const response = await apiClient.post<UserProfile>("/account/2fa/verify", data);
  return response.data;
}

export async function disable2FA(data: DisableTwoFactorRequest): Promise<MessageResponse> {
  const response = await apiClient.post<MessageResponse>("/account/2fa/disable", data);
  return response.data;
}

export async function listSessions(): Promise<SessionInfo[]> {
  const response = await apiClient.get<SessionInfo[]>("/account/sessions");
  return response.data;
}

export async function revokeSession(sessionId: string): Promise<MessageResponse> {
  const response = await apiClient.delete<MessageResponse>(`/account/sessions/${sessionId}`);
  return response.data;
}

export async function deleteAccount(data: DeleteAccountRequest): Promise<MessageResponse> {
  const response = await apiClient.post<MessageResponse>("/account/delete", data);
  return response.data;
}
