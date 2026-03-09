-- Add briefing_delivery_mode column to user_preferences
-- Allows users to choose how they receive their daily briefing: chat, voice, or avatar

ALTER TABLE user_preferences
ADD COLUMN IF NOT EXISTS briefing_delivery_mode TEXT
DEFAULT 'chat'
CHECK (briefing_delivery_mode IN ('chat', 'voice', 'avatar'));

COMMENT ON COLUMN user_preferences.briefing_delivery_mode IS
    'Preferred delivery method for daily briefings: chat (WebSocket message), voice (Tavus audio), or avatar (Tavus video)';
