-- CRM Audit Log Table
-- Tracks all CRM synchronization operations for compliance
CREATE TABLE crm_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    lead_memory_id UUID REFERENCES lead_memories(id) ON DELETE CASCADE,
    operation TEXT NOT NULL,  -- push, pull, conflict_detected, conflict_resolved, error, retry
    provider TEXT NOT NULL,   -- salesforce, hubspot
    success BOOLEAN NOT NULL DEFAULT true,
    details JSONB DEFAULT '{}',
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- RLS Policies
ALTER TABLE crm_audit_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own audit logs" ON crm_audit_log
    FOR SELECT USING (user_id = auth.uid());

CREATE POLICY "Service can manage crm_audit_log" ON crm_audit_log
    FOR ALL USING (auth.role() = 'service_role');

-- Indexes for common queries
CREATE INDEX idx_crm_audit_user ON crm_audit_log(user_id);
CREATE INDEX idx_crm_audit_lead ON crm_audit_log(lead_memory_id);
CREATE INDEX idx_crm_audit_operation ON crm_audit_log(operation);
CREATE INDEX idx_crm_audit_provider ON crm_audit_log(provider);
CREATE INDEX idx_crm_audit_time ON crm_audit_log(created_at DESC);
CREATE INDEX idx_crm_audit_user_lead ON crm_audit_log(user_id, lead_memory_id);

-- Comments for documentation
COMMENT ON TABLE crm_audit_log IS 'Immutable audit trail for all CRM synchronization operations.';
COMMENT ON COLUMN crm_audit_log.operation IS 'push (ARIA→CRM), pull (CRM→ARIA), conflict_detected, conflict_resolved, error, retry.';
COMMENT ON COLUMN crm_audit_log.provider IS 'CRM provider: salesforce or hubspot.';
COMMENT ON COLUMN crm_audit_log.details IS 'Operation-specific details: fields synced, conflict resolution, etc.';
