/**
 * Debrief types for meeting post-documentation.
 * Matches backend API models in src/api/routes/debriefs.py
 */

/** Meeting outcome classification (frontend uses "concern" but backend uses "negative") */
export type DebriefOutcome = "positive" | "neutral" | "concern";

/** Debrief status */
export type DebriefStatus = "pending" | "completed";

// =============================================================================
// Sub-Types
// =============================================================================

/** Extracted action item */
export interface ActionItem {
  task: string;
  owner?: string;
  due_date?: string;
  completed?: boolean;
}

/** Extracted insight */
export interface DebriefInsight {
  insight: string;
  category?: string;
  confidence?: number;
}

/** AI analysis structure for debriefs */
export interface DebriefAnalysis {
  summary: string;
  action_items: ActionItem[];
  commitments: {
    ours: string[];
    theirs: string[];
  };
  insights: string[];
}

/** Follow-up email draft */
export interface FollowUpEmail {
  draft_id: string;
  subject: string;
  body: string;
}

// =============================================================================
// Request Types
// =============================================================================

/** Request to initiate a new debrief */
export interface DebriefInitiateRequest {
  meeting_id: string;
  calendar_event_id?: string;
}

/** Request to submit debrief notes */
export interface DebriefSubmitRequest {
  raw_notes: string;
  outcome?: DebriefOutcome;
  follow_up_needed?: boolean;
}

/** Request to update a debrief (legacy, for useUpdateDebrief) */
export interface UpdateDebriefRequest {
  outcome?: DebriefOutcome;
  notes?: string;
  lead_id?: string | null;
}

// =============================================================================
// Response Types
// =============================================================================

/** Response after initiating a debrief */
export interface DebriefInitiateResponse {
  id: string;
  meeting_title: string | null;
  meeting_time: string | null;
  linked_lead_id: string | null;
  pre_filled_context: Record<string, unknown>;
}

/** Response after submitting debrief notes */
export interface DebriefSubmitResponse {
  id: string;
  summary: string;
  action_items: ActionItem[];
  commitments_ours: string[];
  commitments_theirs: string[];
  insights: DebriefInsight[];
  follow_up_draft: string | null;
}

/**
 * Full debrief type used by frontend components.
 * Combines backend response with frontend-expected fields.
 */
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

/** Full debrief response from backend API */
export interface DebriefResponse {
  id: string;
  user_id: string;
  meeting_id: string;
  meeting_title: string | null;
  meeting_time: string | null;
  raw_notes: string | null;
  summary: string | null;
  outcome: DebriefOutcome | null;
  action_items: ActionItem[];
  commitments_ours: string[];
  commitments_theirs: string[];
  insights: DebriefInsight[];
  follow_up_needed: boolean;
  follow_up_draft: string | null;
  linked_lead_id: string | null;
  status: DebriefStatus;
  created_at: string;
}

/** List item for debrief listings */
export interface DebriefListItem {
  id: string;
  meeting_id: string;
  meeting_title: string | null;
  meeting_time: string | null;
  outcome: DebriefOutcome | null;
  action_items_count: number;
  linked_lead_id: string | null;
  linked_lead_name?: string | null;
  status: DebriefStatus;
  created_at: string;
}

/** Paginated debrief list response */
export interface DebriefListResponse {
  items: DebriefListItem[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
  /** @deprecated Use has_more instead */
  total_pages?: number;
}

/** Meeting that needs debriefing */
export interface PendingDebrief {
  id: string;
  meeting_id?: string;
  title: string | null;
  start_time: string | null;
  end_time?: string | null;
  lead_name?: string | null;
  external_company?: string | null;
  attendees: string[] | unknown[];
}
