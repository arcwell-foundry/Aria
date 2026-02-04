-- Core Lead Memory
CREATE TABLE lead_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    company_id UUID REFERENCES companies(id),
    company_name TEXT NOT NULL,
    lifecycle_stage TEXT DEFAULT 'lead',  -- lead, opportunity, account
    status TEXT DEFAULT 'active',  -- active, won, lost, dormant
    health_score INT DEFAULT 50 CHECK (health_score >= 0 AND health_score <= 100),
    crm_id TEXT,
    crm_provider TEXT,  -- salesforce, hubspot
    first_touch_at TIMESTAMPTZ,
    last_activity_at TIMESTAMPTZ,
    expected_close_date DATE,
    expected_value DECIMAL,
    tags TEXT[],
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Timeline Events
CREATE TABLE lead_memory_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_memory_id UUID REFERENCES lead_memories(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    direction TEXT,  -- inbound, outbound
    subject TEXT,
    content TEXT,
    participants TEXT[],
    occurred_at TIMESTAMPTZ NOT NULL,
    source TEXT,
    source_id TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Stakeholder Map
CREATE TABLE lead_memory_stakeholders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_memory_id UUID REFERENCES lead_memories(id) ON DELETE CASCADE,
    contact_email TEXT NOT NULL,
    contact_name TEXT,
    title TEXT,
    role TEXT,  -- decision_maker, influencer, champion, blocker, user
    influence_level INT DEFAULT 5 CHECK (influence_level >= 1 AND influence_level <= 10),
    sentiment TEXT DEFAULT 'neutral',
    last_contacted_at TIMESTAMPTZ,
    notes TEXT,
    personality_insights JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(lead_memory_id, contact_email)
);

-- AI-Generated Insights
CREATE TABLE lead_memory_insights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_memory_id UUID REFERENCES lead_memories(id) ON DELETE CASCADE,
    insight_type TEXT NOT NULL,  -- objection, buying_signal, commitment, risk, opportunity
    content TEXT NOT NULL,
    confidence FLOAT DEFAULT 0.7 CHECK (confidence >= 0 AND confidence <= 1),
    source_event_id UUID REFERENCES lead_memory_events(id),
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    addressed_at TIMESTAMPTZ,
    addressed_by UUID REFERENCES auth.users(id)
);

-- Multi-User Contributions
CREATE TABLE lead_memory_contributions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_memory_id UUID REFERENCES lead_memories(id) ON DELETE CASCADE,
    contributor_id UUID REFERENCES auth.users(id) NOT NULL,
    contribution_type TEXT NOT NULL,
    contribution_id UUID,
    status TEXT DEFAULT 'pending',  -- pending, merged, rejected
    reviewed_by UUID REFERENCES auth.users(id),
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- CRM Sync State
CREATE TABLE lead_memory_crm_sync (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_memory_id UUID REFERENCES lead_memories(id) ON DELETE CASCADE,
    last_sync_at TIMESTAMPTZ,
    sync_direction TEXT,
    last_push_at TIMESTAMPTZ,
    last_pull_at TIMESTAMPTZ,
    pending_changes JSONB DEFAULT '[]',
    conflict_log JSONB DEFAULT '[]',
    status TEXT DEFAULT 'synced',
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- RLS Policies
ALTER TABLE lead_memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE lead_memory_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE lead_memory_stakeholders ENABLE ROW LEVEL SECURITY;
ALTER TABLE lead_memory_insights ENABLE ROW LEVEL SECURITY;
ALTER TABLE lead_memory_contributions ENABLE ROW LEVEL SECURITY;
ALTER TABLE lead_memory_crm_sync ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own leads" ON lead_memories
    FOR ALL USING (user_id = auth.uid());

CREATE POLICY "Users can manage own lead events" ON lead_memory_events
    FOR ALL USING (lead_memory_id IN (SELECT id FROM lead_memories WHERE user_id = auth.uid()));

CREATE POLICY "Users can manage own stakeholders" ON lead_memory_stakeholders
    FOR ALL USING (lead_memory_id IN (SELECT id FROM lead_memories WHERE user_id = auth.uid()));

CREATE POLICY "Users can manage own insights" ON lead_memory_insights
    FOR ALL USING (lead_memory_id IN (SELECT id FROM lead_memories WHERE user_id = auth.uid()));

CREATE POLICY "Users can view contributions" ON lead_memory_contributions
    FOR ALL USING (lead_memory_id IN (SELECT id FROM lead_memories WHERE user_id = auth.uid()));

CREATE POLICY "Users can view own crm sync" ON lead_memory_crm_sync
    FOR ALL USING (lead_memory_id IN (SELECT id FROM lead_memories WHERE user_id = auth.uid()));

-- Service role has full access
CREATE POLICY "Service can manage lead_memories"
    ON lead_memories
    FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service can manage lead_memory_events"
    ON lead_memory_events
    FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service can manage lead_memory_stakeholders"
    ON lead_memory_stakeholders
    FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service can manage lead_memory_insights"
    ON lead_memory_insights
    FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service can manage lead_memory_contributions"
    ON lead_memory_contributions
    FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service can manage lead_memory_crm_sync"
    ON lead_memory_crm_sync
    FOR ALL
    USING (auth.role() = 'service_role');

-- Indexes
CREATE INDEX idx_lead_memories_user ON lead_memories(user_id);
CREATE INDEX idx_lead_memories_status ON lead_memories(user_id, status);
CREATE INDEX idx_lead_memories_health ON lead_memories(user_id, health_score);
CREATE INDEX idx_lead_memories_stage ON lead_memories(user_id, lifecycle_stage);
CREATE INDEX idx_lead_events_lead ON lead_memory_events(lead_memory_id);
CREATE INDEX idx_lead_events_time ON lead_memory_events(lead_memory_id, occurred_at DESC);
CREATE INDEX idx_lead_events_type ON lead_memory_events(lead_memory_id, event_type);
CREATE INDEX idx_lead_stakeholders_lead ON lead_memory_stakeholders(lead_memory_id);
CREATE INDEX idx_lead_insights_lead ON lead_memory_insights(lead_memory_id);
CREATE INDEX idx_lead_insights_type ON lead_memory_insights(lead_memory_id, insight_type);

-- Comments for documentation
COMMENT ON TABLE lead_memories IS 'Core lead/opportunity/account tracking with full lifecycle history and health scoring.';
COMMENT ON COLUMN lead_memories.lifecycle_stage IS 'lead → opportunity → account progression. History preserved on transition.';
COMMENT ON COLUMN lead_memories.health_score IS '0-100 composite score: communication(25%), response_time(20%), sentiment(20%), stakeholder_breadth(20%), velocity(15%).';
COMMENT ON COLUMN lead_memories.crm_id IS 'External CRM record ID (Salesforce Opportunity ID, HubSpot Deal ID, etc.).';
COMMENT ON COLUMN lead_memories.tags IS 'User-defined tags for categorization and filtering.';

COMMENT ON TABLE lead_memory_events IS 'Timeline of all interactions: emails, meetings, calls, notes, and market signals.';
COMMENT ON COLUMN lead_memory_events.direction IS 'inbound (received) or outbound (sent) for communications.';
COMMENT ON COLUMN lead_memory_events.source IS 'Origin: gmail, calendar, manual, crm, or system.';
COMMENT ON COLUMN lead_memory_events.source_id IS 'Original message/event ID from source system for deduplication.';

COMMENT ON TABLE lead_memory_stakeholders IS 'Contact mapping with role classification, influence scoring, and sentiment tracking.';
COMMENT ON COLUMN lead_memory_stakeholders.role IS 'decision_maker, influencer, champion, blocker, or user.';
COMMENT ON COLUMN lead_memory_stakeholders.influence_level IS '1-10 scale of decision-making influence.';
COMMENT ON COLUMN lead_memory_stakeholders.sentiment IS 'positive, neutral, negative, or unknown based on interactions.';
COMMENT ON COLUMN lead_memory_stakeholders.personality_insights IS 'AI-derived communication preferences and behavioral patterns.';

COMMENT ON TABLE lead_memory_insights IS 'AI-extracted intelligence: objections, buying signals, commitments, risks, and opportunities.';
COMMENT ON COLUMN lead_memory_insights.insight_type IS 'objection, buying_signal, commitment, risk, or opportunity.';
COMMENT ON COLUMN lead_memory_insights.confidence IS '0-1 score from AI model. Lower confidence requires human verification.';
COMMENT ON COLUMN lead_memory_insights.source_event_id IS 'Links insight to the event that generated it.';

COMMENT ON TABLE lead_memory_contributions IS 'Multi-user collaboration with owner approval workflow.';
COMMENT ON COLUMN lead_memory_contributions.contribution_type IS 'event, note, or insight.';
COMMENT ON COLUMN lead_memory_contributions.status IS 'pending (awaiting review), merged (accepted), or rejected.';

COMMENT ON TABLE lead_memory_crm_sync IS 'Bidirectional CRM synchronization state and conflict tracking.';
COMMENT ON COLUMN lead_memory_crm_sync.sync_direction IS 'push (ARIA→CRM), pull (CRM→ARIA), or bidirectional.';
COMMENT ON COLUMN lead_memory_crm_sync.status IS 'synced, pending, conflict, or error.';
COMMENT ON COLUMN lead_memory_crm_sync.pending_changes IS 'Array of changes awaiting sync.';
COMMENT ON COLUMN lead_memory_crm_sync.conflict_log IS 'Array of resolved/unresolved conflicts with timestamps.';
