-- Create corporate_facts table for company-level shared knowledge
-- Part of US-212: Corporate Memory Schema

CREATE TABLE corporate_facts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    confidence FLOAT NOT NULL DEFAULT 0.75,
    source TEXT NOT NULL DEFAULT 'extracted',  -- extracted, aggregated, admin_stated
    graphiti_episode_name TEXT,  -- Reference to Graphiti episode for this fact
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by UUID REFERENCES auth.users(id),  -- NULL = system-generated
    invalidated_at TIMESTAMPTZ,
    invalidation_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for company-based queries (primary access pattern)
CREATE INDEX idx_corporate_facts_company ON corporate_facts(company_id, is_active);

-- Index for subject-based lookups
CREATE INDEX idx_corporate_facts_subject ON corporate_facts(company_id, subject);

-- Index for predicate-based lookups
CREATE INDEX idx_corporate_facts_predicate ON corporate_facts(company_id, predicate);

-- Enable RLS
ALTER TABLE corporate_facts ENABLE ROW LEVEL SECURITY;

-- Users can read facts for their company
CREATE POLICY "Users can read company facts"
    ON corporate_facts
    FOR SELECT
    USING (
        company_id IN (
            SELECT company_id FROM user_profiles
            WHERE id = auth.uid()
        )
    );

-- Admins can insert facts for their company
CREATE POLICY "Admins can insert company facts"
    ON corporate_facts
    FOR INSERT
    WITH CHECK (
        company_id IN (
            SELECT company_id FROM user_profiles
            WHERE id = auth.uid()
            AND role = 'admin'
        )
    );

-- Admins can update facts for their company
CREATE POLICY "Admins can update company facts"
    ON corporate_facts
    FOR UPDATE
    USING (
        company_id IN (
            SELECT company_id FROM user_profiles
            WHERE id = auth.uid()
            AND role = 'admin'
        )
    );

-- Service role has full access (for backend aggregation)
CREATE POLICY "Service can manage corporate facts"
    ON corporate_facts
    FOR ALL
    USING (auth.role() = 'service_role');

-- Add comments for documentation
COMMENT ON TABLE corporate_facts IS 'Company-level shared facts extracted from cross-user patterns. Privacy: no user-identifiable data.';
COMMENT ON COLUMN corporate_facts.source IS 'Fact source: extracted (from user data), aggregated (from patterns), admin_stated (manual entry)';
COMMENT ON COLUMN corporate_facts.graphiti_episode_name IS 'Reference to Graphiti episode containing semantic content';
