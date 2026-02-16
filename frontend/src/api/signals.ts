import { apiClient } from "./client";

// Signal types from backend
export interface Signal {
  id: string;
  user_id: string;
  signal_type: string;
  company_name: string | null;
  content: string;
  source: string | null;
  read_at: string | null;
  dismissed_at: string | null;
  created_at: string;
}

export interface SignalFilters {
  unread_only?: boolean;
  signal_type?: string;
  company?: string;
  limit?: number;
}

export interface UnreadCount {
  count: number;
}

// API functions
export async function listSignals(filters?: SignalFilters): Promise<Signal[]> {
  const params = new URLSearchParams();
  if (filters?.unread_only) params.append("unread_only", "true");
  if (filters?.signal_type) params.append("signal_type", filters.signal_type);
  if (filters?.company) params.append("company", filters.company);
  if (filters?.limit) params.append("limit", filters.limit.toString());

  const url = params.toString() ? `/signals?${params}` : "/signals";
  const response = await apiClient.get<Signal[]>(url);
  return response.data;
}

export async function getUnreadCount(): Promise<UnreadCount> {
  const response = await apiClient.get<UnreadCount>("/signals/unread/count");
  return response.data;
}

export async function markSignalRead(signalId: string): Promise<Signal | null> {
  const response = await apiClient.post<Signal | null>(`/signals/${signalId}/read`);
  return response.data;
}

export async function markAllRead(): Promise<{ marked_read: number }> {
  const response = await apiClient.post<{ marked_read: number }>("/signals/read-all");
  return response.data;
}

export async function dismissSignal(signalId: string): Promise<Signal | null> {
  const response = await apiClient.post<Signal | null>(`/signals/${signalId}/dismiss`);
  return response.data;
}
