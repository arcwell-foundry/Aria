-- Deep sync tracking for CRM and Calendar integrations (US-942)

-- Sync state tracking table
CREATE TABLE IF NOT EXISTS integration_sync_state (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    integration_type TEXT NOT NULL CHECK (integration_type IN ('salesforce', 'hubspot', 'google_calendar', 'outlook')),
    last_sync_at TIMESTAMPTZ,
    last_sync_status TEXT CHECK (last_sync_status IN ('success', 'failed', 'pending')),
    last_sync_error TEXT,
    sync_count INTEGER DEFAULT 0,
    next_sync_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, integration_type)
);

-- Sync log table for audit trail
CREATE TABLE IF NOT EXISTS integration_sync_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    integration_type TEXT NOT NULL,
    sync_type TEXT NOT NULL CHECK (sync_type IN ('pull', 'push')),
    started_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('success', 'failed', 'partial')),
    records_processed INTEGER DEFAULT 0,
    records_succeeded INTEGER DEFAULT 0,
    records_failed INTEGER DEFAULT 0,
    error_details JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Pending push queue for ARIA -> external tool updates (US-937 action queue integration)
CREATE TABLE IF NOT EXISTS integration_push_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    integration_type TEXT NOT NULL,
    action_type TEXT NOT NULL CHECK (action_type IN ('create_note', 'update_field', 'create_event')),
    priority TEXT NOT NULL CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'completed', 'failed')),
    created_at TIMESTAMPTZ DEFAULT now(),
    expires_at TIMESTAMPTZ,
    processed_at TIMESTAMPTZ,
    error_message TEXT
);

-- RLS Policies
ALTER TABLE integration_sync_state ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users_view_own_sync_state" ON integration_sync_state
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "users_insert_own_sync_state" ON integration_sync_state
    FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "users_update_own_sync_state" ON integration_sync_state
    FOR UPDATE USING (auth.uid() = user_id);

ALTER TABLE integration_sync_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users_view_own_sync_log" ON integration_sync_log
    FOR SELECT USING (auth.uid() = user_id);

ALTER TABLE integration_push_queue ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users_view_own_push_queue" ON integration_push_queue
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "users_update_own_push_queue" ON integration_push_queue
    FOR UPDATE USING (auth.uid() = user_id);

-- Indexes for performance
CREATE INDEX idx_sync_state_user_integration ON integration_sync_state(user_id, integration_type);
CREATE INDEX idx_sync_state_next_sync ON integration_sync_state(next_sync_at) WHERE last_sync_status = 'success';
CREATE INDEX idx_sync_log_user_type ON integration_sync_log(user_id, integration_type, started_at DESC);
CREATE INDEX idx_push_queue_user_status ON integration_push_queue(user_id, status, priority DESC);
CREATE INDEX idx_push_queue_expires_at ON integration_push_queue(expires_at) WHERE status = 'pending';

-- Updated at trigger
CREATE OR REPLACE FUNCTION update_integration_sync_state_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER integration_sync_state_updated_at
    BEFORE UPDATE ON integration_sync_state
    FOR EACH ROW
    EXECUTE FUNCTION update_integration_sync_state_updated_at();
