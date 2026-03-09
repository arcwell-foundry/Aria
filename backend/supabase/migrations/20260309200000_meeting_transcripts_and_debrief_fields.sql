-- Stream B2: Meeting transcripts table + debrief fields for webhook processing
-- Supports MeetingBaaS webhook → transcript storage → auto-debrief generation

-- ============================================================================
-- 1. meeting_transcripts: stores raw + flattened transcripts from MeetingBaaS
-- ============================================================================

CREATE TABLE IF NOT EXISTS meeting_transcripts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_session_id  UUID NOT NULL REFERENCES meeting_sessions(id) ON DELETE CASCADE,
    calendar_event_id   UUID REFERENCES calendar_events(id) ON DELETE SET NULL,
    user_id             UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    raw_transcript      JSONB NOT NULL DEFAULT '[]',
    transcript_text     TEXT NOT NULL DEFAULT '',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE meeting_transcripts ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'meeting_transcripts'
        AND policyname = 'meeting_transcripts_user_select'
    ) THEN
        CREATE POLICY meeting_transcripts_user_select
            ON meeting_transcripts FOR SELECT TO authenticated
            USING (user_id = auth.uid());
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'meeting_transcripts'
        AND policyname = 'meeting_transcripts_user_insert'
    ) THEN
        CREATE POLICY meeting_transcripts_user_insert
            ON meeting_transcripts FOR INSERT TO authenticated
            WITH CHECK (user_id = auth.uid());
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'meeting_transcripts'
        AND policyname = 'meeting_transcripts_service_role'
    ) THEN
        CREATE POLICY meeting_transcripts_service_role
            ON meeting_transcripts FOR ALL TO service_role
            USING (true);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_meeting_transcripts_session
    ON meeting_transcripts(meeting_session_id);
CREATE INDEX IF NOT EXISTS idx_meeting_transcripts_user
    ON meeting_transcripts(user_id);
CREATE INDEX IF NOT EXISTS idx_meeting_transcripts_calendar_event
    ON meeting_transcripts(calendar_event_id);

COMMENT ON TABLE meeting_transcripts IS 'Stores raw and flattened meeting transcripts from MeetingBaaS webhook';

-- ============================================================================
-- 2. Add webhook-specific columns to existing meeting_debriefs table
-- ============================================================================

ALTER TABLE meeting_debriefs
    ADD COLUMN IF NOT EXISTS meeting_session_id UUID REFERENCES meeting_sessions(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS calendar_event_id UUID REFERENCES calendar_events(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS key_decisions JSONB DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS objections JSONB DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS stakeholder_signals JSONB DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS next_steps JSONB DEFAULT '[]';

CREATE INDEX IF NOT EXISTS idx_debriefs_session
    ON meeting_debriefs(meeting_session_id);
CREATE INDEX IF NOT EXISTS idx_debriefs_calendar_event
    ON meeting_debriefs(calendar_event_id);

-- ============================================================================
-- 3. Add 'completed' to meeting_sessions status constraint
-- ============================================================================

-- Drop existing constraint and recreate with 'completed' added
ALTER TABLE meeting_sessions DROP CONSTRAINT IF EXISTS meeting_sessions_status_check;
ALTER TABLE meeting_sessions
    ADD CONSTRAINT meeting_sessions_status_check
    CHECK (status IN ('joining', 'in_meeting', 'ended', 'failed', 'left', 'completed'));
