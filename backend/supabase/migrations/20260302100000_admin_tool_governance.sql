-- Phase 4D: Admin Tool Governance
-- Tables: tenant_toolkit_config, toolkit_access_requests

-- ============================================================
-- Table 1: tenant_toolkit_config (per-toolkit admin governance)
-- ============================================================
CREATE TABLE IF NOT EXISTS tenant_toolkit_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    toolkit_slug TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'general',
    status TEXT NOT NULL DEFAULT 'approved'
        CHECK (status IN ('approved', 'denied', 'pending_review')),
    max_seats INT,
    approved_by UUID REFERENCES auth.users(id),
    approved_at TIMESTAMPTZ,
    notes TEXT,
    config_json JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, toolkit_slug)
);

CREATE INDEX idx_ttc_tenant_status ON tenant_toolkit_config(tenant_id, status);
CREATE INDEX idx_ttc_slug ON tenant_toolkit_config(toolkit_slug);

ALTER TABLE tenant_toolkit_config ENABLE ROW LEVEL SECURITY;
CREATE POLICY "ttc_service" ON tenant_toolkit_config
    FOR ALL USING (auth.role() = 'service_role');

-- ============================================================
-- Table 2: toolkit_access_requests (user request workflow)
-- ============================================================
CREATE TABLE IF NOT EXISTS toolkit_access_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,
    toolkit_slug TEXT NOT NULL,
    toolkit_display_name TEXT DEFAULT '',
    reason TEXT,
    discovered_via TEXT DEFAULT 'user_request',
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'denied')),
    reviewed_by UUID REFERENCES auth.users(id),
    reviewed_at TIMESTAMPTZ,
    admin_notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_tar_tenant_status ON toolkit_access_requests(tenant_id, status);
CREATE INDEX idx_tar_user ON toolkit_access_requests(user_id, toolkit_slug);

ALTER TABLE toolkit_access_requests ENABLE ROW LEVEL SECURITY;
CREATE POLICY "tar_service" ON toolkit_access_requests
    FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "tar_user_read_own" ON toolkit_access_requests
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "tar_user_insert_own" ON toolkit_access_requests
    FOR INSERT WITH CHECK (auth.uid() = user_id);
