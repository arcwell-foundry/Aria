import { apiClient } from "./client";

export interface UpcomingMeeting {
  title: string;
  time: string;
  date: string;
  attendees: string[];
}

export interface RecentSignal {
  company: string;
  headline: string;
  type: string;
  score: number;
}

export interface IntelligencePanelResponse {
  meetings: {
    upcoming: UpcomingMeeting[];
    count: number;
  };
  signals: {
    recent: RecentSignal[];
    unread_count: number;
    total_count: number;
  };
  quick_stats: {
    pending_drafts: number;
    open_tasks: number;
    battle_cards: number;
    pipeline_count: number;
  };
}

/**
 * Fetch intelligence panel data for the right panel on the chat page.
 * Returns upcoming meetings, recent signals, and quick stats.
 */
export async function fetchIntelligencePanel(): Promise<IntelligencePanelResponse> {
  const response = await apiClient.get<IntelligencePanelResponse>("/intelligence-panel");
  return response.data;
}
