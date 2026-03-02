import { apiClient } from './client';

export interface ToolkitCatalogItem {
  composio_app_name: string;
  provider_type: string;
  capability_category: string;
  quality_score: number;
  is_active: boolean;
  org_status: string;
}

export interface ToolkitConfig {
  id: string;
  tenant_id: string;
  toolkit_slug: string;
  display_name: string;
  category: string;
  status: string;
  max_seats: number | null;
  current_seats?: number;
  notes: string | null;
  created_at: string;
}

export interface AccessRequest {
  id: string;
  user_id: string;
  toolkit_slug: string;
  toolkit_display_name: string;
  reason: string | null;
  status: string;
  admin_notes: string | null;
  created_at: string;
}

export interface AuditEntry {
  id: string;
  user_id: string;
  action: string;
  toolkit_slug: string;
  detail: Record<string, unknown>;
  created_at: string;
}

export async function getToolCatalog(): Promise<ToolkitCatalogItem[]> {
  const res = await apiClient.get('/admin/tools/catalog');
  return res.data.catalog;
}

export async function getToolConfigs(): Promise<ToolkitConfig[]> {
  const res = await apiClient.get('/admin/tools/config');
  return res.data.toolkits;
}

export async function createToolConfig(data: {
  toolkit_slug: string;
  display_name?: string;
  status?: string;
  category?: string;
}): Promise<ToolkitConfig> {
  const res = await apiClient.post('/admin/tools/config', data);
  return res.data.toolkit;
}

export async function updateToolConfig(slug: string, data: {
  status?: string;
  max_seats?: number | null;
  notes?: string;
}): Promise<ToolkitConfig> {
  const res = await apiClient.patch(`/admin/tools/config/${slug}`, data);
  return res.data.toolkit;
}

export async function getToolRequests(status?: string): Promise<AccessRequest[]> {
  const params = status ? { status } : {};
  const res = await apiClient.get('/admin/tools/requests', { params });
  return res.data.requests;
}

export async function reviewToolRequest(id: string, data: {
  status: 'approved' | 'denied';
  admin_notes?: string;
}): Promise<void> {
  await apiClient.patch(`/admin/tools/requests/${id}`, data);
}

export async function getToolAudit(limit?: number): Promise<AuditEntry[]> {
  const res = await apiClient.get('/admin/tools/audit', { params: { limit: limit ?? 100 } });
  return res.data.audit_entries;
}

export async function requestToolAccess(data: {
  toolkit_slug: string;
  toolkit_display_name?: string;
  reason?: string;
}): Promise<{ status: string; message: string }> {
  const res = await apiClient.post('/tools/request', data);
  return res.data;
}
