-- ============================================================
-- ARIA: Comprehensive Migration for Missing Tables
-- Date: 2026-02-11
-- Purpose: Create all tables referenced in backend code that
--          don't yet exist in the database.
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
-- 1. memory_semantic
--    Core semantic memory: facts with confidence scores.
--    Used by 35+ code locations across onboarding, search,
--    compliance, enrichment, first_conversation, etc.
-- ============================================================
CREATE TABLE IF NOT EXISTS memory_semantic (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    fact        TEXT NOT NULL,
    confidence  FLOAT NOT NULL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
    source      TEXT NOT NULL DEFAULT 'system',
    metadata    JSONB DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE memory_semantic ENABLE ROW LEVEL SECURITY;

CREATE POLICY memory_semantic_user_own
    ON memory_semantic FOR ALL TO authenticated
    USING (user_id = auth.uid());

CREATE POLICY memory_semantic_service_role
    ON memory_semantic FOR ALL TO service_role
    USING (true);

CREATE INDEX IF NOT EXISTS idx_memory_semantic_user
    ON memory_semantic(user_id);
CREATE INDEX IF NOT EXISTS idx_memory_semantic_user_confidence
    ON memory_semantic(user_id, confidence DESC);
CREATE INDEX IF NOT EXISTS idx_memory_semantic_created
    ON memory_semantic(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_semantic_source
    ON memory_semantic(user_id, source);

CREATE TRIGGER update_memory_semantic_updated_at
    BEFORE UPDATE ON memory_semantic
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- ============================================================
-- 2. semantic_facts
--    RDF-style fact triples (subject-predicate-object).
--    Used by priming.py for memory retrieval.
-- ============================================================
CREATE TABLE IF NOT EXISTS semantic_facts (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    subject     TEXT NOT NULL,
    predicate   TEXT NOT NULL,
    object      TEXT NOT NULL,
    confidence  FLOAT NOT NULL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
    source      TEXT DEFAULT 'system',
    metadata    JSONB DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE semantic_facts ENABLE ROW LEVEL SECURITY;

CREATE POLICY semantic_facts_user_own
    ON semantic_facts FOR ALL TO authenticated
    USING (user_id = auth.uid());

CREATE POLICY semantic_facts_service_role
    ON semantic_facts FOR ALL TO service_role
    USING (true);

CREATE INDEX IF NOT EXISTS idx_semantic_facts_user
    ON semantic_facts(user_id);
CREATE INDEX IF NOT EXISTS idx_semantic_facts_subject
    ON semantic_facts(user_id, subject);


-- ============================================================
-- 3. episodic_memories
--    Permanent event history (never deleted).
--    Used by retroactive_enrichment.py.
-- ============================================================
CREATE TABLE IF NOT EXISTS episodic_memories (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    event_type  TEXT NOT NULL,
    content     TEXT NOT NULL,
    metadata    JSONB DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE episodic_memories ENABLE ROW LEVEL SECURITY;

CREATE POLICY episodic_memories_user_own
    ON episodic_memories FOR ALL TO authenticated
    USING (user_id = auth.uid());

CREATE POLICY episodic_memories_service_role
    ON episodic_memories FOR ALL TO service_role
    USING (true);

CREATE INDEX IF NOT EXISTS idx_episodic_memories_user
    ON episodic_memories(user_id);
CREATE INDEX IF NOT EXISTS idx_episodic_memories_user_type
    ON episodic_memories(user_id, event_type);
CREATE INDEX IF NOT EXISTS idx_episodic_memories_created
    ON episodic_memories(created_at DESC);


-- ============================================================
-- 4. memory_prospective
--    Future-oriented memory used by compliance/data export.
--    Separate from prospective_memories for compliance queries.
-- ============================================================
CREATE TABLE IF NOT EXISTS memory_prospective (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    task            TEXT NOT NULL,
    trigger_config  JSONB DEFAULT '{}'::jsonb,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'completed', 'archived', 'cancelled')),
    priority        TEXT DEFAULT 'medium'
                    CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE memory_prospective ENABLE ROW LEVEL SECURITY;

CREATE POLICY memory_prospective_user_own
    ON memory_prospective FOR ALL TO authenticated
    USING (user_id = auth.uid());

CREATE POLICY memory_prospective_service_role
    ON memory_prospective FOR ALL TO service_role
    USING (true);

CREATE INDEX IF NOT EXISTS idx_memory_prospective_user
    ON memory_prospective(user_id);
CREATE INDEX IF NOT EXISTS idx_memory_prospective_status
    ON memory_prospective(user_id, status);

CREATE TRIGGER update_memory_prospective_updated_at
    BEFORE UPDATE ON memory_prospective
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- ============================================================
-- 5. memory_briefing_queue
--    Queue of briefing items to surface to the user.
--    Used by retroactive_enrichment.py.
-- ============================================================
CREATE TABLE IF NOT EXISTS memory_briefing_queue (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    briefing_type   TEXT NOT NULL,
    items           JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_delivered    BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE memory_briefing_queue ENABLE ROW LEVEL SECURITY;

CREATE POLICY memory_briefing_queue_user_own
    ON memory_briefing_queue FOR ALL TO authenticated
    USING (user_id = auth.uid());

CREATE POLICY memory_briefing_queue_service_role
    ON memory_briefing_queue FOR ALL TO service_role
    USING (true);

CREATE INDEX IF NOT EXISTS idx_memory_briefing_queue_user
    ON memory_briefing_queue(user_id);
CREATE INDEX IF NOT EXISTS idx_memory_briefing_queue_undelivered
    ON memory_briefing_queue(user_id, is_delivered) WHERE is_delivered = false;


-- ============================================================
-- 6. prospective_tasks
--    Forward-looking task queue for proactive memory.
--    Used by proactive_memory.py.
-- ============================================================
CREATE TABLE IF NOT EXISTS prospective_tasks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    task            TEXT NOT NULL,
    description     TEXT,
    trigger_config  JSONB DEFAULT '{}'::jsonb,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'in_progress', 'completed', 'cancelled')),
    priority        TEXT DEFAULT 'medium'
                    CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE prospective_tasks ENABLE ROW LEVEL SECURITY;

CREATE POLICY prospective_tasks_user_own
    ON prospective_tasks FOR ALL TO authenticated
    USING (user_id = auth.uid());

CREATE POLICY prospective_tasks_service_role
    ON prospective_tasks FOR ALL TO service_role
    USING (true);

CREATE INDEX IF NOT EXISTS idx_prospective_tasks_user
    ON prospective_tasks(user_id);
CREATE INDEX IF NOT EXISTS idx_prospective_tasks_pending
    ON prospective_tasks(user_id, status) WHERE status = 'pending';

CREATE TRIGGER update_prospective_tasks_updated_at
    BEFORE UPDATE ON prospective_tasks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- ============================================================
-- 7. lead_stakeholders
--    Individual contacts at lead companies.
--    Used by lead_stakeholders.py, account_planning_service.py.
-- ============================================================
CREATE TABLE IF NOT EXISTS lead_stakeholders (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_memory_id      UUID NOT NULL REFERENCES lead_memories(id) ON DELETE CASCADE,
    user_id             UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    contact_email       TEXT,
    contact_name        TEXT,
    title               TEXT,
    role                TEXT CHECK (role IS NULL OR role IN (
                            'decision_maker', 'influencer', 'champion',
                            'blocker', 'user', 'evaluator', 'sponsor', 'other'
                        )),
    influence_level     INT DEFAULT 5 CHECK (influence_level >= 1 AND influence_level <= 10),
    sentiment           TEXT DEFAULT 'neutral'
                        CHECK (sentiment IN ('positive', 'neutral', 'negative', 'unknown')),
    last_contacted_at   TIMESTAMPTZ,
    notes               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE lead_stakeholders ENABLE ROW LEVEL SECURITY;

CREATE POLICY lead_stakeholders_user_own
    ON lead_stakeholders FOR ALL TO authenticated
    USING (user_id = auth.uid());

CREATE POLICY lead_stakeholders_service_role
    ON lead_stakeholders FOR ALL TO service_role
    USING (true);

CREATE INDEX IF NOT EXISTS idx_lead_stakeholders_lead
    ON lead_stakeholders(lead_memory_id);
CREATE INDEX IF NOT EXISTS idx_lead_stakeholders_user
    ON lead_stakeholders(user_id);
CREATE INDEX IF NOT EXISTS idx_lead_stakeholders_influence
    ON lead_stakeholders(lead_memory_id, influence_level DESC);

CREATE TRIGGER update_lead_stakeholders_updated_at
    BEFORE UPDATE ON lead_stakeholders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- ============================================================
-- 8. lead_insights
--    AI-derived insights about leads (buying signals, risks).
--    Used by lead_insights.py.
-- ============================================================
CREATE TABLE IF NOT EXISTS lead_insights (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_memory_id      UUID NOT NULL REFERENCES lead_memories(id) ON DELETE CASCADE,
    user_id             UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    insight_type        TEXT NOT NULL CHECK (insight_type IN (
                            'buying_signal', 'objection', 'risk',
                            'commitment', 'opportunity', 'competitive_threat', 'other'
                        )),
    content             TEXT NOT NULL,
    confidence          FLOAT NOT NULL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
    source_event_id     UUID,
    detected_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    addressed_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE lead_insights ENABLE ROW LEVEL SECURITY;

CREATE POLICY lead_insights_user_own
    ON lead_insights FOR ALL TO authenticated
    USING (user_id = auth.uid());

CREATE POLICY lead_insights_service_role
    ON lead_insights FOR ALL TO service_role
    USING (true);

CREATE INDEX IF NOT EXISTS idx_lead_insights_lead
    ON lead_insights(lead_memory_id);
CREATE INDEX IF NOT EXISTS idx_lead_insights_user
    ON lead_insights(user_id);
CREATE INDEX IF NOT EXISTS idx_lead_insights_type
    ON lead_insights(lead_memory_id, insight_type);
CREATE INDEX IF NOT EXISTS idx_lead_insights_unaddressed
    ON lead_insights(lead_memory_id) WHERE addressed_at IS NULL;


-- ============================================================
-- 9. lead_events
--    Temporal log of lead activities (calls, emails, etc.).
--    Used by account_planning_service.py.
-- ============================================================
CREATE TABLE IF NOT EXISTS lead_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_memory_id  UUID NOT NULL REFERENCES lead_memories(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    event_type      TEXT NOT NULL,
    subject         TEXT,
    description     TEXT,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata        JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE lead_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY lead_events_user_own
    ON lead_events FOR ALL TO authenticated
    USING (user_id = auth.uid());

CREATE POLICY lead_events_service_role
    ON lead_events FOR ALL TO service_role
    USING (true);

CREATE INDEX IF NOT EXISTS idx_lead_events_lead
    ON lead_events(lead_memory_id);
CREATE INDEX IF NOT EXISTS idx_lead_events_user
    ON lead_events(user_id);
CREATE INDEX IF NOT EXISTS idx_lead_events_occurred
    ON lead_events(lead_memory_id, occurred_at DESC);


-- ============================================================
-- 10. leads
--     Individual lead contacts with enrichment tracking.
--     Used by predictive_preexec.py, implication_trigger.py,
--     signal_radar.py.
-- ============================================================
CREATE TABLE IF NOT EXISTS leads (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    contact_name    TEXT,
    company_name    TEXT,
    title           TEXT,
    lifecycle_stage TEXT DEFAULT 'prospect',
    health_score    FLOAT CHECK (health_score IS NULL OR (health_score >= 0 AND health_score <= 100)),
    enriched_at     TIMESTAMPTZ,
    metadata        JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE leads ENABLE ROW LEVEL SECURITY;

CREATE POLICY leads_user_own
    ON leads FOR ALL TO authenticated
    USING (user_id = auth.uid());

CREATE POLICY leads_service_role
    ON leads FOR ALL TO service_role
    USING (true);

CREATE INDEX IF NOT EXISTS idx_leads_user
    ON leads(user_id);
CREATE INDEX IF NOT EXISTS idx_leads_unenriched
    ON leads(user_id) WHERE enriched_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_leads_stage
    ON leads(user_id, lifecycle_stage);

CREATE TRIGGER update_leads_updated_at
    BEFORE UPDATE ON leads
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- ============================================================
-- 11. profiles
--     User professional profiles with company context.
--     Used by signal_radar.py, predictive_preexec.py,
--     implication_trigger.py.
-- ============================================================
CREATE TABLE IF NOT EXISTS profiles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    company_name    TEXT,
    metadata        JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY profiles_user_own
    ON profiles FOR ALL TO authenticated
    USING (user_id = auth.uid());

CREATE POLICY profiles_service_role
    ON profiles FOR ALL TO service_role
    USING (true);

CREATE INDEX IF NOT EXISTS idx_profiles_user
    ON profiles(user_id);

CREATE TRIGGER update_profiles_updated_at
    BEFORE UPDATE ON profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- ============================================================
-- 12. meetings
--     Calendar meetings for brief pre-generation.
--     Used by predictive_preexec.py.
-- ============================================================
CREATE TABLE IF NOT EXISTS meetings (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    attendees   JSONB DEFAULT '[]'::jsonb,
    start_time  TIMESTAMPTZ NOT NULL,
    end_time    TIMESTAMPTZ,
    location    TEXT,
    metadata    JSONB DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE meetings ENABLE ROW LEVEL SECURITY;

CREATE POLICY meetings_user_own
    ON meetings FOR ALL TO authenticated
    USING (user_id = auth.uid());

CREATE POLICY meetings_service_role
    ON meetings FOR ALL TO service_role
    USING (true);

CREATE INDEX IF NOT EXISTS idx_meetings_user
    ON meetings(user_id);
CREATE INDEX IF NOT EXISTS idx_meetings_start
    ON meetings(user_id, start_time);
CREATE INDEX IF NOT EXISTS idx_meetings_end
    ON meetings(user_id, end_time);

CREATE TRIGGER update_meetings_updated_at
    BEFORE UPDATE ON meetings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- ============================================================
-- 13. calendar_events
--     User calendar events for meeting prep context.
--     Used by first_goal.py.
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

CREATE POLICY calendar_events_user_own
    ON calendar_events FOR ALL TO authenticated
    USING (user_id = auth.uid());

CREATE POLICY calendar_events_service_role
    ON calendar_events FOR ALL TO service_role
    USING (true);

CREATE INDEX IF NOT EXISTS idx_calendar_events_user
    ON calendar_events(user_id);
CREATE INDEX IF NOT EXISTS idx_calendar_events_start
    ON calendar_events(user_id, start_time);
CREATE INDEX IF NOT EXISTS idx_calendar_events_external
    ON calendar_events(user_id, external_id) WHERE external_id IS NOT NULL;


-- ============================================================
-- 14. digital_twin_profiles
--     User communication style and personality for AI voice.
--     Used by linkedin.py capability.
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

CREATE POLICY digital_twin_profiles_user_own
    ON digital_twin_profiles FOR ALL TO authenticated
    USING (user_id = auth.uid());

CREATE POLICY digital_twin_profiles_service_role
    ON digital_twin_profiles FOR ALL TO service_role
    USING (true);

CREATE INDEX IF NOT EXISTS idx_digital_twin_profiles_user
    ON digital_twin_profiles(user_id);

CREATE TRIGGER update_digital_twin_profiles_updated_at
    BEFORE UPDATE ON digital_twin_profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- ============================================================
-- 15. user_sessions
--     Cross-modal session persistence (text, voice, avatar).
--     Stores full UnifiedSession object for session recovery
--     across tab closes, modality switches, and new-day detection.
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

CREATE POLICY user_sessions_user_own
    ON user_sessions FOR ALL TO authenticated
    USING (user_id = auth.uid());

CREATE POLICY user_sessions_service_role
    ON user_sessions FOR ALL TO service_role
    USING (true);

CREATE INDEX IF NOT EXISTS idx_user_sessions_user
    ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_sessions_active
    ON user_sessions(user_id, is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_user_sessions_day
    ON user_sessions(user_id, day_date);

CREATE TRIGGER update_user_sessions_updated_at
    BEFORE UPDATE ON user_sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- ============================================================
-- FIX: onboarding_outcomes RLS policy bug (P1)
-- The admin policy references user_profiles.user_id which
-- doesn't exist; the correct column is user_profiles.id.
-- ============================================================
DO $$
BEGIN
    -- Drop the broken policy if it exists
    IF EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'onboarding_outcomes'
        AND policyname = 'admin_view_all_onboarding_outcomes'
    ) THEN
        DROP POLICY admin_view_all_onboarding_outcomes ON onboarding_outcomes;
    END IF;
END $$;

-- Recreate with corrected column reference
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'onboarding_outcomes'
        AND policyname = 'admin_view_all_onboarding_outcomes'
    ) THEN
        CREATE POLICY admin_view_all_onboarding_outcomes
        ON onboarding_outcomes
        FOR SELECT
        TO authenticated
        USING (
            EXISTS (
                SELECT 1 FROM user_profiles
                WHERE user_profiles.id = auth.uid()
                AND user_profiles.role = 'admin'
            )
        );
    END IF;
END $$;


-- ============================================================
-- Done. Summary:
--   15 new tables created
--   1 RLS policy bug fixed
--   All tables have RLS enabled
--   All tables have user-isolation policies
--   All tables have service_role bypass policies
--   Indexes on user_id, created_at, and entity lookups
-- ============================================================
