import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  listDrafts,
  getDraft,
  createDraft,
  updateDraft,
  deleteDraft,
  regenerateDraft,
  sendDraft,
  saveDraftToClient,
  batchDraftAction,
  getDraftCounts,
  type CreateEmailDraftRequest,
  type UpdateEmailDraftRequest,
  type RegenerateDraftRequest,
  type EmailDraftStatus,
  type BatchActionRequest,
} from "@/api/drafts";

// Query keys factory
export const draftKeys = {
  all: ["drafts"] as const,
  counts: () => [...draftKeys.all, "counts"] as const,
  lists: () => [...draftKeys.all, "list"] as const,
  list: (status?: EmailDraftStatus) => [...draftKeys.lists(), { status }] as const,
  details: () => [...draftKeys.all, "detail"] as const,
  detail: (id: string) => [...draftKeys.details(), id] as const,
};

// Pending draft count for sidebar badge (polls every 60s)
export function usePendingDraftCount() {
  return useQuery({
    queryKey: draftKeys.counts(),
    queryFn: getDraftCounts,
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
    staleTime: 30_000,
  });
}

// List drafts
export function useDrafts(status?: EmailDraftStatus) {
  return useQuery({
    queryKey: draftKeys.list(status),
    queryFn: () => listDrafts(status),
  });
}

// Get single draft
export function useDraft(draftId: string) {
  return useQuery({
    queryKey: draftKeys.detail(draftId),
    queryFn: () => getDraft(draftId),
    enabled: !!draftId,
  });
}

// Create draft mutation
export function useCreateDraft() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreateEmailDraftRequest) => createDraft(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: draftKeys.lists() });
      queryClient.invalidateQueries({ queryKey: draftKeys.counts() });
    },
  });
}

// Update draft mutation
export function useUpdateDraft() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ draftId, data }: { draftId: string; data: UpdateEmailDraftRequest }) =>
      updateDraft(draftId, data),
    onSuccess: (updatedDraft) => {
      queryClient.invalidateQueries({ queryKey: draftKeys.lists() });
      queryClient.setQueryData(draftKeys.detail(updatedDraft.id), updatedDraft);
      // Also update IntelPanel's separate cache for the same draft
      queryClient.setQueryData(["intel-panel", "draft", updatedDraft.id], updatedDraft);
    },
  });
}

// Delete draft mutation
export function useDeleteDraft() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (draftId: string) => deleteDraft(draftId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: draftKeys.lists() });
      queryClient.invalidateQueries({ queryKey: draftKeys.counts() });
    },
  });
}

// Regenerate draft mutation
export function useRegenerateDraft() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ draftId, data }: { draftId: string; data?: RegenerateDraftRequest }) =>
      regenerateDraft(draftId, data),
    onSuccess: (updatedDraft) => {
      queryClient.invalidateQueries({ queryKey: draftKeys.lists() });
      queryClient.setQueryData(draftKeys.detail(updatedDraft.id), updatedDraft);
      // Also update IntelPanel's separate cache for the same draft
      queryClient.setQueryData(["intel-panel", "draft", updatedDraft.id], updatedDraft);
    },
  });
}

// Send draft mutation
export function useSendDraft() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (draftId: string) => sendDraft(draftId),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: draftKeys.lists() });
      queryClient.invalidateQueries({ queryKey: draftKeys.detail(result.id) });
      queryClient.invalidateQueries({ queryKey: draftKeys.counts() });
    },
  });
}

// Save draft to email client (Gmail/Outlook) mutation
export function useSaveDraftToClient() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (draftId: string) => saveDraftToClient(draftId),
    onSuccess: (_result, draftId) => {
      queryClient.invalidateQueries({ queryKey: draftKeys.detail(draftId) });
    },
  });
}

// Batch draft action mutation (approve/dismiss multiple drafts)
export function useBatchDraftAction() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: BatchActionRequest) => batchDraftAction(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: draftKeys.lists() });
      queryClient.invalidateQueries({ queryKey: draftKeys.counts() });
    },
  });
}
