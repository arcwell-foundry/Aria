-- Create shared_intelligence table for team-level knowledge sharing
-- Part of Shared Intelligence Layer: allows team members to benefit from each other's insights

-- First, add team_intelligence_opt_in to user_profiles if it doesn't exist
ALTER TABLE user_profiles
ADD COLUMN IF NOT EXISTS team_intelligence_opt_in BOOLEAN DEFAULT FALSE;

ALTER TABLE user_profiles
ADD COLUMN IF NOT EXISTS team_intelligence_opt_in_at TIMESTAMPTZ;

COMMENT ON COLUMN user_profiles.team_intelligence_opt_in IS 'Whether user has opted into sharing their account insights with team';
COMMENT ON COLUMN user_profiles.team_intelligence_opt_in_at IS 'When the user opted in/out of team intelligence sharing';

-- Shared Intelligence table
CREATE TABLE shared_intelligence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,

    -- The actual intelligence content
    subject TEXT NOT NULL,           -- Entity the fact is about (e.g., "Acme Pharma", "John Smith")
    predicate TEXT NOT NULL,         -- Relationship type (e.g., "uses_product", "is_decision_maker_for")
    object TEXT NOT NULL,            -- Value or related entity (e.g., "CellTherapy Platform", "IT Infrastructure")

    -- Confidence and source
    confidence FLOAT NOT NULL DEFAULT 0.5,
    source_type TEXT NOT NULL DEFAULT 'goal_execution',  -- goal_execution, manual_entry, aggregated
    contribution_count INT NOT NULL DEFAULT 1,            -- How many users contributed this fact

    -- Attribution (anonymizable)
    contributed_by UUID NOT NULL REFERENCES auth.users(id),  -- Original contributor
    is_anonymized BOOLEAN NOT NULL DEFAULT FALSE,            -- Whether contributor is hidden from non-admins

    -- Account reference for filtering
    related_account_name TEXT,        -- Account/company this fact relates to (for filtering)
    related_lead_id UUID REFERENCES leads(id) ON DELETE SET NULL,

    -- Privacy controls
    is_shareable BOOLEAN NOT NULL DEFAULT TRUE,  -- Can be shared (some facts may be marked private)

    -- Graphiti integration
    graphiti_episode_name TEXT,

    -- Lifecycle
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    invalidated_at TIMESTAMPTZ,
    invalidation_reason TEXT,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for common access patterns
CREATE INDEX idx_shared_intelligence_company ON shared_intelligence(company_id, is_active);
CREATE INDEX idx_shared_intelligence_account ON shared_intelligence(company_id, related_account_name);
CREATE INDEX idx_shared_intelligence_subject ON shared_intelligence(company_id, subject);
CREATE INDEX idx_shared_intelligence_lead ON shared_intelligence(company_id, related_lead_id);
CREATE INDEX idx_shared_intelligence_contributor ON shared_intelligence(contributed_by);

-- Enable RLS
ALTER TABLE shared_intelligence ENABLE ROW LEVEL SECURITY;

-- Policy: Users can read shared intelligence for their company (if they've opted in)
CREATE POLICY "Users can read company shared intelligence"
    ON shared_intelligence
    FOR SELECT
    USING (
        company_id IN (
            SELECT up.company_id FROM user_profiles up
            WHERE up.id = auth.uid()
            AND up.team_intelligence_opt_in = TRUE
        )
        AND is_active = TRUE
    );

-- Policy: Users who opted in can insert for their company
CREATE POLICY "Users can contribute shared intelligence"
    ON shared_intelligence
    FOR INSERT
    WITH CHECK (
        company_id IN (
            SELECT up.company_id FROM user_profiles up
            WHERE up.id = auth.uid()
            AND up.team_intelligence_opt_in = TRUE
        )
        AND contributed_by = auth.uid()
    );

-- Policy: Only contributor or admin can update their contributions
CREATE POLICY "Users can update own contributions"
    ON shared_intelligence
    FOR UPDATE
    USING (
        contributed_by = auth.uid()
        OR (
            company_id IN (
                SELECT up.company_id FROM user_profiles up
                WHERE up.id = auth.uid() AND up.role = 'admin'
            )
        )
    );

-- Policy: Service role has full access
CREATE POLICY "Service can manage shared intelligence"
    ON shared_intelligence
    FOR ALL
    USING (auth.role() = 'service_role');

-- Comments for documentation
COMMENT ON TABLE shared_intelligence IS 'Team-level shared intelligence about accounts and contacts. Requires opt-in per user. Privacy: contributor attribution can be anonymized for non-admin viewers.';
COMMENT ON COLUMN shared_intelligence.source_type IS 'Source: goal_execution (from agent goals), manual_entry (user added), aggregated (from multiple contributions)';
COMMENT ON COLUMN shared_intelligence.contribution_count IS 'Number of users who have contributed this same fact (increases confidence)';
COMMENT ON COLUMN shared_intelligence.is_anonymized IS 'If true, non-admin users see "Team Member" instead of contributor name';
COMMENT ON COLUMN shared_intelligence.related_account_name IS 'Account/company this fact is about - used for filtering context';

-- Function to get contributor info with optional anonymization
CREATE OR REPLACE FUNCTION get_shared_intelligence_contributor(
    p_contributed_by UUID,
    p_is_anonymized BOOLEAN,
    p_viewer_id UUID DEFAULT NULL
)
RETURNS TEXT AS $$
DECLARE
    viewer_is_admin BOOLEAN;
    contributor_name TEXT;
BEGIN
    -- Check if viewer is admin
    IF p_viewer_id IS NOT NULL THEN
        SELECT role = 'admin' INTO viewer_is_admin
        FROM user_profiles
        WHERE id = p_viewer_id;
    ELSE
        viewer_is_admin := FALSE;
    END IF;

    -- If anonymized and viewer is not admin, return anonymized string
    IF p_is_anonymized AND NOT viewer_is_admin THEN
        RETURN 'Team Member';
    END IF;

    -- Get contributor name
    SELECT COALESCE(full_name, email, 'Unknown')
    INTO contributor_name
    FROM user_profiles up
    JOIN auth.users au ON up.id = au.id
    WHERE up.id = p_contributed_by;

    RETURN COALESCE(contributor_name, 'Team Member');
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_shared_intelligence_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER shared_intelligence_updated_at
    BEFORE UPDATE ON shared_intelligence
    FOR EACH ROW
    EXECUTE FUNCTION update_shared_intelligence_timestamp();

-- Trigger to anonymize contributions by default for privacy
-- Users can opt to show their name later
CREATE OR REPLACE FUNCTION set_default_anonymization()
RETURNS TRIGGER AS $$
BEGIN
    -- Default to anonymized for privacy
    IF NEW.is_anonymized IS NULL THEN
        NEW.is_anonymized := TRUE;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER shared_intelligence_default_anon
    BEFORE INSERT ON shared_intelligence
    FOR EACH ROW
    EXECUTE FUNCTION set_default_anonymization();
