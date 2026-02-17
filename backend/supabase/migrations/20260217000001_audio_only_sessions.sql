-- Add is_audio_only flag to video_sessions
-- Audio-only sessions use Tavus Sparrow-1 + Raven-1 without Phoenix-4 video rendering

ALTER TABLE video_sessions ADD COLUMN is_audio_only boolean NOT NULL DEFAULT false;

-- Also fix session_type constraint to include 'consultation' (existing enum value
-- used in code but missing from original CHECK constraint)
ALTER TABLE video_sessions DROP CONSTRAINT IF EXISTS video_sessions_session_type_check;
ALTER TABLE video_sessions ADD CONSTRAINT video_sessions_session_type_check
  CHECK (session_type IN ('chat', 'briefing', 'debrief', 'consultation'));
