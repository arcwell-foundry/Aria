/**
 * Video session types for Tavus avatar integration.
 *
 * Re-exported from @/api/video for convenience.
 */

// Re-export all types from the API module
export type {
  VideoSession,
  VideoSessionCreate,
  VideoSessionStatus,
  VideoSessionListResponse,
  VideoTranscriptEntry,
  SessionType,
} from "@/api/video";

// Legacy alias for backwards compatibility
export type { TranscriptEntry } from "@/api/video";
