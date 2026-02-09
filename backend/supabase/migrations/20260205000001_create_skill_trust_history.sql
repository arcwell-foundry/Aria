-- Migration: Create skill_trust_history table
-- US-530: Skill Autonomy & Trust System

-- Create skill_trust_history table for per-user-per-skill trust tracking
CREATE TABLE IF NOT EXISTS skill_trust_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    skill_id TEXT NOT NULL,
    successful_executions INT DEFAULT 0 NOT NULL,
    failed_executions INT DEFAULT 0 NOT NULL,
    last_success TIMESTAMPTZ,
    last_failure TIMESTAMPTZ,
    session_trust_granted BOOLEAN DEFAULT FALSE NOT NULL,
    globally_approved BOOLEAN DEFAULT FALSE NOT NULL,
    globally_approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    UNIQUE(user_id, skill_id)
);

-- Index for user-skill lookups (primary access pattern)
CREATE INDEX idx_skill_trust_history_user_skill ON skill_trust_history(user_id, skill_id);

-- Index for finding globally approved skills
CREATE INDEX idx_skill_trust_history_global_approval ON skill_trust_history(user_id, globally_approved) WHERE globally_approved = TRUE;

-- Enable RLS
ALTER TABLE skill_trust_history ENABLE ROW LEVEL SECURITY;

-- Users can read and modify their own trust history
CREATE POLICY "Users can manage own skill trust history"
    ON skill_trust_history
    FOR ALL
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

-- Service role has full access for backend operations
CREATE POLICY "Service role can manage skill trust history"
    ON skill_trust_history
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- Trigger for updated_at
CREATE OR REPLACE FUNCTION update_skill_trust_history_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_skill_trust_history_updated_at
    BEFORE UPDATE ON skill_trust_history
    FOR EACH ROW
    EXECUTE FUNCTION update_skill_trust_history_updated_at();

-- Add comment for documentation
COMMENT ON TABLE skill_trust_history IS 'Tracks per-user-per-skill execution history for graduated autonomy. Skills earn trust through successful executions.';
COMMENT ON COLUMN skill_trust_history.session_trust_granted IS 'User granted trust for current session only. Resets on new session.';
COMMENT ON COLUMN skill_trust_history.globally_approved IS 'User granted permanent auto-approval for this skill. Requires explicit revocation.';
