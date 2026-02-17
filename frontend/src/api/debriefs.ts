/**
 * Debrief API Client
 *
 * Handles API calls for meeting debriefs - post-meeting documentation
 * with AI-powered extraction of action items, commitments, and insights.
 */

import { apiClient } from "./client";

// Re-export types for backwards compatibility
export type {
  DebriefOutcome,
  DebriefStatus,
  ActionItem,
  DebriefInsight,
  DebriefAnalysis,
  FollowUpEmail,
  DebriefInitiateRequest,
  DebriefSubmitRequest,
  UpdateDebriefRequest,
  DebriefInitiateResponse,
  DebriefSubmitResponse,
  Debrief,
  DebriefResponse,
  DebriefListItem,
  DebriefListResponse,
  PendingDebrief,
} from "@/types/debrief";

import type {
  DebriefInitiateRequest,
  DebriefInitiateResponse,
  DebriefSubmitRequest,
  DebriefSubmitResponse,
  DebriefResponse,
  DebriefListResponse,
  PendingDebrief,
  Debrief,
  UpdateDebriefRequest,
} from "@/types/debrief";

// =============================================================================
// API Functions
// =============================================================================

/**
 * Initiate a debrief for a meeting.
 * Creates a pending debrief linked to a calendar event.
 */
export async function initiateDebrief(
  meetingId: string,
  calendarEventId?: string
): Promise<DebriefInitiateResponse> {
  const payload: DebriefInitiateRequest = {
    meeting_id: meetingId,
    ...(calendarEventId && { calendar_event_id: calendarEventId }),
  };
  const response = await apiClient.post<DebriefInitiateResponse>(
    "/debriefs",
    payload
  );
  return response.data;
}

/**
 * Submit debrief notes and trigger AI extraction pipeline.
 * Processes notes to extract action items, commitments, and insights.
 */
export async function submitDebrief(
  debriefId: string,
  data: DebriefSubmitRequest
): Promise<DebriefSubmitResponse> {
  const response = await apiClient.put<DebriefSubmitResponse>(
    `/debriefs/${debriefId}`,
    data
  );
  return response.data;
}

/**
 * Update a debrief with outcome and notes.
 * Legacy function that maps to submitDebrief for backwards compatibility.
 */
export async function updateDebrief(
  debriefId: string,
  data: UpdateDebriefRequest
): Promise<Debrief> {
  // Map legacy UpdateDebriefRequest to DebriefSubmitRequest
  const submitData: DebriefSubmitRequest = {
    raw_notes: data.notes || "",
    outcome: data.outcome,
  };
  const response = await apiClient.put<DebriefSubmitResponse>(
    `/debriefs/${debriefId}`,
    submitData
  );

  // Transform response to Debrief format
  return {
    id: response.data.id,
    meeting_id: debriefId,
    user_id: "",
    title: "",
    occurred_at: new Date().toISOString(),
    attendees: [],
    outcome: data.outcome ?? null,
    notes: submitData.raw_notes,
    ai_analysis: {
      summary: response.data.summary,
      action_items: response.data.action_items,
      commitments: {
        ours: response.data.commitments_ours,
        theirs: response.data.commitments_theirs,
      },
      insights: response.data.insights.map((i) =>
        typeof i === "string" ? i : i.insight
      ),
    },
    follow_up_email: response.data.follow_up_draft
      ? {
          draft_id: response.data.id,
          subject: "Follow-up",
          body: response.data.follow_up_draft,
        }
      : undefined,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
}

/**
 * Get a debrief by meeting ID (returns debriefs for a meeting).
 */
export async function getDebrief(meetingId: string): Promise<Debrief> {
  const response = await apiClient.get<DebriefResponse[]>(
    `/debriefs/meeting/${meetingId}`
  );

  if (!response.data.length) {
    throw new Error("Debrief not found");
  }

  const debriefResponse = response.data[0];

  // Transform DebriefResponse to Debrief format
  return {
    id: debriefResponse.id,
    meeting_id: debriefResponse.meeting_id,
    user_id: debriefResponse.user_id,
    title: debriefResponse.meeting_title || "Meeting",
    occurred_at: debriefResponse.meeting_time || debriefResponse.created_at,
    attendees: [],
    lead_id: debriefResponse.linked_lead_id ?? undefined,
    outcome: debriefResponse.outcome,
    notes: debriefResponse.raw_notes,
    ai_analysis: debriefResponse.summary
      ? {
          summary: debriefResponse.summary,
          action_items: debriefResponse.action_items,
          commitments: {
            ours: debriefResponse.commitments_ours,
            theirs: debriefResponse.commitments_theirs,
          },
          insights: debriefResponse.insights.map((i) =>
            typeof i === "string" ? i : i.insight
          ),
        }
      : undefined,
    follow_up_email: debriefResponse.follow_up_draft
      ? {
          draft_id: debriefResponse.id,
          subject: "Follow-up",
          body: debriefResponse.follow_up_draft,
        }
      : undefined,
    created_at: debriefResponse.created_at,
    updated_at: debriefResponse.created_at,
  };
}

/**
 * Get a debrief by its ID.
 */
export async function getDebriefById(debriefId: string): Promise<DebriefResponse> {
  const response = await apiClient.get<DebriefResponse>(`/debriefs/${debriefId}`);
  return response.data;
}

/**
 * Get debriefs for a specific meeting.
 */
export async function getDebriefsByMeeting(
  meetingId: string
): Promise<DebriefResponse[]> {
  const response = await apiClient.get<DebriefResponse[]>(
    `/debriefs/meeting/${meetingId}`
  );
  return response.data;
}

/**
 * List all debriefs with optional filtering and pagination.
 */
export async function listDebriefs(params?: {
  page?: number;
  page_size?: number;
  start_date?: string;
  end_date?: string;
  linked_lead_id?: string;
  search?: string;
}): Promise<DebriefListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.page) searchParams.append("page", params.page.toString());
  if (params?.page_size) searchParams.append("page_size", params.page_size.toString());
  if (params?.start_date) searchParams.append("start_date", params.start_date);
  if (params?.end_date) searchParams.append("end_date", params.end_date);
  if (params?.linked_lead_id) searchParams.append("linked_lead_id", params.linked_lead_id);
  if (params?.search) searchParams.append("search", params.search);

  const queryString = searchParams.toString();
  const url = queryString ? `/debriefs?${queryString}` : "/debriefs";

  const response = await apiClient.get<DebriefListResponse>(url);

  // Add total_pages for backwards compatibility
  const data = response.data;
  return {
    ...data,
    total_pages: Math.ceil(data.total / (params?.page_size || 20)),
  };
}

/**
 * Get meetings that need debriefs (pending).
 */
export async function getPendingDebriefs(limit?: number): Promise<PendingDebrief[]> {
  const params = limit ? `?limit=${limit}` : "";
  const response = await apiClient.get<PendingDebrief[]>(`/debriefs/pending${params}`);
  return response.data;
}
