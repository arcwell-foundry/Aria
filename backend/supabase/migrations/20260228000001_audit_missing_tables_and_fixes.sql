-- =============================================================================
-- Migration: Database Audit Session 1 — Missing Tables & Fixes
-- Date: 2026-02-28
-- Purpose: Create 11 tables referenced by backend code but missing from DB,
--          plus verify/fix known issues from Feb 8 audit.
-- =============================================================================

-- =====================================================================
-- 1. cognitive_load_snapshots (migration 009 was never applied)
-- =====================================================================
CREATE TABLE IF NOT EXISTS cognitive_load_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    load_level TEXT NOT NULL CHECK (load_level IN ('low', 'medium', 'high', 'critical')),
    load_score FLOAT NOT NULL CHECK (load_score >= 0 AND load_score <= 1),
    factors JSONB NOT NULL DEFAULT '{}',
    session_id UUID,
    measured_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cognitive_load_user ON cognitive_load_snapshots(user_id, measured_at DESC);
CREATE INDEX IF NOT EXISTS idx_cognitive_load_level ON cognitive_load_snapshots(user_id, load_level);
CREATE INDEX IF NOT EXISTS idx_cognitive_load_session ON cognitive_load_snapshots(session_id) WHERE session_id IS NOT NULL;

ALTER TABLE cognitive_load_snapshots ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cognitive_load_user_select" ON cognitive_load_snapshots;
CREATE POLICY "cognitive_load_user_select" ON cognitive_load_snapshots
    FOR SELECT TO authenticated USING (user_id = auth.uid());

DROP POLICY IF EXISTS "cognitive_load_user_insert" ON cognitive_load_snapshots;
CREATE POLICY "cognitive_load_user_insert" ON cognitive_load_snapshots
    FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid());

DROP POLICY IF EXISTS "cognitive_load_service_role" ON cognitive_load_snapshots;
CREATE POLICY "cognitive_load_service_role" ON cognitive_load_snapshots
    FOR ALL TO service_role USING (true);

-- =====================================================================
-- 2. aria_action_queue (migration 20260208010000 was never applied)
-- =====================================================================
CREATE TABLE IF NOT EXISTS aria_action_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    agent TEXT NOT NULL,
    action_type TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    risk_level TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    payload JSONB DEFAULT '{}' NOT NULL,
    reasoning TEXT,
    result JSONB DEFAULT '{}' NOT NULL,
    approved_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_aria_action_queue_user_status ON aria_action_queue(user_id, status);
CREATE INDEX IF NOT EXISTS idx_aria_action_queue_user_created ON aria_action_queue(user_id, created_at DESC);

ALTER TABLE aria_action_queue ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "action_queue_user_select" ON aria_action_queue;
CREATE POLICY "action_queue_user_select" ON aria_action_queue
    FOR SELECT TO authenticated USING (user_id = auth.uid());

DROP POLICY IF EXISTS "action_queue_user_insert" ON aria_action_queue;
CREATE POLICY "action_queue_user_insert" ON aria_action_queue
    FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid());

DROP POLICY IF EXISTS "action_queue_user_update" ON aria_action_queue;
CREATE POLICY "action_queue_user_update" ON aria_action_queue
    FOR UPDATE TO authenticated USING (user_id = auth.uid());

DROP POLICY IF EXISTS "action_queue_user_delete" ON aria_action_queue;
CREATE POLICY "action_queue_user_delete" ON aria_action_queue
    FOR DELETE TO authenticated USING (user_id = auth.uid());

DROP POLICY IF EXISTS "action_queue_service_role" ON aria_action_queue;
CREATE POLICY "action_queue_service_role" ON aria_action_queue
    FOR ALL TO service_role USING (true);

CREATE OR REPLACE FUNCTION update_aria_action_queue_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_aria_action_queue_updated_at ON aria_action_queue;
CREATE TRIGGER update_aria_action_queue_updated_at
    BEFORE UPDATE ON aria_action_queue
    FOR EACH ROW EXECUTE FUNCTION update_aria_action_queue_updated_at();

-- =====================================================================
-- 3. briefing_queue
-- =====================================================================
CREATE TABLE IF NOT EXISTS briefing_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    category TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    consumed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_briefing_queue_user_consumed ON briefing_queue(user_id, consumed);
CREATE INDEX IF NOT EXISTS idx_briefing_queue_created_at ON briefing_queue(created_at DESC);

ALTER TABLE briefing_queue ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "briefing_queue_user_all" ON briefing_queue;
CREATE POLICY "briefing_queue_user_all" ON briefing_queue
    FOR ALL TO authenticated USING (user_id = auth.uid());

DROP POLICY IF EXISTS "briefing_queue_service_role" ON briefing_queue;
CREATE POLICY "briefing_queue_service_role" ON briefing_queue
    FOR ALL TO service_role USING (true);

-- =====================================================================
-- 4. intelligence_signals
-- =====================================================================
CREATE TABLE IF NOT EXISTS intelligence_signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    signal_type TEXT NOT NULL,
    headline TEXT NOT NULL,
    summary TEXT,
    relevance_score NUMERIC(3,2) CHECK (relevance_score >= 0 AND relevance_score <= 1),
    source TEXT,
    metadata JSONB DEFAULT '{}',
    status TEXT DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_intelligence_signals_user ON intelligence_signals(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_intelligence_signals_dedup ON intelligence_signals(user_id, headline);

ALTER TABLE intelligence_signals ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "intelligence_signals_user_all" ON intelligence_signals;
CREATE POLICY "intelligence_signals_user_all" ON intelligence_signals
    FOR ALL TO authenticated USING (user_id = auth.uid());

DROP POLICY IF EXISTS "intelligence_signals_service_role" ON intelligence_signals;
CREATE POLICY "intelligence_signals_service_role" ON intelligence_signals
    FOR ALL TO service_role USING (true);

-- =====================================================================
-- 5. login_message_queue
-- =====================================================================
CREATE TABLE IF NOT EXISTS login_message_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    category TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    delivered BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_login_queue_user_delivered ON login_message_queue(user_id, delivered);
CREATE INDEX IF NOT EXISTS idx_login_queue_created_at ON login_message_queue(created_at DESC);

ALTER TABLE login_message_queue ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "login_queue_user_all" ON login_message_queue;
CREATE POLICY "login_queue_user_all" ON login_message_queue
    FOR ALL TO authenticated USING (user_id = auth.uid());

DROP POLICY IF EXISTS "login_queue_service_role" ON login_message_queue;
CREATE POLICY "login_queue_service_role" ON login_message_queue
    FOR ALL TO service_role USING (true);

-- =====================================================================
-- 6. weekly_digests
-- =====================================================================
CREATE TABLE IF NOT EXISTS weekly_digests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    week_start DATE NOT NULL,
    content JSONB,
    executive_summary TEXT,
    wins JSONB DEFAULT '[]',
    risks JSONB DEFAULT '[]',
    stats JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    UNIQUE(user_id, week_start)
);

CREATE INDEX IF NOT EXISTS idx_weekly_digests_user_week ON weekly_digests(user_id, week_start DESC);

ALTER TABLE weekly_digests ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "weekly_digests_user_all" ON weekly_digests;
CREATE POLICY "weekly_digests_user_all" ON weekly_digests
    FOR ALL TO authenticated USING (user_id = auth.uid());

DROP POLICY IF EXISTS "weekly_digests_service_role" ON weekly_digests;
CREATE POLICY "weekly_digests_service_role" ON weekly_digests
    FOR ALL TO service_role USING (true);

-- =====================================================================
-- 7. webset_jobs
-- =====================================================================
CREATE TABLE IF NOT EXISTS webset_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    webset_id TEXT NOT NULL,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    search_query TEXT,
    items_imported INTEGER DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_webset_jobs_user_status ON webset_jobs(user_id, status);
CREATE INDEX IF NOT EXISTS idx_webset_jobs_created_at ON webset_jobs(created_at DESC);

ALTER TABLE webset_jobs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "webset_jobs_user_all" ON webset_jobs;
CREATE POLICY "webset_jobs_user_all" ON webset_jobs
    FOR ALL TO authenticated USING (user_id = auth.uid());

DROP POLICY IF EXISTS "webset_jobs_service_role" ON webset_jobs;
CREATE POLICY "webset_jobs_service_role" ON webset_jobs
    FOR ALL TO service_role USING (true);

-- =====================================================================
-- 8. api_usage_tracking
-- =====================================================================
CREATE TABLE IF NOT EXISTS api_usage_tracking (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    api_type TEXT NOT NULL,
    call_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    cost_cents NUMERIC(10,2) DEFAULT 0,
    UNIQUE(user_id, date, api_type)
);

CREATE INDEX IF NOT EXISTS idx_api_usage_user_date ON api_usage_tracking(user_id, date DESC);

ALTER TABLE api_usage_tracking ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "api_usage_user_all" ON api_usage_tracking;
CREATE POLICY "api_usage_user_all" ON api_usage_tracking
    FOR ALL TO authenticated USING (user_id = auth.uid());

DROP POLICY IF EXISTS "api_usage_service_role" ON api_usage_tracking;
CREATE POLICY "api_usage_service_role" ON api_usage_tracking
    FOR ALL TO service_role USING (true);

-- RPC for atomic increment (used by usage_tracker.py)
CREATE OR REPLACE FUNCTION increment_api_usage(
    p_user_id UUID,
    p_date DATE,
    p_api_type TEXT,
    p_calls INTEGER DEFAULT 1,
    p_errors INTEGER DEFAULT 0,
    p_cost_cents NUMERIC DEFAULT 0
) RETURNS void AS $$
BEGIN
    INSERT INTO api_usage_tracking (user_id, date, api_type, call_count, error_count, cost_cents)
    VALUES (p_user_id, p_date, p_api_type, p_calls, p_errors, p_cost_cents)
    ON CONFLICT (user_id, date, api_type)
    DO UPDATE SET
        call_count = api_usage_tracking.call_count + p_calls,
        error_count = api_usage_tracking.error_count + p_errors,
        cost_cents = api_usage_tracking.cost_cents + p_cost_cents;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- =====================================================================
-- 9. autonomy_decisions
-- =====================================================================
CREATE TABLE IF NOT EXISTS autonomy_decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    action_type TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    autonomy_level INTEGER,
    auto_execute BOOLEAN,
    decided_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_autonomy_decisions_user ON autonomy_decisions(user_id, decided_at DESC);

ALTER TABLE autonomy_decisions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "autonomy_decisions_user_all" ON autonomy_decisions;
CREATE POLICY "autonomy_decisions_user_all" ON autonomy_decisions
    FOR ALL TO authenticated USING (user_id = auth.uid());

DROP POLICY IF EXISTS "autonomy_decisions_service_role" ON autonomy_decisions;
CREATE POLICY "autonomy_decisions_service_role" ON autonomy_decisions
    FOR ALL TO service_role USING (true);

-- =====================================================================
-- 10. friction_decisions
-- =====================================================================
CREATE TABLE IF NOT EXISTS friction_decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    level TEXT NOT NULL,
    reasoning TEXT,
    user_message TEXT,
    original_request TEXT,
    status TEXT DEFAULT 'pending',
    user_response TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_friction_decisions_user_status ON friction_decisions(user_id, status);
CREATE INDEX IF NOT EXISTS idx_friction_decisions_created_at ON friction_decisions(created_at DESC);

ALTER TABLE friction_decisions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "friction_decisions_user_all" ON friction_decisions;
CREATE POLICY "friction_decisions_user_all" ON friction_decisions
    FOR ALL TO authenticated USING (user_id = auth.uid());

DROP POLICY IF EXISTS "friction_decisions_service_role" ON friction_decisions;
CREATE POLICY "friction_decisions_service_role" ON friction_decisions
    FOR ALL TO service_role USING (true);

-- =====================================================================
-- 11. trust_score_history
-- =====================================================================
CREATE TABLE IF NOT EXISTS trust_score_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    action_category TEXT,
    trust_score NUMERIC(5,4),
    change_type TEXT,
    recorded_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_trust_history_user ON trust_score_history(user_id, recorded_at DESC);

ALTER TABLE trust_score_history ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "trust_history_user_all" ON trust_score_history;
CREATE POLICY "trust_history_user_all" ON trust_score_history
    FOR ALL TO authenticated USING (user_id = auth.uid());

DROP POLICY IF EXISTS "trust_history_service_role" ON trust_score_history;
CREATE POLICY "trust_history_service_role" ON trust_score_history
    FOR ALL TO service_role USING (true);

-- =====================================================================
-- 12. perception_topic_stats
-- =====================================================================
CREATE TABLE IF NOT EXISTS perception_topic_stats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    topic TEXT NOT NULL,
    confusion_count INTEGER DEFAULT 0,
    disengagement_count INTEGER DEFAULT 0,
    total_mentions INTEGER DEFAULT 0,
    last_confused_at TIMESTAMPTZ,
    last_disengaged_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    UNIQUE(user_id, topic)
);

CREATE INDEX IF NOT EXISTS idx_perception_topic_user ON perception_topic_stats(user_id);

ALTER TABLE perception_topic_stats ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "perception_topic_user_all" ON perception_topic_stats;
CREATE POLICY "perception_topic_user_all" ON perception_topic_stats
    FOR ALL TO authenticated USING (user_id = auth.uid());

DROP POLICY IF EXISTS "perception_topic_service_role" ON perception_topic_stats;
CREATE POLICY "perception_topic_service_role" ON perception_topic_stats
    FOR ALL TO service_role USING (true);

-- =====================================================================
-- VERIFICATION: Ensure previous audit fixes are in place
-- =====================================================================

-- Re-apply onboarding_outcomes RLS fix (idempotent)
DROP POLICY IF EXISTS "admin_outcome_select" ON onboarding_outcomes;
CREATE POLICY "admin_outcome_select" ON onboarding_outcomes
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM user_profiles
            WHERE user_profiles.id = auth.uid()
            AND user_profiles.role IN ('admin', 'manager')
        )
    );

-- Re-apply procedural_insights admin RLS fix (idempotent)
DROP POLICY IF EXISTS "admin_insights_all" ON procedural_insights;
CREATE POLICY "admin_insights_all" ON procedural_insights
    FOR ALL TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM user_profiles
            WHERE user_profiles.id = auth.uid()
            AND user_profiles.role = 'admin'
        )
    );

-- Re-apply lead_memory_events index (idempotent)
CREATE INDEX IF NOT EXISTS idx_lead_events_created ON lead_memory_events(created_at DESC);
