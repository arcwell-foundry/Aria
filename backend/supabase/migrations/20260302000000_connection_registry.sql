-- Phase 4A: Connection Registry + Tool Router Audit Log
-- Creates user_connections table, tool_router_audit_log, active_connections view,
-- increment_connection_failure_count RPC, and supporting infrastructure.

-- =============================================================================
-- 1. user_connections — canonical record of each OAuth connection
-- =============================================================================
CREATE TABLE IF NOT EXISTS user_connections (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id         uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    toolkit_slug    text NOT NULL,
    composio_connection_id text,
    composio_entity_id     text,
    status          text NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('active', 'pending', 'disconnected', 'error', 'expired')),
    account_email   text,
    display_name    text,
    failure_count   integer NOT NULL DEFAULT 0,
    last_health_check_at timestamptz,
    metadata        jsonb DEFAULT '{}'::jsonb,
    created_at      timestamptz DEFAULT now(),
    updated_at      timestamptz DEFAULT now(),

    CONSTRAINT uq_user_toolkit UNIQUE (user_id, toolkit_slug)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_user_connections_user_id
    ON user_connections(user_id);
CREATE INDEX IF NOT EXISTS idx_user_connections_composio_connection_id
    ON user_connections(composio_connection_id);
CREATE INDEX IF NOT EXISTS idx_user_connections_status
    ON user_connections(status);

-- =============================================================================
-- 2. tool_router_audit_log — tracks connection lifecycle events
-- =============================================================================
CREATE TABLE IF NOT EXISTS tool_router_audit_log (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id         uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    connection_id   uuid REFERENCES user_connections(id) ON DELETE SET NULL,
    action          text NOT NULL,
    toolkit_slug    text,
    detail          jsonb DEFAULT '{}'::jsonb,
    created_at      timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tool_router_audit_user_id
    ON tool_router_audit_log(user_id);

-- =============================================================================
-- 3. RLS policies — user owns own rows, service role has full access
-- =============================================================================
ALTER TABLE user_connections ENABLE ROW LEVEL SECURITY;
ALTER TABLE tool_router_audit_log ENABLE ROW LEVEL SECURITY;

-- user_connections: users can read/write their own rows
CREATE POLICY user_connections_select ON user_connections
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY user_connections_insert ON user_connections
    FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY user_connections_update ON user_connections
    FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY user_connections_delete ON user_connections
    FOR DELETE USING (auth.uid() = user_id);

-- service role bypass (for backend server-side operations)
CREATE POLICY user_connections_service ON user_connections
    FOR ALL USING (current_setting('request.jwt.claims', true)::jsonb ->> 'role' = 'service_role');

-- tool_router_audit_log: users can read their own, service role can write
CREATE POLICY audit_log_select ON tool_router_audit_log
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY audit_log_service ON tool_router_audit_log
    FOR ALL USING (current_setting('request.jwt.claims', true)::jsonb ->> 'role' = 'service_role');

-- =============================================================================
-- 4. active_connections view — convenience view for active-only queries
-- =============================================================================
CREATE OR REPLACE VIEW active_connections AS
    SELECT * FROM user_connections WHERE status = 'active';

-- =============================================================================
-- 5. increment_connection_failure_count RPC
-- =============================================================================
CREATE OR REPLACE FUNCTION increment_connection_failure_count(
    p_user_id uuid,
    p_toolkit_slug text
)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    new_count integer;
BEGIN
    UPDATE user_connections
    SET failure_count = failure_count + 1,
        updated_at = now()
    WHERE user_id = p_user_id
      AND toolkit_slug = p_toolkit_slug
    RETURNING failure_count INTO new_count;

    RETURN COALESCE(new_count, 0);
END;
$$;

-- =============================================================================
-- 6. update_updated_at trigger
-- =============================================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_user_connections_updated_at
    BEFORE UPDATE ON user_connections
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
