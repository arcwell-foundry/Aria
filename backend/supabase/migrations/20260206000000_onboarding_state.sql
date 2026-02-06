CREATE TABLE IF NOT EXISTS onboarding_state (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    current_step TEXT NOT NULL DEFAULT 'company_discovery',
    step_data JSONB DEFAULT '{}',
    completed_steps TEXT[] DEFAULT '{}',
    skipped_steps TEXT[] DEFAULT '{}',
    started_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ,
    readiness_scores JSONB DEFAULT '{
        "corporate_memory": 0,
        "digital_twin": 0,
        "relationship_graph": 0,
        "integrations": 0,
        "goal_clarity": 0
    }',
    metadata JSONB DEFAULT '{}',
    UNIQUE(user_id)
);

-- RLS
ALTER TABLE onboarding_state ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'own_onboarding_select' AND tablename = 'onboarding_state') THEN
        CREATE POLICY "own_onboarding_select" ON onboarding_state
            FOR SELECT TO authenticated USING (user_id = auth.uid());
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'own_onboarding_insert' AND tablename = 'onboarding_state') THEN
        CREATE POLICY "own_onboarding_insert" ON onboarding_state
            FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid());
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'own_onboarding_update' AND tablename = 'onboarding_state') THEN
        CREATE POLICY "own_onboarding_update" ON onboarding_state
            FOR UPDATE TO authenticated USING (user_id = auth.uid());
    END IF;
END $$;

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_onboarding_state_user ON onboarding_state(user_id);

-- Updated_at trigger
CREATE OR REPLACE FUNCTION update_onboarding_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS onboarding_state_updated_at ON onboarding_state;
CREATE TRIGGER onboarding_state_updated_at
    BEFORE UPDATE ON onboarding_state
    FOR EACH ROW
    EXECUTE FUNCTION update_onboarding_updated_at();
