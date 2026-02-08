import { apiClient } from "./client";

export interface SyncStatus {
  integration_type: string;
  last_sync_at: string | null;
  last_sync_status: string | null;
  next_sync_at: string | null;
  sync_count: number;
}

export interface SyncResult {
  direction: string;
  integration_type: string;
  status: string;
  records_processed: number;
  records_succeeded: number;
  records_failed: number;
  memory_entries_created: number;
  started_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
  success_rate: number;
}

export interface PushItemRequest {
  integration_type: string;
  action_type: "create_note" | "update_field" | "create_event";
  priority: "low" | "medium" | "high" | "critical";
  payload: Record<string, unknown>;
}

export async function getSyncStatus(): Promise<SyncStatus[]> {
  const response = await apiClient.get<SyncStatus[]>("/integrations/sync/status");
  return response.data;
}

export async function triggerSync(integrationType: string): Promise<SyncResult> {
  const response = await apiClient.post<SyncResult>(`/integrations/sync/${integrationType}`);
  return response.data;
}

export async function queuePushItem(
  item: PushItemRequest
): Promise<{ queue_id: string; status: string }> {
  const response = await apiClient.post<{ queue_id: string; status: string }>(
    "/integrations/sync/queue",
    item
  );
  return response.data;
}

export async function updateSyncConfig(config: {
  sync_interval_minutes: number;
  auto_push_enabled: boolean;
}): Promise<{ message: string }> {
  const response = await apiClient.put<{ message: string }>(
    "/integrations/sync/config",
    config
  );
  return response.data;
}

// Convenience object for imports
export const deepSyncApi = {
  getSyncStatus,
  triggerSync,
  queuePushItem,
  updateConfig: updateSyncConfig,
};
