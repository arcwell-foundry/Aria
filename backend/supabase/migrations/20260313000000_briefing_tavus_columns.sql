-- Add Tavus video and conversation tracking columns to daily_briefings
-- Supports one-way video generation and CVI live conversation sessions

ALTER TABLE daily_briefings
ADD COLUMN IF NOT EXISTS tavus_video_id TEXT,
ADD COLUMN IF NOT EXISTS tavus_video_url TEXT,
ADD COLUMN IF NOT EXISTS tavus_conversation_id TEXT,
ADD COLUMN IF NOT EXISTS tavus_conversation_url TEXT,
ADD COLUMN IF NOT EXISTS tavus_script TEXT,
ADD COLUMN IF NOT EXISTS tavus_status TEXT DEFAULT 'pending';

COMMENT ON COLUMN daily_briefings.tavus_video_id IS 'Tavus video ID for one-way generated video briefing';
COMMENT ON COLUMN daily_briefings.tavus_video_url IS 'Hosted URL for the generated video briefing';
COMMENT ON COLUMN daily_briefings.tavus_conversation_id IS 'Tavus conversation ID for live CVI session';
COMMENT ON COLUMN daily_briefings.tavus_conversation_url IS 'URL for the live Tavus CVI conversation session';
COMMENT ON COLUMN daily_briefings.tavus_script IS 'Rich spoken briefing script for video generation';
COMMENT ON COLUMN daily_briefings.tavus_status IS 'Status: pending, script_ready, video_generating, video_ready, conversation_active';
