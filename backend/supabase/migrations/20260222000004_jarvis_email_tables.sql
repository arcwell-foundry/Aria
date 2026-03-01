-- Migration: Jarvis email intelligence tables
-- Creates: lead_memory_events, relationship_health_metrics, cross_email_intelligence

-- lead_memory_events (for Prompt 12: Email → Lead Memory)
CREATE TABLE IF NOT EXISTS lead_memory_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    lead_id UUID NOT NULL,
    event_type TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    confidence FLOAT DEFAULT 0.7,
    source TEXT DEFAULT 'email_intelligence',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_lead_memory_events_user ON lead_memory_events(user_id);
CREATE INDEX idx_lead_memory_events_lead ON lead_memory_events(lead_id);

ALTER TABLE lead_memory_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users see own lead events" ON lead_memory_events
    FOR ALL USING (auth.uid() = user_id);

-- relationship_health_metrics (for Prompt 10: Relationship Health)
CREATE TABLE IF NOT EXISTS relationship_health_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    contact_email TEXT NOT NULL,
    contact_name TEXT,
    total_emails INTEGER DEFAULT 0,
    weekly_frequency FLOAT DEFAULT 0,
    trend TEXT DEFAULT 'stable',
    trend_detail TEXT,
    last_email_date TIMESTAMPTZ,
    days_since_last INTEGER DEFAULT 0,
    needs_reply_count INTEGER DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, contact_email)
);

CREATE INDEX idx_relationship_health_user ON relationship_health_metrics(user_id);

ALTER TABLE relationship_health_metrics ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users see own health metrics" ON relationship_health_metrics
    FOR ALL USING (auth.uid() = user_id);

-- cross_email_intelligence (for Prompt 11: Cross-Email Synthesis)
CREATE TABLE IF NOT EXISTS cross_email_intelligence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    pattern_type TEXT NOT NULL,
    company_domain TEXT,
    email_count INTEGER,
    senders TEXT[],
    insight TEXT NOT NULL,
    strategic_implication TEXT,
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    briefing_included BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_cross_email_intel_user ON cross_email_intelligence(user_id);

ALTER TABLE cross_email_intelligence ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users see own email intelligence" ON cross_email_intelligence
    FOR ALL USING (auth.uid() = user_id);
