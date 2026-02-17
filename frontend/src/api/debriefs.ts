/**
 * Debrief API Client
 *
 * Handles API calls for meeting debriefs - post-meeting documentation
 * with AI-powered extraction of action items, commitments, and insights.
 */

import { apiClient } from "./client";

// Types matching backend

export type DebriefOutcome = "positive" | "neutral" | "concern";

// List item type for the debriefs list view
export interface DebriefListItem {
  id: string;
  meeting_id: string;
  meeting_title: string | null;
  meeting_time: string | null;
  outcome: DebriefOutcome | null;
  action_items_count: number;
  linked_lead_id: string | null;
  linked_lead_name: string | null;
  status: "draft" | "complete";
  created_at: string;
}

// Paginated list response
export interface DebriefListResponse {
  items: DebriefListItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// Pending debrief (meeting without debrief)
export interface PendingDebrief {
  meeting_id: string;
  title: string;
  start_time: string;
  lead_name: string | null;
  attendees: string[];
}

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

/**
 * List all debriefs with optional filtering and pagination.
 */
export async function listDebriefs(
  page = 1,
  pageSize = 20,
  startDate?: string,
  endDate?: string,
  search?: string
): Promise<DebriefListResponse> {
  const params = new URLSearchParams();
  params.append("page", page.toString());
  params.append("page_size", pageSize.toString());
  if (startDate) params.append("start_date", startDate);
  if (endDate) params.append("end_date", endDate);
  if (search) params.append("search", search);

  const response = await apiClient.get<DebriefListResponse>(
    `/debriefs?${params.toString()}`
  );
  return response.data;
}

/**
 * Get meetings that need debriefs (pending).
 */
export async function getPendingDebriefs(): Promise<PendingDebrief[]> {
  const response = await apiClient.get<PendingDebrief[]>("/debriefs/pending");
  return response.data;
}
