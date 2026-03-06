import { apiClient } from "./client";

export interface ReturnBriefing {
  hours_away: number;
  last_active: string;
  generated_at: string;
  changes: {
    new_signals?: { count?: number; by_company?: Record<string, number> };
    new_insights?: { count?: number };
    competitive_changes?: Array<{ type: string; company: string; summary: string }>;
    email_intel?: Record<string, unknown>;
  };
  summary: string;
  priority_items: Array<{
    type: string;
    company?: string;
    text: string;
    priority: number;
  }>;
}

export async function getReturnBriefing(): Promise<ReturnBriefing | null> {
  try {
    const response = await apiClient.get<ReturnBriefing>("/intelligence/return-briefing");
    if (
      !response.data ||
      (response.data as unknown as Record<string, unknown>).status === "no_briefing_needed"
    ) {
      return null;
    }
    return response.data;
  } catch {
    return null;
  }
}
