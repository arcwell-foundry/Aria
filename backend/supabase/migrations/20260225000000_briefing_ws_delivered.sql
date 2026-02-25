-- Add ws_delivered column to daily_briefings for WebSocket delivery tracking
-- This ensures briefings are only delivered once per day via WebSocket

ALTER TABLE daily_briefings
ADD COLUMN IF NOT EXISTS ws_delivered BOOLEAN DEFAULT FALSE;

-- Add index for efficient undelivered briefings lookup
CREATE INDEX IF NOT EXISTS idx_daily_briefings_ws_delivered
ON daily_briefings(user_id, briefing_date, ws_delivered);

COMMENT ON COLUMN daily_briefings.ws_delivered IS
'True if the briefing has been delivered via WebSocket to prevent duplicate delivery';
