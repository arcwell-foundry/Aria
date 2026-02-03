import { apiClient } from "./client";

// Status enum matching backend BriefStatus
export type MeetingBriefStatus = "pending" | "generating" | "completed" | "failed";

// Attendee profile with research data
export interface AttendeeProfile {
  email: string;
  name: string | null;
  title: string | null;
  company: string | null;
  linkedin_url: string | null;
  background: string | null;
  recent_activity: string[];
  talking_points: string[];
}

// Company research data
export interface CompanyResearch {
  name: string;
  industry: string | null;
  size: string | null;
  recent_news: string[];
  our_history: string | null;
}

// Full brief content structure
export interface MeetingBriefContent {
  summary: string;
  attendees: AttendeeProfile[];
  company: CompanyResearch | null;
  suggested_agenda: string[];
  risks_opportunities: string[];
}

// API response model
export interface MeetingBriefResponse {
  id: string;
  calendar_event_id: string;
  meeting_title: string | null;
  meeting_time: string;
  status: MeetingBriefStatus;
  brief_content: MeetingBriefContent | Record<string, never>;
  generated_at: string | null;
  error_message: string | null;
}

// Upcoming meeting with brief status
export interface UpcomingMeeting {
  calendar_event_id: string;
  meeting_title: string | null;
  meeting_time: string;
  attendees: string[];
  brief_status: MeetingBriefStatus | null;
  brief_id: string | null;
}

// Request to generate brief
export interface GenerateBriefRequest {
  meeting_title: string | null;
  meeting_time: string;
  attendee_emails: string[];
}

// User notes for a brief
export interface BriefNotes {
  content: string;
  updated_at: string;
}

// API functions
export async function getMeetingBrief(calendarEventId: string): Promise<MeetingBriefResponse> {
  const response = await apiClient.get<MeetingBriefResponse>(
    `/meetings/${encodeURIComponent(calendarEventId)}/brief`
  );
  return response.data;
}

export async function getUpcomingMeetings(limit = 10): Promise<UpcomingMeeting[]> {
  const response = await apiClient.get<UpcomingMeeting[]>(
    `/meetings/upcoming?limit=${limit}`
  );
  return response.data;
}

export async function generateMeetingBrief(
  calendarEventId: string,
  request: GenerateBriefRequest
): Promise<MeetingBriefResponse> {
  const response = await apiClient.post<MeetingBriefResponse>(
    `/meetings/${encodeURIComponent(calendarEventId)}/brief/generate`,
    request
  );
  return response.data;
}
