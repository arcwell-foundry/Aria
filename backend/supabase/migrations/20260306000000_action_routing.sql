-- Action Routing: Routes Jarvis insights to downstream actions
-- Tables: action_routing_rules, action_execution_log, conference_insights

-- =========================================================================
-- action_routing_rules: Configurable rules for routing insights to actions
-- =========================================================================
CREATE TABLE IF NOT EXISTS action_routing_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_name TEXT NOT NULL,
    description TEXT,
    priority INTEGER NOT NULL DEFAULT 50,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    -- Matching conditions (AND logic: all non-null conditions must match)
    insight_classification TEXT,          -- e.g. 'threat', 'opportunity', 'neutral'
    urgency_level TEXT,                   -- e.g. 'urgent', 'high', 'medium', 'low'
    entity_type TEXT,                     -- e.g. 'competitor', 'own_company', 'industry'
    signal_types TEXT[],                  -- e.g. {'regulatory', 'pricing', 'clinical_trial'}
    min_confidence FLOAT DEFAULT 0,
    -- Actions to execute when rule matches
    actions JSONB NOT NULL DEFAULT '[]',  -- Array of {type, template, urgency, priority, section, ...}
    execution_mode TEXT NOT NULL DEFAULT 'auto' CHECK (execution_mode IN ('auto', 'confirm', 'notify')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_action_routing_rules_active
    ON action_routing_rules (is_active, priority DESC);

ALTER TABLE action_routing_rules ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role manages routing rules"
    ON action_routing_rules FOR ALL
    USING (auth.role() = 'service_role');

-- =========================================================================
-- action_execution_log: Audit trail of all actions taken by the router
-- =========================================================================
CREATE TABLE IF NOT EXISTS action_execution_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    insight_id UUID,
    rule_id UUID REFERENCES action_routing_rules(id) ON DELETE SET NULL,
    action_type TEXT NOT NULL,
    action_details JSONB DEFAULT '{}',
    execution_mode TEXT DEFAULT 'auto',
    status TEXT NOT NULL DEFAULT 'executed' CHECK (status IN ('executed', 'failed', 'skipped')),
    result JSONB DEFAULT '{}',
    executed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_action_execution_log_user
    ON action_execution_log (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_action_execution_log_insight
    ON action_execution_log (insight_id);

ALTER TABLE action_execution_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users read own execution log"
    ON action_execution_log FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Service role manages execution log"
    ON action_execution_log FOR ALL
    USING (auth.role() = 'service_role');

-- =========================================================================
-- conference_insights: Intelligence gathered about conferences
-- =========================================================================
CREATE TABLE IF NOT EXISTS conference_insights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    conference_id UUID,
    insight_type TEXT NOT NULL DEFAULT 'competitive_presence',
    content TEXT NOT NULL,
    companies_mentioned TEXT[] DEFAULT '{}',
    urgency TEXT DEFAULT 'medium',
    actionable BOOLEAN DEFAULT FALSE,
    recommended_actions JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_conference_insights_user
    ON conference_insights (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_conference_insights_conference
    ON conference_insights (conference_id);

ALTER TABLE conference_insights ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users read own conference insights"
    ON conference_insights FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Service role manages conference insights"
    ON conference_insights FOR ALL
    USING (auth.role() = 'service_role');

-- =========================================================================
-- Seed routing rules (8 rules from highest to lowest priority)
-- =========================================================================

-- Rule 1: Supply chain disruption (highest priority)
INSERT INTO action_routing_rules (rule_name, description, priority, insight_classification, urgency_level, entity_type, signal_types, min_confidence, actions, execution_mode) VALUES
(
    'supply_chain_disruption',
    'Supply chain or manufacturing disruption detected at competitor — displacement opportunity',
    100,
    'threat',
    'high',
    'competitor',
    ARRAY['supply_chain', 'manufacturing'],
    0.6,
    '[
        {"type": "write_memory"},
        {"type": "create_proposal", "template": "displacement_outreach"},
        {"type": "create_notification", "urgency": "urgent"},
        {"type": "create_pulse", "priority": "urgent"},
        {"type": "update_battle_card"},
        {"type": "update_briefing", "section": "competitive_intelligence"}
    ]'::jsonb,
    'auto'
);

-- Rule 2: FDA / regulatory event
INSERT INTO action_routing_rules (rule_name, description, priority, insight_classification, urgency_level, entity_type, signal_types, min_confidence, actions, execution_mode) VALUES
(
    'fda_regulatory',
    'FDA warning, approval, or regulatory action detected',
    95,
    NULL,
    'high',
    'competitor',
    ARRAY['regulatory', 'fda_approval', 'fda_warning'],
    0.5,
    '[
        {"type": "write_memory"},
        {"type": "create_proposal", "template": "regulatory_displacement"},
        {"type": "create_notification", "urgency": "urgent"},
        {"type": "create_pulse", "priority": "high"},
        {"type": "update_battle_card"},
        {"type": "update_briefing", "section": "regulatory_intelligence"}
    ]'::jsonb,
    'auto'
);

-- Rule 3: Pricing intelligence
INSERT INTO action_routing_rules (rule_name, description, priority, insight_classification, entity_type, signal_types, min_confidence, actions, execution_mode) VALUES
(
    'pricing_signal',
    'Competitor pricing change, revenue miss, or pricing pressure detected',
    90,
    NULL,
    'competitor',
    ARRAY['pricing', 'revenue_miss', 'pricing_pressure', 'earnings'],
    0.5,
    '[
        {"type": "write_memory"},
        {"type": "create_proposal", "template": "pricing_response"},
        {"type": "create_notification", "urgency": "medium"},
        {"type": "create_pulse", "priority": "high"},
        {"type": "update_battle_card"},
        {"type": "draft_email", "template": "competitive_response"}
    ]'::jsonb,
    'auto'
);

-- Rule 4: Clinical trial signal
INSERT INTO action_routing_rules (rule_name, description, priority, entity_type, signal_types, min_confidence, actions, execution_mode) VALUES
(
    'clinical_trial',
    'Clinical trial phase advancement or new trial detected — potential equipment needs',
    85,
    NULL,
    ARRAY['clinical_trial', 'pipeline'],
    0.5,
    '[
        {"type": "write_memory"},
        {"type": "create_pulse", "priority": "medium"},
        {"type": "check_lead_discovery"},
        {"type": "update_briefing", "section": "pipeline_intelligence"}
    ]'::jsonb,
    'auto'
);

-- Rule 5: Conference-related signal
INSERT INTO action_routing_rules (rule_name, description, priority, signal_types, min_confidence, actions, execution_mode) VALUES
(
    'conference_signal',
    'Conference-related competitive intelligence detected',
    80,
    ARRAY['conference', 'trade_show', 'presentation'],
    0.4,
    '[
        {"type": "write_memory"},
        {"type": "update_conference_insight"},
        {"type": "create_pulse", "priority": "medium"},
        {"type": "update_briefing", "section": "conference_intelligence"}
    ]'::jsonb,
    'auto'
);

-- Rule 6: General competitor signal (catch-all for competitors)
INSERT INTO action_routing_rules (rule_name, description, priority, entity_type, min_confidence, actions, execution_mode) VALUES
(
    'general_competitor',
    'General competitive intelligence about a tracked competitor',
    50,
    'competitor',
    0.4,
    '[
        {"type": "write_memory"},
        {"type": "create_pulse", "priority": "medium"},
        {"type": "update_battle_card"},
        {"type": "update_briefing", "section": "competitive_intelligence"}
    ]'::jsonb,
    'auto'
);

-- Rule 7: Own company signal
INSERT INTO action_routing_rules (rule_name, description, priority, entity_type, min_confidence, actions, execution_mode) VALUES
(
    'own_company',
    'Intelligence about the user''s own company',
    45,
    'own_company',
    0.3,
    '[
        {"type": "write_memory"},
        {"type": "create_notification", "urgency": "medium"},
        {"type": "update_briefing", "section": "company_intelligence"}
    ]'::jsonb,
    'auto'
);

-- Rule 8: Default (lowest priority — catch all remaining)
INSERT INTO action_routing_rules (rule_name, description, priority, min_confidence, actions, execution_mode) VALUES
(
    'default',
    'Default rule for unclassified insights — write to memory at minimum',
    10,
    0.0,
    '[
        {"type": "write_memory"},
        {"type": "update_briefing", "section": "general_intelligence"}
    ]'::jsonb,
    'auto'
);
