-- Self-Provisioning: Phase A — Capability Graph + Gap Detection
-- Tables: capability_graph, capability_gaps_log, capability_demand, tenant_capability_config

-- ============================================================
-- Table 1: capability_graph (seed data — shared across all tenants)
-- Maps abstract capabilities to concrete providers
-- ============================================================
CREATE TABLE IF NOT EXISTS capability_graph (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Abstract capability
    capability_name TEXT NOT NULL,
    capability_category TEXT NOT NULL CHECK (capability_category IN (
        'research', 'data_access', 'communication', 'monitoring', 'analysis', 'creation'
    )),
    description TEXT,

    -- Concrete provider
    provider_name TEXT NOT NULL,
    provider_type TEXT NOT NULL CHECK (provider_type IN (
        'native',
        'composio_oauth',
        'composio_api_key',
        'composite',
        'mcp_server',
        'user_provided'
    )),

    -- Quality and availability
    quality_score FLOAT NOT NULL CHECK (quality_score >= 0 AND quality_score <= 1),
    setup_time_seconds INT DEFAULT 0,
    user_friction TEXT DEFAULT 'none' CHECK (user_friction IN ('none', 'low', 'medium', 'high')),
    estimated_cost_per_use FLOAT DEFAULT 0,

    -- Auth requirements
    composio_app_name TEXT,
    composio_action_name TEXT,
    required_capabilities TEXT[],

    -- Domain and constraints
    domain_constraint TEXT,
    limitations TEXT,
    life_sciences_priority BOOLEAN DEFAULT FALSE,

    -- Provider health
    is_active BOOLEAN DEFAULT TRUE,
    last_health_check TIMESTAMPTZ,
    health_status TEXT DEFAULT 'unknown' CHECK (health_status IN ('healthy', 'degraded', 'down', 'unknown')),

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(capability_name, provider_name)
);

CREATE INDEX IF NOT EXISTS idx_capgraph_capability ON capability_graph(capability_name);
CREATE INDEX IF NOT EXISTS idx_capgraph_category ON capability_graph(capability_category);
CREATE INDEX IF NOT EXISTS idx_capgraph_composio ON capability_graph(composio_app_name) WHERE composio_app_name IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_capgraph_active ON capability_graph(capability_name, quality_score DESC) WHERE is_active = TRUE;

ALTER TABLE capability_graph ENABLE ROW LEVEL SECURITY;
CREATE POLICY "capability_graph_read" ON capability_graph
    FOR SELECT TO authenticated USING (true);
CREATE POLICY "capability_graph_service" ON capability_graph
    FOR ALL USING (auth.role() = 'service_role');

-- ============================================================
-- Table 2: capability_gaps_log (per-user gap tracking)
-- ============================================================
CREATE TABLE IF NOT EXISTS capability_gaps_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,

    capability_name TEXT NOT NULL,
    goal_id UUID REFERENCES goals(id) ON DELETE SET NULL,
    goal_type TEXT,
    step_description TEXT,

    best_available_provider TEXT,
    best_available_quality FLOAT,

    strategies_offered JSONB,

    resolution_strategy TEXT CHECK (resolution_strategy IN (
        'direct_integration', 'composite', 'ecosystem_discovered',
        'skill_created', 'user_provided', 'web_fallback', 'skipped'
    )),
    resolution_provider TEXT,
    resolution_quality FLOAT,

    user_response TEXT CHECK (user_response IN (
        'connected', 'used_fallback', 'dismissed', 'deferred', 'pending'
    )),

    detected_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_capgaps_user ON capability_gaps_log(user_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_capgaps_capability ON capability_gaps_log(capability_name);
CREATE INDEX IF NOT EXISTS idx_capgaps_unresolved ON capability_gaps_log(user_id) WHERE user_response = 'pending';

ALTER TABLE capability_gaps_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "capgaps_own" ON capability_gaps_log
    FOR ALL TO authenticated USING (user_id = auth.uid());
CREATE POLICY "capgaps_service" ON capability_gaps_log
    FOR ALL USING (auth.role() = 'service_role');

-- ============================================================
-- Table 3: capability_demand (aggregate learning per user)
-- ============================================================
CREATE TABLE IF NOT EXISTS capability_demand (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,

    capability_name TEXT NOT NULL,
    goal_type TEXT,

    times_needed INT DEFAULT 0,
    times_satisfied_directly INT DEFAULT 0,
    times_used_composite INT DEFAULT 0,
    times_used_fallback INT DEFAULT 0,

    avg_quality_achieved FLOAT,
    quality_with_ideal_provider FLOAT,

    suggestion_threshold_reached BOOLEAN DEFAULT FALSE,
    last_suggested_at TIMESTAMPTZ,
    suggestion_accepted BOOLEAN,

    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, capability_name, goal_type)
);

CREATE INDEX IF NOT EXISTS idx_capdemand_user ON capability_demand(user_id);
CREATE INDEX IF NOT EXISTS idx_capdemand_suggest ON capability_demand(user_id)
    WHERE suggestion_threshold_reached = FALSE AND times_needed >= 3;

ALTER TABLE capability_demand ENABLE ROW LEVEL SECURITY;
CREATE POLICY "capdemand_own" ON capability_demand
    FOR ALL TO authenticated USING (user_id = auth.uid());
CREATE POLICY "capdemand_service" ON capability_demand
    FOR ALL USING (auth.role() = 'service_role');

-- ============================================================
-- Table 4: tenant_capability_config (enterprise governance)
-- ============================================================
CREATE TABLE IF NOT EXISTS tenant_capability_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,

    allowed_composio_toolkits TEXT[],
    allowed_ecosystem_sources TEXT[] DEFAULT ARRAY['composio'],

    allow_skill_creation BOOLEAN DEFAULT TRUE,
    skill_creation_requires_admin_approval BOOLEAN DEFAULT TRUE,
    max_auto_trust_level TEXT DEFAULT 'MEDIUM' CHECK (max_auto_trust_level IN ('LOW', 'MEDIUM', 'HIGH')),

    allow_data_to_community_tools BOOLEAN DEFAULT FALSE,
    max_data_classification_external TEXT DEFAULT 'INTERNAL' CHECK (
        max_data_classification_external IN ('PUBLIC', 'INTERNAL', 'CONFIDENTIAL')
    ),

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id)
);

ALTER TABLE tenant_capability_config ENABLE ROW LEVEL SECURITY;
CREATE POLICY "tenantcap_service" ON tenant_capability_config
    FOR ALL USING (auth.role() = 'service_role');

-- ============================================================
-- Seed: Day-1 Capability Map
-- ============================================================

-- RESEARCH CAPABILITIES
INSERT INTO capability_graph (capability_name, capability_category, provider_name, provider_type, quality_score, description, domain_constraint, life_sciences_priority) VALUES
('research_person', 'research', 'exa_people_search', 'native', 0.80, 'Search for person background via Exa web search', NULL, FALSE),
('research_person', 'research', 'pubmed_author_search', 'native', 0.70, 'Search PubMed for scientific author publications', 'scientific', TRUE),
('research_person', 'research', 'ask_user', 'user_provided', 0.40, 'Ask user directly for information about a person', NULL, FALSE),
('research_company', 'research', 'exa_company_search', 'native', 0.85, 'Search for company information via Exa', NULL, FALSE),
('research_company', 'research', 'memory_corporate_facts', 'native', 0.60, 'Check ARIA corporate memory for known facts', NULL, FALSE),
('research_company', 'research', 'ask_user', 'user_provided', 0.40, 'Ask user directly about the company', NULL, FALSE),
('research_scientific', 'research', 'pubmed_api', 'native', 0.90, 'Search PubMed for scientific literature', 'scientific', TRUE),
('research_scientific', 'research', 'clinicaltrials_gov', 'native', 0.90, 'Search ClinicalTrials.gov for trial data', 'scientific', TRUE),
('research_scientific', 'research', 'exa_web_search', 'native', 0.70, 'General web search for scientific topics', NULL, FALSE);

-- DATA ACCESS CAPABILITIES (Composio OAuth)
INSERT INTO capability_graph (capability_name, capability_category, provider_name, provider_type, quality_score, description, domain_constraint, life_sciences_priority, setup_time_seconds, user_friction, estimated_cost_per_use, composio_app_name, composio_action_name, required_capabilities) VALUES
('read_email', 'data_access', 'composio_outlook', 'composio_oauth', 0.95, 'Read emails via Microsoft Outlook', NULL, FALSE, 0, 'low', 0, 'OUTLOOK365', 'OUTLOOK365_READ_EMAILS', NULL),
('read_email', 'data_access', 'composio_gmail', 'composio_oauth', 0.95, 'Read emails via Gmail', NULL, FALSE, 0, 'low', 0, 'GMAIL', 'GMAIL_FETCH_EMAILS', NULL),
('read_crm_pipeline', 'data_access', 'composio_veeva', 'composio_oauth', 0.95, 'Read CRM pipeline from Veeva CRM', NULL, TRUE, 0, 'low', 0, 'VEEVA_CRM', NULL, NULL),
('read_crm_pipeline', 'data_access', 'composio_salesforce', 'composio_oauth', 0.95, 'Read CRM pipeline from Salesforce', NULL, FALSE, 0, 'low', 0, 'SALESFORCE', 'SALESFORCE_GET_OPPORTUNITIES', NULL),
('read_crm_pipeline', 'data_access', 'composio_hubspot', 'composio_oauth', 0.95, 'Read CRM pipeline from HubSpot', NULL, FALSE, 0, 'low', 0, 'HUBSPOT', 'HUBSPOT_GET_DEALS', NULL),
('read_crm_pipeline', 'data_access', 'email_deal_inference', 'composite', 0.65, 'Infer deal stages from email thread language patterns', NULL, FALSE, 0, 'none', 0.05, NULL, NULL, ARRAY['read_email']),
('read_crm_pipeline', 'data_access', 'user_stated', 'user_provided', 0.50, 'Ask user about current pipeline status', NULL, FALSE, 0, 'medium', 0, NULL, NULL, NULL),
('read_calendar', 'data_access', 'composio_google_calendar', 'composio_oauth', 0.95, 'Read Google Calendar events', NULL, FALSE, 0, 'low', 0, 'GOOGLE_CALENDAR', NULL, NULL),
('read_calendar', 'data_access', 'composio_outlook_calendar', 'composio_oauth', 0.95, 'Read Outlook Calendar events', NULL, FALSE, 0, 'low', 0, 'OUTLOOK365', NULL, NULL),
('read_calendar', 'data_access', 'ask_user', 'user_provided', 0.40, 'Ask user about upcoming meetings', NULL, FALSE, 0, 'medium', 0, NULL, NULL, NULL);

-- COMMUNICATION CAPABILITIES
INSERT INTO capability_graph (capability_name, capability_category, provider_name, provider_type, quality_score, description, domain_constraint, life_sciences_priority, setup_time_seconds, user_friction, estimated_cost_per_use, composio_app_name, composio_action_name, required_capabilities) VALUES
('send_email', 'communication', 'composio_outlook', 'composio_oauth', 0.95, 'Send emails via Outlook', NULL, FALSE, 0, 'low', 0, 'OUTLOOK365', 'OUTLOOK365_SEND_EMAIL', NULL),
('send_email', 'communication', 'composio_gmail', 'composio_oauth', 0.95, 'Send emails via Gmail', NULL, FALSE, 0, 'low', 0, 'GMAIL', 'GMAIL_SEND_EMAIL', NULL);

INSERT INTO capability_graph (capability_name, capability_category, provider_name, provider_type, quality_score, description, domain_constraint, life_sciences_priority) VALUES
('send_email', 'communication', 'resend_transactional', 'native', 0.70, 'Send transactional emails via Resend (no reply tracking)', NULL, FALSE),
('send_email', 'communication', 'draft_for_user', 'native', 0.30, 'Generate draft text for user to copy-paste', NULL, FALSE);

-- MONITORING CAPABILITIES
INSERT INTO capability_graph (capability_name, capability_category, provider_name, provider_type, quality_score, description, domain_constraint, life_sciences_priority) VALUES
('monitor_competitor', 'monitoring', 'exa_web_search', 'native', 0.75, 'Monitor competitor news via Exa web search', NULL, FALSE),
('monitor_competitor', 'monitoring', 'exa_company_news', 'native', 0.70, 'Track company-specific news feed', NULL, FALSE),
('track_fda_activity', 'monitoring', 'openfda_api', 'native', 0.85, 'Track FDA approvals, recalls, warnings via openFDA', 'life_sciences', TRUE),
('track_fda_activity', 'monitoring', 'clinicaltrials_gov', 'native', 0.80, 'Monitor clinical trial status changes', 'life_sciences', TRUE),
('track_fda_activity', 'monitoring', 'exa_regulatory_search', 'native', 0.70, 'Search web for regulatory news', NULL, FALSE),
('track_patents', 'monitoring', 'exa_web_search', 'native', 0.60, 'Search web for patent filings (limited accuracy)', NULL, FALSE);
