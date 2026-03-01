-- Migration: installed_capabilities
-- Purpose: Track user-installed external MCP servers for capability expansion
-- Phase: 5B - MCP Tool Discovery, Evaluation, and Installation

CREATE TABLE IF NOT EXISTS installed_capabilities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    server_name TEXT NOT NULL,
    server_display_name TEXT NOT NULL DEFAULT '',
    registry_source TEXT NOT NULL DEFAULT 'unknown',  -- smithery, npm, mcp_run, manual
    registry_package_id TEXT NOT NULL DEFAULT '',
    transport TEXT NOT NULL DEFAULT 'stdio',  -- stdio or sse
    connection_config JSONB NOT NULL DEFAULT '{}',
    declared_tools JSONB NOT NULL DEFAULT '[]',
    declared_permissions JSONB NOT NULL DEFAULT '{}',
    security_assessment JSONB NOT NULL DEFAULT '{}',
    reliability_score REAL NOT NULL DEFAULT 0.5,
    total_calls INTEGER NOT NULL DEFAULT 0,
    successful_calls INTEGER NOT NULL DEFAULT 0,
    failed_calls INTEGER NOT NULL DEFAULT 0,
    last_used_at TIMESTAMPTZ,
    last_health_check_at TIMESTAMPTZ,
    health_status TEXT NOT NULL DEFAULT 'unknown',  -- healthy, degraded, unhealthy, unknown
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    installed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Unique constraint: one server_name per user
ALTER TABLE installed_capabilities
    ADD CONSTRAINT installed_capabilities_user_server_unique
    UNIQUE (user_id, server_name);

-- Indexes for common queries
CREATE INDEX idx_installed_capabilities_user_enabled
    ON installed_capabilities (user_id, is_enabled);
CREATE INDEX idx_installed_capabilities_user_last_used
    ON installed_capabilities (user_id, last_used_at);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_installed_capabilities_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_installed_capabilities_updated_at
    BEFORE UPDATE ON installed_capabilities
    FOR EACH ROW EXECUTE FUNCTION update_installed_capabilities_updated_at();

-- RLS policies
ALTER TABLE installed_capabilities ENABLE ROW LEVEL SECURITY;

-- Users can read their own capabilities
CREATE POLICY "Users can read own capabilities"
    ON installed_capabilities FOR SELECT
    USING (auth.uid() = user_id);

-- Users can insert their own capabilities
CREATE POLICY "Users can insert own capabilities"
    ON installed_capabilities FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- Users can update their own capabilities
CREATE POLICY "Users can update own capabilities"
    ON installed_capabilities FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Users can delete their own capabilities
CREATE POLICY "Users can delete own capabilities"
    ON installed_capabilities FOR DELETE
    USING (auth.uid() = user_id);

-- Service role bypass for backend operations
CREATE POLICY "Service role full access to capabilities"
    ON installed_capabilities FOR ALL
    USING (auth.role() = 'service_role');
