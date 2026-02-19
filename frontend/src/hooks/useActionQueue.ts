import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  listActions,
  getAction,
  approveAction,
  rejectAction,
  batchApproveActions,
  getPendingCount,
  undoAction,
  type ActionStatus,
} from "@/api/actionQueue";

// Query keys
export const actionKeys = {
  all: ["actions"] as const,
  lists: () => [...actionKeys.all, "list"] as const,
  list: (status?: ActionStatus) => [...actionKeys.lists(), { status }] as const,
  details: () => [...actionKeys.all, "detail"] as const,
  detail: (id: string) => [...actionKeys.details(), id] as const,
  pendingCount: () => [...actionKeys.all, "pending-count"] as const,
};

// List actions query
export function useActions(status?: ActionStatus) {
  return useQuery({
    queryKey: actionKeys.list(status),
    queryFn: () => listActions(status),
  });
}

// Single action query
export function useAction(actionId: string) {
  return useQuery({
    queryKey: actionKeys.detail(actionId),
    queryFn: () => getAction(actionId),
    enabled: !!actionId,
  });
}

// Pending count query (poll every 30s)
export function usePendingCount() {
  return useQuery({
    queryKey: actionKeys.pendingCount(),
    queryFn: () => getPendingCount(),
    refetchInterval: 30000,
  });
}

// Approve action mutation
export function useApproveAction() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (actionId: string) => approveAction(actionId),
    onSuccess: (updatedAction) => {
      queryClient.setQueryData(actionKeys.detail(updatedAction.id), updatedAction);
      queryClient.invalidateQueries({ queryKey: actionKeys.lists() });
      queryClient.invalidateQueries({ queryKey: actionKeys.pendingCount() });
    },
  });
}

// Reject action mutation
export function useRejectAction() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ actionId, reason }: { actionId: string; reason?: string }) =>
      rejectAction(actionId, reason),
    onSuccess: (updatedAction) => {
      queryClient.setQueryData(actionKeys.detail(updatedAction.id), updatedAction);
      queryClient.invalidateQueries({ queryKey: actionKeys.lists() });
      queryClient.invalidateQueries({ queryKey: actionKeys.pendingCount() });
    },
  });
}

// Batch approve mutation
export function useBatchApprove() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (actionIds: string[]) => batchApproveActions(actionIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: actionKeys.lists() });
      queryClient.invalidateQueries({ queryKey: actionKeys.pendingCount() });
    },
  });
}

// Undo action mutation
export function useUndoAction() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (actionId: string) => undoAction(actionId),
    onSuccess: (_result, actionId) => {
      queryClient.invalidateQueries({ queryKey: actionKeys.detail(actionId) });
      queryClient.invalidateQueries({ queryKey: actionKeys.lists() });
    },
  });
}
