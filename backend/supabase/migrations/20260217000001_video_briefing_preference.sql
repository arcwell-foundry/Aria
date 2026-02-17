-- Add video_briefing_enabled column to user_preferences
-- This enables users to opt-in to video briefing delivery via Tavus avatar

ALTER TABLE user_preferences
ADD COLUMN IF NOT EXISTS video_briefing_enabled BOOLEAN DEFAULT false NOT NULL;

COMMENT ON COLUMN user_preferences.video_briefing_enabled IS
    'When true, morning briefing notification includes a Watch Briefing CTA with Tavus room URL';
