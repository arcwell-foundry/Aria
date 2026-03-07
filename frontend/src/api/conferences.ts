import { apiClient } from "./client";

export interface ConferenceReason {
  reason: string;
  weight: number;
}

export interface ConferenceRecommendation {
  conference_id: string;
  conference_name: string;
  short_name: string | null;
  start_date: string | null;
  end_date: string | null;
  city: string | null;
  country: string | null;
  recommendation_type: "must_attend" | "consider" | "monitor_remotely";
  relevance_score: number;
  competitor_presence: number;
  topic_relevance: number;
  reasons: ConferenceReason[];
  estimated_attendance: number | null;
  website_url?: string | null;
  topics?: string[];
  description?: string | null;
}

export interface ConferenceDetail {
  id: string;
  name: string;
  short_name: string | null;
  start_date: string | null;
  end_date: string | null;
  city: string | null;
  country: string | null;
  description: string | null;
  website_url: string | null;
  therapeutic_areas: string[] | null;
  manufacturing_focus: string[] | null;
  estimated_attendance: number | null;
}

export interface ConferenceParticipant {
  id: string;
  company_name: string;
  participation_type: string;
  is_competitor: boolean;
  is_own_company: boolean;
  person_name: string | null;
  presentation_title: string | null;
}

export async function getUpcomingConferences(): Promise<ConferenceRecommendation[]> {
  const response = await apiClient.get<{
    conferences: ConferenceRecommendation[];
    count: number;
  }>("/intelligence/conferences/upcoming");
  return response.data.conferences;
}

export async function getConferenceDetail(conferenceId: string): Promise<{
  conference: ConferenceDetail;
  participants: ConferenceParticipant[];
  insights: unknown[];
  competitor_count: number;
}> {
  const response = await apiClient.get(`/intelligence/conferences/${conferenceId}`);
  return response.data;
}
