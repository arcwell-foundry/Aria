import { apiClient } from "./client";

export interface AuditLogEntry {
  id: string;
  user_id: string | null;
  event_type: string;
  source: "security" | "memory";
  resource_type: string | null;
  resource_id: string | null;
  ip_address: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface AuditLogResponse {
  items: AuditLogEntry[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface AuditLogFilters {
  page?: number;
  page_size?: number;
  event_type?: string;
  user_id?: string;
  date_from?: string;
  date_to?: string;
  search?: string;
}

export async function getAuditLogs(filters: AuditLogFilters = {}): Promise<AuditLogResponse> {
  const params = new URLSearchParams();

  if (filters.page) params.append("page", filters.page.toString());
  if (filters.page_size) params.append("page_size", filters.page_size.toString());
  if (filters.event_type) params.append("event_type", filters.event_type);
  if (filters.user_id) params.append("user_id", filters.user_id);
  if (filters.date_from) params.append("date_from", filters.date_from);
  if (filters.date_to) params.append("date_to", filters.date_to);
  if (filters.search) params.append("search", filters.search);

  const queryString = params.toString();
  const url = queryString ? `/admin/audit-log?${queryString}` : "/admin/audit-log";

  const response = await apiClient.get<AuditLogResponse>(url);
  return response.data;
}

export async function exportAuditLogs(filters: AuditLogFilters = {}): Promise<Blob> {
  const params = new URLSearchParams();

  if (filters.event_type) params.append("event_type", filters.event_type);
  if (filters.user_id) params.append("user_id", filters.user_id);
  if (filters.date_from) params.append("date_from", filters.date_from);
  if (filters.date_to) params.append("date_to", filters.date_to);
  if (filters.search) params.append("search", filters.search);

  const queryString = params.toString();
  const url = queryString ? `/admin/audit-log/export?${queryString}` : "/admin/audit-log/export";

  const response = await apiClient.get(url, { responseType: "blob" });
  return response.data as Blob;
}
