-- US-937: Autonomous Action Queue & Approval Workflow
-- Creates the aria_action_queue table for tracking ARIA's autonomous actions
-- with approval workflow (auto-approve, pending, approved, rejected states).
-- NOTE: aria_actions is used by ROI analytics (US-943); this table is separate.

CREATE TABLE IF NOT EXISTS aria_action_queue (
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

COMMENT ON TABLE aria_action_queue IS 'Tracks ARIA autonomous actions with approval workflow (US-937)';

-- Indexes
CREATE INDEX IF NOT EXISTS idx_aria_action_queue_user_status ON aria_action_queue(user_id, status);
CREATE INDEX IF NOT EXISTS idx_aria_action_queue_user_created ON aria_action_queue(user_id, created_at DESC);

-- Enable RLS
ALTER TABLE aria_action_queue ENABLE ROW LEVEL SECURITY;

-- RLS Policies (idempotent: drop if exists, then create)
DROP POLICY IF EXISTS "Users can view their own actions" ON aria_action_queue;
CREATE POLICY "Users can view their own actions" ON aria_action_queue
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can create their own actions" ON aria_action_queue;
CREATE POLICY "Users can create their own actions" ON aria_action_queue
    FOR INSERT WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update their own actions" ON aria_action_queue;
CREATE POLICY "Users can update their own actions" ON aria_action_queue
    FOR UPDATE USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete their own actions" ON aria_action_queue;
CREATE POLICY "Users can delete their own actions" ON aria_action_queue
    FOR DELETE USING (auth.uid() = user_id);

-- updated_at trigger
CREATE OR REPLACE FUNCTION update_aria_action_queue_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_aria_action_queue_updated_at ON aria_action_queue;
CREATE TRIGGER update_aria_action_queue_updated_at
    BEFORE UPDATE ON aria_action_queue
    FOR EACH ROW EXECUTE FUNCTION update_aria_action_queue_updated_at();
