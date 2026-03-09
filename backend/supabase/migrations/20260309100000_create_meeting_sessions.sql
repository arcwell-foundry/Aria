-- Meeting sessions: tracks MeetingBaaS bot dispatch per calendar event
-- Used by meeting_bot_dispatcher job and meeting_sessions API routes

CREATE TABLE IF NOT EXISTS meeting_sessions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    calendar_event_id   UUID NOT NULL REFERENCES calendar_events(id) ON DELETE CASCADE,
    user_id             UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    bot_id              TEXT,
    status              TEXT NOT NULL DEFAULT 'joining'
                        CHECK (status IN ('joining', 'in_meeting', 'ended', 'failed', 'left')),
    meeting_url         TEXT,
    meeting_title       TEXT,
    started_at          TIMESTAMPTZ DEFAULT now(),
    ended_at            TIMESTAMPTZ,
    transcript          JSONB,
    debrief             JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(calendar_event_id, user_id)
);

ALTER TABLE meeting_sessions ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'meeting_sessions'
        AND policyname = 'meeting_sessions_user_own'
    ) THEN
        CREATE POLICY meeting_sessions_user_own
            ON meeting_sessions FOR ALL TO authenticated
            USING (user_id = auth.uid());
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'meeting_sessions'
        AND policyname = 'meeting_sessions_service_role'
    ) THEN
        CREATE POLICY meeting_sessions_service_role
            ON meeting_sessions FOR ALL TO service_role
            USING (true);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_meeting_sessions_user
    ON meeting_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_meeting_sessions_calendar_event
    ON meeting_sessions(calendar_event_id);
CREATE INDEX IF NOT EXISTS idx_meeting_sessions_status
    ON meeting_sessions(status);
CREATE INDEX IF NOT EXISTS idx_meeting_sessions_user_status
    ON meeting_sessions(user_id, status);

CREATE TRIGGER update_meeting_sessions_updated_at
    BEFORE UPDATE ON meeting_sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

COMMENT ON TABLE meeting_sessions IS 'Tracks MeetingBaaS bot dispatch and lifecycle per calendar event';
