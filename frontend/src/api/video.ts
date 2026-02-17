/**
 * Video session API client for Tavus avatar integration.
 */

import { apiClient } from "./client";

// Types matching backend/src/models/video.py

export type VideoSessionStatus = "created" | "active" | "ended" | "error";
export type SessionType = "chat" | "briefing" | "debrief" | "consultation";

export interface VideoSessionCreate {
  session_type?: SessionType;
  context?: string;
  custom_greeting?: string;
  lead_id?: string;
  audio_only?: boolean;
}

export interface VideoTranscriptEntry {
  id: string;
  video_session_id: string;
  speaker: string;
  content: string;
  timestamp_ms: number;
  created_at: string;
}

/** @deprecated Use VideoTranscriptEntry */
export type TranscriptEntry = VideoTranscriptEntry;

export interface VideoSession {
  id: string;
  user_id: string;
  tavus_conversation_id: string;
  room_url: string | null;
  status: VideoSessionStatus;
  session_type: SessionType;
  started_at: string | null;
  ended_at: string | null;
  duration_seconds: number | null;
  created_at: string;
  lead_id?: string;
  is_audio_only?: boolean;
  perception_analysis?: Record<string, unknown>;
  transcripts?: VideoTranscriptEntry[];
}

export interface VideoSessionListResponse {
  items: VideoSession[];
  total: number;
  limit: number;
  offset: number;
}

/**
 * Create a new video session with Tavus avatar.
 */
export async function createVideoSession(
  data: VideoSessionCreate
): Promise<VideoSession> {
  const response = await apiClient.post<VideoSession>("/video/sessions", data);
  return response.data;
}

/**
 * List video sessions for the current user.
 */
export async function listVideoSessions(params?: {
  limit?: number;
  offset?: number;
  session_type?: SessionType;
  status?: VideoSessionStatus;
}): Promise<VideoSessionListResponse> {
  const response = await apiClient.get<VideoSessionListResponse>(
    "/video/sessions",
    { params }
  );
  return response.data;
}

/**
 * Get a specific video session by ID.
 */
export async function getVideoSession(sessionId: string): Promise<VideoSession> {
  const response = await apiClient.get<VideoSession>(
    `/video/sessions/${sessionId}`
  );
  return response.data;
}

/**
 * End an active video session.
 */
export async function endVideoSession(sessionId: string): Promise<VideoSession> {
  const response = await apiClient.post<VideoSession>(
    `/video/sessions/${sessionId}/end`
  );
  return response.data;
}
