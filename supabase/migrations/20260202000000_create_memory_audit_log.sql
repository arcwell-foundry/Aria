-- Create memory_audit_log table for tracking all memory operations
-- Part of US-211: Memory Audit Log Implementation

CREATE TABLE memory_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    operation TEXT NOT NULL,  -- create, update, delete, query, invalidate
    memory_type TEXT NOT NULL,  -- episodic, semantic, procedural, prospective
    memory_id UUID,  -- ID of the affected memory record (null for queries)
    metadata JSONB,  -- Additional operation context (query params, counts, etc.)
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for user-based queries (most common access pattern)
CREATE INDEX idx_audit_user_time ON memory_audit_log(user_id, created_at DESC);

-- Index for operation type filtering
CREATE INDEX idx_audit_operation ON memory_audit_log(operation);

-- Index for memory type filtering
CREATE INDEX idx_audit_memory_type ON memory_audit_log(memory_type);

-- Enable RLS
ALTER TABLE memory_audit_log ENABLE ROW LEVEL SECURITY;

-- Admin can read all audit logs
CREATE POLICY "Admins can read all audit logs"
    ON memory_audit_log
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM user_profiles
            WHERE user_profiles.id = auth.uid()
            AND user_profiles.role = 'admin'
        )
    );

-- Users can only read their own audit logs
CREATE POLICY "Users can read own audit logs"
    ON memory_audit_log
    FOR SELECT
    USING (user_id = auth.uid());

-- Service role can insert audit logs
CREATE POLICY "Service can insert audit logs"
    ON memory_audit_log
    FOR INSERT
    WITH CHECK (true);

-- Service role can read audit logs (for backend admin queries)
CREATE POLICY "Service can read audit logs"
    ON memory_audit_log
    FOR SELECT
    USING (auth.role() = 'service_role');

-- Add comment for documentation
COMMENT ON TABLE memory_audit_log IS 'Audit log for all memory operations. Retention: 90 days (managed by cleanup job)';
