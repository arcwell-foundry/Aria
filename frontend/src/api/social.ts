import { apiClient } from "./client";

export interface PostVariation {
  variation_type: "insight" | "educational" | "engagement";
  text: string;
  hashtags: string[];
  voice_match_confidence: number;
}

export interface SocialDraft {
  id: string;
  user_id: string;
  action_type: string;
  status: string;
  metadata: {
    trigger_type: string;
    trigger_source: string;
    variations: PostVariation[];
    suggested_time: string | null;
    suggested_time_reasoning: string;
    selected_variation_index?: number;
    edited_text?: string;
    edited_hashtags?: string[];
    scheduled_time?: string;
    rejection_reason?: string;
    post_urn?: string;
    published_text?: string;
    published_at?: string;
    engagement_metrics?: EngagementStats;
    notable_engagers?: NotableEngager[];
  };
  estimated_minutes_saved: number;
  created_at: string;
  completed_at: string | null;
}

export interface EngagementStats {
  likes: number;
  comments: number;
  shares: number;
  impressions: number;
}

export interface NotableEngager {
  name: string;
  linkedin_url: string | null;
  relationship: string;
  lead_id: string | null;
}

export interface SocialStats {
  total_posts: number;
  posts_this_week: number;
  avg_likes: number;
  avg_comments: number;
  avg_shares: number;
  avg_impressions: number;
  best_post_id: string | null;
  best_post_impressions: number;
  posting_goal: number;
  posting_goal_met: boolean;
}

export async function listDrafts(channel = "linkedin"): Promise<SocialDraft[]> {
  const response = await apiClient.get<SocialDraft[]>(`/social/drafts?channel=${channel}`);
  return response.data;
}

export async function approveDraft(
  draftId: string,
  data: { selected_variation_index: number; edited_text?: string; edited_hashtags?: string[] },
): Promise<SocialDraft> {
  const response = await apiClient.put<SocialDraft>(`/social/drafts/${draftId}/approve`, data);
  return response.data;
}

export async function rejectDraft(draftId: string, reason: string): Promise<SocialDraft> {
  const response = await apiClient.put<SocialDraft>(`/social/drafts/${draftId}/reject`, { reason });
  return response.data;
}

export async function publishDraft(draftId: string): Promise<{ id: string; post_urn: string; status: string }> {
  const response = await apiClient.post<{ id: string; post_urn: string; status: string }>(`/social/drafts/${draftId}/publish`);
  return response.data;
}

export async function scheduleDraft(
  draftId: string,
  data: { selected_variation_index: number; scheduled_time: string; edited_text?: string; edited_hashtags?: string[] },
): Promise<SocialDraft> {
  const response = await apiClient.post<SocialDraft>(`/social/drafts/${draftId}/schedule`, data);
  return response.data;
}

export async function listPublished(channel = "linkedin"): Promise<SocialDraft[]> {
  const response = await apiClient.get<SocialDraft[]>(`/social/published?channel=${channel}`);
  return response.data;
}

export async function approveReply(replyId: string, editedText?: string): Promise<SocialDraft> {
  const response = await apiClient.put<SocialDraft>(`/social/replies/${replyId}/approve`, { edited_text: editedText ?? null });
  return response.data;
}

export async function getSocialStats(): Promise<SocialStats> {
  const response = await apiClient.get<SocialStats>("/social/stats");
  return response.data;
}
