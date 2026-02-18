import { apiClient } from './client';

export async function requestUndo(actionId: string): Promise<void> {
  await apiClient.post(`/api/v1/actions/${actionId}/undo`);
}
