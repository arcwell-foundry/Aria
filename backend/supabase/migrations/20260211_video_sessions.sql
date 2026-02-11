-- ============================================================
-- Video Sessions Migration
-- Date: 2026-02-11
-- Purpose: Create video_sessions and video_transcripts tables
--          for Tavus avatar Dialogue Mode integration.
-- Uses IF NOT EXISTS for idempotency.
-- ============================================================


-- ============================================================
-- 1. video_sessions
--    Tracks Tavus avatar video sessions per user.
-- ============================================================
CREATE TABLE IF NOT EXISTS video_sessions (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    tavus_conversation_id   text,
    room_url                text,
    status                  text NOT NULL DEFAULT 'created'
                            CHECK (status IN ('created', 'active', 'ended', 'error')),
    session_type            text NOT NULL DEFAULT 'chat'
                            CHECK (session_type IN ('chat', 'briefing', 'debrief')),
    started_at              timestamptz,
    ended_at                timestamptz,
    duration_seconds        integer,
    created_at              timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE video_sessions ENABLE ROW LEVEL SECURITY;

-- Separate RLS policies scoped to auth.uid() = user_id
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'video_sessions'
        AND policyname = 'video_sessions_select_own'
    ) THEN
        CREATE POLICY video_sessions_select_own
            ON video_sessions FOR SELECT
            TO authenticated
            USING (auth.uid() = user_id);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'video_sessions'
        AND policyname = 'video_sessions_insert_own'
    ) THEN
        CREATE POLICY video_sessions_insert_own
            ON video_sessions FOR INSERT
            TO authenticated
            WITH CHECK (auth.uid() = user_id);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'video_sessions'
        AND policyname = 'video_sessions_update_own'
    ) THEN
        CREATE POLICY video_sessions_update_own
            ON video_sessions FOR UPDATE
            TO authenticated
            USING (auth.uid() = user_id);
    END IF;
END $$;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_video_sessions_user_id
    ON video_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_video_sessions_status
    ON video_sessions(status);


-- ============================================================
-- 2. video_transcripts
--    Transcript entries from Tavus avatar video sessions.
-- ============================================================
CREATE TABLE IF NOT EXISTS video_transcripts (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    video_session_id    uuid NOT NULL REFERENCES video_sessions(id) ON DELETE CASCADE,
    speaker             text NOT NULL CHECK (speaker IN ('aria', 'user')),
    content             text NOT NULL,
    timestamp_ms        integer NOT NULL DEFAULT 0,
    created_at          timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE video_transcripts ENABLE ROW LEVEL SECURITY;

-- RLS policies using EXISTS subquery to verify user owns the parent session
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'video_transcripts'
        AND policyname = 'video_transcripts_select_own'
    ) THEN
        CREATE POLICY video_transcripts_select_own
            ON video_transcripts FOR SELECT
            TO authenticated
            USING (
                EXISTS (
                    SELECT 1 FROM video_sessions vs
                    WHERE vs.id = video_transcripts.video_session_id
                    AND vs.user_id = auth.uid()
                )
            );
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'video_transcripts'
        AND policyname = 'video_transcripts_insert_own'
    ) THEN
        CREATE POLICY video_transcripts_insert_own
            ON video_transcripts FOR INSERT
            TO authenticated
            WITH CHECK (
                EXISTS (
                    SELECT 1 FROM video_sessions vs
                    WHERE vs.id = video_transcripts.video_session_id
                    AND vs.user_id = auth.uid()
                )
            );
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'video_transcripts'
        AND policyname = 'video_transcripts_update_own'
    ) THEN
        CREATE POLICY video_transcripts_update_own
            ON video_transcripts FOR UPDATE
            TO authenticated
            USING (
                EXISTS (
                    SELECT 1 FROM video_sessions vs
                    WHERE vs.id = video_transcripts.video_session_id
                    AND vs.user_id = auth.uid()
                )
            );
    END IF;
END $$;

-- Index
CREATE INDEX IF NOT EXISTS idx_video_transcripts_session_id
    ON video_transcripts(video_session_id);
