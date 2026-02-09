-- Create companies and user_profiles tables
-- Prerequisites for corporate_facts and other company-scoped features

-- Companies table
CREATE TABLE IF NOT EXISTS companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    domain TEXT,
    settings JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for domain lookups
CREATE INDEX IF NOT EXISTS idx_companies_domain ON companies(domain);

-- Enable RLS
ALTER TABLE companies ENABLE ROW LEVEL SECURITY;

-- Service role has full access
CREATE POLICY "Service can manage companies"
    ON companies
    FOR ALL
    USING (auth.role() = 'service_role');

-- User profiles table (links auth.users to companies)
CREATE TABLE IF NOT EXISTS user_profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    company_id UUID REFERENCES companies(id) ON DELETE SET NULL,
    role TEXT NOT NULL DEFAULT 'user',  -- user, admin
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for company lookups
CREATE INDEX IF NOT EXISTS idx_user_profiles_company ON user_profiles(company_id);

-- Enable RLS
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;

-- Users can read their own profile
CREATE POLICY "Users can read own profile"
    ON user_profiles
    FOR SELECT
    USING (id = auth.uid());

-- Users can read profiles in their company
CREATE POLICY "Users can read company profiles"
    ON user_profiles
    FOR SELECT
    USING (
        company_id IN (
            SELECT company_id FROM user_profiles WHERE id = auth.uid()
        )
    );

-- Service role has full access
CREATE POLICY "Service can manage profiles"
    ON user_profiles
    FOR ALL
    USING (auth.role() = 'service_role');

-- Add comments
COMMENT ON TABLE companies IS 'Organizations using ARIA';
COMMENT ON TABLE user_profiles IS 'Links auth.users to companies with role information';
