import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  listDrafts,
  getDraft,
  createDraft,
  updateDraft,
  deleteDraft,
  regenerateDraft,
  sendDraft,
  type CreateEmailDraftRequest,
  type UpdateEmailDraftRequest,
  type RegenerateDraftRequest,
  type EmailDraftStatus,
} from "@/api/drafts";

// Query keys factory
export const draftKeys = {
  all: ["drafts"] as const,
  lists: () => [...draftKeys.all, "list"] as const,
  list: (status?: EmailDraftStatus) => [...draftKeys.lists(), { status }] as const,
  details: () => [...draftKeys.all, "detail"] as const,
  detail: (id: string) => [...draftKeys.details(), id] as const,
};

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
    },
  });
}
