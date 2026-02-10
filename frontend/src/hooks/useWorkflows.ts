import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  listWorkflows,
  listPrebuiltWorkflows,
  getWorkflow,
  createWorkflow,
  updateWorkflow,
  deleteWorkflow,
  executeWorkflow,
  type CreateWorkflowData,
  type UpdateWorkflowData,
} from "@/api/workflows";

// Query keys
export const workflowKeys = {
  all: ["workflows"] as const,
  list: (includeShared?: boolean) =>
    [...workflowKeys.all, "list", { includeShared }] as const,
  prebuilt: () => [...workflowKeys.all, "prebuilt"] as const,
  detail: (workflowId: string) =>
    [...workflowKeys.all, "detail", workflowId] as const,
};

// List workflows
export function useWorkflows(includeShared?: boolean) {
  return useQuery({
    queryKey: workflowKeys.list(includeShared),
    queryFn: () => listWorkflows(includeShared),
  });
}

// List prebuilt workflows (static data, never stale)
export function usePrebuiltWorkflows() {
  return useQuery({
    queryKey: workflowKeys.prebuilt(),
    queryFn: () => listPrebuiltWorkflows(),
    staleTime: Infinity,
  });
}

// Get single workflow detail
export function useWorkflow(workflowId: string | null) {
  return useQuery({
    queryKey: workflowKeys.detail(workflowId ?? ""),
    queryFn: () => getWorkflow(workflowId!),
    enabled: !!workflowId,
  });
}

// Create workflow mutation
export function useCreateWorkflow() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreateWorkflowData) => createWorkflow(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: workflowKeys.all });
    },
  });
}

// Update workflow mutation
export function useUpdateWorkflow() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      workflowId,
      data,
    }: {
      workflowId: string;
      data: UpdateWorkflowData;
    }) => updateWorkflow(workflowId, data),
    onSuccess: (_result, variables) => {
      queryClient.invalidateQueries({ queryKey: workflowKeys.all });
      queryClient.invalidateQueries({
        queryKey: workflowKeys.detail(variables.workflowId),
      });
    },
  });
}

// Delete workflow mutation
export function useDeleteWorkflow() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (workflowId: string) => deleteWorkflow(workflowId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: workflowKeys.all });
    },
  });
}

// Execute workflow mutation
export function useExecuteWorkflow() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      workflowId,
      triggerContext,
    }: {
      workflowId: string;
      triggerContext?: Record<string, unknown>;
    }) => executeWorkflow(workflowId, triggerContext),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: workflowKeys.all });
    },
  });
}
