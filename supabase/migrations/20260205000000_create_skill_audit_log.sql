-- Migration: Create skill_audit_log table
-- US-527: Skill Audit Trail

-- Create skill_audit_log table with hash chain for tamper evidence
CREATE TABLE skill_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    user_id UUID NOT NULL REFERENCES auth.users(id),
    tenant_id UUID,  -- Future: for multi-tenant support
    skill_id TEXT NOT NULL,
    skill_path TEXT NOT NULL,
    skill_trust_level TEXT NOT NULL,
    task_id UUID,  -- Nullable: not all executions have task IDs
    agent_id TEXT,  -- Nullable: which agent triggered the skill
    trigger_reason TEXT NOT NULL,  -- Why this skill was invoked
    data_classes_requested TEXT[] NOT NULL,  -- Data classes skill wanted
    data_classes_granted TEXT[] NOT NULL,  -- Data classes actually allowed
    data_redacted BOOLEAN DEFAULT FALSE NOT NULL,  -- Was sensitive data redacted?
    tokens_used TEXT[] DEFAULT '{}',  -- Token counts per model used
    input_hash TEXT NOT NULL,  -- Hash of input data for integrity
    output_hash TEXT,  -- Hash of output data (null if failed)
    execution_time_ms INT,  -- Execution duration in milliseconds
    success BOOLEAN NOT NULL,  -- Did execution succeed?
    error TEXT,  -- Error message if failed
    sandbox_config JSONB,  -- Sandbox settings used
    security_flags TEXT[] DEFAULT '{}',  -- Any security concerns flagged
    previous_hash TEXT NOT NULL,  -- Hash of previous entry for chain
    entry_hash TEXT NOT NULL  -- Hash of this entry (includes previous_hash)
);

-- Index for user-based queries (most common access pattern)
CREATE INDEX idx_skill_audit_user_time ON skill_audit_log(user_id, timestamp DESC);

-- Index for skill_id filtering
CREATE INDEX idx_skill_audit_skill_id ON skill_audit_log(skill_id);

-- Index for hash chain verification
CREATE INDEX idx_skill_audit_entry_hash ON skill_audit_log(entry_hash);

-- Enable RLS
ALTER TABLE skill_audit_log ENABLE ROW LEVEL SECURITY;

-- Users can only read their own audit logs
CREATE POLICY "Users can read own skill audit logs"
    ON skill_audit_log
    FOR SELECT
    USING (user_id = auth.uid());

-- Service role can insert audit logs
CREATE POLICY "Service can insert skill audit logs"
    ON skill_audit_log
    FOR INSERT
    WITH CHECK (true);

-- Service role can read audit logs (for backend admin queries)
CREATE POLICY "Service can read skill audit logs"
    ON skill_audit_log
    FOR SELECT
    USING (auth.role() = 'service_role');

-- Add comment for documentation
COMMENT ON TABLE skill_audit_log IS 'Immutable audit trail for skill executions with hash chain integrity. Tampering breaks the cryptographic chain.';
