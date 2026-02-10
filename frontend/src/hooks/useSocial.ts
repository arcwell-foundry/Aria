import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  approveDraft,
  approveReply,
  getSocialStats,
  listDrafts,
  listPublished,
  publishDraft,
  rejectDraft,
  scheduleDraft,
} from "@/api/social";

const SOCIAL_KEYS = {
  drafts: (channel: string) => ["social", "drafts", channel] as const,
  published: (channel: string) => ["social", "published", channel] as const,
  stats: ["social", "stats"] as const,
};

export function useSocialDrafts(channel = "linkedin") {
  return useQuery({ queryKey: SOCIAL_KEYS.drafts(channel), queryFn: () => listDrafts(channel) });
}

export function useSocialPublished(channel = "linkedin") {
  return useQuery({ queryKey: SOCIAL_KEYS.published(channel), queryFn: () => listPublished(channel) });
}

export function useSocialStats() {
  return useQuery({ queryKey: SOCIAL_KEYS.stats, queryFn: getSocialStats });
}

export function useApproveDraft() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ draftId, data }: { draftId: string; data: { selected_variation_index: number; edited_text?: string; edited_hashtags?: string[] } }) =>
      approveDraft(draftId, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["social"] }); },
  });
}

export function useRejectDraft() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ draftId, reason }: { draftId: string; reason: string }) => rejectDraft(draftId, reason),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["social"] }); },
  });
}

export function usePublishDraft() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (draftId: string) => publishDraft(draftId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["social"] }); },
  });
}

export function useScheduleDraft() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ draftId, data }: { draftId: string; data: { selected_variation_index: number; scheduled_time: string; edited_text?: string; edited_hashtags?: string[] } }) =>
      scheduleDraft(draftId, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["social"] }); },
  });
}

export function useApproveReply() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ replyId, editedText }: { replyId: string; editedText?: string }) => approveReply(replyId, editedText),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["social"] }); },
  });
}
