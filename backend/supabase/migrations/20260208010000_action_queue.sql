-- US-937: Autonomous Action Queue & Approval Workflow
-- Creates the aria_actions table for tracking ARIA's autonomous actions
-- with approval workflow (auto-approve, pending, approved, rejected states).

CREATE TABLE IF NOT EXISTS aria_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
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

COMMENT ON TABLE aria_actions IS 'Tracks ARIA autonomous actions with approval workflow (US-937)';

-- Indexes
CREATE INDEX IF NOT EXISTS idx_aria_actions_user_status ON aria_actions(user_id, status);
CREATE INDEX IF NOT EXISTS idx_aria_actions_user_created ON aria_actions(user_id, created_at DESC);

-- Enable RLS
ALTER TABLE aria_actions ENABLE ROW LEVEL SECURITY;

-- RLS Policies (idempotent: drop if exists, then create)
DROP POLICY IF EXISTS "Users can view their own actions" ON aria_actions;
CREATE POLICY "Users can view their own actions" ON aria_actions
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can create their own actions" ON aria_actions;
CREATE POLICY "Users can create their own actions" ON aria_actions
    FOR INSERT WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update their own actions" ON aria_actions;
CREATE POLICY "Users can update their own actions" ON aria_actions
    FOR UPDATE USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete their own actions" ON aria_actions;
CREATE POLICY "Users can delete their own actions" ON aria_actions
    FOR DELETE USING (auth.uid() = user_id);

-- updated_at trigger
CREATE OR REPLACE FUNCTION update_aria_actions_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_aria_actions_updated_at ON aria_actions;
CREATE TRIGGER update_aria_actions_updated_at
    BEFORE UPDATE ON aria_actions
    FOR EACH ROW EXECUTE FUNCTION update_aria_actions_updated_at();
