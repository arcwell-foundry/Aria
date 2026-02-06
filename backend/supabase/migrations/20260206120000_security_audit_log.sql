-- Security Audit Log Migration (US-926)
-- Tracks all security-relevant events for compliance and monitoring

CREATE TABLE IF NOT EXISTS security_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    ip_address TEXT,
    user_agent TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Index for efficient user-specific audit queries
CREATE INDEX IF NOT EXISTS idx_audit_user ON security_audit_log(user_id, created_at DESC);

-- Index for event type filtering
CREATE INDEX IF NOT EXISTS idx_audit_event_type ON security_audit_log(event_type, created_at DESC);

-- Enable Row Level Security
ALTER TABLE security_audit_log ENABLE ROW LEVEL SECURITY;

-- RLS Policies
CREATE POLICY "own_audit" ON security_audit_log
    FOR SELECT TO authenticated USING (user_id = auth.uid());

CREATE POLICY "service_role_full_access" ON security_audit_log
    FOR ALL USING (auth.role() = 'service_role');

-- Comment for documentation
COMMENT ON TABLE security_audit_log IS 'Security event log for compliance monitoring. Events: login, logout, password_change, 2fa_enabled, 2fa_disabled, account_deleted, session_revoked, etc.';
COMMENT ON COLUMN security_audit_log.event_type IS 'Type of security event (e.g., login, password_change, 2fa_enabled, account_deleted)';
COMMENT ON COLUMN security_audit_log.metadata IS 'Additional event context as JSONB (e.g., {"success": true, "reason": "..."})';
