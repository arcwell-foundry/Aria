-- Market signals schema for ARIA
-- This migration creates tables for tracking market signals and monitored entities

-- Market signals detected from various sources
CREATE TABLE market_signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    company_name TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    headline TEXT NOT NULL,
    summary TEXT,
    source_url TEXT,
    source_name TEXT,
    relevance_score FLOAT DEFAULT 0.5,
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    read_at TIMESTAMPTZ,
    dismissed_at TIMESTAMPTZ,
    linked_lead_id UUID,
    metadata JSONB DEFAULT '{}'
);

-- Entities being monitored for signals
CREATE TABLE monitored_entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    entity_type TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    monitoring_config JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT true,
    last_checked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, entity_type, entity_name)
);

-- Enable Row Level Security
ALTER TABLE market_signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE monitored_entities ENABLE ROW LEVEL SECURITY;

-- RLS policies for market_signals
CREATE POLICY "Users can manage own signals" ON market_signals
    FOR ALL USING (user_id = auth.uid());

-- RLS policies for monitored_entities
CREATE POLICY "Users can manage own monitored entities" ON monitored_entities
    FOR ALL USING (user_id = auth.uid());

-- Indexes for market_signals
CREATE INDEX idx_signals_user_unread ON market_signals(user_id, read_at) WHERE read_at IS NULL;
CREATE INDEX idx_signals_user_company ON market_signals(user_id, company_name);
CREATE INDEX idx_signals_user_type ON market_signals(user_id, signal_type);
CREATE INDEX idx_signals_detected ON market_signals(detected_at DESC);

-- Indexes for monitored_entities
CREATE INDEX idx_monitored_user_active ON monitored_entities(user_id, is_active);
CREATE INDEX idx_monitored_type_name ON monitored_entities(entity_type, entity_name);

-- Add comments for documentation
COMMENT ON TABLE market_signals IS 'Market signals detected from various sources (funding, hiring, leadership, product, partnership, regulatory, earnings, clinical_trial, fda_approval, patent)';
COMMENT ON TABLE monitored_entities IS 'Entities being monitored for market signals (companies, people, topics)';
COMMENT ON COLUMN market_signals.signal_type IS 'Type of signal: funding, hiring, leadership, product, partnership, regulatory, earnings, clinical_trial, fda_approval, patent';
COMMENT ON COLUMN market_signals.relevance_score IS 'Relevance score from 0 to 1';
COMMENT ON COLUMN monitored_entities.entity_type IS 'Type of entity: company, person, topic';
COMMENT ON COLUMN monitored_entities.monitoring_config IS 'Configuration for monitoring (frequency, signal_types, etc.)';
