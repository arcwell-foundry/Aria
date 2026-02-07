-- US-939: Lead Generation Workflow
-- Tables for ICP profiles and discovered leads

-- ICP Profiles: One active ICP per user
CREATE TABLE lead_icp_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    icp_data JSONB NOT NULL DEFAULT '{}',
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX idx_icp_profiles_user ON lead_icp_profiles(user_id);

ALTER TABLE lead_icp_profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own_icp_profiles" ON lead_icp_profiles
    FOR ALL TO authenticated USING (user_id = auth.uid());

-- Discovered Leads: Leads found by Hunter agent pending review
CREATE TABLE discovered_leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    icp_id UUID REFERENCES lead_icp_profiles(id),
    company_name TEXT NOT NULL,
    company_data JSONB NOT NULL DEFAULT '{}',
    contacts JSONB NOT NULL DEFAULT '[]',
    fit_score INT NOT NULL DEFAULT 0 CHECK (fit_score >= 0 AND fit_score <= 100),
    score_breakdown JSONB NOT NULL DEFAULT '{}',
    signals JSONB NOT NULL DEFAULT '[]',
    review_status TEXT NOT NULL DEFAULT 'pending' CHECK (review_status IN ('pending', 'approved', 'rejected', 'saved')),
    reviewed_at TIMESTAMPTZ,
    source TEXT NOT NULL DEFAULT 'hunter_agent',
    lead_memory_id UUID REFERENCES lead_memories(id),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_discovered_leads_user ON discovered_leads(user_id);
CREATE INDEX idx_discovered_leads_status ON discovered_leads(user_id, review_status);
CREATE INDEX idx_discovered_leads_score ON discovered_leads(user_id, fit_score DESC);

ALTER TABLE discovered_leads ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own_discovered_leads" ON discovered_leads
    FOR ALL TO authenticated USING (user_id = auth.uid());
