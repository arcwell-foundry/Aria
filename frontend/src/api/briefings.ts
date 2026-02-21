import { apiClient } from "./client";

// Briefing content types matching backend schema
export interface BriefingMeeting {
  time: string;
  title: string;
  attendees: string[];
}

export interface BriefingCalendar {
  meeting_count: number;
  key_meetings: BriefingMeeting[];
}

export interface BriefingLead {
  id: string;
  name: string;
  company: string;
  status?: string;
  last_contact?: string;
  health_score?: number;
}

export interface BriefingLeads {
  hot_leads: BriefingLead[];
  needs_attention: BriefingLead[];
  recently_active: BriefingLead[];
}

export interface BriefingSignal {
  id: string;
  type: "company_news" | "market_trend" | "competitive_intel";
  title: string;
  summary: string;
  source?: string;
  relevance?: number;
}

export interface BriefingSignals {
  company_news: BriefingSignal[];
  market_trends: BriefingSignal[];
  competitive_intel: BriefingSignal[];
}

export interface BriefingTask {
  id: string;
  title: string;
  due_date?: string;
  priority?: "high" | "medium" | "low";
  related_lead_id?: string;
}

export interface BriefingTasks {
  overdue: BriefingTask[];
  due_today: BriefingTask[];
}

export interface BriefingContent {
  summary: string;
  calendar: BriefingCalendar;
  leads: BriefingLeads;
  signals: BriefingSignals;
  tasks: BriefingTasks;
  generated_at: string;
}

export interface BriefingListItem {
  id: string;
  briefing_date: string;
  content: BriefingContent;
}

export interface BriefingResponse {
  id: string;
  user_id: string;
  briefing_date: string;
  content: BriefingContent;
}

// Response wrapper from GET /briefings/today
interface TodayBriefingResponse {
  briefing: BriefingContent | null;
  status: "ready" | "not_generated";
}

// API functions
export async function getTodayBriefing(regenerate = false): Promise<BriefingContent | null> {
  const params = regenerate ? "?regenerate=true" : "";
  const response = await apiClient.get<TodayBriefingResponse>(
    `/briefings/today${params}`,
    { headers: { "X-Background": "true" } },
  );
  return response.data.briefing;
}

export async function listBriefings(limit = 7): Promise<BriefingListItem[]> {
  const response = await apiClient.get<BriefingListItem[]>(
    `/briefings?limit=${limit}`,
    { headers: { "X-Background": "true" } },
  );
  return response.data;
}

export async function getBriefingByDate(briefingDate: string): Promise<BriefingResponse> {
  const response = await apiClient.get<BriefingResponse>(`/briefings/${briefingDate}`);
  return response.data;
}

export async function generateBriefing(briefingDate?: string): Promise<BriefingContent> {
  const response = await apiClient.post<BriefingContent>("/briefings/generate", {
    briefing_date: briefingDate ?? null,
  });
  return response.data;
}

// Video briefing status types
export interface BriefingStatusResponse {
  ready: boolean;
  viewed: boolean;
  briefing_id: string | null;
  duration: number;
  topics: string[];
}

export interface BriefingViewResponse {
  key_points: string[];
  action_items: BriefingActionItem[];
  completed_at: string;
}

export interface BriefingActionItem {
  id: string;
  text: string;
  status: 'pending' | 'done';
}

// Background request config — suppresses error toasts for non-user-initiated fetches
const backgroundConfig = { headers: { "X-Background": "true" } };

// Video briefing API functions
export async function getBriefingStatus(): Promise<BriefingStatusResponse> {
  const response = await apiClient.get<BriefingStatusResponse>("/briefings/status", backgroundConfig);
  return response.data;
}

export async function markBriefingViewed(briefingId: string): Promise<BriefingViewResponse> {
  const response = await apiClient.post<BriefingViewResponse>(`/briefings/${briefingId}/view`);
  return response.data;
}

export async function getTextBriefing(briefingId: string): Promise<string> {
  const response = await apiClient.get<{ text: string; briefing_id: string }>(`/briefings/${briefingId}/text`, backgroundConfig);
  return response.data.text;
}
