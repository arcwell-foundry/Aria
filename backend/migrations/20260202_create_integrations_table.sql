-- User integrations table for storing OAuth connection metadata
-- Note: Actual tokens are stored securely by Composio, we only store references

CREATE TABLE IF NOT EXISTS user_integrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    integration_type TEXT NOT NULL, -- 'google_calendar', 'gmail', 'outlook', 'salesforce', 'hubspot'
    composio_connection_id TEXT NOT NULL, -- Reference to Composio's stored connection
    composio_account_id TEXT, -- Composio account identifier
    display_name TEXT, -- User-friendly name (e.g., user's email)
    status TEXT NOT NULL DEFAULT 'active', -- 'active', 'disconnected', 'error'
    last_sync_at TIMESTAMPTZ,
    sync_status TEXT DEFAULT 'success', -- 'success', 'pending', 'failed'
    error_message TEXT,
    metadata JSONB DEFAULT '{}', -- Additional integration-specific data
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, integration_type)
);

-- Enable RLS
ALTER TABLE user_integrations ENABLE ROW LEVEL SECURITY;

-- RLS Policies: Users can only see their own integrations
CREATE POLICY "Users can view own integrations"
    ON user_integrations FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own integrations"
    ON user_integrations FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own integrations"
    ON user_integrations FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own integrations"
    ON user_integrations FOR DELETE
    USING (auth.uid() = user_id);

-- Index for quick lookups
CREATE INDEX idx_user_integrations_user_type ON user_integrations(user_id, integration_type);
CREATE INDEX idx_user_integrations_status ON user_integrations(status);

-- Updated at trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_user_integrations_updated_at
    BEFORE UPDATE ON user_integrations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
