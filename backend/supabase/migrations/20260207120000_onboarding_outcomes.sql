-- US-924: Onboarding Procedural Memory (Self-Improving Onboarding)
-- Tracks onboarding quality per user and feeds system-level insights

-- Per-user onboarding outcomes (multi-tenant safe - one record per user)
CREATE TABLE IF NOT EXISTS onboarding_outcomes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE UNIQUE NOT NULL,
    readiness_snapshot JSONB DEFAULT '{}',
    completion_time_minutes FLOAT,
    steps_completed INTEGER DEFAULT 0,
    steps_skipped INTEGER DEFAULT 0,
    company_type TEXT,
    first_goal_category TEXT,
    documents_uploaded INTEGER DEFAULT 0,
    email_connected BOOLEAN DEFAULT false,
    crm_connected BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- System-level procedural insights (no user_id - aggregated learnings)
CREATE TABLE IF NOT EXISTS procedural_insights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    insight TEXT NOT NULL,
    evidence_count INTEGER DEFAULT 1,
    confidence FLOAT DEFAULT 0.5,
    insight_type TEXT DEFAULT 'onboarding', -- onboarding, retention, engagement
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- RLS for onboarding_outcomes: users can see their own, admins see all
ALTER TABLE onboarding_outcomes ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'own_outcome_select' AND tablename = 'onboarding_outcomes') THEN
        CREATE POLICY "own_outcome_select" ON onboarding_outcomes
            FOR SELECT TO authenticated USING (user_id = auth.uid());
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'admin_outcome_select' AND tablename = 'onboarding_outcomes') THEN
        CREATE POLICY "admin_outcome_select" ON onboarding_outcomes
            FOR SELECT TO authenticated
            USING (
                EXISTS (
                    SELECT 1 FROM user_profiles
                    WHERE user_profiles.user_id = auth.uid()
                    AND user_profiles.role IN ('admin', 'manager')
                )
            );
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'service_role_outcome_insert' AND tablename = 'onboarding_outcomes') THEN
        CREATE POLICY "service_role_outcome_insert" ON onboarding_outcomes
            FOR INSERT TO service_role WITH CHECK (true);
    END IF;
END $$;

-- RLS for procedural_insights: system-level, admins only
ALTER TABLE procedural_insights ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'admin_insights_all' AND tablename = 'procedural_insights') THEN
        CREATE POLICY "admin_insights_all" ON procedural_insights
            FOR ALL TO authenticated
            USING (
                EXISTS (
                    SELECT 1 FROM user_profiles
                    WHERE user_profiles.user_id = auth.uid()
                    AND user_profiles.role = 'admin'
                )
            );
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'service_role_insights_all' AND tablename = 'procedural_insights') THEN
        CREATE POLICY "service_role_insights_all" ON procedural_insights
            FOR ALL TO service_role USING (true);
    END IF;
END $$;

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_onboarding_outcomes_user ON onboarding_outcomes(user_id);
CREATE INDEX IF NOT EXISTS idx_onboarding_outcomes_company_type ON onboarding_outcomes(company_type);
CREATE INDEX IF NOT EXISTS idx_onboarding_outcomes_created_at ON onboarding_outcomes(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_procedural_insights_type ON procedural_insights(insight_type);
CREATE INDEX IF NOT EXISTS idx_procedural_insights_confidence ON procedural_insights(confidence DESC);

-- Updated_at trigger for onboarding_outcomes
CREATE OR REPLACE FUNCTION update_onboarding_outcomes_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS onboarding_outcomes_updated_at ON onboarding_outcomes;
CREATE TRIGGER onboarding_outcomes_updated_at
    BEFORE UPDATE ON onboarding_outcomes
    FOR EACH ROW
    EXECUTE FUNCTION update_onboarding_outcomes_updated_at();

-- Updated_at trigger for procedural_insights
CREATE OR REPLACE FUNCTION update_procedural_insights_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS procedural_insights_updated_at ON procedural_insights;
CREATE TRIGGER procedural_insights_updated_at
    BEFORE UPDATE ON procedural_insights
    FOR EACH ROW
    EXECUTE FUNCTION update_procedural_insights_updated_at();
