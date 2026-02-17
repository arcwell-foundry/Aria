/**
 * Debrief API Client
 *
 * Handles API calls for meeting debriefs - post-meeting documentation
 * with AI-powered extraction of action items, commitments, and insights.
 */

import { apiClient } from "./client";

// Types matching backend

export type DebriefOutcome = "positive" | "neutral" | "concern";

export interface Debrief {
  id: string;
  meeting_id: string;
  user_id: string;
  title: string;
  occurred_at: string;
  attendees: string[];
  lead_id?: string;
  lead_name?: string;
  outcome: DebriefOutcome | null;
  notes: string | null;
  ai_analysis?: DebriefAnalysis;
  follow_up_email?: FollowUpEmail;
  created_at: string;
  updated_at: string;
}

export interface DebriefAnalysis {
  summary: string;
  action_items: ActionItem[];
  commitments: {
    ours: string[];
    theirs: string[];
  };
  insights: string[];
}

export interface ActionItem {
  task: string;
  owner?: string;
  due_date?: string;
  completed?: boolean;
}

export interface FollowUpEmail {
  draft_id: string;
  subject: string;
  body: string;
}

// Request types

export interface UpdateDebriefRequest {
  outcome?: DebriefOutcome;
  notes?: string;
  lead_id?: string | null; // null to unlink
}

// API functions

/**
 * Get a debrief by meeting ID.
 */
export async function getDebrief(meetingId: string): Promise<Debrief> {
  const response = await apiClient.get<Debrief>(`/debriefs/meeting/${meetingId}`);
  return response.data;
}

/**
 * Update a debrief with outcome and notes.
 * Triggers AI analysis on the backend.
 */
export async function updateDebrief(
  debriefId: string,
  data: UpdateDebriefRequest
): Promise<Debrief> {
  const response = await apiClient.put<Debrief>(`/debriefs/${debriefId}`, data);
  return response.data;
}
