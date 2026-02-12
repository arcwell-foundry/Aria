-- ============================================================
-- ARIA: Safety Migration — Ensure All 10 Audit Tables Exist
-- Date: 2026-02-12
-- Purpose: Idempotent CREATE TABLE IF NOT EXISTS for every table
--          flagged by the V3 audit. If a prior migration already
--          created the table, IF NOT EXISTS makes this a no-op.
--          Also fixes the video_transcript_entries / video_transcripts
--          naming mismatch between 006 and 20260211 migrations.
-- ============================================================


-- Helper: ensure updated_at trigger function exists
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ============================================================
-- 1. battle_card_changes
--    History tracking for battle card field updates.
--    Original: 20260203000002_create_battle_cards.sql
-- ============================================================
CREATE TABLE IF NOT EXISTS battle_card_changes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    battle_card_id  UUID NOT NULL,
    change_type     TEXT NOT NULL,
    field_name      TEXT,
    old_value       JSONB,
    new_value       JSONB,
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE battle_card_changes ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'battle_card_changes'
        AND policyname = 'battle_card_changes_select_own'
    ) THEN
        CREATE POLICY battle_card_changes_select_own
            ON battle_card_changes FOR SELECT TO authenticated
            USING (
                battle_card_id IN (
                    SELECT id FROM battle_cards WHERE user_id = auth.uid()
                )
            );
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'battle_card_changes'
        AND policyname = 'battle_card_changes_insert_own'
    ) THEN
        CREATE POLICY battle_card_changes_insert_own
            ON battle_card_changes FOR INSERT TO authenticated
            WITH CHECK (
                battle_card_id IN (
                    SELECT id FROM battle_cards WHERE user_id = auth.uid()
                )
            );
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'battle_card_changes'
        AND policyname = 'battle_card_changes_service_role'
    ) THEN
        CREATE POLICY battle_card_changes_service_role
            ON battle_card_changes FOR ALL TO service_role
            USING (true);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_battle_card_changes_card_id
    ON battle_card_changes(battle_card_id);
CREATE INDEX IF NOT EXISTS idx_battle_card_changes_detected_at
    ON battle_card_changes(detected_at DESC);


-- ============================================================
-- 2. calendar_events
--    Calendar events for meeting prep context.
--    Original: 20260211000000_missing_tables_comprehensive.sql
-- ============================================================
CREATE TABLE IF NOT EXISTS calendar_events (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title               TEXT NOT NULL,
    start_time          TIMESTAMPTZ NOT NULL,
    end_time            TIMESTAMPTZ,
    attendees           JSONB DEFAULT '[]'::jsonb,
    external_company    TEXT,
    source              TEXT DEFAULT 'manual',
    external_id         TEXT,
    metadata            JSONB DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE calendar_events ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'calendar_events'
        AND policyname = 'calendar_events_user_own'
    ) THEN
        CREATE POLICY calendar_events_user_own
            ON calendar_events FOR ALL TO authenticated
            USING (user_id = auth.uid());
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'calendar_events'
        AND policyname = 'calendar_events_service_role'
    ) THEN
        CREATE POLICY calendar_events_service_role
            ON calendar_events FOR ALL TO service_role
            USING (true);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_calendar_events_user
    ON calendar_events(user_id);
CREATE INDEX IF NOT EXISTS idx_calendar_events_start
    ON calendar_events(user_id, start_time);
CREATE INDEX IF NOT EXISTS idx_calendar_events_external
    ON calendar_events(user_id, external_id) WHERE external_id IS NOT NULL;


-- ============================================================
-- 3. digital_twin_profiles
--    User communication style and personality for AI voice.
--    Original: 20260211000000_missing_tables_comprehensive.sql
-- ============================================================
CREATE TABLE IF NOT EXISTS digital_twin_profiles (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    tone                TEXT DEFAULT 'professional',
    writing_style       TEXT,
    vocabulary_patterns TEXT,
    formality_level     TEXT DEFAULT 'business'
                        CHECK (formality_level IN ('casual', 'business', 'formal', 'academic')),
    metadata            JSONB DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id)
);

ALTER TABLE digital_twin_profiles ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'digital_twin_profiles'
        AND policyname = 'digital_twin_profiles_user_own'
    ) THEN
        CREATE POLICY digital_twin_profiles_user_own
            ON digital_twin_profiles FOR ALL TO authenticated
            USING (user_id = auth.uid());
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'digital_twin_profiles'
        AND policyname = 'digital_twin_profiles_service_role'
    ) THEN
        CREATE POLICY digital_twin_profiles_service_role
            ON digital_twin_profiles FOR ALL TO service_role
            USING (true);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_digital_twin_profiles_user
    ON digital_twin_profiles(user_id);

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'update_digital_twin_profiles_updated_at'
    ) THEN
        CREATE TRIGGER update_digital_twin_profiles_updated_at
            BEFORE UPDATE ON digital_twin_profiles
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;


-- ============================================================
-- 4. document_chunks
--    RAG document chunks with vector embeddings.
--    Original: 20260207000000_company_documents.sql
--    NOTE: Requires pgvector extension.
-- ============================================================
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS document_chunks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID NOT NULL,
    chunk_index     INTEGER NOT NULL,
    content         TEXT NOT NULL,
    chunk_type      TEXT DEFAULT 'paragraph',
    embedding       vector(1536),
    entities        JSONB DEFAULT '[]'::jsonb,
    metadata        JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'document_chunks'
        AND policyname = 'document_chunks_select_own'
    ) THEN
        CREATE POLICY document_chunks_select_own
            ON document_chunks FOR SELECT TO authenticated
            USING (
                document_id IN (
                    SELECT id FROM company_documents WHERE user_id = auth.uid()
                )
            );
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'document_chunks'
        AND policyname = 'document_chunks_service_role'
    ) THEN
        CREATE POLICY document_chunks_service_role
            ON document_chunks FOR ALL TO service_role
            USING (true);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_document_chunks_document
    ON document_chunks(document_id);


-- ============================================================
-- 5. intelligence_delivered
--    Tracks what intelligence ARIA has shown to users.
--    Original: 20260207130000_roi_analytics.sql
-- ============================================================
CREATE TABLE IF NOT EXISTS intelligence_delivered (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    intelligence_type   TEXT NOT NULL,
    source_id           TEXT,
    confidence_score    FLOAT CHECK (confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)),
    metadata            JSONB DEFAULT '{}'::jsonb,
    delivered_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE intelligence_delivered ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'intelligence_delivered'
        AND policyname = 'intelligence_delivered_user_own'
    ) THEN
        CREATE POLICY intelligence_delivered_user_own
            ON intelligence_delivered FOR ALL TO authenticated
            USING (user_id = auth.uid());
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'intelligence_delivered'
        AND policyname = 'intelligence_delivered_service_role'
    ) THEN
        CREATE POLICY intelligence_delivered_service_role
            ON intelligence_delivered FOR ALL TO service_role
            USING (true);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_intelligence_delivered_user
    ON intelligence_delivered(user_id, delivered_at DESC);
CREATE INDEX IF NOT EXISTS idx_intelligence_delivered_type
    ON intelligence_delivered(intelligence_type);
CREATE INDEX IF NOT EXISTS idx_intelligence_delivered_source
    ON intelligence_delivered(source_id);


-- ============================================================
-- 6. pipeline_impact
--    Pipeline analytics tracking.
--    Original: 20260207130000_roi_analytics.sql
-- ============================================================
CREATE TABLE IF NOT EXISTS pipeline_impact (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    impact_type     TEXT NOT NULL,
    source_id       TEXT,
    estimated_value FLOAT CHECK (estimated_value IS NULL OR estimated_value >= 0),
    metadata        JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE pipeline_impact ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'pipeline_impact'
        AND policyname = 'pipeline_impact_user_own'
    ) THEN
        CREATE POLICY pipeline_impact_user_own
            ON pipeline_impact FOR ALL TO authenticated
            USING (user_id = auth.uid());
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'pipeline_impact'
        AND policyname = 'pipeline_impact_service_role'
    ) THEN
        CREATE POLICY pipeline_impact_service_role
            ON pipeline_impact FOR ALL TO service_role
            USING (true);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_pipeline_impact_user
    ON pipeline_impact(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pipeline_impact_type
    ON pipeline_impact(impact_type);
CREATE INDEX IF NOT EXISTS idx_pipeline_impact_source
    ON pipeline_impact(source_id);


-- ============================================================
-- 7. prediction_calibration
--    ML calibration data for prediction accuracy.
--    Original: 20260203000006_create_predictions.sql
-- ============================================================
CREATE TABLE IF NOT EXISTS prediction_calibration (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    prediction_type     TEXT NOT NULL,
    confidence_bucket   FLOAT NOT NULL CHECK (confidence_bucket >= 0.1 AND confidence_bucket <= 1.0),
    total_predictions   INTEGER NOT NULL DEFAULT 0,
    correct_predictions INTEGER NOT NULL DEFAULT 0,
    last_updated        TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, prediction_type, confidence_bucket)
);

ALTER TABLE prediction_calibration ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'prediction_calibration'
        AND policyname = 'prediction_calibration_user_own'
    ) THEN
        CREATE POLICY prediction_calibration_user_own
            ON prediction_calibration FOR ALL TO authenticated
            USING (user_id = auth.uid());
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'prediction_calibration'
        AND policyname = 'prediction_calibration_service_role'
    ) THEN
        CREATE POLICY prediction_calibration_service_role
            ON prediction_calibration FOR ALL TO service_role
            USING (true);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_prediction_calibration_user
    ON prediction_calibration(user_id);
CREATE INDEX IF NOT EXISTS idx_prediction_calibration_type
    ON prediction_calibration(user_id, prediction_type);


-- ============================================================
-- 8. user_documents
--    User document storage for uploaded files.
--    Original: 20260207120001_us921_profile_page.sql
-- ============================================================
CREATE TABLE IF NOT EXISTS user_documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    filename        TEXT NOT NULL,
    file_path       TEXT NOT NULL,
    content_type    TEXT,
    file_size       BIGINT,
    metadata        JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE user_documents ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'user_documents'
        AND policyname = 'user_documents_user_own'
    ) THEN
        CREATE POLICY user_documents_user_own
            ON user_documents FOR ALL TO authenticated
            USING (user_id = auth.uid());
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'user_documents'
        AND policyname = 'user_documents_service_role'
    ) THEN
        CREATE POLICY user_documents_service_role
            ON user_documents FOR ALL TO service_role
            USING (true);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_user_documents_user
    ON user_documents(user_id);
CREATE INDEX IF NOT EXISTS idx_user_documents_created
    ON user_documents(user_id, created_at DESC);

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'update_user_documents_updated_at'
    ) THEN
        CREATE TRIGGER update_user_documents_updated_at
            BEFORE UPDATE ON user_documents
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;


-- ============================================================
-- 9. user_quotas
--    Sales quota tracking by period.
--    Original: 20260208000000_account_planning.sql
-- ============================================================
CREATE TABLE IF NOT EXISTS user_quotas (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    period          TEXT NOT NULL,
    target_value    NUMERIC NOT NULL DEFAULT 0,
    actual_value    NUMERIC NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, period)
);

ALTER TABLE user_quotas ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'user_quotas'
        AND policyname = 'user_quotas_user_own'
    ) THEN
        CREATE POLICY user_quotas_user_own
            ON user_quotas FOR ALL TO authenticated
            USING (user_id = auth.uid());
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'user_quotas'
        AND policyname = 'user_quotas_service_role'
    ) THEN
        CREATE POLICY user_quotas_service_role
            ON user_quotas FOR ALL TO service_role
            USING (true);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_user_quotas_user
    ON user_quotas(user_id);
CREATE INDEX IF NOT EXISTS idx_user_quotas_period
    ON user_quotas(user_id, period);

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'update_user_quotas_updated_at'
    ) THEN
        CREATE TRIGGER update_user_quotas_updated_at
            BEFORE UPDATE ON user_quotas
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;


-- ============================================================
-- 10. user_sessions
--     Cross-modal session persistence (text, voice, avatar).
--     Original: 20260211000000_missing_tables_comprehensive.sql
-- ============================================================
CREATE TABLE IF NOT EXISTS user_sessions (
    session_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    session_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active   BOOLEAN NOT NULL DEFAULT true,
    day_date    DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE user_sessions ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'user_sessions'
        AND policyname = 'user_sessions_user_own'
    ) THEN
        CREATE POLICY user_sessions_user_own
            ON user_sessions FOR ALL TO authenticated
            USING (user_id = auth.uid());
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'user_sessions'
        AND policyname = 'user_sessions_service_role'
    ) THEN
        CREATE POLICY user_sessions_service_role
            ON user_sessions FOR ALL TO service_role
            USING (true);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_user_sessions_user
    ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_sessions_active
    ON user_sessions(user_id, is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_user_sessions_day
    ON user_sessions(user_id, day_date);

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'update_user_sessions_updated_at'
    ) THEN
        CREATE TRIGGER update_user_sessions_updated_at
            BEFORE UPDATE ON user_sessions
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;


-- ============================================================
-- FIX: Video transcript table naming mismatch
--
-- 006_video_sessions.sql creates: video_transcript_entries
-- 20260211_video_sessions.sql creates: video_transcript_entries (aligned)
--
-- Both migrations now target the same canonical table name.
-- Create a compatibility VIEW (video_transcripts) as an alias
-- in case any future code references the alternate name.
-- ============================================================

-- Ensure the base video_sessions table exists (IF NOT EXISTS
-- is already in 20260211_video_sessions.sql, but be safe)
CREATE TABLE IF NOT EXISTS video_sessions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    tavus_conversation_id   TEXT,
    room_url                TEXT,
    status                  TEXT NOT NULL DEFAULT 'created',
    session_type            TEXT NOT NULL DEFAULT 'chat',
    started_at              TIMESTAMPTZ,
    ended_at                TIMESTAMPTZ,
    duration_seconds        INTEGER,
    metadata                JSONB DEFAULT '{}'::jsonb,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE video_sessions ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'video_sessions'
        AND policyname = 'video_sessions_user_own_v3'
    ) THEN
        CREATE POLICY video_sessions_user_own_v3
            ON video_sessions FOR ALL TO authenticated
            USING (user_id = auth.uid());
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_video_sessions_user_id
    ON video_sessions(user_id);

-- Ensure video_transcript_entries exists (from 006)
CREATE TABLE IF NOT EXISTS video_transcript_entries (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_session_id    UUID REFERENCES video_sessions(id) ON DELETE CASCADE,
    speaker             TEXT NOT NULL,
    content             TEXT NOT NULL,
    timestamp_ms        INTEGER NOT NULL DEFAULT 0,
    confidence          FLOAT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE video_transcript_entries ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'video_transcript_entries'
        AND policyname = 'video_transcript_entries_user_own'
    ) THEN
        CREATE POLICY video_transcript_entries_user_own
            ON video_transcript_entries FOR ALL TO authenticated
            USING (
                video_session_id IN (
                    SELECT id FROM video_sessions WHERE user_id = auth.uid()
                )
            );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_video_transcript_entries_session
    ON video_transcript_entries(video_session_id);

-- Create compatibility VIEW: video_transcripts -> video_transcript_entries
-- Only if video_transcripts does NOT already exist as a real table.
DO $$
BEGIN
    -- If video_transcripts already exists as a TABLE, leave it alone
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_name = 'video_transcripts'
        AND table_type = 'BASE TABLE'
    ) THEN
        RAISE NOTICE 'video_transcripts already exists as a table, skipping VIEW creation';
    ELSE
        -- Drop existing view if any, then recreate
        DROP VIEW IF EXISTS video_transcripts;
        CREATE VIEW video_transcripts AS
            SELECT id, video_session_id, speaker, content, timestamp_ms, created_at
            FROM video_transcript_entries;
    END IF;
END $$;


-- ============================================================
-- Done. Summary:
--   10 tables ensured via CREATE TABLE IF NOT EXISTS
--   All tables have RLS enabled
--   All tables have idempotent policies (checked via pg_policies)
--   All tables have appropriate indexes
--   Video transcript naming mismatch resolved with VIEW alias
-- ============================================================
