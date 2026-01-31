import { apiClient } from "./client";

export interface SignupData {
  email: string;
  password: string;
  full_name: string;
  company_name?: string;
}

export interface LoginData {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  company_id: string | null;
  role: string;
  avatar_url: string | null;
}

export async function signup(data: SignupData): Promise<TokenResponse> {
  const response = await apiClient.post<TokenResponse>("/auth/signup", data);
  return response.data;
}

export async function login(data: LoginData): Promise<TokenResponse> {
  const response = await apiClient.post<TokenResponse>("/auth/login", data);
  return response.data;
}

export async function logout(): Promise<void> {
  await apiClient.post("/auth/logout");
}

export async function refreshToken(
  refreshToken: string
): Promise<TokenResponse> {
  const response = await apiClient.post<TokenResponse>("/auth/refresh", {
    refresh_token: refreshToken,
  });
  return response.data;
}

export async function getCurrentUser(): Promise<User> {
  const response = await apiClient.get<User>("/auth/me");
  return response.data;
}
