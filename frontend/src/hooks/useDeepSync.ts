import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  deepSyncApi,
  queuePushItem as queuePushItemApi,
  triggerSync as triggerSyncApi,
  type PushItemRequest,
} from "@/api/deepSync";

// Query keys
export const deepSyncKeys = {
  all: ["deep-sync"] as const,
  status: () => [...deepSyncKeys.all, "status"] as const,
};

export function useSyncStatus() {
  return useQuery({
    queryKey: deepSyncKeys.status(),
    queryFn: deepSyncApi.getSyncStatus,
    refetchInterval: 60000, // Refetch every minute
  });
}

export function useTriggerSync() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (integrationType: string) => triggerSyncApi(integrationType),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: deepSyncKeys.status() });
    },
  });
}

export function useQueuePushItem() {
  return useMutation({
    mutationFn: (item: PushItemRequest) => queuePushItemApi(item),
  });
}

export function useUpdateSyncConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (config: { sync_interval_minutes: number; auto_push_enabled: boolean }) =>
      deepSyncApi.updateConfig(config),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: deepSyncKeys.status() });
    },
  });
}
