-- Attendee profiles cached from research
-- Shared across users to avoid redundant lookups

CREATE TABLE IF NOT EXISTS attendee_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL UNIQUE,
    name TEXT,
    title TEXT,
    company TEXT,
    linkedin_url TEXT,
    profile_data JSONB DEFAULT '{}',
    research_status TEXT NOT NULL DEFAULT 'pending' CHECK (research_status IN ('pending', 'researching', 'completed', 'not_found')),
    last_researched_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Enable RLS
ALTER TABLE attendee_profiles ENABLE ROW LEVEL SECURITY;

-- RLS Policies: All authenticated users can read profiles (shared cache)
CREATE POLICY "Authenticated users can view attendee profiles"
    ON attendee_profiles FOR SELECT
    TO authenticated
    USING (true);

-- Only service role can write (prevents user manipulation)
CREATE POLICY "Service role full access to attendee profiles"
    ON attendee_profiles
    FOR ALL
    USING (auth.role() = 'service_role');

-- Indexes (email has implicit unique index from UNIQUE constraint)
CREATE INDEX idx_attendee_profiles_company ON attendee_profiles(company);
CREATE INDEX idx_attendee_profiles_status ON attendee_profiles(research_status);
CREATE INDEX idx_attendee_profiles_data ON attendee_profiles USING GIN(profile_data);

-- Updated at trigger
CREATE TRIGGER update_attendee_profiles_updated_at
    BEFORE UPDATE ON attendee_profiles
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Table comment
COMMENT ON TABLE attendee_profiles IS 'Cached attendee research profiles shared across users';

-- Data lifecycle: Profiles are cached indefinitely. Stale entries
-- should be refreshed via last_researched_at, not deleted (per AGI patterns).
