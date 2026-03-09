-- Add missing columns to meeting_sessions table for MeetingBaaS integration

ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS bot_id TEXT;
ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS meeting_title TEXT;
ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS transcript JSONB;
ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS debrief JSONB;

-- Update status check constraint to include 'left' and 'failed' if not present
-- Drop and recreate since ALTER CONSTRAINT isn't supported
DO $$ BEGIN
    ALTER TABLE meeting_sessions DROP CONSTRAINT IF EXISTS meeting_sessions_status_check;
    ALTER TABLE meeting_sessions ADD CONSTRAINT meeting_sessions_status_check
        CHECK (status IN ('joining', 'in_meeting', 'ended', 'failed', 'left'));
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Constraint update skipped: %', SQLERRM;
END $$;

-- Add unique constraint on calendar_event_id + user_id if not present
DO $$ BEGIN
    ALTER TABLE meeting_sessions
        ADD CONSTRAINT meeting_sessions_calendar_event_id_user_id_key
        UNIQUE (calendar_event_id, user_id);
EXCEPTION WHEN duplicate_object THEN
    RAISE NOTICE 'Unique constraint already exists';
END $$;

-- Add indexes if not present
CREATE INDEX IF NOT EXISTS idx_meeting_sessions_status
    ON meeting_sessions(status);
CREATE INDEX IF NOT EXISTS idx_meeting_sessions_user_status
    ON meeting_sessions(user_id, status);
