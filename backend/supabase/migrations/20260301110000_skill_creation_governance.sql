-- Migration: Skill Creation & Enterprise Governance tables (Phase B)
-- Depends on: 20260301100000_self_provisioning.sql (Phase A)

-- ============================================================
-- Table 1: ecosystem_search_cache
-- Caches external ecosystem search results for 7 days
-- ============================================================
CREATE TABLE ecosystem_search_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    capability_name TEXT NOT NULL,
    search_source TEXT NOT NULL CHECK (search_source IN ('composio', 'mcp_registry', 'smithery')),
    search_query TEXT NOT NULL,
    results JSONB NOT NULL DEFAULT '[]',
    result_count INT DEFAULT 0,
    searched_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '7 days'),
    UNIQUE(capability_name, search_source)
);

CREATE INDEX idx_ecosystem_cache_capability ON ecosystem_search_cache(capability_name);
CREATE INDEX idx_ecosystem_cache_expires ON ecosystem_search_cache(expires_at);

ALTER TABLE ecosystem_search_cache ENABLE ROW LEVEL SECURITY;
CREATE POLICY "ecosystem_cache_service" ON ecosystem_search_cache
    FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "ecosystem_cache_read" ON ecosystem_search_cache
    FOR SELECT TO authenticated USING (true);

-- ============================================================
-- Table 2: aria_generated_skills
-- Skills ARIA creates herself (prompt chains, API wrappers, composite workflows)
-- ============================================================
CREATE TABLE aria_generated_skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    tenant_id UUID NOT NULL,
    skill_name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    description TEXT NOT NULL,
    skill_type TEXT NOT NULL CHECK (skill_type IN ('prompt_chain', 'api_wrapper', 'composite_workflow')),
    created_from_capability_gap TEXT,
    created_from_goal_id UUID,
    creation_reasoning TEXT,
    definition JSONB NOT NULL,
    generated_code TEXT,
    code_hash TEXT,
    status TEXT DEFAULT 'draft' CHECK (status IN (
        'draft', 'tested', 'user_reviewed', 'active', 'graduated',
        'tenant_approved', 'published', 'disabled', 'deprecated'
    )),
    trust_level TEXT DEFAULT 'LOW' CHECK (trust_level IN ('LOW', 'MEDIUM', 'HIGH')),
    execution_count INT DEFAULT 0,
    success_count INT DEFAULT 0,
    failure_count INT DEFAULT 0,
    avg_quality_score FLOAT,
    avg_execution_time_ms INT,
    last_executed_at TIMESTAMPTZ,
    user_feedback_score FLOAT,
    last_health_check TIMESTAMPTZ,
    health_status TEXT DEFAULT 'unknown' CHECK (health_status IN ('healthy', 'degraded', 'broken', 'unknown')),
    error_rate_7d FLOAT DEFAULT 0,
    sandbox_test_passed BOOLEAN DEFAULT FALSE,
    sandbox_test_output JSONB,
    sandbox_tested_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_aria_skills_user ON aria_generated_skills(user_id, status);
CREATE INDEX idx_aria_skills_tenant ON aria_generated_skills(tenant_id, status);
CREATE INDEX idx_aria_skills_capability ON aria_generated_skills(created_from_capability_gap);
CREATE INDEX idx_aria_skills_health ON aria_generated_skills(health_status)
    WHERE status = 'active' OR status = 'graduated';

ALTER TABLE aria_generated_skills ENABLE ROW LEVEL SECURITY;
CREATE POLICY "aria_skills_own" ON aria_generated_skills
    FOR ALL TO authenticated USING (user_id = auth.uid());
CREATE POLICY "aria_skills_tenant_read" ON aria_generated_skills
    FOR SELECT TO authenticated USING (
        tenant_id IN (SELECT company_id FROM user_profiles WHERE id = auth.uid())
        AND status IN ('tenant_approved', 'published')
    );
CREATE POLICY "aria_skills_service" ON aria_generated_skills
    FOR ALL USING (auth.role() = 'service_role');

CREATE TRIGGER update_aria_generated_skills_updated_at
    BEFORE UPDATE ON aria_generated_skills
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- Table 3: skill_approval_queue
-- Admin approval workflow for trust graduation and publishing
-- ============================================================
CREATE TABLE skill_approval_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_id UUID REFERENCES aria_generated_skills(id) ON DELETE CASCADE NOT NULL,
    tenant_id UUID NOT NULL,
    requested_by UUID REFERENCES auth.users(id) NOT NULL,
    approval_type TEXT NOT NULL CHECK (approval_type IN (
        'first_use', 'trust_graduation', 'tenant_publish', 'marketplace_publish'
    )),
    current_trust_level TEXT,
    requested_trust_level TEXT,
    justification TEXT,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    decided_by UUID REFERENCES auth.users(id),
    decision_reason TEXT,
    decided_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_approval_queue_pending ON skill_approval_queue(tenant_id, status)
    WHERE status = 'pending';

ALTER TABLE skill_approval_queue ENABLE ROW LEVEL SECURITY;
CREATE POLICY "approval_queue_service" ON skill_approval_queue
    FOR ALL USING (auth.role() = 'service_role');

-- ============================================================
-- Table 4: published_skills (marketplace schema — future use)
-- ============================================================
CREATE TABLE published_skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_skill_id UUID REFERENCES aria_generated_skills(id),
    source_tenant_id UUID NOT NULL,
    published_by_role TEXT,
    skill_name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    description TEXT NOT NULL,
    skill_type TEXT NOT NULL,
    definition JSONB NOT NULL,
    industry_vertical TEXT DEFAULT 'life_sciences',
    install_count INT DEFAULT 0,
    avg_rating FLOAT,
    rating_count INT DEFAULT 0,
    tags TEXT[],
    moderation_status TEXT DEFAULT 'pending' CHECK (moderation_status IN (
        'pending', 'approved', 'rejected', 'flagged'
    )),
    moderated_by TEXT,
    moderated_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE published_skills ENABLE ROW LEVEL SECURITY;
CREATE POLICY "published_skills_read" ON published_skills
    FOR SELECT TO authenticated USING (moderation_status = 'approved');
CREATE POLICY "published_skills_service" ON published_skills
    FOR ALL USING (auth.role() = 'service_role');
